"""Postgres implementation of the Repository protocol (raw SQL, one clinic per instance).

Every query filters by `clinic_id` explicitly. For a user request RLS would filter anyway; for the
service connection (background synchronisation, RLS bypassed) the explicit filter is the isolation.
Only whitelisted column names are ever interpolated into SQL; all values are bound parameters.
"""

import json
import uuid
from collections.abc import Collection, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.errors import forbidden
from app.rows import (
    AccountRow,
    CardPaymentRow,
    CategoryRow,
    ClinicRow,
    ConnectionRow,
    NewTx,
    ReviewRow,
    RuleRow,
    SummaryRow,
    SyncRunRow,
    TxRow,
)
from engine.balance import AccountInput, TransactionInput
from engine.dedup import TxRef
from engine.vetmanager import Payment, Sale, Visit

_CLINIC_COLS = "id::text, name, legal_entity, tax_regime, timezone, safe_balance"
_EDITABLE_CLINIC = ("name", "legal_entity", "tax_regime", "timezone", "safe_balance")
_TX_EDITABLE = (
    "category_id",
    "category_source",
    "rule_id",
    "status",
    "duplicate_of",
    "duplicate_state",
    "duplicate_dismissed",
)
_TX_SELECT = (
    "select t.id::text, t.date, t.description, t.amount, t.kind, t.source, t.status, "
    "t.account_id::text, a.name, t.category_id::text, c.name, t.category_source, t.rule_id::text, "
    "t.counterparty_inn, t.counterparty_name, t.duplicate_of::text, t.duplicate_state, "
    "t.duplicate_dismissed, t.created_at "
    "from transactions t join accounts a on a.id = t.account_id "
    "left join categories c on c.id = t.category_id "
)
_TAB_FILTERS = {
    "all": "",
    "check": " and t.status = 'check'",
    "duplicates": " and t.status = 'duplicate' and coalesce(t.duplicate_state, 'pending') = 'pending'",
}
_RUN_COLS = "id::text, connection_id::text, status, started_at, finished_at, error_code, counts"
_NEW_TX_COLS = (
    "id, clinic_id, account_id, date, description, amount, kind, source, external_id, dedup_hash, "
    "status, category_id, category_source, rule_id, counterparty_inn, counterparty_name, doc_number, "
    "transfer_group, duplicate_of, duplicate_state, import_id"
)


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


def _uuids(values: Sequence[str]) -> list[uuid.UUID]:
    return [uuid.UUID(v) for v in values]


def _opt_uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


class PgRepository:
    """`clinic_id=None`: the clinic is the user's first membership (user request, RLS applies).
    With `clinic_id` and `service=True` the connection is a trusted background job of that clinic."""

    def __init__(
        self, conn: AsyncConnection, clinic_id: str | None = None, *, service: bool = False
    ) -> None:
        self._conn = conn
        self._clinic_id = clinic_id
        self._service = service

    async def _clinic(self) -> str:
        if self._clinic_id is None:
            row = (
                await self._conn.execute(
                    text("select clinic_id::text from memberships order by created_at, id limit 1")
                )
            ).first()
            if row is None:
                raise forbidden("Пользователь не привязан ни к одной клинике.")
            self._clinic_id = str(row[0])
        return self._clinic_id

    # ------------------------------------------------------------ clinic and accounts
    async def get_clinic(self) -> ClinicRow:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(f"select {_CLINIC_COLS} from clinics where id = :cid"),  # noqa: S608
            {"cid": cid},
        )
        return ClinicRow(*res.one())

    async def update_clinic(self, changes: dict[str, Any]) -> ClinicRow:
        cid = await self._clinic()
        cols = [c for c in changes if c in _EDITABLE_CLINIC]
        if not cols:
            return await self.get_clinic()
        assignments = ", ".join(f"{c} = :{c}" for c in cols)  # column names from a whitelist
        res = await self._conn.execute(
            text(f"update clinics set {assignments} where id = :cid returning {_CLINIC_COLS}"),  # noqa: S608
            {**{c: changes[c] for c in cols}, "cid": cid},
        )
        return ClinicRow(*res.one())

    async def get_acquiring_rate_bp(self) -> int:
        cid = await self._clinic()
        res = await self._conn.execute(
            text("select acquiring_rate_bp from clinics where id = :cid"), {"cid": cid}
        )
        return int(res.scalar_one())

    async def list_accounts(self) -> list[AccountInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select id::text, name, kind, opening_balance, opening_date from accounts "
                "where clinic_id = :cid order by name, id"
            ),
            {"cid": cid},
        )
        return [AccountInput(*r) for r in res.all()]

    async def list_account_rows(self) -> list[AccountRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select id::text, name, kind, opening_balance, opening_date, number, last_statement_to "
                "from accounts where clinic_id = :cid order by name, id"
            ),
            {"cid": cid},
        )
        return [AccountRow(*r) for r in res.all()]

    async def set_last_statement_to(self, account_id: str, day: date) -> None:
        cid = await self._clinic()
        await self._conn.execute(
            text(
                "update accounts set last_statement_to = greatest(coalesce(last_statement_to, :day), :day) "
                "where id = :id and clinic_id = :cid"
            ),
            {"day": day, "id": _uuid(account_id), "cid": cid},
        )

    # ------------------------------------------------------------ balance
    async def list_transactions(self, as_of: date) -> list[TransactionInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select account_id::text, date, amount, status, source from transactions "
                "where clinic_id = :cid and date <= :as_of and status <> 'duplicate'"
            ),
            {"cid": cid, "as_of": as_of},
        )
        return [TransactionInput(*r) for r in res.all()]

    async def last_data_at(self) -> datetime | None:
        cid = await self._clinic()
        res = await self._conn.execute(
            text("select max(created_at) from transactions where clinic_id = :cid"), {"cid": cid}
        )
        value: datetime | None = res.scalar()
        return value

    # ------------------------------------------------------------ categories and rules
    async def list_categories(self) -> list[CategoryRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select id::text, name, type, norm_min_pct::float8, norm_max_pct::float8 "
                "from categories where clinic_id = :cid "
                "order by case type when 'income' then 0 when 'variable' then 1 else 2 end, name"
            ),
            {"cid": cid},
        )
        return [CategoryRow(*r) for r in res.all()]

    _RULE_SELECT = (
        "select r.id::text, r.match, r.value, r.display_name, r.direction, r.category_id::text, "
        "c.name, r.created_at from category_rules r join categories c on c.id = r.category_id "
    )

    async def list_rules(self) -> list[RuleRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(self._RULE_SELECT + "where r.clinic_id = :cid order by r.sort_key"),  # noqa: S608
            {"cid": cid},
        )
        return [RuleRow(*r) for r in res.all()]

    async def insert_rule(
        self,
        *,
        match: str,
        value: str,
        display_name: str | None,
        direction: str | None,
        category_id: str,
    ) -> RuleRow:
        cid = await self._clinic()
        rule_id = uuid.uuid4()
        await self._conn.execute(
            text(
                "insert into category_rules (id, clinic_id, match, value, display_name, direction, category_id) "
                "values (:id, :cid, :match, :value, :name, :direction, :category)"
            ),
            {
                "id": rule_id,
                "cid": cid,
                "match": match,
                "value": value,
                "name": display_name,
                "direction": direction,
                "category": _uuid(category_id),
            },
        )
        res = await self._conn.execute(
            text(self._RULE_SELECT + "where r.id = :id and r.clinic_id = :cid"),  # noqa: S608
            {"id": rule_id, "cid": cid},
        )
        return RuleRow(*res.one())

    async def delete_rule(self, rule_id: str) -> bool:
        cid = await self._clinic()
        res = await self._conn.execute(
            text("delete from category_rules where id = :id and clinic_id = :cid returning 1"),
            {"id": _uuid(rule_id), "cid": cid},
        )
        return res.first() is not None

    async def rule_applied_counts(self, month_start: date) -> dict[str, tuple[int, int]]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select rule_id::text, count(*) filter (where date >= :month_start), count(*) "
                "from transactions where clinic_id = :cid and rule_id is not null group by rule_id"
            ),
            {"cid": cid, "month_start": month_start},
        )
        return {str(r[0]): (int(r[1]), int(r[2])) for r in res.all()}

    # ------------------------------------------------------------ transactions
    async def page_transactions(
        self,
        *,
        tab: str,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        after: tuple[date, str] | None,
    ) -> list[TxRow]:
        cid = await self._clinic()
        sql = _TX_SELECT + "where t.clinic_id = :cid" + _TAB_FILTERS[tab]
        params: dict[str, Any] = {"cid": cid, "limit": limit}
        if date_from is not None:
            sql += " and t.date >= :date_from"
            params["date_from"] = date_from
        if date_to is not None:
            sql += " and t.date <= :date_to"
            params["date_to"] = date_to
        if after is not None:
            sql += " and (t.date, t.id) < (:after_date, :after_id)"
            params.update(after_date=after[0], after_id=_uuid(after[1]))
        sql += " order by t.date desc, t.id desc limit :limit"
        res = await self._conn.execute(text(sql), params)
        return [TxRow(*r) for r in res.all()]

    async def tab_counts(self) -> dict[str, int]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select count(*), count(*) filter (where status = 'check'), "
                "count(*) filter (where status = 'duplicate' "
                "and coalesce(duplicate_state, 'pending') = 'pending') "
                "from transactions where clinic_id = :cid"
            ),
            {"cid": cid},
        )
        total, check, duplicates = res.one()
        return {"all": int(total), "check": int(check), "duplicates": int(duplicates)}

    async def get_transactions(self, ids: Sequence[str]) -> list[TxRow]:
        if not ids:
            return []
        cid = await self._clinic()
        res = await self._conn.execute(
            text(_TX_SELECT + "where t.clinic_id = :cid and t.id = any(:ids)"),  # noqa: S608
            {"cid": cid, "ids": _uuids(ids)},
        )
        return [TxRow(*r) for r in res.all()]

    async def get_duplicate_partners(self, tx_id: str) -> list[TxRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                _TX_SELECT
                + "where t.clinic_id = :cid and t.duplicate_of = :id order by t.date, t.id"
            ),  # noqa: S608
            {"cid": cid, "id": _uuid(tx_id)},
        )
        return [TxRow(*r) for r in res.all()]

    async def summary_rows(self, first: date, last: date) -> list[SummaryRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select t.date, t.amount, t.kind, t.status, c.name, t.source from transactions t "
                "left join categories c on c.id = t.category_id "
                "where t.clinic_id = :cid and t.date between :first and :last "
                "and t.status <> 'duplicate' and t.kind <> 'transfer'"
            ),
            {"cid": cid, "first": first, "last": last},
        )
        return [SummaryRow(*r) for r in res.all()]

    async def insert_transactions(self, rows: Sequence[NewTx]) -> list[str]:
        if not rows:
            return []
        cid = await self._clinic()
        ids = [uuid.uuid4() for _ in rows]
        params = [
            {
                "id": new_id,
                "cid": cid,
                "account_id": _uuid(r.account_id),
                "date": r.date,
                "description": r.description,
                "amount": r.amount,
                "kind": r.kind,
                "source": r.source,
                "external_id": r.external_id,
                "dedup_hash": r.dedup_hash,
                "status": r.status,
                "category_id": _opt_uuid(r.category_id),
                "category_source": r.category_source,
                "rule_id": _opt_uuid(r.rule_id),
                "inn": r.counterparty_inn,
                "name": r.counterparty_name,
                "doc_number": r.doc_number,
                "transfer_group": r.transfer_group,
                "duplicate_of": _opt_uuid(r.duplicate_of),
                "duplicate_state": r.duplicate_state,
                "import_id": _opt_uuid(r.import_id),
            }
            for new_id, r in zip(ids, rows, strict=True)
        ]
        await self._conn.execute(
            text(
                f"insert into transactions ({_NEW_TX_COLS}) values (:id, :cid, :account_id, :date, "  # noqa: S608
                ":description, :amount, :kind, :source, :external_id, :dedup_hash, :status, :category_id, "
                ":category_source, :rule_id, :inn, :name, :doc_number, :transfer_group, :duplicate_of, "
                ":duplicate_state, :import_id) "
                "on conflict (clinic_id, source, external_id) where external_id is not null do nothing"
            ),
            params,
        )
        return [str(i) for i in ids]

    async def update_transaction(self, tx_id: str, changes: Mapping[str, Any]) -> None:
        cid = await self._clinic()
        cols = [c for c in changes if c in _TX_EDITABLE]
        if not cols:
            return
        assignments = ", ".join(f"{c} = :{c}" for c in cols)  # column names from a whitelist
        values = {
            c: (
                _opt_uuid(changes[c])
                if c in ("category_id", "rule_id", "duplicate_of")
                else changes[c]
            )
            for c in cols
        }
        await self._conn.execute(
            text(f"update transactions set {assignments} where id = :id and clinic_id = :cid"),  # noqa: S608
            {**values, "id": _uuid(tx_id), "cid": cid},
        )

    async def existing_external_ids(self, source: str, ids: Collection[str]) -> set[str]:
        if not ids:
            return set()
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select external_id from transactions where clinic_id = :cid and source = :source "
                "and external_id = any(:ids)"
            ),
            {"cid": cid, "source": source, "ids": list(ids)},
        )
        return {str(r[0]) for r in res.all()}

    async def duplicate_candidates(self, first: date, last: date) -> list[TxRef]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select t.id::text, t.account_id::text, t.date, t.amount, t.source, t.kind "
                "from transactions t where t.clinic_id = :cid and t.date between :first and :last "
                "and t.status <> 'duplicate' and t.kind <> 'transfer' and not t.duplicate_dismissed "
                "and not exists (select 1 from transactions d "
                "where d.clinic_id = t.clinic_id and d.duplicate_of = t.id) "
                "order by t.date, t.created_at, t.id"
            ),
            {"cid": cid, "first": first, "last": last},
        )
        return [TxRef(*r) for r in res.all()]

    async def uncategorised_checks(self) -> list[TxRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                _TX_SELECT  # noqa: S608
                + "where t.clinic_id = :cid and t.status = 'check' and t.category_id is null "
                "and t.kind <> 'transfer' order by t.date, t.id"
            ),
            {"cid": cid},
        )
        return [TxRow(*r) for r in res.all()]

    async def category_history(self, inns: Collection[str]) -> dict[str, dict[str, int]]:
        if not inns:
            return {}
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select counterparty_inn, category_id::text, count(*) from transactions "
                "where clinic_id = :cid and counterparty_inn = any(:inns) and category_id is not null "
                "and status <> 'duplicate' group by counterparty_inn, category_id"
            ),
            {"cid": cid, "inns": list(inns)},
        )
        history: dict[str, dict[str, int]] = {}
        for inn, category, count in res.all():
            history.setdefault(str(inn), {})[str(category)] = int(count)
        return history

    # ------------------------------------------------------------ imports
    async def add_raw_event(
        self, source: str, file_hash: str | None, byte_size: int | None, payload: Mapping[str, Any]
    ) -> str:
        cid = await self._clinic()
        event_id = uuid.uuid4()
        await self._conn.execute(
            text(
                "insert into raw_events (id, clinic_id, source, file_hash, byte_size, payload) "
                "values (:id, :cid, :source, :hash, :size, cast(:payload as jsonb))"
            ),
            {
                "id": event_id,
                "cid": cid,
                "source": source,
                "hash": file_hash,
                "size": byte_size,
                "payload": json.dumps(dict(payload), ensure_ascii=False, default=str),
            },
        )
        return str(event_id)

    async def count_recent_raw_events(self, source: str, seconds: int) -> int:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select count(*) from raw_events where clinic_id = :cid and source = :source "
                "and created_at > now() - (:seconds * interval '1 second')"
            ),
            {"cid": cid, "source": source, "seconds": seconds},
        )
        return int(res.scalar_one())

    async def last_raw_event_at(self, source: str) -> datetime | None:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select max(created_at) from raw_events where clinic_id = :cid and source = :source"
            ),
            {"cid": cid, "source": source},
        )
        value: datetime | None = res.scalar()
        return value

    # ------------------------------------------------------------ acquiring
    async def list_card_payments(self) -> list[CardPaymentRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select date, amount, invoice_external_id from payments "
                "where clinic_id = :cid and method = 'card' order by date, external_id"
            ),
            {"cid": cid},
        )
        return [CardPaymentRow(*r) for r in res.all()]

    async def list_acquiring_credits(self, category_name: str) -> list[TxRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                _TX_SELECT  # noqa: S608
                + "where t.clinic_id = :cid and c.name = :name and t.kind = 'in' "
                "and t.status <> 'duplicate' order by t.date, t.id"
            ),
            {"cid": cid, "name": category_name},
        )
        return [TxRow(*r) for r in res.all()]

    async def bank_covered_to(self) -> date | None:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select max(last_statement_to) from accounts where clinic_id = :cid and kind = 'bank'"
            ),
            {"cid": cid},
        )
        value: date | None = res.scalar()
        return value

    async def list_reviews(self) -> list[ReviewRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text("select sale_date, note from acquiring_reviews where clinic_id = :cid"),
            {"cid": cid},
        )
        return [ReviewRow(*r) for r in res.all()]

    async def save_review(self, sale_date: date, note: str | None) -> None:
        cid = await self._clinic()
        await self._conn.execute(
            text(
                "insert into acquiring_reviews (clinic_id, sale_date, note) values (:cid, :day, :note) "
                "on conflict (clinic_id, sale_date) do update set note = excluded.note, reviewed_at = now()"
            ),
            {"cid": cid, "day": sale_date, "note": note},
        )

    # ------------------------------------------------------------ connections and synchronisation
    async def list_connections(self) -> list[ConnectionRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select id::text, type, address, key_hint from connections where clinic_id = :cid "
                "order by case type when 'vetmanager' then 0 else 1 end"
            ),
            {"cid": cid},
        )
        return [ConnectionRow(*r) for r in res.all()]

    async def get_connection(self, connection_id: str) -> ConnectionRow | None:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "select id::text, type, address, key_hint from connections "
                "where id = :id and clinic_id = :cid"
            ),
            {"id": _uuid(connection_id), "cid": cid},
        )
        row = res.first()
        return ConnectionRow(*row) if row else None

    async def update_connection(
        self, connection_id: str, address: str | None, key_hint: str | None
    ) -> None:
        cid = await self._clinic()
        await self._conn.execute(
            text(
                "update connections set address = :address, key_hint = :hint "
                "where id = :id and clinic_id = :cid"
            ),
            {"address": address, "hint": key_hint, "id": _uuid(connection_id), "cid": cid},
        )

    async def save_connection_secret(self, connection_id: str, cipher: str) -> None:
        cid = await self._clinic()
        if self._service:
            await self._conn.execute(
                text(
                    "insert into connection_secrets (connection_id, clinic_id, key_cipher) "
                    "values (:id, :cid, :cipher) on conflict (connection_id) "
                    "do update set key_cipher = excluded.key_cipher, updated_at = now()"
                ),
                {"id": _uuid(connection_id), "cid": cid, "cipher": cipher},
            )
            return
        await self._conn.execute(
            text("select public.set_connection_secret(:id, :cipher)"),
            {"id": _uuid(connection_id), "cipher": cipher},
        )

    async def get_connection_secret(self, connection_id: str) -> str | None:
        cid = await self._clinic()
        if self._service:
            res = await self._conn.execute(
                text(
                    "select key_cipher from connection_secrets "
                    "where connection_id = :id and clinic_id = :cid"
                ),
                {"id": _uuid(connection_id), "cid": cid},
            )
        else:
            res = await self._conn.execute(
                text("select public.get_connection_secret(:id)"), {"id": _uuid(connection_id)}
            )
        value: str | None = res.scalar()
        return value

    async def list_runs(self, connection_id: str, limit: int) -> list[SyncRunRow]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                f"select {_RUN_COLS} from sync_runs where clinic_id = :cid "  # noqa: S608
                "and connection_id = :id order by started_at desc, id limit :limit"
            ),
            {"cid": cid, "id": _uuid(connection_id), "limit": limit},
        )
        return [SyncRunRow(*r) for r in res.all()]

    async def create_run(self, connection_id: str) -> SyncRunRow:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "insert into sync_runs (clinic_id, connection_id, status) "  # noqa: S608
                f"values (:cid, :id, 'running') returning {_RUN_COLS}"
            ),
            {"cid": cid, "id": _uuid(connection_id)},
        )
        return SyncRunRow(*res.one())

    async def get_run(self, run_id: str) -> SyncRunRow | None:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(f"select {_RUN_COLS} from sync_runs where id = :id and clinic_id = :cid"),  # noqa: S608
            {"id": _uuid(run_id), "cid": cid},
        )
        row = res.first()
        return SyncRunRow(*row) if row else None

    async def finish_run(
        self, run_id: str, status: str, error_code: str | None, counts: Mapping[str, int] | None
    ) -> None:
        cid = await self._clinic()
        await self._conn.execute(
            text(
                "update sync_runs set status = :status, error_code = :error, finished_at = now(), "
                "counts = cast(:counts as jsonb) where id = :id and clinic_id = :cid"
            ),
            {
                "status": status,
                "error": error_code,
                "counts": json.dumps(dict(counts)) if counts is not None else None,
                "id": _uuid(run_id),
                "cid": cid,
            },
        )

    # ------------------------------------------------------------ Vetmanager data
    async def list_doctors(self) -> dict[str, tuple[str, str]]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text("select external_id, id::text, code from doctors where clinic_id = :cid"),
            {"cid": cid},
        )
        return {str(r[0]): (str(r[1]), str(r[2])) for r in res.all()}

    async def upsert_doctor(self, external_id: str, code: str, name: str) -> str:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(
                "insert into doctors (clinic_id, external_id, code, name) values (:cid, :ext, :code, :name) "
                "on conflict (clinic_id, external_id) do update set name = excluded.name returning id::text"
            ),
            {"cid": cid, "ext": external_id, "code": code, "name": name},
        )
        return str(res.scalar_one())

    async def _classify(self, sql: str, params: dict[str, Any]) -> str:
        """Run an upsert that returns a row only when it inserted or changed something."""
        res = await self._conn.execute(text(sql), {**params, "cid": await self._clinic()})
        row = res.first()
        if row is None:
            return "same"
        return "new" if row[0] else "updated"

    async def upsert_visit(self, visit: Visit, doctor_id: str | None) -> str:
        return await self._classify(
            "insert into visits (clinic_id, external_id, date, doctor_id) values (:cid, :ext, :date, :doctor) "
            "on conflict (clinic_id, external_id) do update set date = excluded.date, "
            "doctor_id = excluded.doctor_id "
            "where (visits.date, visits.doctor_id) is distinct from (excluded.date, excluded.doctor_id) "
            "returning (xmax = 0)",
            {"ext": visit.external_id, "date": visit.date, "doctor": _opt_uuid(doctor_id)},
        )

    async def upsert_sale(self, sale: Sale) -> str:
        lines = json.dumps([{"kind": line.kind, "amount": line.amount} for line in sale.lines])
        return await self._classify(
            "insert into sales (clinic_id, external_id, date, status, amount, lines) "
            "values (:cid, :ext, :date, :status, :amount, cast(:lines as jsonb)) "
            "on conflict (clinic_id, external_id) do update set date = excluded.date, "
            "status = excluded.status, amount = excluded.amount, lines = excluded.lines "
            "where (sales.date, sales.status, sales.amount, sales.lines) "
            "is distinct from (excluded.date, excluded.status, excluded.amount, excluded.lines) "
            "returning (xmax = 0)",
            {
                "ext": sale.external_id,
                "date": sale.date,
                "status": sale.status,
                "amount": sale.amount,
                "lines": lines,
            },
        )

    async def upsert_payment(self, payment: Payment, transaction_id: str | None) -> str:
        return await self._classify(
            "insert into payments (clinic_id, external_id, date, amount, method, invoice_external_id, "
            "transaction_id) values (:cid, :ext, :date, :amount, :method, :invoice, :tx) "
            "on conflict (clinic_id, external_id) do update set date = excluded.date, "
            "amount = excluded.amount, method = excluded.method, "
            "invoice_external_id = excluded.invoice_external_id, "
            "transaction_id = coalesce(payments.transaction_id, excluded.transaction_id) "
            "where (payments.date, payments.amount, payments.method, payments.invoice_external_id) "
            "is distinct from (excluded.date, excluded.amount, excluded.method, excluded.invoice_external_id) "
            "returning (xmax = 0)",
            {
                "ext": payment.external_id,
                "date": payment.date,
                "amount": payment.amount,
                "method": payment.method,
                "invoice": payment.invoice_external_id,
                "tx": _opt_uuid(transaction_id),
            },
        )
