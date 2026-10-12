"""Card acquiring reconciliation (function 10): card payments of Vetmanager against bank credits.

For the earliest sale day that is not reconciled yet the credit window is [next business day,
day + max_delay business days]. Inside the window:
1. a credit equal (within the tolerance) to the expected net of 1..max_group_days consecutive sale days
   closes them: `matched` (one credit may close a Friday-to-Sunday group);
2. otherwise the nearest credit whose amount differs from the expected net by at most
   `mismatch_search_pct` percent is an under- or over-payment: `mismatch`;
3. otherwise there is no credit: `waiting` while `as_of` is not past the end of the window; after it
   `no_statement` if the bank statement ends before the window does, else `mismatch` with 0 credited.

Business days are Monday to Friday (no holiday calendar yet). Pure functions; money in kopecks.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from engine.money import BASIS_POINTS, apply_rate_bp, div_round

MATCHED = "matched"
MISMATCH = "mismatch"
WAITING = "waiting"
NO_STATEMENT = "no_statement"
_WEEKDAYS = 5
_PERCENT = 100


@dataclass(frozen=True)
class CardPayment:
    date: date
    amount: int


@dataclass(frozen=True)
class BankCredit:
    id: str
    date: date
    amount: int


@dataclass(frozen=True)
class AcquiringParams:
    rate_bp: int = 190
    max_delay_business_days: int = 3
    tolerance_kop: int = 100
    max_group_days: int = 3
    mismatch_search_pct: int = 10


@dataclass(frozen=True)
class DayResult:
    sale_date: date
    card_total: int
    expected_commission: int
    expected_credit: int
    group_days: tuple[date, ...]
    credit_id: str | None
    credit_date: date | None
    credit_amount: int | None
    group_gross: int
    group_expected_credit: int
    diff: int | None
    actual_commission: int | None
    actual_rate_bp: int | None
    delay_business_days: int | None
    expected_by: date
    status: str


def next_business_day(day: date) -> date:
    day += timedelta(days=1)
    while day.weekday() >= _WEEKDAYS:
        day += timedelta(days=1)
    return day


def add_business_days(day: date, count: int) -> date:
    for _ in range(count):
        day = next_business_day(day)
    return day


def business_days_between(start: date, end: date) -> int:
    """Business days after `start` up to and including `end`."""
    count, day = 0, start
    while day < end:
        day = next_business_day(day)
        count += 1
    return count


@dataclass(frozen=True)
class _Day:
    day: date
    gross: int
    net: int


def _daily(card_payments: Sequence[CardPayment], rate_bp: int) -> list[_Day]:
    gross: dict[date, int] = {}
    for payment in card_payments:
        gross[payment.date] = gross.get(payment.date, 0) + payment.amount
    return [
        _Day(day, total, total - apply_rate_bp(total, rate_bp))
        for day, total in sorted(gross.items())
        if total > 0
    ]


def _consecutive(group: Sequence[_Day]) -> bool:
    return all((b.day - a.day).days <= 1 for a, b in zip(group, group[1:], strict=False))


def _find_group(
    days: Sequence[_Day], start: int, window: Sequence[BankCredit], params: AcquiringParams
) -> tuple[list[_Day], BankCredit] | None:
    for length in range(1, params.max_group_days + 1):
        group = list(days[start : start + length])
        if len(group) < length or not _consecutive(group):
            break
        wanted = sum(d.net for d in group)
        for credit in window:
            if abs(credit.amount - wanted) <= params.tolerance_kop:
                return group, credit
    return None


def _find_mismatch(
    first: _Day, window: Sequence[BankCredit], params: AcquiringParams
) -> BankCredit | None:
    for credit in window:
        if abs(credit.amount - first.net) * _PERCENT <= first.net * params.mismatch_search_pct:
            return credit
    return None


def _matched_rows(
    group: Sequence[_Day], credit: BankCredit, status: str, params: AcquiringParams
) -> list[DayResult]:
    gross = sum(d.gross for d in group)
    expected = sum(d.net for d in group)
    actual_commission = gross - credit.amount
    rate = div_round(actual_commission * BASIS_POINTS, gross)
    delay = business_days_between(group[-1].day, credit.date)
    days = tuple(d.day for d in group)
    return [
        DayResult(
            sale_date=d.day,
            card_total=d.gross,
            expected_commission=d.gross - d.net,
            expected_credit=d.net,
            group_days=days,
            credit_id=credit.id,
            credit_date=credit.date,
            credit_amount=credit.amount,
            group_gross=gross,
            group_expected_credit=expected,
            diff=credit.amount - expected,
            actual_commission=actual_commission,
            actual_rate_bp=rate,
            delay_business_days=delay,
            expected_by=add_business_days(d.day, params.max_delay_business_days),
            status=status,
        )
        for d in group
    ]


def _unmatched_row(
    first: _Day,
    deadline: date,
    as_of: date,
    bank_covered_to: date | None,
) -> DayResult:
    credited: int | None = None
    diff: int | None = None
    if as_of <= deadline:
        status = WAITING
    elif bank_covered_to is None or bank_covered_to < deadline:
        status = NO_STATEMENT
    else:
        status, credited, diff = MISMATCH, 0, -first.net
    return DayResult(
        sale_date=first.day,
        card_total=first.gross,
        expected_commission=first.gross - first.net,
        expected_credit=first.net,
        group_days=(first.day,),
        credit_id=None,
        credit_date=None,
        credit_amount=credited,
        group_gross=first.gross,
        group_expected_credit=first.net,
        diff=diff,
        actual_commission=None,
        actual_rate_bp=None,
        delay_business_days=None,
        expected_by=deadline,
        status=status,
    )


def reconcile_acquiring(
    card_payments: Sequence[CardPayment],
    credits: Sequence[BankCredit],
    params: AcquiringParams,
    *,
    as_of: date,
    bank_covered_to: date | None,
) -> list[DayResult]:
    """One result per sale day (days of one group share the credit and the group totals)."""
    days = _daily(card_payments, params.rate_bp)
    free = sorted(credits, key=lambda c: (c.date, c.id))
    results: list[DayResult] = []
    index = 0
    while index < len(days):
        first = days[index]
        low = next_business_day(first.day)
        high = add_business_days(first.day, params.max_delay_business_days)
        window = [c for c in free if low <= c.date <= high]
        found = _find_group(days, index, window, params)
        if found is not None:
            group, credit = found
            results.extend(_matched_rows(group, credit, MATCHED, params))
            free.remove(credit)
            index += len(group)
            continue
        near = _find_mismatch(first, window, params)
        if near is not None:
            results.extend(_matched_rows([first], near, MISMATCH, params))
            free.remove(near)
        else:
            results.append(_unmatched_row(first, high, as_of, bank_covered_to))
        index += 1
    return results
