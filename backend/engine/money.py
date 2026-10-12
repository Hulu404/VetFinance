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


def floor_div(numerator: int, denominator: int) -> int:
    """Whole part of a positive ratio, rounded down (days of cash: 17.6 is shown as 17)."""
    if denominator <= 0 or numerator < 0:
        raise ValueError("floor_div expects a non-negative numerator and a positive denominator")
    return numerator // denominator


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


BASIS_POINTS = 10_000
NBSP = "\u00a0"


def apply_rate_bp(amount: int, rate_bp: int) -> int:
    """`amount` kopecks times a rate in basis points (190 = 1.9%), rounded half away from zero."""
    return div_round(amount * rate_bp, BASIS_POINTS)


def rate_bp_to_pct(rate_bp: int) -> Decimal:
    """Basis points to percent with two decimals available (190 -> Decimal('1.9'))."""
    return (Decimal(rate_bp) / Decimal(100)).normalize()


def pct_to_rate_bp(pct: Decimal | str) -> int:
    """Percent (as the user types it) to whole basis points; more than two decimals are rounded."""
    return int((Decimal(pct) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def format_rub(kopecks: int) -> str:
    """'5 400 ₽' or '5 400,50 ₽' for texts built on the backend (no rounding, exact kopecks)."""
    sign = "\u2212" if kopecks < 0 else ""
    rub, kop = divmod(abs(kopecks), KOPECKS_IN_RUB)
    digits = f"{rub:,}".replace(",", NBSP)
    tail = f",{kop:02d}" if kop else ""
    return f"{sign}{digits}{tail}{NBSP}\u20bd"


def format_pct(value: Decimal) -> str:
    """'40,3' or '−30,6' for texts built on the backend; `value` already has one decimal."""
    text = f"{value:.1f}".replace(".", ",")
    return text.replace("-", "−")
