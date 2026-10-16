"""Stock and expiry dates (function 17): value, items without movement, batches about to expire, write-offs, turnover.

Pure functions. The stock is valued at the purchase price of each batch (`qty * unit_cost`). Rules:
tests/golden/set04/README.md (rules 19-23). The Vetmanager loader does not read the stock yet, so the
tables are filled from the seed of the golden set until the loader exists.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from engine.figure import Figure, FigureItem
from engine.money import (
    TURNOVER_WINDOW_DAYS,
    bound_amount,
    format_pct,
    format_rub,
    pct_to_tenths,
    turnover_days,
)
from engine.report_facts import (
    SOURCE_MANUAL,
    SOURCE_VETMANAGER,
    STATUS_EMPTY,
    STATUS_OK,
    desc_sorted,
    month_bounds,
    month_key,
)
from engine.report_text import format_bound
from engine.reports_inputs import (
    REASON_DAMAGED,
    REASON_EXPIRED,
    REASON_OTHER,
    BenchmarkInput,
    ConsumptionInput,
    StockBatchInput,
    StockItemInput,
    WriteoffInput,
)
from engine.ru import format_day_month, month_genitive, plural

EXPIRING_DAYS = 60
NORM_TURNOVER_DAYS = 45
KEY_WRITEOFF = "writeoff"
BUCKETS = (
    # key, label of the interval, label of the line in the breakdown of `frozen`, first idle day
    ("180_plus", "От 180 дней", "Без движения от 180 дней", 180),
    ("90_179", "90–179 дней", "Без движения 90–179 дней", 90),
    ("60_89", "60–89 дней", "Без движения 60–89 дней", 60),
)
BUCKET_ORDER = ("60_89", "90_179", "180_plus")
REASON_LABELS = (
    (REASON_EXPIRED, "Истёк срок годности"),
    (REASON_DAMAGED, "Брак и бой"),
    (REASON_OTHER, "Другое"),
)


@dataclass(frozen=True)
class ExpiringRow:
    item: str
    expires_on: date
    days_left: int  # 0..60 in `expiring`, negative in `expired_items`
    qty: int
    amount: Figure


@dataclass(frozen=True)
class IdleItem:
    item: str
    last_movement_on: date
    idle_days: int
    bucket: str  # 60_89 | 90_179 | 180_plus
    qty: int
    amount: int  # kopecks
    amount_figure: Figure


@dataclass(frozen=True)
class IdleBucket:
    key: str
    label: str
    amount: Figure
    positions: Figure


@dataclass(frozen=True)
class WrittenOffRow:
    item: str
    date: date
    qty: int
    reason: str
    amount: Figure


@dataclass(frozen=True)
class StockResult:
    as_of: date
    month: str  # the month of `written_off_*`, 'YYYY-MM'
    status: str  # ok | empty
    partial_reasons: tuple[str, ...]
    headline: str | None
    stock_value: Figure
    frozen: Figure
    frozen_positions: Figure
    idle_buckets: tuple[IdleBucket, ...]
    frozen_items: tuple[IdleItem, ...]  # amount descending, ties by name
    expiring_60d: Figure
    expiring: tuple[ExpiringRow, ...]
    expired_on_hand: Figure
    expired_items: tuple[ExpiringRow, ...]
    written_off_month: Figure
    written_off_norm: Figure
    written_off_items: tuple[WrittenOffRow, ...]
    turnover_days: Figure
    norm_turnover_days: int


@dataclass(frozen=True)
class _Position:
    item: StockItemInput
    batches: tuple[StockBatchInput, ...]

    @property
    def qty(self) -> int:
        return sum(b.qty for b in self.batches)

    @property
    def amount(self) -> int:
        return sum(b.qty * b.unit_cost for b in self.batches)


def _positions(
    items: Sequence[StockItemInput], batches: Sequence[StockBatchInput]
) -> list[_Position]:
    """Items with something on hand: batches with a positive quantity only."""
    by_item: dict[str, list[StockBatchInput]] = {}
    for b in batches:
        if b.qty > 0:
            by_item.setdefault(b.item_id, []).append(b)
    known = {i.id: i for i in items}
    return [
        _Position(known[item_id], tuple(sorted(rows, key=_batch_order)))
        for item_id, rows in sorted(by_item.items())
        if item_id in known
    ]


def _batch_order(b: StockBatchInput) -> tuple[date, int, int]:
    return (b.expires_on or date.max, b.unit_cost, b.qty)


def _batch_label(qty: int, unit_cost: int) -> str:
    return f"{qty} × {format_rub(unit_cost)}"


def _amount_figure(
    value: int, rows: Sequence[FigureItem], note: str, details: tuple[FigureItem, ...] = ()
) -> Figure:
    return Figure(
        value=value,
        unit="rub",
        breakdown=tuple(rows),
        source=(SOURCE_VETMANAGER,),
        note=note,
        details=details,
    )


def _by_item(rows: Sequence[ExpiringRow]) -> list[tuple[str, int]]:
    agg: dict[str, int] = {}
    for r in rows:
        agg[r.item] = agg.get(r.item, 0) + int(r.amount.value)
    return desc_sorted(agg.items())


def _expiry_rows(positions: Sequence[_Position], as_of: date) -> list[ExpiringRow]:
    rows = []
    for p in positions:
        for b in p.batches:
            if b.expires_on is None:
                continue
            amount = b.qty * b.unit_cost
            rows.append(
                ExpiringRow(
                    item=p.item.name,
                    expires_on=b.expires_on,
                    days_left=(b.expires_on - as_of).days,
                    qty=b.qty,
                    amount=_amount_figure(
                        amount,
                        [FigureItem(_batch_label(b.qty, b.unit_cost), amount)],
                        "Остаток партии по закупочной цене партии.",
                    ),
                )
            )
    return sorted(rows, key=lambda r: (r.expires_on, r.item, r.qty))


def _expiring_figure(rows: Sequence[ExpiringRow]) -> Figure:
    return Figure(
        value=sum(int(r.amount.value) for r in rows),
        unit="rub",
        breakdown=tuple(FigureItem(n, v) for n, v in _by_item(rows)),
        source=(SOURCE_VETMANAGER,) if rows else (SOURCE_MANUAL,),
        note="Партии с остатком и сроком годности не позже чем через 60 дней (включая сегодняшний "
        "день). Просроченные на полке считаются отдельно.",
    )


def _expired_figure(rows: Sequence[ExpiringRow]) -> Figure:
    details: tuple[FigureItem, ...] = ()
    if rows:
        oldest = min(rows, key=lambda r: r.days_left)
        details = (
            FigureItem(
                f"Самая давняя: срок истёк {format_day_month(oldest.expires_on)}",
                -oldest.days_left,
                "days",
            ),
        )
    return Figure(
        value=sum(int(r.amount.value) for r in rows),
        unit="rub",
        breakdown=tuple(FigureItem(n, v) for n, v in _by_item(rows)),
        source=(SOURCE_VETMANAGER,) if rows else (SOURCE_MANUAL,),
        note="Партии с истёкшим сроком, которые ещё числятся на складе.",
        details=details,
    )


def _bucket_of(idle_days: int) -> str | None:
    for key, _label, _line, first in BUCKETS:
        if idle_days >= first:
            return key
    return None


def _idle_items(positions: Sequence[_Position], as_of: date) -> list[IdleItem]:
    found = []
    for p in positions:
        moved = p.item.last_movement
        if moved is None:
            continue
        idle = (as_of - moved).days
        bucket = _bucket_of(idle)
        if bucket is None:
            continue
        found.append(
            IdleItem(
                item=p.item.name,
                last_movement_on=moved,
                idle_days=idle,
                bucket=bucket,
                qty=p.qty,
                amount=p.amount,
                amount_figure=_amount_figure(
                    p.amount,
                    [
                        FigureItem(_batch_label(b.qty, b.unit_cost), b.qty * b.unit_cost)
                        for b in p.batches
                    ],
                    "Остаток позиции по закупочной цене. Движение: продажа или списание на приём.",
                    (FigureItem("Дней без движения", idle, "days"),),
                ),
            )
        )
    return sorted(found, key=lambda i: (-i.amount, i.item))


def _idle_figures(
    idle: Sequence[IdleItem],
) -> tuple[Figure, Figure, tuple[IdleBucket, ...]]:
    labels = {key: (label, line) for key, label, line, _ in BUCKETS}
    amounts = {k: sum(i.amount for i in idle if i.bucket == k) for k in BUCKET_ORDER}
    counts = {k: sum(1 for i in idle if i.bucket == k) for k in BUCKET_ORDER}
    total = sum(amounts.values())
    sources = (SOURCE_VETMANAGER,) if idle else (SOURCE_MANUAL,)
    frozen = Figure(
        value=total,
        unit="rub",
        breakdown=tuple(FigureItem(labels[k][1], amounts[k]) for k in BUCKET_ORDER),
        source=sources,
        note="Позиции, по которым не было ни продажи, ни списания на приём. Считаем с последнего "
        "движения; интервалы не пересекаются.",
    )
    positions = Figure(
        value=len(idle),
        unit="count",
        breakdown=tuple(FigureItem(labels[k][0], counts[k], "count") for k in BUCKET_ORDER),
        source=sources,
        note="Число позиций с остатком, у которых с последнего движения прошло 60 дней и больше.",
    )
    buckets = tuple(
        IdleBucket(
            key=k,
            label=labels[k][0],
            amount=Figure(
                value=amounts[k],
                unit="rub",
                breakdown=(FigureItem(labels[k][0], amounts[k]),),
                source=sources,
                note="Остаток позиций без движения этого интервала по закупочной цене.",
            ),
            positions=Figure(
                value=counts[k],
                unit="count",
                breakdown=(FigureItem("Позиций", counts[k], "count"),),
                source=sources,
                note=f"Позиции с остатком, без продаж и списаний на приём: {labels[k][0].lower()}.",
            ),
        )
        for k in BUCKET_ORDER
    )
    return frozen, positions, buckets


def idle_total_figure(items: Sequence[IdleItem], bucket: str) -> Figure:
    """Number of positions of one interval (or of all of them: bucket `all`) for the paged list."""
    chosen = [i for i in items if bucket in ("all", i.bucket)]
    labels = {key: label for key, label, _, _ in BUCKETS}
    where = "от 60 дней" if bucket == "all" else labels[bucket].lower()
    return Figure(
        value=len(chosen),
        unit="count",
        breakdown=(FigureItem("Позиций", len(chosen), "count"),),
        source=(SOURCE_VETMANAGER,) if chosen else (SOURCE_MANUAL,),
        note=f"Позиции с остатком, без продаж и списаний на приём: {where}.",
    )


def _writeoff_label(w: WriteoffInput) -> str:
    if w.qty and w.amount % w.qty == 0:
        return _batch_label(w.qty, w.amount // w.qty)
    return f"{w.qty} шт."


def _written_off(
    writeoffs: Sequence[WriteoffInput], first: date, last: date
) -> tuple[Figure, tuple[WrittenOffRow, ...], int]:
    """(figure of the month by reasons, rows by amount, the part written off by expiry date)."""
    rows = sorted(
        (w for w in writeoffs if first <= w.date <= last),
        key=lambda w: (-w.amount, w.item, w.date),
    )
    by_reason = [
        (label, sum(w.amount for w in rows if w.reason == key)) for key, label in REASON_LABELS
    ]
    figure = Figure(
        value=sum(w.amount for w in rows),
        unit="rub",
        breakdown=tuple(FigureItem(label, v) for label, v in by_reason if v),
        source=(SOURCE_VETMANAGER,) if rows else (SOURCE_MANUAL,),
        note=f"Списания {month_genitive(first.month)} {first.year} по закупочной цене, по причинам.",
    )
    items = tuple(
        WrittenOffRow(
            item=w.item,
            date=w.date,
            qty=w.qty,
            reason=w.reason,
            amount=_amount_figure(
                w.amount, [FigureItem(_writeoff_label(w), w.amount)], "Списание по закупочной цене."
            ),
        )
        for w in rows
    )
    expired = sum(w.amount for w in rows if w.reason == REASON_EXPIRED)
    return figure, items, expired


def _writeoff_norm(
    benchmarks: Sequence[BenchmarkInput], month_revenue: int | None, expired: int, first: date
) -> Figure:
    """The upper border of the `writeoff` row of the norm report: the same number as there."""
    bench = next((b for b in benchmarks if b.key == KEY_WRITEOFF and b.max_pct is not None), None)
    if bench is None or bench.max_pct is None or not month_revenue:
        return Figure(
            value=0,
            unit="rub",
            breakdown=(),
            source=("calc",),
            note="Норма списания не посчитана: нет выручки за месяц или нормы для клиники.",
        )
    limit = bound_amount(month_revenue, pct_to_tenths(bench.max_pct))
    gap = expired - limit
    return Figure(
        value=limit,
        unit="rub",
        breakdown=(
            FigureItem(f"Норма, {format_bound(bench.max_pct)}% выручки", bench.max_pct, "pct"),
            FigureItem(f"Выручка {month_genitive(first.month)}", month_revenue),
        ),
        source=("calc",),
        note="Та же норма, что в отчёте «Норма»: списание по сроку до "
        f"{format_pct(bench.max_pct)}% выручки того же месяца.",
        details=(
            FigureItem("Списано по сроку", expired),
            FigureItem("Сверх нормы" if gap > 0 else "Запас до нормы", abs(gap)),
        ),
    )


def _turnover(stock_value: int, consumption: int) -> Figure:
    value = turnover_days(stock_value, consumption) if consumption > 0 else 0
    note = (
        f"{format_rub(stock_value)} × {TURNOVER_WINDOW_DAYS} ÷ {format_rub(consumption)} = "
        f"{value} дн. Расход: продажи и использование на приёме по закупочной цене."
        if consumption > 0
        else "За 90 дней расхода со склада нет, оборачиваемость не посчитать."
    )
    return Figure(
        value=value,
        unit="days",
        breakdown=(
            FigureItem("Запас на складе", stock_value),
            FigureItem("Расход за 90 дней", consumption),
            FigureItem("Окно расчёта", TURNOVER_WINDOW_DAYS, "days"),
        ),
        source=(SOURCE_VETMANAGER, "calc"),
        note=note,
        details=(FigureItem("Норма", NORM_TURNOVER_DAYS, "days"),),
    )


def _headline(expired: int, expiring: Sequence[ExpiringRow], frozen: int) -> str:
    parts = []
    if expired:
        parts.append(
            f"На полке лежат партии с истёкшим сроком на {format_rub(expired)}. Их стоит списать."
        )
    if expiring:
        n = len(expiring)
        total = sum(int(r.amount.value) for r in expiring)
        parts.append(
            f"Срок годности истекает у {n} {plural(n, 'партии', 'партий', 'партий')} "
            f"на {format_rub(total)}."
        )
    if frozen:
        lead = "Ещё" if parts else "Всего"
        parts.append(f"{lead} {format_rub(frozen)} лежат без движения.")
    return " ".join(parts) or "Просроченных партий, скорых сроков и позиций без движения нет."


def _stock_value(positions: Sequence[_Position]) -> Figure:
    value = sum(p.amount for p in positions)
    return Figure(
        value=value,
        unit="rub",
        breakdown=(FigureItem("Остаток на складе по закупочной цене", value),),
        source=(SOURCE_VETMANAGER,) if positions else (SOURCE_MANUAL,),
        note="Количество на остатке, умноженное на закупочную цену партии.",
        details=(FigureItem("Позиций", len(positions), "count"),),
    )


def compute_stock(
    items: Sequence[StockItemInput],
    batches: Sequence[StockBatchInput],
    writeoffs: Sequence[WriteoffInput],
    consumption: Sequence[ConsumptionInput],
    as_of: date,
    month: date | None = None,
    month_revenue: int | None = None,
    benchmarks: Sequence[BenchmarkInput] = (),
) -> StockResult:
    """Stock report at the end of `as_of`.

    `month` (any day of it; default the month of `as_of`) is the month of the write-offs, taken up to `as_of`;
    `month_revenue` is the revenue of that month from the P&L (for the write-off norm).
    """
    first, last = month_bounds(month or as_of)
    positions = _positions(items, batches)
    expiry = _expiry_rows(positions, as_of)
    expiring = [r for r in expiry if 0 <= r.days_left <= EXPIRING_DAYS]
    expired = [r for r in expiry if r.days_left < 0]
    idle = _idle_items(positions, as_of)
    frozen, frozen_positions, buckets = _idle_figures(idle)
    written, written_items, expired_writeoffs = _written_off(writeoffs, first, min(last, as_of))
    window_start = as_of - timedelta(days=TURNOVER_WINDOW_DAYS - 1)
    spent = sum(c.amount for c in consumption if window_start <= c.date <= as_of)
    stock_value = _stock_value(positions)
    empty = not (items or batches or writeoffs or consumption)
    return StockResult(
        as_of=as_of,
        month=month_key(first),
        status=STATUS_EMPTY if empty else STATUS_OK,
        partial_reasons=(),
        headline=None
        if empty
        else _headline(sum(int(r.amount.value) for r in expired), expiring, int(frozen.value)),
        stock_value=stock_value,
        frozen=frozen,
        frozen_positions=frozen_positions,
        idle_buckets=buckets,
        frozen_items=tuple(idle),
        expiring_60d=_expiring_figure(expiring),
        expiring=tuple(expiring),
        expired_on_hand=_expired_figure(expired),
        expired_items=tuple(expired),
        written_off_month=written,
        written_off_norm=_writeoff_norm(benchmarks, month_revenue, expired_writeoffs, first),
        written_off_items=written_items,
        turnover_days=_turnover(int(stock_value.value), spent),
        norm_turnover_days=NORM_TURNOVER_DAYS,
    )
