"""Connections: Vetmanager and bank."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends

from app.deps import NowDep, RepoDep, today_of
from app.errors import error_responses, not_found
from app.integrations.vetmanager import VetmanagerApi, get_vetmanager_api
from app.jobs import SyncRunner, get_runner
from app.schemas_acq import (
    ConnectionOut,
    ConnectionsOut,
    RunStartedOut,
    VetmanagerBody,
    VetmanagerImportBody,
)
from app.secrets import SecretBox, get_secret_box
from app.services import connections
from app.settings import Settings, get_settings

router = APIRouter(prefix="/v1/connections", responses=error_responses(401, 403, 422))
SettingsDep = Annotated[Settings, Depends(get_settings)]
RunnerDep = Annotated[SyncRunner, Depends(get_runner)]


@router.get("", response_model=ConnectionsOut)
async def list_connections(repo: RepoDep, now: NowDep) -> ConnectionsOut:
    return await connections.list_connections(repo, now, await today_of(repo, now))


@router.put("/vetmanager", response_model=ConnectionOut)
async def save_vetmanager(
    body: VetmanagerBody,
    repo: RepoDep,
    now: NowDep,
    settings: SettingsDep,
    api: Annotated[VetmanagerApi, Depends(get_vetmanager_api)],
    box: Annotated[SecretBox, Depends(get_secret_box)],
    runner: RunnerDep,
    background: BackgroundTasks,
) -> ConnectionOut:
    return await connections.save_vetmanager(
        repo,
        address=body.address,
        key=body.key,
        suffixes=settings.vetmanager_host_suffixes or "vetmanager.ru",
        api=api,
        box=box,
        runner=runner,
        background=background,
        now=now,
        today=await today_of(repo, now),
    )


@router.post("/vetmanager/import", response_model=RunStartedOut, responses=error_responses(404))
async def import_vetmanager(
    body: VetmanagerImportBody, repo: RepoDep, now: NowDep, settings: SettingsDep, runner: RunnerDep
) -> RunStartedOut:
    if not settings.vetmanager_import_enabled:
        raise not_found()
    run = await connections.import_raw(
        repo, {k: dict(v) for k, v in body.entities.items()}, runner=runner, now=now
    )
    return RunStartedOut(run=run)


@router.post(
    "/{connection_id}/sync",
    response_model=RunStartedOut,
    status_code=202,
    responses=error_responses(404, 409, 429),
)
async def sync_connection(
    connection_id: UUID,
    repo: RepoDep,
    now: NowDep,
    runner: RunnerDep,
    background: BackgroundTasks,
) -> RunStartedOut:
    run = await connections.start_sync(
        repo, str(connection_id), runner=runner, background=background, now=now
    )
    return RunStartedOut(run=run)
