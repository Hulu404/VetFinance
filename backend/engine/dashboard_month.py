"""Month block of the dashboard: revenue, expenses, profit, margin, visits, average check.

Revenue comes from closed Vetmanager invoices, expenses from the money of bank and cash (not a P&L: the
report of stage 3 does that). Rules: tests/golden/set03/README.md (section 4).
"""

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from engine.balance import TransactionInput
from engine.dashboard_balance import KIND_OUT, SOURCE_MANUAL
from engine.dashboard_inputs import (
    LINE_GOOD,
    LINE_SERVICE,
    SALE_EXEC,
    NormsInput,
    SaleInput,
    VisitInput,
)
from engine.figure import Figure, FigureItem, ordered_sources
from engine.money import div_round, format_pct, format_rub, pct_one_decimal
from engine.ru import format_days_range, plural

SOURCE_VETMANAGER = "vetmanager"
NO_CATEGORY = "Без статьи"
NO_DOCTOR = "Без врача"


@dataclass(frozen=True)
class MonthBlock:
    days_passed: int
    days_total: int
    revenue: Figure
    expenses: Figure
    profit: Figure
    profit_margin_pct: Figure | None
    visits: Figure
    avg_check: Figure | None


@dataclass(frozen=True)
class SalesTotals:
    services: int
    goods: int
    invoices: int

    @property
    def revenue(self) -> int:
        return self.services + self.goods


def month_start(day: date) -> date:
    return day.replace(day=1)


def sales_totals(sales: Sequence[SaleInput], first: date, last: date) -> SalesTotals:
    """Closed invoices dated within [first, last]; drafts are not revenue."""
    services = goods = invoices = 0
    for sale in sales:
        if sale.status != SALE_EXEC or not first <= sale.date <= last:
            continue
        invoices += 1
        for line in sale.lines:
            if line.kind == LINE_SERVICE:
                services += line.amount
            elif line.kind == LINE_GOOD:
                goods += line.amount
    return SalesTotals(services, goods, invoices)


def count_visits(visits: Sequence[VisitInput], first: date, last: date) -> dict[str, int]:
    per_doctor: dict[str, int] = {}
    for visit in visits:
        if first <= visit.date <= last:
            name = visit.doctor or NO_DOCTOR
            per_doctor[name] = per_doctor.get(name, 0) + 1
    return per_doctor


def expense_operations(
    counted: Sequence[TransactionInput], first: date, last: date
) -> list[TransactionInput]:
    return [t for t in counted if t.kind == KIND_OUT and first <= t.date <= last]


def _sorted_items(amounts: dict[str, int], unit: str) -> tuple[FigureItem, ...]:
    ranked = sorted(amounts.items(), key=lambda kv: (-kv[1], kv[0]))
    return tuple(FigureItem(label, value, unit) for label, value in ranked)


def _revenue(totals: SalesTotals, period: str, passed: int, total_days: int) -> Figure:
    word = plural(totals.invoices, "закрытый счёт", "закрытых счёта", "закрытых счетов")
    return Figure(
        value=totals.revenue,
        unit="rub",
        breakdown=(FigureItem("Услуги", totals.services), FigureItem("Товары", totals.goods)),
        source=(SOURCE_VETMANAGER,) if totals.invoices else (SOURCE_MANUAL,),
        note=(
            f"Закрытые счета Ветменеджера за {period} ({passed} из {total_days} дн.): "
            f"{totals.invoices} {word}. Черновики счетов не входят."
        ),
    )


def _expenses(operations: Sequence[TransactionInput], period: str) -> Figure:
    by_category: dict[str, int] = {}
    for t in operations:
        key = t.category or NO_CATEGORY
        by_category[key] = by_category.get(key, 0) - t.amount
    return Figure(
        value=sum(by_category.values()),
        unit="rub",
        breakdown=_sorted_items(by_category, "rub"),
        source=ordered_sources({t.source for t in operations}) or (SOURCE_MANUAL,),
        note=(
            f"Деньги, ушедшие с банковских счетов и из кассы за {period}, по статьям; "
            "дубли и переводы между своими счетами не входят. Закупка впрок попадает в расходы "
            "целиком, в месяц покупки."
        ),
    )


def _profit(revenue: Figure, expenses: Figure, period: str) -> Figure:
    sources = {*revenue.source, *expenses.source}
    return Figure(
        value=int(revenue.value) - int(expenses.value),
        unit="rub",
        breakdown=(
            FigureItem("Выручка", int(revenue.value)),
            FigureItem("Расходы", -int(expenses.value)),
        ),
        source=ordered_sources(sources),
        note=(
            f"Выручка минус уже заплаченные расходы за {period}. Налоги и амортизацию считает "
            "отчёт «Прибыль и убытки» при закрытии месяца, поэтому число может отличаться "
            "от чистой прибыли отчёта."
        ),
    )


def _margin(profit: Figure, revenue: Figure, norms: NormsInput) -> Figure | None:
    if int(revenue.value) <= 0:
        return None
    pct: Decimal = pct_one_decimal(int(profit.value), int(revenue.value))
    return Figure(
        value=pct,
        unit="pct",
        breakdown=(
            FigureItem("Прибыль", int(profit.value)),
            FigureItem("Выручка", int(revenue.value)),
        ),
        source=profit.source,
        note=(
            f"Прибыль {format_rub(int(profit.value))} ÷ выручка {format_rub(int(revenue.value))} = "
            f"{format_pct(pct)}%. Норма клиники: не ниже {norms.margin_min_pct}%."
        ),
    )


def _visits(per_doctor: dict[str, int], period: str) -> Figure:
    items = _sorted_items(per_doctor, "count") or (FigureItem("Нет приёмов", 0, "count"),)
    return Figure(
        value=sum(per_doctor.values()),
        unit="count",
        breakdown=items,
        source=(SOURCE_VETMANAGER,),
        note=f"Приёмы по данным Ветменеджера за {period}, по врачам.",
    )


def _avg_check(totals: SalesTotals, period: str) -> Figure | None:
    if totals.invoices == 0:
        return None
    return Figure(
        value=div_round(totals.revenue, totals.invoices),
        unit="rub",
        breakdown=(
            FigureItem("Выручка", totals.revenue),
            FigureItem("Счетов", totals.invoices, "count"),
        ),
        source=(SOURCE_VETMANAGER,),
        note=f"Выручка {format_rub(totals.revenue)} ÷ {totals.invoices} закрытых счетов за {period}.",
    )


def compute_month_block(
    counted: Sequence[TransactionInput],
    sales: Sequence[SaleInput],
    visits: Sequence[VisitInput],
    norms: NormsInput,
    as_of: date,
) -> MonthBlock:
    start = month_start(as_of)
    days_total = calendar.monthrange(as_of.year, as_of.month)[1]
    period = f"{format_days_range(start, as_of)} {as_of.year}"
    totals = sales_totals(sales, start, as_of)
    per_doctor = count_visits(visits, start, as_of)
    revenue = _revenue(totals, period, as_of.day, days_total)
    expenses = _expenses(expense_operations(counted, start, as_of), period)
    profit = _profit(revenue, expenses, period)
    avg_check = _avg_check(totals, period)
    details: list[FigureItem] = []
    if avg_check is not None:
        details.append(FigureItem("Средний чек", int(avg_check.value)))
    if avg_check is not None or per_doctor:
        details.append(FigureItem("Приёмов", sum(per_doctor.values()), "count"))
    revenue_with_details = Figure(
        revenue.value,
        revenue.unit,
        revenue.breakdown,
        revenue.source,
        revenue.note,
        details=tuple(details),
    )
    return MonthBlock(
        days_passed=as_of.day,
        days_total=days_total,
        revenue=revenue_with_details,
        expenses=expenses,
        profit=profit,
        profit_margin_pct=_margin(profit, revenue, norms),
        visits=_visits(per_doctor, period),
        avg_check=avg_check,
    )
