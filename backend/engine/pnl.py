"""Profit and loss of one month (function 14) and its split into services and goods (function 18).

Pure functions: a snapshot of the data goes in, rows with breakdowns and sources come out. Money is integer
kopecks; percents are rounded only in engine.money. The identity
net_profit = revenue - variable - fixed - taxes - obligations holds to the kopeck. Rules: set04/README.md.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from engine.acquiring import CardPayment
from engine.balance import TransactionInput
from engine.dashboard_inputs import SaleInput
from engine.figure import Figure, FigureItem
from engine.money import format_pct, format_rub, pct_one_decimal, pct_to_tenths
from engine.report_facts import (
    ACQUIRING_LABEL,
    NO_CATEGORY,
    SOURCE_MANUAL,
    SOURCE_VETMANAGER,
    MonthFacts,
    Period,
    Totals,
    collect_facts,
    compute_totals,
    desc_sorted,
    partial_reasons,
    report_status,
    rub_items,
    sources_for,
    sources_of,
)
from engine.report_text import format_norm_range, lower_first, period_phrase
from engine.reports_inputs import (
    DIRECTION_GOODS,
    DIRECTION_SERVICES,
    TYPE_VARIABLE,
    BenchmarkInput,
    CategoryInput,
    ObligationChargeInput,
)
from engine.ru import format_day_month, month_prepositional

KIND_REVENUE = "revenue"
KIND_EXPENSE = "expense"
KIND_SUBTOTAL = "subtotal"
KIND_TOTAL = "total"
KIND_CHILD = "child"
WARNING_NO_OBLIGATIONS = "no_obligations"
NET_PROFIT_KEY = "net_profit"
DIRECTION_LABELS = {DIRECTION_SERVICES: "Услуги", DIRECTION_GOODS: "Товары"}
PAYROLL_LABEL = "ФОТ (оклады)"
OTHER_FIXED_LABEL = "Аренда и прочие постоянные"
OBLIGATIONS_LABEL = "Обязательства и амортизация"


@dataclass(frozen=True)
class PnlRow:
    key: str
    label: str
    kind: str
    amount: Figure
    share_pct: Figure | None = None  # None without revenue
    warning: str | None = None
    children: tuple["PnlRow", ...] | None = None


@dataclass(frozen=True)
class DirectionRow:
    direction: str
    label: str
    revenue: Figure
    revenue_share_pct: Figure
    direct_costs: Figure
    margin: Figure
    margin_pct: Figure


@dataclass(frozen=True)
class PnlResult:
    period: Period
    status: str
    partial_reasons: tuple[str, ...]
    headline: str | None
    rows: tuple[PnlRow, ...]
    unclassified: Figure
    unclassified_count: int
    directions: tuple[DirectionRow, ...] | None = None  # only compute_direction_view
    common_variable: Figure | None = None


# ------------------------------------------------------------------ figures
def _share(amount: int, revenue: int, sources: tuple[str, ...]) -> Figure:
    pct: Decimal = pct_one_decimal(amount, revenue)
    return Figure(
        value=pct,
        unit="pct",
        breakdown=(FigureItem("Сумма строки", amount), FigureItem("Выручка", revenue)),
        source=sources,
        note=f"{format_rub(amount)} ÷ {format_rub(revenue)}",
    )


def _row(
    key: str,
    label: str,
    kind: str,
    amount: Figure,
    revenue: int,
    *,
    warning: str | None = None,
    children: tuple[PnlRow, ...] | None = None,
) -> PnlRow:
    share = _share(int(amount.value), revenue, amount.source) if revenue else None
    return PnlRow(key, label, kind, amount, share, warning, children)


def _amount(
    value: int,
    breakdown: Sequence[tuple[str, int]],
    sources: tuple[str, ...],
    note: str,
    details: tuple[FigureItem, ...] = (),
) -> Figure:
    return Figure(
        value=value,
        unit="rub",
        breakdown=rub_items(breakdown),
        source=sources,
        note=note,
        details=details,
    )


def _revenue_note(facts: MonthFacts) -> str:
    return (
        f"Закрытые счета Ветменеджера за {period_phrase(facts)}, черновики не входят. "
        "Деньги на счетах (наличные, зачисления эквайринга) выручкой не считаются."
    )


def _fixed_note(facts: MonthFacts) -> str:
    text = "ФОТ (оклады) и аренда с прочими постоянными. Проценты врачам учтены в переменных."
    if facts.unclassified_count:
        text += (
            f" Операций без статьи: {facts.unclassified_count} на "
            f"{format_rub(facts.unclassified_amount)}, они идут строкой «{NO_CATEGORY}» "
            f"в «{OTHER_FIXED_LABEL}»."
        )
    return text


def _taxes_note(facts: MonthFacts) -> str:
    if facts.open and facts.as_of is not None:
        return (
            f"Только налоги и взносы, уже уплаченные к {format_day_month(facts.as_of)}. "
            "К концу месяца прибыль изменится."
        )
    return "Налоги и взносы, уплаченные в месяце."


def _obligations_note(facts: MonthFacts, totals: Totals) -> str:
    if not facts.charges:
        return (
            "Начислений обязательств нет: проценты по кредиту, лизинг и амортизация не заполнены, "
            "строка равна 0 ₽ и прибыль выше, чем будет с ними."
        )
    text = "Проценты по кредиту, лизинг и амортизация оборудования"
    text += " за весь месяц, в том числе идущий. " if facts.open else " за весь месяц. "
    if totals.obligation_payments:
        text += (
            f"Платёж по кредиту и лизингу {format_rub(totals.obligation_payments)} расходом "
            "не считается: основной долг не расход, проценты уже учтены здесь."
        )
    else:
        text += "Основной долг расходом не считается."
    return text


def _identity_note(totals: Totals) -> str:
    return (
        f"Выручка {format_rub(totals.revenue)} − переменные {format_rub(totals.variable)} − "
        f"постоянные {format_rub(totals.fixed)} − налоги и взносы {format_rub(totals.taxes)} − "
        f"обязательства и амортизация {format_rub(totals.obligations)} = "
        f"{format_rub(totals.net_profit)}."
    )


def _net_details(benchmark: BenchmarkInput | None) -> tuple[FigureItem, ...]:
    if benchmark is None:
        return ()
    items = []
    if benchmark.min_pct is not None:
        items.append(FigureItem("Норма отрасли, от", benchmark.min_pct, "pct"))
    if benchmark.max_pct is not None:
        items.append(FigureItem("Норма отрасли, до", benchmark.max_pct, "pct"))
    return tuple(items)


def _build_rows(
    facts: MonthFacts, totals: Totals, benchmark: BenchmarkInput | None
) -> tuple[PnlRow, ...]:
    revenue = totals.revenue
    var_names = [n for n, _ in totals.variable_lines]
    var_src = set(sources_for(facts, var_names)) | (
        {SOURCE_VETMANAGER} if facts.commission else set()
    )
    rev_src = {SOURCE_VETMANAGER} if revenue else set()
    pay_src = sources_for(facts, [n for n, _ in totals.payroll_lines])
    other_src = sources_for(facts, [n for n, _ in totals.other_fixed_lines])
    tax_src = sources_for(facts, [n for n, _ in totals.tax_lines])
    charge_src = {SOURCE_MANUAL} if facts.charges else set()
    all_src = rev_src | var_src | pay_src | other_src | tax_src | charge_src

    revenue_fig = _amount(
        revenue,
        [("Услуги", facts.revenue_services), ("Товары", facts.revenue_goods)],
        sources_of(rev_src),
        _revenue_note(facts),
    )
    variable_fig = _amount(
        totals.variable,
        totals.variable_lines,
        sources_of(var_src),
        "Деньги, заплаченные за месяц: закупка впрок целиком попадает в месяц оплаты. "
        "Комиссия эквайринга считается по тарифу клиники с оплат картой.",
    )
    marginal_fig = _amount(
        totals.marginal,
        [("Выручка", revenue), ("Переменные расходы", -totals.variable)],
        sources_of(rev_src, var_src),
        "Выручка минус переменные расходы.",
    )
    payroll_fig = _amount(
        totals.fixed_payroll,
        totals.payroll_lines,
        sources_of(pay_src),
        "Оклады врачей и персонала. Проценты врачам учтены в переменных расходах, "
        "полный ФОТ врачей показывает отчёт «Норма».",
    )
    other_fig = _amount(
        totals.fixed_other,
        totals.other_fixed_lines,
        sources_of(other_src),
        "Аренда, коммунальные услуги, реклама, прочие расходы кассы и операции без статьи.",
    )
    fixed_fig = _amount(
        totals.fixed,
        [(PAYROLL_LABEL, totals.fixed_payroll), (OTHER_FIXED_LABEL, totals.fixed_other)],
        sources_of(pay_src, other_src),
        _fixed_note(facts),
    )
    taxes_fig = _amount(totals.taxes, totals.tax_lines, sources_of(tax_src), _taxes_note(facts))
    obligations_fig = _amount(
        totals.obligations,
        totals.obligation_lines,
        (SOURCE_MANUAL,),
        _obligations_note(facts, totals),
    )
    net_fig = _amount(
        totals.net_profit,
        [
            ("Выручка", revenue),
            ("Переменные расходы", -totals.variable),
            ("Постоянные расходы", -totals.fixed),
            ("Налоги и взносы", -totals.taxes),
            (OBLIGATIONS_LABEL, -totals.obligations),
        ],
        sources_of(all_src),
        _identity_note(totals),
        _net_details(benchmark),
    )
    children = (
        _row("fixed_payroll", PAYROLL_LABEL, KIND_CHILD, payroll_fig, revenue),
        _row("fixed_other", OTHER_FIXED_LABEL, KIND_CHILD, other_fig, revenue),
    )
    return (
        _row("revenue", "Выручка", KIND_REVENUE, revenue_fig, revenue),
        _row("variable", "Переменные расходы", KIND_EXPENSE, variable_fig, revenue),
        _row("marginal_profit", "Маржинальная прибыль", KIND_SUBTOTAL, marginal_fig, revenue),
        _row("fixed", "Постоянные расходы", KIND_EXPENSE, fixed_fig, revenue, children=children),
        _row("taxes", "Налоги и взносы", KIND_EXPENSE, taxes_fig, revenue),
        _row(
            "obligations",
            OBLIGATIONS_LABEL,
            KIND_EXPENSE,
            obligations_fig,
            revenue,
            warning=None if facts.any_charges else WARNING_NO_OBLIGATIONS,
        ),
        _row(
            NET_PROFIT_KEY,
            "Чистая прибыль" if totals.net_profit >= 0 else "Чистый убыток",
            KIND_TOTAL,
            net_fig,
            revenue,
        ),
    )


# ------------------------------------------------------------------ headline
def _norm_phrase(totals: Totals, benchmark: BenchmarkInput | None) -> str:
    if benchmark is None or (benchmark.min_pct is None and benchmark.max_pct is None):
        return ""
    low = pct_to_tenths(benchmark.min_pct) if benchmark.min_pct is not None else None
    high = pct_to_tenths(benchmark.max_pct) if benchmark.max_pct is not None else None
    scaled = totals.net_profit * 1000
    if low is not None and scaled < low * totals.revenue:
        place = "ниже нормы"
    elif high is not None and scaled > high * totals.revenue:
        place = "выше нормы"
    else:
        place = "в норме"
    return f", {place} {format_norm_range(benchmark.min_pct, benchmark.max_pct)}"


def _headline(facts: MonthFacts, totals: Totals, benchmark: BenchmarkInput | None) -> str:
    when = (
        f"К {format_day_month(facts.as_of)}"
        if facts.open and facts.as_of is not None
        else f"В {month_prepositional(facts.first_day.month)}"
    )
    expenses = totals.variable + totals.fixed + totals.taxes + totals.obligations
    if totals.revenue == 0:
        return f"{when} выручки нет, расходы {format_rub(expenses)}."
    if totals.net_profit < 0:
        return f"{when} расходы были больше выручки на {format_rub(-totals.net_profit)}."
    share = format_pct(pct_one_decimal(totals.net_profit, totals.revenue))
    start = f"{when} клиника заработала" if facts.open else "Клиника заработала"
    phrase = "" if facts.open else _norm_phrase(totals, benchmark)
    return f"{start} {format_rub(totals.net_profit)} чистыми: {share}% выручки{phrase}."


# ------------------------------------------------------------------ public functions
@dataclass(frozen=True)
class _Computed:
    facts: MonthFacts
    totals: Totals
    result: PnlResult


def _compute(
    categories: Sequence[CategoryInput],
    transactions: Sequence[TransactionInput],
    sales: Sequence[SaleInput],
    card_payments: Sequence[CardPayment],
    charges: Sequence[ObligationChargeInput],
    month: date,
    acquiring_rate_bp: int,
    bank_covered_to: date | None,
    as_of: date | None,
    benchmarks: Sequence[BenchmarkInput],
) -> _Computed:
    facts = collect_facts(
        categories, transactions, sales, card_payments, charges, month,
        acquiring_rate_bp, bank_covered_to, as_of,
    )  # fmt: skip
    totals = compute_totals(facts)
    benchmark = next((b for b in benchmarks if b.key == NET_PROFIT_KEY), None)
    empty = (
        totals.revenue == 0
        and totals.variable + totals.fixed + totals.taxes == 0
        and not facts.charges
    )
    reasons = (
        ()
        if empty
        else partial_reasons(
            facts, check_obligations=True, check_benchmarks=False, has_benchmarks=True
        )
    )
    unclassified = Figure(
        value=facts.unclassified_amount,
        unit="rub",
        breakdown=(
            (FigureItem(NO_CATEGORY, facts.unclassified_amount),)
            if facts.unclassified_amount
            else ()
        ),
        source=sources_of(facts.unclassified_sources),
        note=(
            f"Операции без статьи ({facts.unclassified_count}) учтены в «{OTHER_FIXED_LABEL}». "
            "Разнесите их на экране «Транзакции», и отчёт уточнится."
            if facts.unclassified_count
            else "Операций без статьи в месяце нет."
        ),
    )
    result = PnlResult(
        period=facts.period,
        status=report_status(reasons, empty=empty),
        partial_reasons=reasons,
        headline=None if empty else _headline(facts, totals, benchmark),
        rows=_build_rows(facts, totals, benchmark),
        unclassified=unclassified,
        unclassified_count=facts.unclassified_count,
    )
    return _Computed(facts, totals, result)


def compute_pnl(
    categories: Sequence[CategoryInput],
    transactions: Sequence[TransactionInput],
    sales: Sequence[SaleInput],
    card_payments: Sequence[CardPayment],
    charges: Sequence[ObligationChargeInput],
    month: date,
    acquiring_rate_bp: int,
    bank_covered_to: date | None = None,
    as_of: date | None = None,
    benchmarks: Sequence[BenchmarkInput] = (),
) -> PnlResult:
    """P&L of the calendar month of `month` (the 1st). `as_of` inside the month makes it a running month."""
    return _compute(
        categories, transactions, sales, card_payments, charges, month, acquiring_rate_bp,
        bank_covered_to, as_of, benchmarks,
    ).result  # fmt: skip


# ------------------------------------------------------------------ services and goods
def _direction_row(facts: MonthFacts, totals: Totals, direction: str, revenue: int) -> DirectionRow:
    label = DIRECTION_LABELS[direction]
    costs = [
        (c.name, c.amount)
        for c in facts.costs
        if c.type == TYPE_VARIABLE and c.category is not None and c.category.direction == direction
    ]
    cost = sum(v for _, v in costs)
    cost_src = sources_for(facts, [n for n, _ in costs])
    rev_src = (SOURCE_VETMANAGER,) if revenue else (SOURCE_MANUAL,)
    margin = revenue - cost
    clinic_revenue = totals.revenue
    margin_pct = (
        pct_one_decimal(margin, revenue) if revenue else Decimal(0)
    )  # no revenue of the direction: no share
    share_pct = pct_one_decimal(revenue, clinic_revenue) if clinic_revenue else Decimal(0)
    return DirectionRow(
        direction=direction,
        label=label,
        revenue=Figure(
            value=revenue,
            unit="rub",
            breakdown=(FigureItem(label, revenue),),
            source=rev_src,
            note=f"Закрытые счета Ветменеджера, строки вида «{lower_first(label)}».",
        ),
        revenue_share_pct=Figure(
            value=share_pct,
            unit="pct",
            breakdown=(
                FigureItem("Выручка направления", revenue),
                FigureItem("Выручка клиники", clinic_revenue),
            ),
            source=rev_src,
            note=(
                f"{format_rub(revenue)} ÷ {format_rub(clinic_revenue)}"
                if clinic_revenue
                else "Выручки за месяц нет, доля не считается."
            ),
        ),
        direct_costs=Figure(
            value=cost,
            unit="rub",
            breakdown=rub_items(desc_sorted(costs)),
            source=sources_of(cost_src),
            note="Переменные статьи, закреплённые за направлением. Постоянные расходы к "
            "направлениям не относятся.",
        ),
        margin=Figure(
            value=margin,
            unit="rub",
            breakdown=(
                FigureItem("Выручка", revenue),
                FigureItem("Прямые расходы", -cost, delta=True),
            ),
            source=sources_of(rev_src, cost_src),
            note="Выручка направления минус его прямые расходы.",
        ),
        margin_pct=Figure(
            value=margin_pct,
            unit="pct",
            breakdown=(FigureItem("Маржа", margin), FigureItem("Выручка направления", revenue)),
            source=rev_src,
            note=(
                f"{format_rub(margin)} ÷ {format_rub(revenue)}"
                if revenue
                else "Выручки направления нет, маржа в процентах не считается."
            ),
        ),
    )


def _common_variable(facts: MonthFacts) -> Figure:
    lines = [
        (c.name, c.amount)
        for c in facts.costs
        if c.type == TYPE_VARIABLE and (c.category is None or c.category.direction is None)
    ]
    if facts.commission:
        lines.append((ACQUIRING_LABEL, facts.commission))
    sources = set(sources_for(facts, [n for n, _ in lines]))
    if facts.commission:
        sources.add(SOURCE_VETMANAGER)
    return Figure(
        value=sum(v for _, v in lines),
        unit="rub",
        breakdown=rub_items(desc_sorted(lines)),
        source=sources_of(sources),
        note="Комиссия эквайринга по тарифу клиники с оплат картой: её нельзя отнести ни к услугам, "
        "ни к товарам.",
    )


def compute_direction_view(
    categories: Sequence[CategoryInput],
    transactions: Sequence[TransactionInput],
    sales: Sequence[SaleInput],
    card_payments: Sequence[CardPayment],
    charges: Sequence[ObligationChargeInput],
    month: date,
    acquiring_rate_bp: int,
    bank_covered_to: date | None = None,
    as_of: date | None = None,
    benchmarks: Sequence[BenchmarkInput] = (),
) -> PnlResult:
    """The P&L plus the split into services and goods: a bridge from the margin of the directions to the profit."""
    computed = _compute(
        categories, transactions, sales, card_payments, charges, month, acquiring_rate_bp,
        bank_covered_to, as_of, benchmarks,
    )  # fmt: skip
    facts, totals = computed.facts, computed.totals
    return replace(
        computed.result,
        directions=(
            _direction_row(facts, totals, DIRECTION_SERVICES, facts.revenue_services),
            _direction_row(facts, totals, DIRECTION_GOODS, facts.revenue_goods),
        ),
        common_variable=_common_variable(facts),
    )
