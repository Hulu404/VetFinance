"""Data layer. The Repository protocol is what the API depends on; tests substitute it.

PgRepository runs every request in one transaction as role `authenticated` with the
JWT claims of the user in `request.jwt.claims`, so Postgres RLS (auth.uid()) applies.
The connection itself uses the DATABASE_URL role (postgres) only to `set local role`.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, Protocol

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.auth import Principal, get_principal
from app.errors import ApiError, forbidden
from app.settings import Settings, get_settings
from engine.balance import AccountInput, TransactionInput


@dataclass(frozen=True)
class ClinicRow:
    id: str
    name: str
    legal_entity: str | None
    tax_regime: str | None
    timezone: str
    safe_balance: int


class Repository(Protocol):
    async def get_clinic(self) -> ClinicRow: ...
    async def update_clinic(self, changes: dict[str, Any]) -> ClinicRow: ...
    async def list_accounts(self) -> list[AccountInput]: ...
    async def list_transactions(self, as_of: date) -> list[TransactionInput]: ...
    async def last_data_at(self) -> datetime | None: ...


_CLINIC_COLS = "id::text, name, legal_entity, tax_regime, timezone, safe_balance"
_EDITABLE = ("name", "legal_entity", "tax_regime", "timezone", "safe_balance")


class PgRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn
        self._clinic_id: str | None = None

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

    @staticmethod
    def _clinic_row(row: Any) -> ClinicRow:
        return ClinicRow(*row)

    async def get_clinic(self) -> ClinicRow:
        cid = await self._clinic()
        res = await self._conn.execute(
            text(f"select {_CLINIC_COLS} from clinics where id = :cid"),  # noqa: S608
            {"cid": cid},
        )
        return self._clinic_row(res.one())

    async def update_clinic(self, changes: dict[str, Any]) -> ClinicRow:
        cid = await self._clinic()
        cols = [c for c in changes if c in _EDITABLE]
        if not cols:
            return await self.get_clinic()
        assignments = ", ".join(f"{c} = :{c}" for c in cols)  # column names from a whitelist
        res = await self._conn.execute(
            text(f"update clinics set {assignments} where id = :cid returning {_CLINIC_COLS}"),  # noqa: S608
            {**{c: changes[c] for c in cols}, "cid": cid},
        )
        return self._clinic_row(res.one())

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


_engines: dict[str, AsyncEngine] = {}


def _engine(settings: Settings) -> AsyncEngine:
    url = settings.database_url.get_secret_value()
    if not url:
        raise ApiError(503, "sync_failed", "База данных не настроена.")
    engine = _engines.get(url)
    if engine is None:
        # SQLAlchemy needs the driver in the scheme; Supabase gives postgresql://
        driver_url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(
            driver_url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"prepare_threshold": None},  # pooler in transaction mode
        )
        _engines[url] = engine
    return engine


async def get_repo(
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[Repository]:
    engine = _engine(settings)
    claims = json.dumps({**principal.claims, "role": "authenticated"})
    async with engine.connect() as conn, conn.begin():
        await conn.execute(text("set local role authenticated"))
        await conn.execute(text("select set_config('request.jwt.claims', :c, true)"), {"c": claims})
        yield PgRepository(conn)
