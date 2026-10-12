"""Dashboard engine (stage 2): one pure function from a snapshot of data to every number of the screen.

No network, no randomness, no mutation of the inputs, no dependence on the order of the rows. Every figure
carries a breakdown and a source (rule 4 of CLAUDE.md). Rounding only through `engine.money`.
Rules and expected numbers: tests/golden/set03.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from engine.balance import AccountInput, TransactionInput
from engine.dashboard_advice import Advice, AdviceContext, Why, build_advice
from engine.dashboard_balance import (
    BalanceBlock,
    TrendInfo,
    TrendPoint,
    compute_balance_block,
    counted_transactions,
)
from engine.dashboard_inputs import (
    NormsInput,
    SaleInput,
    SaleLineInput,
    VisitInput,
)
from engine.dashboard_month import MonthBlock, compute_month_block, month_start

__all__ = [
    "AccountInput",
    "Advice",
    "BalanceBlock",
    "DashboardResult",
    "MonthBlock",
    "NormsInput",
    "SaleInput",
    "SaleLineInput",
    "TransactionInput",
    "TrendInfo",
    "TrendPoint",
    "VisitInput",
    "Why",
    "compute_dashboard",
    "history_start",
]


@dataclass(frozen=True)
class DashboardResult:
    as_of: date
    balance: BalanceBlock
    month: MonthBlock
    balance_trend: tuple[TrendPoint, ...]
    balance_trend_info: TrendInfo
    advice: tuple[Advice, ...]


def history_start(as_of: date) -> date:
    """First day of the previous month: sales and visits before it are not needed (revenue_drop rule)."""
    return month_start(month_start(as_of) - timedelta(days=1))


def compute_dashboard(
    accounts: Sequence[AccountInput],
    transactions: Sequence[TransactionInput],
    sales: Sequence[SaleInput],
    visits: Sequence[VisitInput],
    norms: NormsInput,
    as_of: date,
) -> DashboardResult:
    """Everything the Рабочий стол shows, as of the end of `as_of` (inclusive)."""
    balance, trend, trend_info = compute_balance_block(accounts, transactions, as_of)
    counted = counted_transactions(accounts, transactions, as_of)
    month = compute_month_block(counted, sales, visits, norms, as_of)
    first_day = min((a.opening_date for a in accounts), default=None)
    advice: tuple[Advice, ...] = ()
    if first_day is not None and first_day <= as_of:
        advice = build_advice(
            AdviceContext(
                as_of=as_of,
                first_day=first_day,
                month=month,
                runway=balance.runway_days,
                counted=counted,
                sales=sales,
                visits=visits,
                norms=norms,
            )
        )
    return DashboardResult(as_of, balance, month, trend, trend_info, advice)
