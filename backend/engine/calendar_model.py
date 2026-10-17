"""Data of the payment calendar and its day-by-day arithmetic (no texts, no Figures): shared by calendar.py and
calendar_alerts.py. Rules: tests/golden/set05/README.md, rules 3, 14, 16.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

Day = date  # annotations after a field named `date`

WINDOW_DAYS = 22
WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
STATUS_OK = "ok"
STATUS_BELOW_SAFE = "below_safe"
STATUS_BELOW_ZERO = "below_zero"
SOURCE_RECURRING = "recurring"
SOURCE_OBLIGATION = "obligation"
SOURCE_MANUAL = "manual"


@dataclass(frozen=True)
class Payment:
    id: str
    date: date
    name: str
    amount: int
    source: str  # recurring | obligation | manual
    category: str | None = None
    counterparty_key: str | None = None
    counterparty_inn: str | None = None
    counterparty_name: str | None = None
    max_deferral_days: int = 0
    nominal_date: Day | None = None
    moved_from: Day | None = None
    details: tuple[tuple[str, int], ...] = ()  # (label, kopecks) rows of the tooltip of the amount


@dataclass(frozen=True)
class NumDay:
    date: date
    opening: int
    income: int
    payments: tuple[tuple[Payment, int], ...]  # (payment, balance after it), by amount descending
    closing: int
    status: str

    @property
    def red(self) -> bool:
        return self.status != STATUS_OK


def payment_order(p: Payment) -> tuple[int, str, str]:
    return (-p.amount, p.name, p.id)


def build_days(
    start: date,
    opening: int,
    income_for: Callable[[date], int],
    payments: Sequence[Payment],
    safe_balance: int,
    count: int = WINDOW_DAYS,
) -> list[NumDay]:
    """Payments of a day first (largest first), the income of the day at the end (rules 3 and 14)."""
    by_day: dict[date, list[Payment]] = {}
    for p in payments:
        by_day.setdefault(p.date, []).append(p)
    days: list[NumDay] = []
    balance = opening
    for i in range(count):
        day = start + timedelta(days=i)
        running = balance
        paid: list[tuple[Payment, int]] = []
        for p in sorted(by_day.get(day, []), key=payment_order):
            running -= p.amount
            paid.append((p, running))
        closing = running + income_for(day)
        lowest = min([closing] + [after for _, after in paid])
        status = (
            STATUS_BELOW_ZERO
            if lowest < 0
            else STATUS_BELOW_SAFE
            if closing < safe_balance
            else STATUS_OK
        )
        days.append(NumDay(day, balance, income_for(day), tuple(paid), closing, status))
        balance = closing
    return days


def episodes(days: Sequence[NumDay]) -> list[tuple[int, int]]:
    """Runs of red days as (first index, last index)."""
    runs: list[tuple[int, int]] = []
    first: int | None = None
    for i, day in enumerate(days):
        if day.red and first is None:
            first = i
        if not day.red and first is not None:
            runs.append((first, i - 1))
            first = None
    if first is not None:
        runs.append((first, len(days) - 1))
    return runs


def moved(payments: Sequence[Payment], target: Payment, to: date) -> list[Payment]:
    return [replace(p, date=to, moved_from=p.date) if p is target else p for p in payments]
