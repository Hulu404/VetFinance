"""Postgres queries of stage 4: obligations (terms and frozen charges), planned payments, counterparty terms.

A mixin of PgRepository; every query is limited to the clinic of the connection (RLS applies as well).
"""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from engine.planning_inputs import CounterpartyTermsInput, ObligationInput, PlannedPaymentInput
from engine.reports_inputs import ObligationChargeInput

_OBL_COLS = (
    "id::text, kind, name, lender, counterparty_inn, principal, annual_rate_bp, payment, payment_day, "
    "first_payment_date, payments_total, cost, life_years, in_service_date, start_balance, "
    "effective_from, closed_from"
)
_OBL_EDITABLE = frozenset(
    {
        "name", "lender", "principal", "annual_rate_bp", "payment", "payment_day", "first_payment_date",
        "payments_total", "cost", "life_years", "in_service_date", "start_balance", "effective_from",
    }
)  # fmt: skip
_OBL_NEW = tuple(c for c in _OBL_COLS.split(", ")[1:] if c not in ("effective_from", "closed_from"))


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class PgPlanning:
    _conn: AsyncConnection

    async def _clinic(self) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------ obligations
    async def list_obligation_inputs(self) -> list[ObligationInput]:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(f"select {_OBL_COLS} from obligations where clinic_id = :cid order by name, id"),  # noqa: S608
            {"cid": cid},
        )
        return [ObligationInput(*r) for r in res.all()]

    async def create_obligation(self, ob: ObligationInput) -> ObligationInput:
        cid = await self._clinic()
        values = {c: getattr(ob, c) for c in _OBL_NEW}
        values["effective_from"] = ob.effective_from
        cols = ["code", "clinic_id", *values]
        marks = ["'api-' || gen_random_uuid()::text", ":cid", *(f":{c}" for c in values)]
        res = await self._conn.execute(
            text(
                f"insert into obligations ({', '.join(cols)}) values ({', '.join(marks)}) "  # noqa: S608
                f"returning {_OBL_COLS}"
            ),
            {"cid": cid, **values},
        )
        return ObligationInput(*res.one())

    async def update_obligation(
        self, obligation_id: str, changes: dict[str, Any]
    ) -> ObligationInput | None:
        key = _uuid_or_none(obligation_id)
        cols = [c for c in changes if c in _OBL_EDITABLE]
        if key is None:
            return None
        cid = await self._clinic()
        if not cols:
            res = await self._conn.execute(
                text(
                    f"select {_OBL_COLS} from obligations "  # noqa: S608
                    "where id = :id and clinic_id = :cid and closed_from is null"
                ),
                {"id": key, "cid": cid},
            )
        else:
            assignments = ", ".join(f"{c} = :{c}" for c in cols)  # names from a whitelist
            res = await self._conn.execute(
                text(
                    f"update obligations set {assignments} where id = :id and clinic_id = :cid "  # noqa: S608
                    f"and closed_from is null returning {_OBL_COLS}"
                ),
                {**{c: changes[c] for c in cols}, "id": key, "cid": cid},
            )
        row = res.first()
        return ObligationInput(*row) if row else None

    async def close_obligation(self, obligation_id: str, month: date) -> bool:
        key = _uuid_or_none(obligation_id)
        if key is None:
            return False
        res = await self._conn.execute(
            text(
                "update obligations set closed_from = :month where id = :id and clinic_id = :cid "
                "and closed_from is null returning id"
            ),
            {"month": month, "id": key, "cid": await self._clinic()},
        )
        return res.first() is not None

    async def insert_charges(self, rows: Sequence[ObligationChargeInput]) -> None:
        """Freeze accruals of past months; rows that exist stay as they are."""
        cid = await self._clinic()
        for r in rows:
            key = _uuid_or_none(r.obligation_id)
            if key is None:
                continue
            await self._conn.execute(
                text(
                    "insert into obligation_charges (clinic_id, obligation_id, month, kind, amount, basis) "
                    "values (:cid, :oid, :month, :kind, :amount, 'frozen') "
                    "on conflict (clinic_id, obligation_id, month, kind) do nothing"
                ),
                {
                    "cid": cid,
                    "oid": key,
                    "month": date(int(r.month[:4]), int(r.month[5:7]), 1),
                    "kind": r.kind,
                    "amount": r.amount,
                },
            )

    # ------------------------------------------------------------ planned payments
    async def list_planned_payments(self) -> list[PlannedPaymentInput]:
        res = await self._conn.execute(
            text(
                "select p.id::text, p.date, p.name, p.amount, p.max_deferral_days, c.name "
                "from planned_payments p left join categories c on c.id = p.category_id "
                "and c.clinic_id = p.clinic_id where p.clinic_id = :cid order by p.date, p.name, p.id"
            ),
            {"cid": await self._clinic()},
        )
        return [PlannedPaymentInput(*r) for r in res.all()]

    async def add_planned_payment(
        self, day: date, name: str, amount: int, category_id: str | None, max_deferral_days: int
    ) -> PlannedPaymentInput:
        res = await self._conn.execute(
            text(
                "with new as (insert into planned_payments (clinic_id, date, name, amount, category_id, "
                "max_deferral_days) values (:cid, :day, :name, :amount, :cat, :days) returning *) "
                "select n.id::text, n.date, n.name, n.amount, n.max_deferral_days, c.name from new n "
                "left join categories c on c.id = n.category_id and c.clinic_id = n.clinic_id"
            ),
            {
                "cid": await self._clinic(),
                "day": day,
                "name": name,
                "amount": amount,
                "cat": _uuid_or_none(category_id) if category_id else None,
                "days": max_deferral_days,
            },
        )
        return PlannedPaymentInput(*res.one())

    async def delete_planned_payment(self, payment_id: str) -> bool:
        key = _uuid_or_none(payment_id)
        if key is None:
            return False
        res = await self._conn.execute(
            text("delete from planned_payments where id = :id and clinic_id = :cid returning id"),
            {"id": key, "cid": await self._clinic()},
        )
        return res.first() is not None

    # ------------------------------------------------------------ counterparties
    async def list_counterparty_terms(self) -> list[CounterpartyTermsInput]:
        res = await self._conn.execute(
            text(
                "select key, name, max_deferral_days from counterparties "
                "where clinic_id = :cid order by key"
            ),
            {"cid": await self._clinic()},
        )
        return [CounterpartyTermsInput(*r) for r in res.all()]

    async def set_counterparty_terms(self, key: str, name: str, days: int) -> None:
        await self._conn.execute(
            text(
                "insert into counterparties (clinic_id, key, name, max_deferral_days) "
                "values (:cid, :key, :name, :days) "
                "on conflict (clinic_id, key) do update set max_deferral_days = excluded.max_deferral_days"
            ),
            {"cid": await self._clinic(), "key": key, "name": name, "days": days},
        )
