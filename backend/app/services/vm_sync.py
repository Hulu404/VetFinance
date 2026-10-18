"""Synchronisation of one clinic with Vetmanager.

Runs as a background job over a repository bound to the clinic. Fetches (or takes ready) raw responses,
normalises them with the engine (no data of pet owners passes through), stores visits, sales, doctors,
payments, and turns cash payments into operations of the cash desk. Every outcome is written to the
sync run, the key never reaches a log.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.integrations.vetmanager import UNKNOWN, VetmanagerApi, VetmanagerError
from app.repo import Repository
from app.rows import AccountRow, NewTx
from app.secrets import SecretBox
from engine.dedup import TxRef, find_duplicate_pairs
from engine.vetmanager import METHOD_CASH, NormalizedVetmanager, Payment, normalize_vetmanager

FIRST_SYNC_DAYS = 730  # two years of history on the first run
OVERLAP_DAYS = 14  # later runs re-read the last two weeks: invoices get paid and edited
REVENUE_CATEGORY = "Выручка"
SOURCE = "vetmanager"
DEDUP_WINDOW_DAYS = 3


class _Tally:
    def __init__(self) -> None:
        self.new = 0
        self.updated = 0
        self.same = 0

    def add(self, outcome: str) -> None:
        if outcome == "new":
            self.new += 1
        elif outcome == "updated":
            self.updated += 1
        else:
            self.same += 1


async def _store_doctors(repo: Repository, normalized: NormalizedVetmanager) -> dict[str, str]:
    known = await repo.list_doctors()
    next_number = len(known) + 1
    ids: dict[str, str] = {}
    for doctor in normalized.doctors:
        if doctor.external_id in known:
            code = known[doctor.external_id][1]
        else:
            code = f"D{next_number}"
            next_number += 1
        ids[doctor.external_id] = await repo.upsert_doctor(doctor.external_id, code, doctor.name)
    return ids


def _cash_account(accounts: Sequence[AccountRow]) -> AccountRow | None:
    return next((a for a in accounts if a.kind == "cash"), None)


async def _cash_transactions(
    repo: Repository, new_cash: Sequence[Payment], account: AccountRow, category_id: str | None
) -> dict[str, str]:
    """Operations for new cash payments: payment external id -> operation id."""
    if not new_cash:
        return {}
    window = timedelta(days=DEDUP_WINDOW_DAYS)
    candidates = await repo.duplicate_candidates(
        min(p.date for p in new_cash) - window, max(p.date for p in new_cash) + window
    )
    ordered = sorted(new_cash, key=lambda p: (p.date, p.external_id))
    refs = [TxRef(p.external_id, account.id, p.date, p.amount, SOURCE, "in") for p in ordered]
    originals = {p.duplicate_id: p.original_id for p in find_duplicate_pairs(refs, candidates)}
    rows = [
        NewTx(
            account_id=account.id,
            date=p.date,
            description="Оплата наличными · Ветменеджер",
            amount=p.amount,
            kind="in",
            source=SOURCE,
            status="duplicate"
            if p.external_id in originals
            else ("ok" if category_id else "check"),
            external_id=p.external_id,
            category_id=category_id,
            category_source="rule" if category_id else None,
            rule_id=None,
            duplicate_of=originals.get(p.external_id),
            duplicate_state="pending" if p.external_id in originals else None,
        )
        for p in ordered
    ]
    ids = await repo.insert_transactions(rows)
    return {p.external_id: tx_id for p, tx_id in zip(ordered, ids, strict=True)}


async def _store_payments(repo: Repository, payments: Sequence[Payment], tally: _Tally) -> bool:
    """Stores payments; cash ones also become operations. False if some could not be turned into one."""
    cash = [p for p in payments if p.method == METHOD_CASH]
    known = await repo.existing_external_ids(SOURCE, [p.external_id for p in cash])
    account = _cash_account(await repo.list_account_rows())
    category = next((c for c in await repo.list_categories() if c.name == REVENUE_CATEGORY), None)
    new_cash = [p for p in cash if p.external_id not in known]
    created = (
        await _cash_transactions(repo, new_cash, account, category.id if category else None)
        if account is not None
        else {}
    )
    for payment in payments:
        tally.add(await repo.upsert_payment(payment, created.get(payment.external_id)))
    return account is not None or not new_cash


async def store_normalized(
    repo: Repository, normalized: NormalizedVetmanager
) -> tuple[_Tally, bool]:
    """Writes the normalised data. Returns the counters and whether everything was stored."""
    tally = _Tally()
    doctor_ids = await _store_doctors(repo, normalized)
    for visit in normalized.visits:
        doctor = doctor_ids.get(visit.doctor_external_id) if visit.doctor_external_id else None
        tally.add(await repo.upsert_visit(visit, doctor))
    for found in normalized.services:
        await repo.upsert_service(found)  # not counted: the counters tell about operations
    for sale in normalized.sales:
        tally.add(await repo.upsert_sale(sale))
    complete = await _store_payments(repo, normalized.payments, tally)
    return tally, complete and normalized.skipped == 0


async def _since(repo: Repository, connection_id: str, today: date) -> date:
    for run in await repo.list_runs(connection_id, 10):
        if run.status in ("success", "partial") and run.finished_at is not None:
            return run.finished_at.date() - timedelta(days=OVERLAP_DAYS)
    return today - timedelta(days=FIRST_SYNC_DAYS)


@dataclass(frozen=True)
class SyncOutcome:
    status: str  # "success" | "partial" | "failed"
    error_code: str | None
    counts: dict[str, int] | None


async def execute_sync(
    repo: Repository,
    *,
    connection_id: str,
    api: VetmanagerApi,
    box_factory: Callable[[], SecretBox],
    today: date,
    raw: Mapping[str, Mapping[str, Any]] | None = None,
) -> SyncOutcome:
    """Loads, normalises and stores. Errors of the Vetmanager API become a failed outcome (nothing is
    written before the fetch ends); a database error propagates, the caller rolls back and records it."""
    try:
        if raw is None:
            raw = await _fetch(repo, connection_id, api, box_factory, today)
    except VetmanagerError as exc:
        return SyncOutcome("failed", exc.code, None)
    tally, complete = await store_normalized(repo, normalize_vetmanager(raw))
    counts = {"new": tally.new, "updated": tally.updated, "skipped_duplicates": tally.same}
    return SyncOutcome("success" if complete else "partial", None, counts)


async def _fetch(
    repo: Repository,
    connection_id: str,
    api: VetmanagerApi,
    box_factory: Callable[[], SecretBox],
    today: date,
) -> dict[str, dict[str, Any]]:
    connection = await repo.get_connection(connection_id)
    cipher = await repo.get_connection_secret(connection_id)
    if connection is None or not connection.address or not cipher:
        raise VetmanagerError(UNKNOWN)
    since = await _since(repo, connection_id, today)
    return await api.fetch(connection.address, box_factory().decrypt(cipher), since)
