"""Shared FastAPI dependencies."""

from datetime import date, datetime
from typing import Annotated

from fastapi import Depends

from app.clock import clinic_today, get_now
from app.repo import Repository, get_repo

RepoDep = Annotated[Repository, Depends(get_repo)]
NowDep = Annotated[datetime, Depends(get_now)]


async def today_of(repo: Repository, now: datetime) -> date:
    """ "Today" in the time zone of the clinic."""
    return clinic_today(now, (await repo.get_clinic()).timezone)
