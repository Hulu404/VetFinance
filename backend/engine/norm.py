"""Norm report (function 15): the shares of the cost groups in the revenue against the norm of clinics of this size.

Pure functions. Money is integer kopecks, shares have one decimal, borders are whole tenths of a percent, so a
share and its deviation can be checked by hand. Rules: tests/golden/set04/README.md (rules 13-18).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from engine.acquiring import CardPayment
from engine.balance import TransactionInput
from engine.dashboard_inputs import SaleInput
from engine.figure import Figure, FigureItem
from engine.money import (
    bound_amount,
    deviation_pp,
    format_pct,
    format_rub,
    pct_one_decimal,
    pct_to_tenths,
)
from engine.report_facts import (
    ACQUIRING_LABEL,
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
from engine.report_text import NUMBER_WORDS, format_bound, lower_first
from engine.reports_inputs import (
    REASON_EXPIRED,
    TYPE_FIXED,
    TYPE_TAX,
    TYPE_VARIABLE,
    BenchmarkInput,
    CategoryInput,
    ObligationChargeInput,
    WriteoffInput,
)
from engine.ru import format_day_month, plural

STATUS_OK = "ok"
STATUS_ABOVE = "above"
STATUS_BELOW = "below"
STATUS_NO_NORM = "no_norm"
TONE_GOOD = "good"
TONE_WARN = "warn"
TONE_BAD = "bad"
TONE_NEUTRAL = "neutral"
KIND_EXPENSE = "expense"
KIND_OTHER = "other"
KIND_PROFIT = "profit"
SOURCE_INDUSTRY = "industry"
SOURCE_CLINIC = "clinic"
KEY_ACQUIRING = "acquiring"
KEY_WRITEOFF = "writeoff"
KEY_NET_PROFIT = "net_profit"
MEMO_KEYS = frozenset({KEY_WRITEOFF})  # shown for reference, outside the 100% of the revenue
OTHER_LABEL = "Остальные статьи"
NET_PROFIT_LABEL = "Чистая прибыль"
WRITEOFF_PART_LABEL = "Списано по сроку годности"
INDUSTRY_NOTE = (
    "Норма отрасли для ветклиник на 2–6 врачей. Оценка по прототипу, "
    "заменим данными отраслевых опросов."
)
CLINIC_NOTE = "Норма вашей клиники, заданная в настройках статьи."
OPEN_MONTH_NOTE = " Закупки впрок и оплата аренды могут попасть в месяц позже, доли ещё поменяются."


@dataclass(frozen=True)
class NormBounds:
    min_pct: Decimal | None
    max_pct: Decimal | None
    source: str  # industry | clinic
    breakdown: tuple[FigureItem, ...]  # the borders in roubles at the revenue of the month
    note: str


@dataclass(frozen=True)
class NormShare:
    """A row of the norm report as shown in a running month: the share and the norm borders, no rating."""

    key: str
    label: str
    kind: str  # expense | other | profit
    memo: bool
    norm: NormBounds | None
    actual_pct: Figure


@dataclass(frozen=True)
class NormItem(NormShare):
    """A rated row (closed month)."""

    status: str  # ok | above | below | no_norm
    tone: str  # good | warn | bad | neutral
    deviation_pp: Figure | None
    deviation_rub: Figure | None


@dataclass(frozen=True)
class NormResult:
    period: Period
    status: str
    partial_reasons: tuple[str, ...]
    headline: str | None
    items: tuple[NormShare, ...]  # NormItem for a closed month, NormShare for a running one


@dataclass(frozen=True)
class _Resolved:
    min_pct: Decimal | None
    max_pct: Decimal | None
    source: str


def _resolve_norm(benchmark: BenchmarkInput, cats: Sequence[CategoryInput]) -> _Resolved | None:
    """The clinic's own norm of an article beats the industry one."""
    for c in sorted(cats, key=lambda c: c.name):
        if c.norm_min_pct is not None or c.norm_max_pct is not None:
            return _Resolved(c.norm_min_pct, c.norm_max_pct, SOURCE_CLINIC)
    if benchmark.min_pct is None and benchmark.max_pct is None:
        return None
    return _Resolved(benchmark.min_pct, benchmark.max_pct, SOURCE_INDUSTRY)


def _status(amount: int, revenue: int, norm: _Resolved | None) -> tuple[str, int | None]:
    """(status, border in tenths of a percent the amount is measured against)."""
    if norm is None:
        return STATUS_NO_NORM, None
    scaled = amount * 1000
    if norm.max_pct is not None and scaled > pct_to_tenths(norm.max_pct) * revenue:
        return STATUS_ABOVE, pct_to_tenths(norm.max_pct)
    if norm.min_pct is not None and scaled < pct_to_tenths(norm.min_pct) * revenue:
        return STATUS_BELOW, pct_to_tenths(norm.min_pct)
    return STATUS_OK, None


def _tone(status: str, profit: bool) -> str:
    if status == STATUS_NO_NORM:
        return TONE_NEUTRAL
    if status == STATUS_OK:
        return TONE_GOOD
    if status == STATUS_ABOVE:
        return TONE_GOOD if profit else TONE_BAD
    return TONE_BAD if profit else TONE_WARN


def _bounds(norm: _Resolved, revenue: int) -> NormBounds:
    borders = []
    if norm.min_pct is not None:
        borders.append(
            FigureItem(
                f"Нижняя граница, {format_pct(norm.min_pct)}%",
                bound_amount(revenue, pct_to_tenths(norm.min_pct)),
            )
        )
    if norm.max_pct is not None:
        borders.append(
            FigureItem(
                f"Верхняя граница, {format_pct(norm.max_pct)}%",
                bound_amount(revenue, pct_to_tenths(norm.max_pct)),
            )
        )
    note = CLINIC_NOTE if norm.source == SOURCE_CLINIC else INDUSTRY_NOTE
    return NormBounds(norm.min_pct, norm.max_pct, norm.source, tuple(borders), note)


def _reserve(norm: _Resolved, amount: int, revenue: int, profit: bool) -> tuple[FigureItem, ...]:
    """Roubles left before the nearest border in the direction that matters (in norm)."""
    if profit and norm.min_pct is not None:
        low = bound_amount(revenue, pct_to_tenths(norm.min_pct))
        return (FigureItem("Запас до нижней границы", amount - low),)
    if not profit and norm.max_pct is not None:
        high = bound_amount(revenue, pct_to_tenths(norm.max_pct))
        return (FigureItem("Запас до верхней границы", high - amount),)
    return ()


def _deviations(
    status: str,
    border: int | None,
    amount: int,
    revenue: int,
    share: Decimal,
    norm: _Resolved,
    profit: bool,
) -> tuple[Figure, Figure]:
    if status == STATUS_OK or border is None:
        return (
            Figure(
                value=Decimal(0),
                unit="pp",
                breakdown=(FigureItem("Ваша доля", share, "pct"),),
                source=("calc",),
                note="Доля в пределах нормы.",
                delta=True,
            ),
            Figure(
                value=0,
                unit="rub",
                breakdown=(),
                source=("calc",),
                note="Расход в пределах нормы." if not profit else "Прибыль в пределах нормы.",
                delta=True,
                details=_reserve(norm, amount, revenue, profit),
            ),
        )
    above = status == STATUS_ABOVE
    word = "выше" if above else "ниже"
    border_pct = norm.max_pct if above else norm.min_pct
    border_rub = bound_amount(revenue, border)
    shift = deviation_pp(amount, border, revenue)
    pp = Figure(
        value=shift,
        unit="pp",
        breakdown=(
            FigureItem("Ваша доля", share, "pct"),
            FigureItem("Граница нормы", border_pct or Decimal(0), "pct"),
            FigureItem("Отклонение", shift, "pp", delta=True),
        ),
        source=("calc",),
        note=f"Доля {word} границы нормы на {format_pct(abs(shift))} п.п.",
        delta=True,
    )
    rub = Figure(
        value=amount - border_rub,
        unit="rub",
        breakdown=(
            FigureItem("Ваша прибыль" if profit else "Ваш расход", amount),
            FigureItem(f"Граница нормы, {format_pct(border_pct or Decimal(0))}%", -border_rub),
        ),
        source=("calc",),
        note=(
            f"Сумма {word} границы нормы. Граница считается от выручки месяца "
            f"{format_rub(revenue)}."
        ),
        delta=True,
    )
    return pp, rub


def _item(
    *,
    key: str,
    label: str,
    kind: str,
    memo: bool,
    amount: int,
    parts: Sequence[tuple[str, int]],
    sources: tuple[str, ...],
    revenue: int,
    resolved: _Resolved | None,
    open_month: bool,
) -> NormShare:
    share: Decimal = pct_one_decimal(amount, revenue)
    note = f"{format_rub(amount)} ÷ {format_rub(revenue)} = {format_pct(share)}%"
    if memo:
        note += ". Справочно: в сумму долей не входит."
    if open_month:
        note += ("" if memo else ".") + OPEN_MONTH_NOTE
    actual = Figure(
        value=share,
        unit="pct",
        breakdown=rub_items(parts),
        source=sources,
        note=note,
        details=(FigureItem("Выручка месяца", revenue),),
    )
    bounds = _bounds(resolved, revenue) if resolved is not None else None
    if open_month:  # the norm is not assessed until the month is over
        return NormShare(key, label, kind, memo, bounds, actual)
    if resolved is None:
        return NormItem(
            key, label, kind, memo, None, actual, STATUS_NO_NORM, TONE_NEUTRAL, None, None
        )
    profit = kind == KIND_PROFIT
    status, border = _status(amount, revenue, resolved)
    pp_fig, rub_fig = _deviations(status, border, amount, revenue, share, resolved, profit)
    return NormItem(
        key, label, kind, memo, bounds, actual, status, _tone(status, profit), pp_fig, rub_fig
    )


def _expired_writeoffs(writeoffs: Sequence[WriteoffInput], facts: MonthFacts) -> int:
    return sum(
        w.amount
        for w in writeoffs
        if w.reason == REASON_EXPIRED and facts.first_day <= w.date <= facts.data_last_day
    )


def _group_items(
    benchmarks: Sequence[BenchmarkInput],
    categories: Sequence[CategoryInput],
    facts: MonthFacts,
    writeoffs: Sequence[WriteoffInput],
    revenue: int,
) -> tuple[list[NormShare], int]:
    """Items of the groups with a norm in the order of `benchmarks.sort`; the sum of the groups outside the memo."""
    paid = {c.name: c.amount for c in facts.costs}
    items: list[NormShare] = []
    grouped = 0
    for bench in sorted(benchmarks, key=lambda b: (b.sort, b.key)):
        if bench.key == KEY_NET_PROFIT or bench.kind == KIND_PROFIT:
            continue
        cats = [c for c in categories if c.norm_key == bench.key]
        sources: set[str]
        if bench.key == KEY_ACQUIRING:
            amount, parts = facts.commission, [(ACQUIRING_LABEL, facts.commission)]
            sources = {SOURCE_VETMANAGER} if facts.commission else set()
        elif bench.key == KEY_WRITEOFF:
            amount = _expired_writeoffs(writeoffs, facts)
            parts = [(WRITEOFF_PART_LABEL, amount)]
            sources = {SOURCE_VETMANAGER} if amount else set()
        else:
            parts = desc_sorted((c.name, paid.get(c.name, 0)) for c in cats)
            amount = sum(v for _, v in parts)
            sources = set(sources_for(facts, [n for n, _ in parts]))
        memo = bench.key in MEMO_KEYS
        if not memo:
            grouped += amount
        items.append(
            _item(
                key=bench.key,
                label=bench.label,
                kind=KIND_EXPENSE,
                memo=memo,
                amount=amount,
                parts=parts,
                sources=sources_of(sources),
                revenue=revenue,
                resolved=_resolve_norm(bench, cats),
                open_month=facts.open,
            )
        )
    return items, grouped


def _other_item(
    facts: MonthFacts, totals: Totals, handled: set[str], categories: Sequence[CategoryInput],
    revenue: int,
) -> tuple[NormShare, int]:  # fmt: skip
    """Everything the P&L spends that has no norm row, so that groups + other + profit = revenue."""
    keyed = {c.name for c in categories if c.norm_key in handled}
    parts = [
        (c.name, c.amount)
        for c in facts.costs
        if c.type in (TYPE_VARIABLE, TYPE_FIXED, TYPE_TAX) and c.name not in keyed
    ]
    sources = set(sources_for(facts, [n for n, _ in parts]))
    if KEY_ACQUIRING not in handled and facts.commission:
        parts.append((ACQUIRING_LABEL, facts.commission))
        sources.add(SOURCE_VETMANAGER)
    if totals.obligations:
        parts.append(("Обязательства и амортизация", totals.obligations))
        sources.add("manual")
    amount = sum(v for _, v in parts)
    item = _item(
        key="other",
        label=OTHER_LABEL,
        kind=KIND_OTHER,
        memo=False,
        amount=amount,
        parts=desc_sorted(parts),
        sources=sources_of(sources),
        revenue=revenue,
        resolved=None,
        open_month=facts.open,
    )
    return item, amount


def _profit_sources(facts: MonthFacts, totals: Totals) -> tuple[str, ...]:
    found: set[str] = {SOURCE_VETMANAGER} if totals.revenue else set()
    found |= sources_for(
        facts, [c.name for c in facts.costs if c.type in (TYPE_VARIABLE, TYPE_FIXED, TYPE_TAX)]
    )
    if facts.commission:
        found.add(SOURCE_VETMANAGER)
    if facts.charges:
        found.add("manual")
    return sources_of(found)


# ------------------------------------------------------------------ headline
def _join(parts: Sequence[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " и " + parts[-1]


def _count_words(n: int, noun_few: str, noun_many: str, tail: str) -> str:
    """'Две статьи выше нормы', '5 статей выше нормы'."""
    head = NUMBER_WORDS.get(n)
    return f"{head} {noun_few} {tail}" if head else f"{n} {noun_many} {tail}"


def _deviation_parts(items: Sequence[NormItem], status: str) -> tuple[list[str], int]:
    parts, total = [], 0
    for i in items:
        if i.memo or i.kind != KIND_EXPENSE or i.status != status or i.deviation_rub is None:
            continue
        rub = int(i.deviation_rub.value)
        total += rub
        parts.append(f"{lower_first(i.label)} ({'+' if rub > 0 else ''}{format_rub(rub)})")
    return parts, total


def _closed_headline(items: Sequence[NormItem]) -> str:
    above, above_total = _deviation_parts(items, STATUS_ABOVE)
    below, _ = _deviation_parts(items, STATUS_BELOW)
    text: list[str] = []
    if above:
        if len(above) == 1:
            text.append(f"Выше нормы одна статья: {above[0]}.")
        else:
            text.append(
                _count_words(len(above), "статьи", "статей", "выше нормы")
                + f": {_join(above)}. Вместе это {format_rub(above_total)}."
            )
    if below:
        if above:
            text.append(f"Ниже нормы: {_join(below)}.")
        elif len(below) == 1:
            text.append(
                f"Ниже нормы одна статья: {below[0]}. Это не всегда плохо, проверьте, "
                "нет ли недофинансирования."
            )
        else:
            text.append(
                _count_words(len(below), "статьи", "статей", "ниже нормы") + f": {_join(below)}. "
                "Это не всегда плохо, проверьте, нет ли недофинансирования."
            )
    if not above and not below:
        text.append("Все статьи в пределах нормы.")
    memo = next((i for i in items if i.memo and i.status == STATUS_ABOVE), None)
    if memo is not None and memo.deviation_rub is not None:
        memo_rub = int(memo.deviation_rub.value)
        sentence = (
            f"Отдельно: {lower_first(memo.label)} выше нормы на {format_rub(memo_rub)}, "
            "в расходы месяца оно не входит."
        )
        if above:
            sentence += f" Вместе со статьями выше нормы это {format_rub(above_total + memo_rub)}."
        text.append(sentence)
    text.extend(_profit_sentence(items))
    return " ".join(text)


def _profit_sentence(items: Sequence[NormItem]) -> list[str]:
    profit = next((i for i in items if i.kind == KIND_PROFIT), None)
    if (
        profit is None
        or profit.status != STATUS_BELOW
        or profit.deviation_pp is None
        or profit.deviation_rub is None
        or profit.norm is None
        or profit.norm.min_pct is None
    ):
        return []
    return [
        f"Чистая прибыль ниже нормы на {format_pct(abs(Decimal(profit.deviation_pp.value)))} п.п.: "
        f"не хватает {format_rub(-int(profit.deviation_rub.value))} до "
        f"{format_bound(profit.norm.min_pct)}% выручки."
    ]


def _headline(facts: MonthFacts, items: Sequence[NormItem], has_benchmarks: bool) -> str:
    if facts.open and facts.as_of is not None:
        days = facts.as_of.day
        return (
            f"К {format_day_month(facts.as_of)} доли статей посчитаны от выручки за {days} "
            f"{plural(days, 'день', 'дня', 'дней')}. Сравним с нормой, когда месяц закончится."
        )
    if not has_benchmarks:
        return "Нормы для вашей клиники пока нет, но доли статей ниже."
    return _closed_headline(items)


# ------------------------------------------------------------------ public function
def compute_norm(
    categories: Sequence[CategoryInput],
    transactions: Sequence[TransactionInput],
    sales: Sequence[SaleInput],
    card_payments: Sequence[CardPayment],
    charges: Sequence[ObligationChargeInput],
    writeoffs: Sequence[WriteoffInput],
    benchmarks: Sequence[BenchmarkInput],
    month: date,
    acquiring_rate_bp: int,
    bank_covered_to: date | None = None,
    as_of: date | None = None,
) -> NormResult:
    """Norm report of the calendar month of `month` (the 1st).

    The ratings (status, tone, deviations) are computed for a running month too; the API leaves them out
    there (owner decision of 2026-10-14), the engine stays honest about what the numbers would say.
    """
    facts = collect_facts(
        categories, transactions, sales, card_payments, charges, month,
        acquiring_rate_bp, bank_covered_to, as_of,
    )  # fmt: skip
    totals = compute_totals(facts)
    revenue = totals.revenue
    if revenue == 0:
        return NormResult(facts.period, report_status((), empty=True), (), None, ())
    reasons = partial_reasons(
        facts, check_obligations=False, check_benchmarks=True, has_benchmarks=bool(benchmarks)
    )
    items, _grouped = _group_items(benchmarks, categories, facts, writeoffs, revenue)
    handled = {b.key for b in benchmarks if b.key != KEY_NET_PROFIT and b.kind != KIND_PROFIT}
    other, _ = _other_item(facts, totals, handled, categories, revenue)
    bench_profit = next((b for b in benchmarks if b.key == KEY_NET_PROFIT), None)
    profit = _item(
        key=KEY_NET_PROFIT,
        label=bench_profit.label if bench_profit else NET_PROFIT_LABEL,
        kind=KIND_PROFIT,
        memo=False,
        amount=totals.net_profit,
        parts=[(NET_PROFIT_LABEL, totals.net_profit)],
        sources=_profit_sources(facts, totals),
        revenue=revenue,
        resolved=_resolve_norm(bench_profit, []) if bench_profit else None,
        open_month=facts.open,
    )
    all_items = (*items, other, profit)
    return NormResult(
        period=facts.period,
        status=report_status(reasons, empty=False),
        partial_reasons=reasons,
        headline=_headline(
            facts, [i for i in all_items if isinstance(i, NormItem)], bool(benchmarks)
        ),
        items=all_items,
    )
