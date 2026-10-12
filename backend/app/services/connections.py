"""Connections: state of Vetmanager and the bank, saving the Vetmanager key, starting runs."""

import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any, cast

from fastapi import BackgroundTasks

from app.errors import conflict, not_found, rate_limited, validation_fields, validation_reason
from app.integrations.vetmanager import INVALID_KEY, OK, VetmanagerApi
from app.jobs import SyncRunner
from app.repo import Repository
from app.rows import ConnectionRow, SyncRunRow
from app.schemas import figure_out
from app.schemas_acq import (
    BankAccountStatusOut,
    BankInfoOut,
    ConnectionOut,
    ConnectionsOut,
    ScheduleOut,
    SyncRunOut,
)
from app.schemas_tx import NamedRefOut
from app.secrets import SecretBox, key_hint
from engine.freshness import bank_is_stale, vetmanager_is_stale
from engine.sync_counts import sync_counts_figure

RUN_STALE_AFTER = timedelta(minutes=30)  # a "running" run older than this is considered lost
MIN_SYNC_INTERVAL = timedelta(minutes=5)
RUNS_SHOWN = 5
RUNS_LOOKED_AT = 30
SYNC_TIME = "04:00"
BANK_SOURCE = "bank_statement"
_HOST = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
IMPORT_ENTITIES = frozenset(
    {"user", "admission", "invoice", "invoiceDocument", "good", "payment", "cassa"}
)


def normalize_address(address: str, suffixes: str) -> str | None:
    """Host name of a Vetmanager address, or None if it is not in the allowed domains.

    The server calls this host, so only subdomains of the listed Vetmanager domains are accepted.
    """
    text = _SCHEME.sub("", address.strip()).split("/", 1)[0].strip().lower().rstrip(".")
    if not _HOST.match(text):
        return None
    allowed = [s.strip().lower() for s in suffixes.split(",") if s.strip()]
    return text if any(text.endswith("." + s) for s in allowed) else None


def _is_active(run: SyncRunRow, now: datetime) -> bool:
    return run.status == "running" and now - run.started_at <= RUN_STALE_AFTER


def run_out(run: SyncRunRow, now: datetime) -> SyncRunOut:
    """A run as the API shows it; a run that never ended is reported as failed."""
    lost = run.status == "running" and not _is_active(run, now)
    counts = run.counts
    figure = (
        figure_out(
            sync_counts_figure(
                int(counts.get("new", 0)),
                int(counts.get("updated", 0)),
                int(counts.get("skipped_duplicates", 0)),
            )
        )
        if counts is not None and not lost
        else None
    )
    return SyncRunOut(
        id=run.id,
        status=cast(Any, "failed" if lost else run.status),
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_code=cast(Any, "unknown" if lost else run.error_code),
        counts=figure,
    )


def _last_success(runs: list[SyncRunRow]) -> datetime | None:
    for run in runs:
        if run.status in ("success", "partial") and run.finished_at is not None:
            return run.finished_at
    return None


async def _vetmanager_out(repo: Repository, conn: ConnectionRow, now: datetime) -> ConnectionOut:
    runs = await repo.list_runs(conn.id, RUNS_LOOKED_AT)
    shown = [run_out(r, now) for r in runs[:RUNS_SHOWN]]
    connected = bool(conn.address and conn.key_hint)
    last_success = _last_success(runs)
    return ConnectionOut(
        id=conn.id,
        type="vetmanager",
        connected=connected,
        address=conn.address,
        key_hint=conn.key_hint,
        schedule=ScheduleOut(kind="nightly", time=SYNC_TIME) if connected else None,
        data_stale=vetmanager_is_stale(connected, last_success, now),
        last_success_at=last_success,
        last_run=shown[0] if shown else None,
        runs=shown,
        bank=None,
    )


async def _bank_out(repo: Repository, conn: ConnectionRow, today: date) -> ConnectionOut:
    accounts = [a for a in await repo.list_account_rows() if a.kind == "bank"]
    latest = max((a.last_statement_to for a in accounts if a.last_statement_to), default=None)
    return ConnectionOut(
        id=conn.id,
        type="bank",
        connected=latest is not None,
        address=None,
        key_hint=None,
        schedule=None,
        data_stale=bank_is_stale(latest, today),
        last_success_at=await repo.last_raw_event_at(BANK_SOURCE),
        last_run=None,
        runs=[],
        bank=BankInfoOut(
            accounts=[
                BankAccountStatusOut(
                    account=NamedRefOut(id=a.id, name=a.name), last_statement_to=a.last_statement_to
                )
                for a in accounts
            ]
        ),
    )


async def connection_state(
    repo: Repository, conn: ConnectionRow, now: datetime, today: date
) -> ConnectionOut:
    if conn.type == "vetmanager":
        return await _vetmanager_out(repo, conn, now)
    return await _bank_out(repo, conn, today)


async def list_connections(repo: Repository, now: datetime, today: date) -> ConnectionsOut:
    return ConnectionsOut(
        items=[await connection_state(repo, c, now, today) for c in await repo.list_connections()]
    )


async def data_is_stale(repo: Repository, now: datetime, today: date) -> bool:
    """True if any connected source is stale (for the dashboard)."""
    return any(c.data_stale for c in (await list_connections(repo, now, today)).items)


async def vetmanager_connection(repo: Repository) -> ConnectionRow:
    for conn in await repo.list_connections():
        if conn.type == "vetmanager":
            return conn
    raise not_found("Подключение не найдено.")


async def save_vetmanager(
    repo: Repository,
    *,
    address: str,
    key: str | None,
    suffixes: str,
    api: VetmanagerApi,
    box: SecretBox,
    runner: SyncRunner,
    background: BackgroundTasks,
    now: datetime,
    today: date,
) -> ConnectionOut:
    conn = await vetmanager_connection(repo)
    host = normalize_address(address, suffixes)
    was_connected = bool(conn.address and conn.key_hint)
    if host is None:
        raise validation_fields({"address": "unreachable"})
    secret = key
    if secret is None:
        cipher = await repo.get_connection_secret(conn.id) if was_connected else None
        if cipher is None:
            raise validation_fields({"key": "required"})
        secret = box.decrypt(cipher)
    check = await api.ping(host, secret)
    if check == INVALID_KEY:
        raise validation_fields({"key": "invalid"})
    if check != OK:
        raise validation_fields({"address": "unreachable"})
    if key is not None:
        await repo.save_connection_secret(conn.id, box.encrypt(key))
    await repo.update_connection(conn.id, host, key_hint(secret))
    if not was_connected:
        clinic_id = (await repo.get_clinic()).id
        run = await runner.start(clinic_id, conn.id)
        background.add_task(runner.run, clinic_id, conn.id, run.id)
    refreshed = await vetmanager_connection(repo)
    return await connection_state(repo, refreshed, now, today)


async def start_sync(
    repo: Repository,
    connection_id: str,
    *,
    runner: SyncRunner,
    background: BackgroundTasks,
    now: datetime,
) -> SyncRunOut:
    conn = await repo.get_connection(connection_id)
    if conn is None:
        raise not_found("Подключение не найдено.")
    if conn.type != "vetmanager" or not (conn.address and conn.key_hint):
        raise validation_reason("not_syncable", "Это подключение нельзя синхронизировать.")
    last = await repo.list_runs(conn.id, 1)
    if last and _is_active(last[0], now):
        raise conflict("Синхронизация уже идёт.")
    if last and now - last[0].started_at < MIN_SYNC_INTERVAL:
        wait = MIN_SYNC_INTERVAL - (now - last[0].started_at)
        raise rate_limited(
            "Синхронизировать можно не чаще раза в 5 минут.", int(wait.total_seconds()) + 1
        )
    clinic_id = (await repo.get_clinic()).id
    run = await runner.start(clinic_id, conn.id)
    background.add_task(runner.run, clinic_id, conn.id, run.id)
    return run_out(run, now)


async def import_raw(
    repo: Repository,
    entities: Mapping[str, Mapping[str, Any]],
    *,
    runner: SyncRunner,
    now: datetime,
) -> SyncRunOut:
    """Service load of raw Vetmanager responses (no live account): same path as a synchronisation."""
    conn = await vetmanager_connection(repo)
    clinic_id = (await repo.get_clinic()).id
    started = await runner.start(clinic_id, conn.id)
    allowed = {name: body for name, body in entities.items() if name in IMPORT_ENTITIES}
    finished = await runner.run(clinic_id, conn.id, started.id, allowed)
    return run_out(finished, now)
