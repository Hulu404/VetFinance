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


TENTHS_IN_PCT = 10
PER_MILLE = 1000
TURNOVER_WINDOW_DAYS = 90


def pct_to_tenths(pct: Decimal) -> int:
    """A norm border in percent to whole tenths of a percent (22.0 -> 220); half up."""
    return int((pct * TENTHS_IN_PCT).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def tenths_to_pct(tenths: int) -> Decimal:
    """Whole tenths of a percent to a percent with one decimal (5 -> Decimal('0.5'))."""
    return Decimal(tenths) / Decimal(TENTHS_IN_PCT)


def bound_amount(revenue: int, bound_tenths: int) -> int:
    """The border of a norm in kopecks: `bound_tenths` tenths of a percent of the revenue (not rounded to hundreds)."""
    return div_round(revenue * bound_tenths, PER_MILLE)


def deviation_pp(amount: int, bound_tenths: int, revenue: int) -> Decimal:
    """Percentage points between the share `amount / revenue` and the border, from unrounded values."""
    return tenths_to_pct(div_round(amount * PER_MILLE - bound_tenths * revenue, revenue))


def turnover_days(stock_value: int, consumption: int, window: int = TURNOVER_WINDOW_DAYS) -> int:
    """Days the stock lasts: stock * window / consumption over the window, to the nearest day (half up)."""
    return div_round(stock_value * window, consumption)
