import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Annotated, Any

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.auth import Principal, get_principal
from app.clock import clinic_today, get_now
from app.integrations.vetmanager import OK, VetmanagerError, get_vetmanager_api
from app.jobs import get_runner
from app.main import create_app
from app.repo import get_repo
from app.rows import ClinicRow, SyncRunRow
from app.secrets import FernetBox, SecretBox, get_secret_box
from app.services.vm_sync import execute_sync
from app.settings import Settings, get_settings
from tests.memory_repo import MemoryRepo

SECRET = "test-secret-with-enough-length-for-hs256-xx"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
BANK_ID = str(uuid.UUID(int=0xA1))
CASH_ID = str(uuid.UUID(int=0xA2))


class FakeVetmanagerApi:
    """Answers `ping` and `fetch` from the test; never touches the network."""

    def __init__(self) -> None:
        self.ping_result = OK
        self.raw: Mapping[str, Mapping[str, Any]] = {}
        self.error: str | None = None
        self.calls: list[tuple[str, str]] = []  # (host, key hint) of every call; keys are not kept

    async def ping(self, host: str, key: str) -> str:
        self.calls.append((host, key[-4:]))
        return self.ping_result

    async def fetch(self, host: str, key: str, since: date) -> dict[str, dict[str, Any]]:
        self.calls.append((host, key[-4:]))
        if self.error:
            raise VetmanagerError(self.error)
        return {k: dict(v) for k, v in self.raw.items()}


class InlineRunner:
    """Runs a synchronisation in the same process over the in-memory repository."""

    def __init__(self, repo: MemoryRepo, api: FakeVetmanagerApi, box: SecretBox) -> None:
        self.repo, self.api, self.box = repo, api, box

    async def start(self, clinic_id: str, connection_id: str) -> SyncRunRow:
        return await self.repo.create_run(connection_id)

    async def run(
        self,
        clinic_id: str,
        connection_id: str,
        run_id: str,
        raw: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> SyncRunRow:
        today = clinic_today(NOW, self.repo.clinic.timezone)
        outcome = await execute_sync(
            self.repo,
            connection_id=connection_id,
            api=self.api,
            box_factory=lambda: self.box,
            today=today,
            raw=raw,
        )
        await self.repo.finish_run(run_id, outcome.status, outcome.error_code, outcome.counts)
        final = await self.repo.get_run(run_id)
        assert final is not None
        return final


def make_token(secret: str = SECRET, exp_delta: int = 3600, aud: str = "authenticated") -> str:
    now = int(datetime.now(UTC).timestamp())
    payload = {"sub": "11111111-1111-1111-1111-111111111111", "aud": aud, "exp": now + exp_delta}
    return jwt.encode(payload, secret, algorithm="HS256")


def seed_stage0(repo: MemoryRepo) -> None:
    bank = repo.add_account(
        id=BANK_ID, name="Расчётный счёт", kind="bank", opening_balance=10_000_000
    )
    repo.add_account(id=CASH_ID, name="Касса", kind="cash", opening_balance=500_000)
    repo.add_tx(bank.id, date(2001, 1, 1), -1_000_000)


@pytest.fixture
def repo() -> MemoryRepo:
    memory = MemoryRepo(ClinicRow("c1", "Клиника A", None, None, "Europe/Moscow", 0))
    memory.now = NOW
    memory.add_connections()
    seed_stage0(memory)
    return memory


@pytest.fixture
def api() -> FakeVetmanagerApi:
    return FakeVetmanagerApi()


@pytest.fixture
def box() -> SecretBox:
    return FernetBox(Fernet.generate_key().decode())


def build_app(repo: MemoryRepo, api: FakeVetmanagerApi, box: SecretBox) -> FastAPI:
    settings = Settings(
        supabase_jwt_secret=SecretStr(SECRET),
        cors_origins="http://localhost:5173",
        vetmanager_import_enabled=True,
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    # Same shape as the real get_repo: authentication stays active, only the DB is replaced.
    async def _repo(_: Annotated[Principal, Depends(get_principal)]) -> MemoryRepo:
        return repo

    app.dependency_overrides[get_repo] = _repo
    app.dependency_overrides[get_now] = lambda: NOW
    app.dependency_overrides[get_vetmanager_api] = lambda: api
    app.dependency_overrides[get_secret_box] = lambda: box
    runner = InlineRunner(repo, api, box)
    app.dependency_overrides[get_runner] = lambda: runner
    return app


@pytest.fixture
def client(repo: MemoryRepo, api: FakeVetmanagerApi, box: SecretBox) -> Iterator[TestClient]:
    app = build_app(repo, api, box)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
