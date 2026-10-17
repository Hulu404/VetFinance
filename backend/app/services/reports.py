"""Reports of stage 3: P&L, norm, stock. Loads the snapshot, calls the engine, maps the result to the API model.

The export files are built from the same API models (app/services/report_export.py), never from a second
calculation.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.deps import today_of
from app.errors import validation_fields
from app.repo import Repository
from app.reports_out import idle_item_out, norm_out, pnl_out, stock_out
from app.rows import CategoryRow
from app.schemas import figure_out
from app.schemas_reports import IdleItemOut, NormOut, PnlOut, StockIdleOut, StockOut
from app.services import planning
from engine.acquiring import CardPayment
from engine.balance import TransactionInput
from engine.dashboard_inputs import SaleInput
from engine.money import TURNOVER_WINDOW_DAYS
from engine.norm import compute_norm
from engine.pnl import PnlResult, compute_direction_view, compute_pnl
from engine.report_facts import last_closed_month, month_bounds, month_key
from engine.reports_inputs import (
    BenchmarkInput,
    CategoryInput,
    ObligationChargeInput,
)
from engine.stock import StockResult, compute_stock, idle_total_figure

EARLIEST = date(2000, 1, 1)  # the snapshot of the P&L starts at the beginning of the history
IDLE_BUCKETS = ("all", "60_89", "90_179", "180_plus")


@dataclass(frozen=True)
class Window:
    as_of: date
    month: date  # first day of the report month


@dataclass(frozen=True)
class ReportData:
    categories: list[CategoryInput]
    transactions: list[TransactionInput]
    sales: list[SaleInput]
    card_payments: list[CardPayment]
    charges: list[ObligationChargeInput]
    benchmarks: list[BenchmarkInput]
    acquiring_rate_bp: int
    bank_covered_to: date | None


def category_inputs(rows: list[CategoryRow]) -> list[CategoryInput]:
    return [
        CategoryInput(
            name=c.name,
            type=c.type,
            norm_key=c.norm_key,
            direction=c.direction,
            norm_min_pct=None if c.norm_min_pct is None else Decimal(str(c.norm_min_pct)),
            norm_max_pct=None if c.norm_max_pct is None else Decimal(str(c.norm_max_pct)),
            payroll=c.payroll,
        )
        for c in rows
    ]


async def resolve_window(
    repo: Repository, now: datetime, month: str | None, as_of: date | None
) -> Window:
    """`as_of` defaults to today of the clinic; `month` to the last month that has ended by `as_of`."""
    today = as_of or await today_of(repo, now)
    if month is None:
        return Window(today, last_closed_month(today))
    try:
        first = date(int(month[:4]), int(month[5:7]), 1)
    except ValueError as exc:
        raise validation_fields({"month": "invalid"}) from exc
    if month > month_key(today):
        raise validation_fields({"month": "in_future"})
    return Window(today, first)


async def _load(repo: Repository, window: Window) -> ReportData:
    return ReportData(
        categories=category_inputs(await repo.list_categories()),
        transactions=await repo.list_transactions(window.as_of),
        sales=await repo.list_sales(EARLIEST, window.as_of),
        card_payments=[CardPayment(r.date, r.amount) for r in await repo.list_card_payments()],
        charges=await planning.charges_for_report(repo, window.month),
        benchmarks=await repo.list_benchmarks(),
        acquiring_rate_bp=await repo.get_acquiring_rate_bp(),
        bank_covered_to=await repo.bank_covered_to(),
    )


async def _pnl_result(repo: Repository, window: Window, *, directions: bool) -> PnlResult:
    data = await _load(repo, window)
    compute = compute_direction_view if directions else compute_pnl
    return compute(
        data.categories, data.transactions, data.sales, data.card_payments, data.charges,
        window.month, data.acquiring_rate_bp, data.bank_covered_to, window.as_of,
        data.benchmarks,
    )  # fmt: skip


async def build_pnl(repo: Repository, window: Window, view: str) -> PnlOut:
    result = await _pnl_result(repo, window, directions=view == "direction")
    return pnl_out(result, view=view, as_of=window.as_of, data_as_of=await repo.last_data_at())


async def build_norm(repo: Repository, window: Window) -> NormOut:
    data = await _load(repo, window)
    first, last = month_bounds(window.month)
    result = compute_norm(
        data.categories, data.transactions, data.sales, data.card_payments, data.charges,
        await repo.list_writeoffs(first, last), data.benchmarks, window.month,
        data.acquiring_rate_bp, data.bank_covered_to, window.as_of,
    )  # fmt: skip
    return norm_out(result, as_of=window.as_of, data_as_of=await repo.last_data_at())


async def _stock_result(repo: Repository, window: Window) -> StockResult:
    pnl = await _pnl_result(repo, window, directions=False)
    first, last = month_bounds(window.month)
    since = window.as_of - timedelta(days=TURNOVER_WINDOW_DAYS - 1)
    return compute_stock(
        await repo.list_stock_items(),
        await repo.list_stock_batches(),
        await repo.list_writeoffs(first, last),
        await repo.list_stock_consumption(since, window.as_of),
        window.as_of,
        month=window.month,
        month_revenue=int(pnl.rows[0].amount.value),
        benchmarks=await repo.list_benchmarks(),
    )


async def build_stock(repo: Repository, window: Window) -> StockOut:
    return stock_out(await _stock_result(repo, window), data_as_of=await repo.last_data_at())


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdecimal():
        raise validation_fields({"cursor": "invalid"})
    return int(cursor)


async def build_idle(
    repo: Repository, window: Window, bucket: str, cursor: str | None, limit: int
) -> StockIdleOut:
    offset = _offset(cursor)
    result = await _stock_result(repo, window)
    rows = [i for i in result.frozen_items if bucket in ("all", i.bucket)]
    page = rows[offset : offset + limit]
    return StockIdleOut(
        items=[idle_item_out(i) for i in page],
        next_cursor=str(offset + limit) if offset + limit < len(rows) else None,
        total=figure_out(idle_total_figure(result.frozen_items, bucket)),
    )


async def build_full_idle(repo: Repository, window: Window) -> list[IdleItemOut]:
    """Every position without movement, for the export (no pages)."""
    return [idle_item_out(i) for i in (await _stock_result(repo, window)).frozen_items]
