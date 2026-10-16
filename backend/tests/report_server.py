"""Loopback-only integration fixture: real API and exports, in-memory golden data.

Started by tests/run_reports_local.py, never by app.main. The small Auth fixture
exercises the frontend's Supabase client without using any external credentials.
This does not test Postgres or its RLS policies.
"""

import os
import uuid
from dataclasses import replace
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
from app.ratelimit import SlidingWindowLimiter, get_export_limiter
from app.repo import get_repo
from app.rows import ClinicRow
from app.settings import Settings, get_settings
from tests.conftest import NOW, SECRET
from tests.memory_repo import MemoryRepo
from tests.set04_loader import load_set04

if os.environ.get("VF_LOCAL_REPORT_TESTS") != "1":
    raise RuntimeError("Use tests/run_reports_local.py to start this test fixture")

PASSWORD = "local-reports-only"
USERS = {
    f"test-{letter}@vetfinance.test": str(uuid.UUID(int=n))
    for n, letter in enumerate(("a", "b", "e"), start=1)
}
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "apikey", "x-client-info", "x-supabase-api-version"],
)
repos: dict[str, MemoryRepo] = {}
for email, user_id in USERS.items():
    repo = (
        MemoryRepo(ClinicRow("b", "Пустая тестовая клиника", None, None, "Europe/Moscow", 0))
        if email.startswith("test-b")
        else load_set04()
    )
    if email.startswith("test-a"):
        # A has its own data and a distinct profit; only E is the unmodified golden clinic.
        repo.clinic = replace(repo.clinic, id="a", name="Тестовая клиника A")
        repo.charges = [replace(c, amount=c.amount + 100_000) for c in repo.charges]
    repos[user_id] = repo


async def repository(principal: Annotated[Principal, Depends(get_principal)]) -> MemoryRepo:
    if principal.user_id not in repos:
        raise forbidden()
    return repos[principal.user_id]


app.dependency_overrides[get_repo] = repository
app.dependency_overrides[get_settings] = lambda: settings
app.dependency_overrides[get_now] = lambda: NOW
# Bulk export tests share a clinic. The production 10/minute limit has separate unit coverage.
limiter = SlidingWindowLimiter(limit=1000)
app.dependency_overrides[get_export_limiter] = lambda: limiter


@app.post("/auth/v1/token")
async def login(body: dict[str, Any]) -> dict[str, Any]:
    email = body.get("email", "")
    if email not in USERS or body.get("password") != PASSWORD:
        raise HTTPException(status_code=400, detail="invalid_credentials")
    now = int(datetime.now(UTC).timestamp())
    user = {"id": USERS[email], "email": email, "aud": "authenticated", "role": "authenticated"}
    token = jwt.encode(
        {"sub": user["id"], "aud": "authenticated", "exp": now + 3600}, SECRET, algorithm="HS256"
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": now + 3600,
        "refresh_token": "local-unused",
        "user": user,
    }


@app.post("/auth/v1/logout", status_code=204)
async def logout() -> None:
    pass
