"""Background synchronisation runs.

A run is created and committed first (so the client sees "running" at once), then executed after the
response over a service connection bound to one clinic (RLS is bypassed there, every query filters by
the clinic id). The result of the run is committed together with the data it loaded; if anything fails,
the data are rolled back and the run is recorded as failed in a separate transaction.
"""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol

from fastapi import Depends

from app.clock import clinic_today
from app.integrations.vetmanager import UNKNOWN, VetmanagerApi, get_vetmanager_api
from app.pg_repo import PgRepository
from app.repo import service_engine
from app.rows import SyncRunRow
from app.secrets import box_from_settings
from app.services.vm_sync import execute_sync
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class SyncRunner(Protocol):
    async def start(self, clinic_id: str, connection_id: str) -> SyncRunRow: ...

    async def run(
        self,
        clinic_id: str,
        connection_id: str,
        run_id: str,
        raw: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> SyncRunRow: ...


class DbSyncRunner:
    def __init__(self, settings: Settings, api: VetmanagerApi) -> None:
        self._settings = settings
        self._api = api

    async def start(self, clinic_id: str, connection_id: str) -> SyncRunRow:
        async with service_engine(self._settings).begin() as conn:
            return await PgRepository(conn, clinic_id, service=True).create_run(connection_id)

    async def run(
        self,
        clinic_id: str,
        connection_id: str,
        run_id: str,
        raw: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> SyncRunRow:
        engine = service_engine(self._settings)
        try:
            async with engine.begin() as conn:
                repo = PgRepository(conn, clinic_id, service=True)
                today = clinic_today(datetime.now(UTC), (await repo.get_clinic()).timezone)
                outcome = await execute_sync(
                    repo,
                    connection_id=connection_id,
                    api=self._api,
                    box_factory=lambda: box_from_settings(self._settings),
                    today=today,
                    raw=raw,
                )
                await repo.finish_run(run_id, outcome.status, outcome.error_code, outcome.counts)
        except Exception:  # noqa: BLE001 - the run must end in a final state
            logger.exception("vetmanager sync failed (run %s)", run_id)
            async with engine.begin() as conn:
                await PgRepository(conn, clinic_id, service=True).finish_run(
                    run_id, "failed", UNKNOWN, None
                )
        async with engine.begin() as conn:
            final = await PgRepository(conn, clinic_id, service=True).get_run(run_id)
        if final is None:
            raise RuntimeError("sync run disappeared")
        return final


def get_runner(
    settings: Annotated[Settings, Depends(get_settings)],
    api: Annotated[VetmanagerApi, Depends(get_vetmanager_api)],
) -> SyncRunner:
    return DbSyncRunner(settings, api)
