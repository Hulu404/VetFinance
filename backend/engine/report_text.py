"""Texts shared by the report engines: norm ranges, periods, ordinals. Money and percents come from engine.money."""

from decimal import Decimal

from engine.money import format_pct
from engine.report_facts import MonthFacts
from engine.ru import format_days_range, month_name

EN_DASH = "–"
NUMBER_WORDS = {2: "Две", 3: "Три", 4: "Четыре"}


def format_bound(pct: Decimal) -> str:
    """'12' for 12.0, '0,8' for 0.8: borders of a norm without a trailing zero."""
    text = format_pct(pct)
    return text[:-2] if text.endswith(",0") else text


def format_norm_range(min_pct: Decimal | None, max_pct: Decimal | None) -> str:
    """'12–20%', 'от 12%', 'до 0,8%'."""
    if min_pct is not None and max_pct is not None:
        return f"{format_bound(min_pct)}{EN_DASH}{format_bound(max_pct)}%"
    if min_pct is not None:
        return f"от {format_bound(min_pct)}%"
    if max_pct is not None:
        return f"до {format_bound(max_pct)}%"
    return ""


def period_phrase(facts: MonthFacts) -> str:
    """'сентябрь 2026' for a closed month, '1–15 сентября 2026' for a running one."""
    first = facts.first_day
    if facts.open and facts.as_of is not None:
        return f"{format_days_range(first, facts.as_of)} {first.year}"
    return month_name(first.year, first.month)


def lower_first(text: str) -> str:
    """'Аренда и коммуналка' -> 'аренда и коммуналка'; an abbreviation ('ФОТ врачей') stays as it is."""
    if text[1:2].isupper():
        return text
    return text[:1].lower() + text[1:]
