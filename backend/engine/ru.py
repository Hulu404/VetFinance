"""Russian text helpers for notes and reasons built by the backend (dates, plurals)."""

from datetime import date

MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
MONTHS_NOMINATIVE = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)
MONTHS_SHORT = (
    "янв",
    "фев",
    "мар",
    "апр",
    "мая",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)


def format_date(d: date) -> str:
    """'11 октября 2026' (never ISO in user-facing text)."""
    return f"{d.day} {MONTHS_GENITIVE[d.month - 1]} {d.year}"


def format_date_short(d: date) -> str:
    """'6 сен'."""
    return f"{d.day} {MONTHS_SHORT[d.month - 1]}"


def format_day_month(d: date) -> str:
    """'6 сентября'."""
    return f"{d.day} {MONTHS_GENITIVE[d.month - 1]}"


def month_name(year: int, month: int) -> str:
    """'сентябрь 2026'."""
    return f"{MONTHS_NOMINATIVE[month - 1]} {year}"


def month_genitive(month: int) -> str:
    """'сентября' (for 'в сентябре' use month_prepositional)."""
    return MONTHS_GENITIVE[month - 1]


def plural(n: int, one: str, few: str, many: str) -> str:
    """Pick the Russian plural form for n: 1 операция, 2 операции, 5 операций."""
    n10, n100 = abs(n) % 10, abs(n) % 100
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def format_range_short(first: date, last: date) -> str:
    """'4 сен' for one day, '4–6 сен' inside a month, '30 авг – 1 сен' across months."""
    if first == last:
        return format_date_short(first)
    if (first.year, first.month) == (last.year, last.month):
        return f"{first.day}–{format_date_short(last)}"
    return f"{format_date_short(first)} – {format_date_short(last)}"
