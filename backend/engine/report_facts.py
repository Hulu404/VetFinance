"""Facts of one report month shared by the P&L and the norm report (stage 3).

Rules (tests/golden/set04/README.md, "Правила расчёта"): revenue is the closed invoices of Vetmanager; costs are the
money that left the bank and the cash desk in the month (cash method, a purchase in advance counts in the month of
payment); the acquiring commission is calculated from card payments per day; obligations and amortization are
accrued for the whole calendar month. A running month (`as_of` inside it) cuts revenue, card payments and
operations at `as_of` inclusive.
"""

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from engine.acquiring import CardPayment
from engine.balance import TransactionInput
from engine.dashboard_inputs import LINE_SERVICE, SALE_EXEC, SaleInput
from engine.figure import FigureItem, ordered_sources
from engine.money import apply_rate_bp
from engine.reports_inputs import (
    TYPE_FIXED,
    TYPE_OBLIGATION,
    TYPE_TAX,
    TYPE_VARIABLE,
    CategoryInput,
    ObligationChargeInput,
)

NO_CATEGORY = "Без статьи"
ACQUIRING_LABEL = "Комиссия эквайринга"
SOURCE_VETMANAGER = "vetmanager"
SOURCE_MANUAL = "manual"
KIND_OUT = "out"
STATUS_DUPLICATE = "duplicate"
STATUS_CHECK = "check"
SHORT_PERIOD_DAYS = 7  # a running month with fewer days of data is a partial report

PERIOD_CLOSED = "closed"
PERIOD_OPEN = "open"
STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_EMPTY = "empty"

REASON_NO_VETMANAGER = "no_vetmanager"
REASON_BANK_GAP = "bank_gap"
REASON_SHORT_PERIOD = "short_period"
REASON_NO_OBLIGATIONS = "no_obligations"
REASON_NO_BENCHMARK = "no_benchmark"


@dataclass(frozen=True)
class Period:
    month: str  # 'YYYY-MM'
    status: str  # closed | open
    to: date | None  # open: the last day of the data (as_of); closed: None
    first_month: str | None  # month of the earliest sale or transaction


@dataclass(frozen=True)
class CostLine:
    """Money paid in the month under one article (or without one)."""

    name: str
    type: str  # effective type: an operation without an article, or an unknown one, is a fixed cost
    category: CategoryInput | None
    amount: int
    sources: frozenset[str]


@dataclass(frozen=True)
class MonthFacts:
    first_day: date
    last_day: date  # last day of the calendar month
    as_of: date | None
    period: Period
    revenue_services: int
    revenue_goods: int
    commission: int
    costs: tuple[CostLine, ...]  # every article of the month, by name
    unclassified_count: int
    unclassified_amount: int
    unclassified_sources: frozenset[str]
    charges: tuple[
        ObligationChargeInput, ...
    ]  # accrued for this month, by amount descending then name
    any_charges: bool  # the clinic has at least one accrual in any month
    bank_covered_to: date | None

    @property
    def revenue(self) -> int:
        return self.revenue_services + self.revenue_goods

    @property
    def open(self) -> bool:
        return self.period.status == PERIOD_OPEN

    @property
    def data_last_day(self) -> date:
        """Last day the numbers cover: `as_of` for a running month, the end of the month otherwise."""
        return self.as_of if self.open and self.as_of is not None else self.last_day


def month_bounds(month: date) -> tuple[date, date]:
    first = month.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def last_closed_month(as_of: date) -> date:
    """First day of the last month that has ended by the end of `as_of` (30 Sep gives September, 15 Sep August)."""
    first, last = month_bounds(as_of)
    if as_of >= last:
        return first
    previous = first.replace(day=1) - date.resolution
    return previous.replace(day=1)


def desc_sorted(items: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    """By amount descending, ties by name: the order of every breakdown by articles."""
    return sorted(items, key=lambda kv: (-kv[1], kv[0]))


def rub_items(pairs: Iterable[tuple[str, int]]) -> tuple[FigureItem, ...]:
    return tuple(FigureItem(label, value) for label, value in pairs)


def sources_of(*groups: Iterable[str]) -> tuple[str, ...]:
    """Sources in the stable order; `manual` when nothing contributed (the figure is empty or typed by hand)."""
    found: set[str] = set()
    for group in groups:
        found.update(group)
    return ordered_sources(found - {"calc"}) or (SOURCE_MANUAL,)


def _first_month(
    transactions: Sequence[TransactionInput], sales: Sequence[SaleInput]
) -> str | None:
    days = [t.date for t in transactions] + [s.date for s in sales]
    return month_key(min(days)) if days else None


def _revenue(sales: Sequence[SaleInput], first: date, last: date) -> tuple[int, int]:
    services = goods = 0
    for sale in sales:
        if sale.status != SALE_EXEC or not first <= sale.date <= last:
            continue
        for line in sale.lines:
            if line.kind == LINE_SERVICE:
                services += line.amount
            else:
                goods += line.amount
    return services, goods


def _commission(card_payments: Sequence[CardPayment], first: date, last: date, rate_bp: int) -> int:
    """Rounded per day, as on the acquiring reconciliation screen."""
    per_day: dict[date, int] = {}
    for payment in card_payments:
        if first <= payment.date <= last:
            per_day[payment.date] = per_day.get(payment.date, 0) + payment.amount
    return sum(apply_rate_bp(total, rate_bp) for total in per_day.values())


def _costs(
    categories: dict[str, CategoryInput],
    transactions: Sequence[TransactionInput],
    first: date,
    last: date,
) -> tuple[tuple[CostLine, ...], int, int, frozenset[str]]:
    amounts: dict[str, int] = {}
    sources: dict[str, set[str]] = {}
    unclassified: list[int] = []
    for t in transactions:
        if t.kind != KIND_OUT or t.status == STATUS_DUPLICATE or not first <= t.date <= last:
            continue
        has_article = bool(t.category) and t.status != STATUS_CHECK
        name = t.category if has_article and t.category else NO_CATEGORY
        amounts[name] = amounts.get(name, 0) - t.amount
        sources.setdefault(name, set()).add(t.source)
        if name == NO_CATEGORY:
            unclassified.append(-t.amount)
    lines = []
    for name in sorted(amounts):
        category = categories.get(name)
        lines.append(
            CostLine(
                name=name,
                type=category.type if category else TYPE_FIXED,
                category=category,
                amount=amounts[name],
                sources=frozenset(sources[name]),
            )
        )
    return (
        tuple(lines),
        len(unclassified),
        sum(unclassified),
        frozenset(sources.get(NO_CATEGORY, set())),
    )


def collect_facts(
    categories: Sequence[CategoryInput],
    transactions: Sequence[TransactionInput],
    sales: Sequence[SaleInput],
    card_payments: Sequence[CardPayment],
    charges: Sequence[ObligationChargeInput],
    month: date,
    acquiring_rate_bp: int,
    bank_covered_to: date | None,
    as_of: date | None,
) -> MonthFacts:
    first, last_day = month_bounds(month)
    running = as_of is not None and as_of < last_day
    last = as_of if running and as_of is not None else last_day
    if as_of is not None and as_of < first:
        last = first - date.resolution  # the month has not started: nothing is counted
    services, goods = _revenue(sales, first, last)
    costs, unclassified_count, unclassified_amount, unclassified_sources = _costs(
        {c.name: c for c in sorted(categories, key=lambda c: c.name)}, transactions, first, last
    )
    key = month_key(first)
    accrued = sorted(
        (c for c in charges if c.month == key), key=lambda c: (-c.amount, c.name, c.obligation_id)
    )
    return MonthFacts(
        first_day=first,
        last_day=last_day,
        as_of=as_of,
        period=Period(
            month=key,
            status=PERIOD_OPEN if running else PERIOD_CLOSED,
            to=as_of if running else None,
            first_month=_first_month(transactions, sales),
        ),
        revenue_services=services,
        revenue_goods=goods,
        commission=_commission(card_payments, first, last, acquiring_rate_bp),
        costs=costs,
        unclassified_count=unclassified_count,
        unclassified_amount=unclassified_amount,
        unclassified_sources=unclassified_sources,
        charges=tuple(accrued),
        any_charges=bool(charges),
        bank_covered_to=bank_covered_to,
    )


def partial_reasons(
    facts: MonthFacts, *, check_obligations: bool, check_benchmarks: bool, has_benchmarks: bool
) -> tuple[str, ...]:
    """Why a report is partial, in the order of the screens: no Vetmanager, bank gap, short period, no obligations."""
    reasons: list[str] = []
    if facts.revenue == 0:
        reasons.append(REASON_NO_VETMANAGER)
    covered = facts.bank_covered_to
    if covered is None or covered < min(facts.data_last_day, facts.last_day):
        reasons.append(REASON_BANK_GAP)
    if facts.open and (facts.data_last_day - facts.first_day).days + 1 < SHORT_PERIOD_DAYS:
        reasons.append(REASON_SHORT_PERIOD)
    if check_obligations and not facts.any_charges:
        reasons.append(REASON_NO_OBLIGATIONS)
    if check_benchmarks and not has_benchmarks:
        reasons.append(REASON_NO_BENCHMARK)
    return tuple(reasons)


def report_status(reasons: Sequence[str], *, empty: bool) -> str:
    if empty:
        return STATUS_EMPTY
    return STATUS_PARTIAL if reasons else STATUS_OK


@dataclass(frozen=True)
class Totals:
    """Amounts of the P&L lines of one month; the identity net = revenue - variable - fixed - taxes - obligations."""

    revenue: int
    variable_lines: tuple[tuple[str, int], ...]  # articles and the commission, amount descending
    variable: int
    payroll_lines: tuple[tuple[str, int], ...]
    other_fixed_lines: tuple[tuple[str, int], ...]
    fixed_payroll: int
    fixed_other: int
    fixed: int
    tax_lines: tuple[tuple[str, int], ...]
    taxes: int
    obligation_lines: tuple[tuple[str, int], ...]
    obligations: int
    obligation_payments: (
        int  # bank payments on loans and leases: not a cost, only named in the note
    )
    marginal: int
    net_profit: int


def compute_totals(facts: MonthFacts) -> Totals:
    variable = [(c.name, c.amount) for c in facts.costs if c.type == TYPE_VARIABLE]
    if facts.commission:
        variable.append((ACQUIRING_LABEL, facts.commission))
    fixed = [c for c in facts.costs if c.type == TYPE_FIXED]
    payroll = [(c.name, c.amount) for c in fixed if c.category is not None and c.category.payroll]
    other = [(c.name, c.amount) for c in fixed if c.category is None or not c.category.payroll]
    taxes = [(c.name, c.amount) for c in facts.costs if c.type == TYPE_TAX]
    obligations = [(c.name, c.amount) for c in facts.charges]
    payments = sum(c.amount for c in facts.costs if c.type == TYPE_OBLIGATION)
    revenue = facts.revenue
    var_total = sum(v for _, v in variable)
    fixed_payroll, fixed_other = sum(v for _, v in payroll), sum(v for _, v in other)
    tax_total = sum(v for _, v in taxes)
    obligation_total = sum(v for _, v in obligations)
    marginal = revenue - var_total
    fixed_total = fixed_payroll + fixed_other
    return Totals(
        revenue=revenue,
        variable_lines=tuple(desc_sorted(variable)),
        variable=var_total,
        payroll_lines=tuple(desc_sorted(payroll)),
        other_fixed_lines=tuple(desc_sorted(other)),
        fixed_payroll=fixed_payroll,
        fixed_other=fixed_other,
        fixed=fixed_total,
        tax_lines=tuple(desc_sorted(taxes)),
        taxes=tax_total,
        obligation_lines=tuple(desc_sorted(obligations)),
        obligations=obligation_total,
        obligation_payments=payments,
        marginal=marginal,
        net_profit=marginal - fixed_total - tax_total - obligation_total,
    )


def sources_for(facts: MonthFacts, names: Iterable[str]) -> frozenset[str]:
    wanted = set(names)
    found: set[str] = set()
    for line in facts.costs:
        if line.name in wanted:
            found |= line.sources
    return frozenset(found)
