"""The only place where money and percentages are rounded.

Money is an integer number of kopecks. Rounding is half away from zero.
"""

from decimal import ROUND_HALF_UP, Decimal

KOPECKS_IN_RUB = 100


def div_round(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero."""
    if denominator == 0:
        raise ZeroDivisionError("denominator must not be zero")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    sign = -1 if numerator < 0 else 1
    return sign * ((abs(numerator) * 2 + denominator) // (denominator * 2))


def rub_to_kopecks(rub: Decimal | str | int) -> int:
    """Convert a rouble amount (from user input) to kopecks."""
    value = Decimal(rub) * KOPECKS_IN_RUB
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def pct_one_decimal(part: int, whole: int) -> Decimal:
    """Percentage of `part` in `whole` with one decimal place (e.g. Decimal('15.0'))."""
    if whole == 0:
        raise ZeroDivisionError("whole must not be zero")
    tenths = div_round(part * 1000, whole)
    return Decimal(tenths) / Decimal(10)
