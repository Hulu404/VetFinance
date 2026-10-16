"""Reports of stage 3: P&L, norm, stock and the export of each (docs/api-contract.md, "Отчёты").

The routes only check the request and call app/services/reports.py; the numbers come from the engine.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.deps import NowDep, RepoDep
from app.errors import error_responses, not_found
from app.ratelimit import SlidingWindowLimiter, get_export_limiter
from app.schemas_reports import NormOut, PnlOut, StockIdleOut, StockOut
from app.services import reports as service
from app.services.report_export import build_export

router = APIRouter(prefix="/v1/reports", responses=error_responses(401, 403, 422))

MonthParam = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
REPORT_NAMES = ("pnl", "norm", "stock")
IDLE_PAGE_MAX = 50
IDLE_PAGE_DEFAULT = 10


@router.get("/pnl", response_model=PnlOut)
async def pnl(
    repo: RepoDep,
    now: NowDep,
    month: MonthParam = None,
    view: Literal["clinic", "direction"] = "clinic",
    as_of: date | None = None,
) -> PnlOut:
    window = await service.resolve_window(repo, now, month, as_of)
    return await service.build_pnl(repo, window, view)


@router.get("/norm", response_model=NormOut)
async def norm(
    repo: RepoDep, now: NowDep, month: MonthParam = None, as_of: date | None = None
) -> NormOut:
    window = await service.resolve_window(repo, now, month, as_of)
    return await service.build_norm(repo, window)


@router.get("/stock", response_model=StockOut)
async def stock(
    repo: RepoDep, now: NowDep, month: MonthParam = None, as_of: date | None = None
) -> StockOut:
    window = await service.resolve_window(repo, now, month, as_of)
    return await service.build_stock(repo, window)


@router.get("/stock/idle", response_model=StockIdleOut)
async def stock_idle(
    repo: RepoDep,
    now: NowDep,
    bucket: Literal["all", "60_89", "90_179", "180_plus"] = "all",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=IDLE_PAGE_MAX)] = IDLE_PAGE_DEFAULT,
    as_of: date | None = None,
) -> StockIdleOut:
    window = await service.resolve_window(repo, now, None, as_of)
    return await service.build_idle(repo, window, bucket, cursor, limit)


@router.get(
    "/{name}/export",
    responses={
        200: {
            "description": "Файл отчёта: те же цифры, что в JSON отчёта.",
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "application/pdf": {},
            },
        },
        **error_responses(404, 429),
    },
)
async def export(
    name: str,
    repo: RepoDep,
    now: NowDep,
    limiter: Annotated[SlidingWindowLimiter, Depends(get_export_limiter)],
    format: Annotated[Literal["xlsx", "pdf"], Query()],  # noqa: A002 (the name is the contract's)
    month: MonthParam = None,
    as_of: date | None = None,
) -> Response:
    if name not in REPORT_NAMES:
        raise not_found("Такого отчёта нет.")
    window = await service.resolve_window(repo, now, month, as_of)
    limiter.check((await repo.get_clinic()).id, now)
    file = await build_export(repo, window, name, format, now)
    return Response(
        file.content,
        media_type=file.media_type,
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )
