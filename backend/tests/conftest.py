from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated, Any

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.auth import Principal, get_principal
from app.main import create_app
from app.repo import ClinicRow, get_repo
from app.settings import Settings, get_settings
from engine.balance import AccountInput, TransactionInput

SECRET = "test-secret-with-enough-length-for-hs256-xx"


class FakeRepo:
    def __init__(self) -> None:
        self.clinic = ClinicRow("c1", "Клиника A", None, None, "Europe/Moscow", 0)
        self.accounts = [
            AccountInput("a1", "Расчётный счёт", "bank", 10_000_000, date(2000, 1, 1)),
            AccountInput("a2", "Касса", "cash", 500_000, date(2000, 1, 1)),
        ]
        self.transactions = [TransactionInput("a1", date(2001, 1, 1), -1_000_000, "ok", "bank")]

    async def get_clinic(self) -> ClinicRow:
        return self.clinic

    async def update_clinic(self, changes: dict[str, Any]) -> ClinicRow:
        self.clinic = ClinicRow(**{**self.clinic.__dict__, **changes})
        return self.clinic

    async def list_accounts(self) -> list[AccountInput]:
        return self.accounts

    async def list_transactions(self, as_of: date) -> list[TransactionInput]:
        return [t for t in self.transactions if t.date <= as_of]

    async def last_data_at(self) -> datetime | None:
        return datetime(2026, 9, 9, 4, 12, tzinfo=UTC)


def make_token(secret: str = SECRET, exp_delta: int = 3600, aud: str = "authenticated") -> str:
    now = int(datetime.now(UTC).timestamp())
    payload = {"sub": "11111111-1111-1111-1111-111111111111", "aud": aud, "exp": now + exp_delta}
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def client(repo: FakeRepo) -> Iterator[TestClient]:
    settings = Settings(supabase_jwt_secret=SecretStr(SECRET), cors_origins="http://localhost:5173")
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    # Same shape as the real get_repo: authentication stays active, only the DB is replaced.
    async def _repo(_: Annotated[Principal, Depends(get_principal)]) -> FakeRepo:
        return repo

    app.dependency_overrides[get_repo] = _repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
