"""Acquiring reconciliation."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import NowDep, RepoDep, today_of
from app.errors import error_responses
from app.schemas_acq import AcquiringDayOut, AcquiringOut, AcquiringRowOut, ReviewBody
from app.services import acquiring

router = APIRouter(prefix="/v1/acquiring", responses=error_responses(401, 403, 422))
MONTH_QUERY = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("/reconciliation", response_model=AcquiringOut)
async def reconciliation(
    repo: RepoDep, now: NowDep, month: Annotated[str, MONTH_QUERY]
) -> AcquiringOut:
    return await acquiring.reconciliation(repo, month, await today_of(repo, now))


@router.get("/days/{day}", response_model=AcquiringDayOut, responses=error_responses(404))
async def day_details(day: date, repo: RepoDep, now: NowDep) -> AcquiringDayOut:
    return await acquiring.day_details(repo, day, await today_of(repo, now))


@router.post("/days/{day}/review", response_model=AcquiringRowOut, responses=error_responses(404))
async def review_day(day: date, body: ReviewBody, repo: RepoDep, now: NowDep) -> AcquiringRowOut:
    return await acquiring.review_day(repo, day, body.note, await today_of(repo, now))
