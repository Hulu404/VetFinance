"""Loopback-only fixture for the stage 5 contract tests: real API, in-memory data (no Postgres, no RLS).

Clinic G holds golden set 6 (rooms mode), clinic A its copy without rooms (mode "by doctors"), clinic B is empty (tests/golden/set06). Started by hand:
    VF_LOCAL_PRICING_TESTS=1 backend/.venv/Scripts/python -m uvicorn tests.pricing_server:app --port 8765
Tokens: `python -m tests.pricing_server` prints `export VF_TOKEN_A=...` lines for the contract tests.
"""

import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import SecretStr

from app.auth import Principal, get_principal
from app.clock import get_now
from app.errors import forbidden
from app.main import create_app
from app.repo import get_repo
from app.rows import ClinicRow
from app.settings import Settings, get_settings
from tests.conftest import SECRET
from tests.memory_repo import MemoryRepo
from tests.set06_loader import load_set06

USERS = {letter: str(uuid.UUID(int=n)) for n, letter in enumerate(("a", "b", "g"), start=1)}
# The browser run (tests/run_pricing_local.py) signs in through the small Auth fixture below.
PASSWORD = "local-pricing-only"
# "Today" of the stand is the as_of of golden set 6.
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def token(user_id: str) -> str:
    exp = int(datetime.now(UTC).timestamp()) + 3600
    return jwt.encode(
        {"sub": user_id, "aud": "authenticated", "exp": exp}, SECRET, algorithm="HS256"
    )


def _clinic_a() -> MemoryRepo:
    """Clinic A has its own copy of the data of set 6, so that the shape and write tests have services to work on."""
    repo = load_set06()
    repo.clinic = ClinicRow("a", "Тестовая клиника A", None, None, "Europe/Moscow", 0)
    # The usual case of life: Vetmanager gives no rooms, the screen works "by doctors" with the hours of reception.
    repo.rooms = []
    repo.room_bookings = []
    return repo


if __name__ == "__main__":
    for letter, user_id in USERS.items():
        sys.stdout.write(f"export VF_TOKEN_{letter.upper()}={token(user_id)}\n")
    raise SystemExit(0)

if os.environ.get("VF_LOCAL_PRICING_TESTS") != "1":
    raise RuntimeError("Set VF_LOCAL_PRICING_TESTS=1: this fixture is for local contract runs only")

settings = Settings(
    _env_file=None,
    database_url=SecretStr(""),
    supabase_url="",
    supabase_jwt_secret=SecretStr(SECRET),
    cors_origins="http://127.0.0.1:5173,http://localhost:5173",
)
app = create_app(settings)
# The local Auth fixture also receives Supabase-js public client headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "apikey",
        "x-client-info",
        "x-supabase-api-version",
    ],
)
repos = {
    USERS["a"]: _clinic_a(),
    USERS["b"]: MemoryRepo(ClinicRow("b", "Пустая клиника", None, None, "Europe/Moscow", 0)),
    USERS["g"]: load_set06(),
}


async def repository(principal: Annotated[Principal, Depends(get_principal)]) -> MemoryRepo:
    if principal.user_id not in repos:
        raise forbidden()
    return repos[principal.user_id]


app.dependency_overrides[get_repo] = repository
app.dependency_overrides[get_settings] = lambda: settings
app.dependency_overrides[get_now] = lambda: NOW


@app.post("/auth/v1/token")
async def login(body: dict[str, Any]) -> dict[str, Any]:
    letter = str(body.get("email", "")).removeprefix("test-").removesuffix("@vetfinance.test")
    if letter not in USERS or body.get("password") != PASSWORD:
        raise HTTPException(status_code=400, detail="invalid_credentials")
    now = int(datetime.now(UTC).timestamp())
    user = {
        "id": USERS[letter],
        "email": body["email"],
        "aud": "authenticated",
        "role": "authenticated",
    }
    return {
        "access_token": token(USERS[letter]),
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": now + 3600,
        "refresh_token": "local-unused",
        "user": user,
    }


@app.post("/auth/v1/logout", status_code=204)
async def logout() -> None:
    pass
