"""Rule-based advice of the dashboard (functions 3-4). No model: texts are templates filled from the engine result.

The `why` block is structured so that a model can later produce the same shape: summary, numbered steps with the
numbers of the calculation, and the sources. Rules and thresholds: tests/golden/set03/README.md (section 5).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from engine.balance import TransactionInput
from engine.dashboard_inputs import NormsInput, SaleInput, VisitInput
from engine.dashboard_month import (
    MonthBlock,
    count_visits,
    expense_operations,
    month_start,
    sales_totals,
)
from engine.figure import Figure
from engine.money import div_round, format_pct, format_rub, pct_one_decimal
from engine.ru import format_days_range, plural

MIN_DATA_DAYS = 7  # no advice with less history
MIN_MONTH_DAY = 7  # month rules need a week of the month
RUNWAY_ALERT_DAYS = 14
RUNWAY_WARNING_DAYS = 30
REVENUE_DROP_PCT = 85  # revenue below 85% of the same days of the previous month
MAX_ADVICE = 5
SEVERITY_RANK = {"alert": 0, "warning": 1, "good": 2}
SOURCE_NAMES = {
    "bank": "выписки банка",
    "vetmanager": "Ветменеджер",
    "bot": "ввод из мессенджера",
    "manual": "ручной ввод",
}


@dataclass(frozen=True)
class Why:
    summary: str
    steps: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Advice:
    id: str
    severity: str  # "alert" | "warning" | "good"
    icon: str
    title: str
    text: str
    why: Why


@dataclass(frozen=True)
class AdviceContext:
    as_of: date
    first_day: date
    month: MonthBlock
    runway: Figure | None
    counted: Sequence[TransactionInput]
    sales: Sequence[SaleInput]
    visits: Sequence[VisitInput]
    norms: NormsInput


def _sources_line(prefix: str, sources: Sequence[str]) -> str:
    names = ", ".join(SOURCE_NAMES.get(s, s) for s in sources)
    return f"{prefix}: {names}"


def _days(n: int) -> str:
    return f"{n} {plural(n, 'день', 'дня', 'дней')}"


def _cash_runway(ctx: AdviceContext) -> Advice | None:
    runway = ctx.runway
    if runway is None or int(runway.value) >= RUNWAY_WARNING_DAYS:
        return None
    days = int(runway.value)
    balance, burn, daily, window = (int(b.value) for b in runway.breakdown)
    severity = "alert" if days < RUNWAY_ALERT_DAYS else "warning"
    return Advice(
        id="cash_runway",
        severity=severity,
        icon="🩸",
        title=f"Денег хватит примерно на {_days(days)}",
        text=(
            f"Остаток {format_rub(balance)} при расходах в среднем {format_rub(daily)} в день. "
            "Платежи вперёд здесь не учтены: их покажет платёжный календарь."
        ),
        why=Why(
            summary=(
                f"Остатка {format_rub(balance)} хватит на {_days(days)} при расходах "
                f"{format_rub(daily)} в день (среднее за {_days(window)})."
            ),
            steps=(
                f"Остаток на всех счетах, банк и касса: {format_rub(balance)}.",
                f"Расходы за последние {_days(window)}: {format_rub(burn)} "
                "(переводы между своими счетами и дубли не входят).",
                f"В среднем в день: {format_rub(daily)} ({format_rub(burn)} ÷ {window}).",
                f"Остаток делим на расход в день и берём целые дни вниз: {_days(days)}.",
            ),
            sources=(
                _sources_line("Остатки счетов и операции", runway.source),
                f"Расчёт по среднему расходу за {_days(window)}",
            ),
        ),
    )


def _drugs(ctx: AdviceContext) -> int:
    for item in ctx.month.expenses.breakdown:
        if item.label == ctx.norms.drugs_category:
            return item.value
    return 0


def _drug_share(ctx: AdviceContext) -> Advice | None:
    revenue = int(ctx.month.revenue.value)
    drugs = _drugs(ctx)
    norms = ctx.norms
    if revenue <= 0 or drugs * 100 <= norms.drugs_max_pct * revenue:
        return None
    start = month_start(ctx.as_of)
    purchases = [
        t
        for t in expense_operations(ctx.counted, start, ctx.as_of)
        if t.category == norms.drugs_category
    ]
    biggest = min(purchases, key=lambda t: (t.amount, t.date))
    limit = div_round(revenue * norms.drugs_max_pct, 100)
    excess = drugs - limit
    share = format_pct(pct_one_decimal(drugs, revenue))
    period = format_days_range(start, ctx.as_of)
    return Advice(
        id="drug_share",
        severity="warning",
        icon="💊",
        title=f"Препараты съедают {share}% выручки при норме до {norms.drugs_max_pct}%",
        text=(
            f"За месяц на препараты ушло {format_rub(drugs)} из выручки {format_rub(revenue)}. "
            f"Это на {format_rub(excess)} больше нормы клиники."
        ),
        why=Why(
            summary=(
                f"Доля препаратов {share}% выручки, норма клиники до {norms.drugs_max_pct}%: "
                f"сверх нормы {format_rub(excess)}."
            ),
            steps=(
                f"Статья «{norms.drugs_category}» за {period}: {format_rub(drugs)}.",
                f"Выручка за тот же период: {format_rub(revenue)}; доля препаратов {share}%.",
                f"Норма клиники до {norms.drugs_max_pct}% выручки, это {format_rub(limit)}; "
                f"превышение {format_rub(excess)}.",
                f"Самая крупная закупка месяца {format_rub(-biggest.amount)} от "
                f"{format_days_range(biggest.date, biggest.date)}. Закупка впрок целиком попадает "
                "в расходы месяца, поэтому доля может снизиться в следующие недели.",
            ),
            sources=(
                "Операции банка и кассы по статье расходов",
                "Закрытые счета Ветменеджера (выручка)",
            ),
        ),
    )


def _revenue_drop(ctx: AdviceContext) -> Advice | None:
    revenue = int(ctx.month.revenue.value)
    start = month_start(ctx.as_of)
    prev_start = month_start(start - timedelta(days=1))
    if revenue <= 0 or prev_start < ctx.first_day:
        return None
    prev_end = min(prev_start + timedelta(days=ctx.as_of.day - 1), start - timedelta(days=1))
    prior = sales_totals(ctx.sales, prev_start, prev_end).revenue
    if prior <= 0 or revenue * 100 >= prior * REVENUE_DROP_PCT:
        return None
    diff = prior - revenue
    drop = format_pct(pct_one_decimal(diff, prior))
    visits_now = int(ctx.month.visits.value)
    visits_before = sum(count_visits(ctx.visits, prev_start, prev_end).values())
    now_period = format_days_range(start, ctx.as_of)
    then_period = format_days_range(prev_start, prev_end)
    return Advice(
        id="revenue_drop",
        severity="warning",
        icon="📈",
        title=f"Выручка на {drop}% ниже, чем за те же дни прошлого месяца",
        text=(
            f"За {now_period} выручка {format_rub(revenue)}, за {then_period} было "
            f"{format_rub(prior)}. Приёмов: {visits_now} против {visits_before}."
        ),
        why=Why(
            summary=(
                f"Выручка за {now_period} {format_rub(revenue)} против {format_rub(prior)} "
                f"за {then_period}: ниже на {format_rub(diff)} ({drop}%)."
            ),
            steps=(
                f"Выручка за {now_period}: {format_rub(revenue)} (закрытые счета Ветменеджера).",
                f"Выручка за те же дни прошлого месяца, {then_period}: {format_rub(prior)}.",
                f"Разница {format_rub(diff)}, это {drop}% от прошлой выручки.",
                f"Приёмов за эти дни: {visits_now} против {visits_before} в прошлом месяце.",
            ),
            sources=("Закрытые счета и приёмы Ветменеджера",),
        ),
    )


def _margin_ok(ctx: AdviceContext) -> Advice | None:
    margin = ctx.month.profit_margin_pct
    if margin is None:
        return None
    revenue, profit = int(ctx.month.revenue.value), int(ctx.month.profit.value)
    expenses = int(ctx.month.expenses.value)
    minimum = ctx.norms.margin_min_pct
    if margin.value < minimum:
        return None
    pct = format_pct(pct_one_decimal(profit, revenue))
    period = format_days_range(month_start(ctx.as_of), ctx.as_of)
    return Advice(
        id="margin_ok",
        severity="good",
        icon="📈",
        title=f"Рентабельность месяца {pct}%, не ниже нормы {minimum}%",
        text=(
            f"За {period} прибыль {format_rub(profit)} при выручке {format_rub(revenue)}. "
            "Налоги и амортизацию учтёт отчёт при закрытии месяца."
        ),
        why=Why(
            summary=(
                f"Прибыль {format_rub(profit)} от выручки {format_rub(revenue)}: рентабельность "
                f"{pct}%, нижняя граница нормы {minimum}%."
            ),
            steps=(
                f"Выручка за {period}: {format_rub(revenue)}.",
                f"Расходы за тот же период: {format_rub(expenses)}.",
                f"Прибыль, выручка минус расходы: {format_rub(profit)}.",
                f"Рентабельность {pct}% (прибыль ÷ выручка), нижняя граница нормы {minimum}%.",
            ),
            sources=(
                "Закрытые счета Ветменеджера (выручка)",
                "Операции банка и кассы (расходы)",
            ),
        ),
    )


_RULES = (_cash_runway, _drug_share, _revenue_drop, _margin_ok)
_MONTH_RULES = {_drug_share, _revenue_drop, _margin_ok}


def build_advice(ctx: AdviceContext) -> tuple[Advice, ...]:
    """Advice sorted by severity (alert, warning, good), then by the order of the rules; at most five."""
    if (ctx.as_of - ctx.first_day).days + 1 < MIN_DATA_DAYS:
        return ()
    found: list[Advice] = []
    for rule in _RULES:
        if rule in _MONTH_RULES and ctx.as_of.day < MIN_MONTH_DAY:
            continue
        advice = rule(ctx)
        if advice is not None:
            found.append(advice)
    ranked = sorted(found, key=lambda a: SEVERITY_RANK[a.severity])  # stable: rule order inside
    return tuple(ranked[:MAX_ADVICE])
