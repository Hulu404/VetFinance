"""Balance block of the dashboard: balances, the 14-day trend, the weekly change and "enough for N days".

Rules: tests/golden/set03/README.md (sections 1-3), docs/api-contract.md ("Рабочий стол").
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from engine.balance import (
    STATUS_DUPLICATE,
    AccountInput,
    TransactionInput,
    account_balance,
    compute_balance,
)
from engine.figure import Figure, FigureItem, ordered_sources
from engine.money import (
    div_round,
    floor_div,
    format_pct,
    format_rub,
    pct_one_decimal,
)
from engine.ru import format_day_month, plural

RUNWAY_WINDOW_DAYS = 28
TREND_DAYS = 14
WEEK_DAYS = 7
KIND_OUT = "out"
SOURCE_MANUAL = "manual"


@dataclass(frozen=True)
class BalanceBlock:
    total: Figure
    bank: Figure
    cash: Figure
    week_change: Figure | None
    week_change_pct: Figure | None
    runway_days: Figure | None


@dataclass(frozen=True)
class TrendPoint:
    date: date
    value: int


@dataclass(frozen=True)
class TrendInfo:
    note: str
    source: tuple[str, ...]


def counted_transactions(
    accounts: Sequence[AccountInput], transactions: Sequence[TransactionInput], as_of: date
) -> list[TransactionInput]:
    """Operations that take part in any figure: no duplicates, inside [opening_date, as_of] of their account."""
    opening = {a.id: a.opening_date for a in accounts}
    return [
        t
        for t in transactions
        if t.status != STATUS_DUPLICATE
        and t.account_id in opening
        and opening[t.account_id] <= t.date <= as_of
    ]


def _by_account(transactions: Sequence[TransactionInput]) -> dict[str, list[TransactionInput]]:
    grouped: dict[str, list[TransactionInput]] = {}
    for t in transactions:
        grouped.setdefault(t.account_id, []).append(t)
    return grouped


def _balances_at(
    accounts: Sequence[AccountInput], grouped: dict[str, list[TransactionInput]], day: date
) -> dict[str, int]:
    return {a.id: account_balance(a, grouped.get(a.id, ()), day)[0] for a in accounts}


def _week_change(
    accounts: Sequence[AccountInput],
    grouped: dict[str, list[TransactionInput]],
    counted: Sequence[TransactionInput],
    as_of: date,
    first_day: date,
) -> tuple[Figure | None, Figure | None]:
    prev_day = as_of - timedelta(days=WEEK_DAYS)
    if prev_day < first_day:
        return None, None
    now, before = _balances_at(accounts, grouped, as_of), _balances_at(accounts, grouped, prev_day)
    items = tuple(FigureItem(a.name, now[a.id] - before[a.id], "rub", delta=True) for a in accounts)
    change = sum(now[a.id] - before[a.id] for a in accounts)
    previous, current = sum(before.values()), sum(now.values())
    sources = ordered_sources({t.source for t in counted if t.date > prev_day}) or (SOURCE_MANUAL,)
    then_label = f"Неделю назад ({format_day_month(prev_day)})"
    ends = (FigureItem(then_label, previous), FigureItem("Сейчас", current))
    week = Figure(
        value=change,
        unit="rub",
        breakdown=items,
        source=sources,
        note=(
            f"Изменение остатка на всех счетах за 7 дней: с конца {format_day_month(prev_day)} "
            f"до конца {format_day_month(as_of)}. В разбивке изменение по каждому счёту."
        ),
        delta=True,
        details=ends,
    )
    if previous <= 0:
        return week, None
    pct = pct_one_decimal(change, previous)
    week_pct = Figure(
        value=pct,
        unit="pct",
        breakdown=ends,
        source=sources,
        note=(
            f"Изменение {format_rub(change)} к остатку неделю назад ({format_rub(previous)}): "
            f"{format_pct(pct)}%."
        ),
        delta=True,
    )
    return week, week_pct


def _trend(
    accounts: Sequence[AccountInput],
    grouped: dict[str, list[TransactionInput]],
    as_of: date,
    first_day: date,
) -> tuple[TrendPoint, ...]:
    days = [as_of - timedelta(days=k) for k in range(TREND_DAYS - 1, -1, -1)]
    return tuple(
        TrendPoint(day, sum(_balances_at(accounts, grouped, day).values()))
        for day in days
        if day >= first_day
    )


def _runway(
    total: Figure, counted: Sequence[TransactionInput], as_of: date, first_day: date
) -> Figure | None:
    window = min(RUNWAY_WINDOW_DAYS, (as_of - first_day).days + 1)
    window_start = as_of - timedelta(days=window - 1)
    burn = sum(-t.amount for t in counted if t.kind == KIND_OUT and t.date >= window_start)
    if burn <= 0:
        return None
    balance = int(total.value)
    value = 0 if balance <= 0 else floor_div(balance * window, burn)
    daily = div_round(burn, window)
    days_word = plural(window, "день", "дня", "дней")
    return Figure(
        value=value,
        unit="days",
        breakdown=(
            FigureItem("Остаток на счетах", balance),
            FigureItem(f"Расходы за {window} {days_word}", burn),
            FigureItem("Расходы в день, в среднем", daily),
            FigureItem("Окно расчёта", window, "days"),
        ),
        source=total.source,
        note=(
            f"Остаток {format_rub(balance)} делим на средний расход в день {format_rub(daily)} "
            f"(расходы за {window} {days_word} {format_rub(burn)} ÷ {window}) и берём целые дни "
            "вниз. Платежи вперёд не учитываются: смотрите платёжный календарь."
        ),
    )


def compute_balance_block(
    accounts: Sequence[AccountInput], transactions: Sequence[TransactionInput], as_of: date
) -> tuple[BalanceBlock, tuple[TrendPoint, ...], TrendInfo]:
    result = compute_balance(accounts, transactions, as_of)
    ordered = sorted(accounts, key=lambda a: (a.name, a.id))
    counted = counted_transactions(ordered, transactions, as_of)
    grouped = _by_account(counted)
    first_day = min((a.opening_date for a in ordered), default=None)
    week = week_pct = runway = None
    trend: tuple[TrendPoint, ...] = ()
    if first_day is not None and first_day <= as_of:
        week, week_pct = _week_change(ordered, grouped, counted, as_of, first_day)
        trend = _trend(ordered, grouped, as_of, first_day)
        runway = _runway(result.total, counted, as_of, first_day)
    block = BalanceBlock(result.total, result.bank, result.cash, week, week_pct, runway)
    info = TrendInfo(
        note=(
            f"Остаток на конец каждого дня по всем счетам (банк и касса): {len(trend)} "
            f"{plural(len(trend), 'день', 'дня', 'дней')} по {format_day_month(as_of)} включительно."
        ),
        source=result.total.source,
    )
    return block, trend, info
