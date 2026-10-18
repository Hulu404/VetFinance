"""Helpers for make_pricing_examples.py: ids, Figure dicts and Russian number formats (display only, no business logic).

The numbers come from tests/golden/set06/expected.json (read only); nothing is recomputed here except the display
percentages of notes, which use engine/money.py.
"""

import json
import sys
import uuid
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from engine.figure import SOURCE_ORDER  # noqa: E402
from engine.money import NBSP, format_pct, format_rub, pct_one_decimal  # noqa: E402

SET06 = ROOT / "tests" / "golden" / "set06"
DATA: dict[str, Any] = json.loads((SET06 / "data.json").read_text(encoding="utf-8"))
EXPECTED: dict[str, Any] = json.loads((SET06 / "expected.json").read_text(encoding="utf-8"))
NAMESPACE = uuid.UUID("5e7c0a06-0000-4000-8000-000000000006")
PNL = DATA["pnl_month"]
MONTH_LABEL = "сентябрь 2026"
PART_LABELS = {
    "doctor_pay": "ЗП врача",
    "drugs": "Препараты",
    "anesthesia": "Анестезия",
    "supplies": "Расходники",
    "acquiring": "Эквайринг",
    "fixed": "Постоянные",
    "taxes": "Налоги и взносы",
}
PART_KEYS = list(PART_LABELS)
DAYS_UNIT = {"S6": "сутки"}


def sid(key: str) -> str:
    """Stable opaque id of an example object (service S4, doctor D1, item i05 ...)."""
    return str(uuid.uuid5(NAMESPACE, key))


def money(kopecks: int) -> str:
    return format_rub(kopecks)


def num(kopecks: int) -> str:
    """'1 168,06' without the rouble sign."""
    return format_rub(kopecks).replace(f"{NBSP}₽", "")


def pct(value: float) -> str:
    return format_pct(Decimal(str(value)))


def pct_of(part: int, whole: int) -> float:
    return float(pct_one_decimal(part, whole))


def item(label: str, value: int | float, unit: str = "rub") -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit}


def figure(
    value: int | float,
    unit: str,
    breakdown: list[dict[str, Any]],
    sources: list[str],
    note: str,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "value": value,
        "unit": unit,
        "breakdown": breakdown,
        "source": sorted(set(sources), key=SOURCE_ORDER.index),
        "note": note,
    }
    if details:
        out["details"] = details
    return out


def rub_fig(
    value: int, label: str, sources: list[str], note: str, details: Any = None
) -> dict[str, Any]:
    return figure(value, "rub", [item(label, value)], sources, note, details)


def count_fig(
    value: int, label: str, sources: list[str], note: str, details: Any = None
) -> dict[str, Any]:
    return figure(value, "count", [item(label, value, "count")], sources, note, details)


def unit_price_text(cost: Fraction) -> str:
    """'140 ₽' or '0,12375 ₽' for a price per unit given in kopecks as a fraction."""
    rub = Decimal(cost.numerator) / Decimal(cost.denominator) / 100
    text = f"{rub:,.4f}".rstrip("0").rstrip(".").replace(",", NBSP).replace(".", ",")
    return f"{text}{NBSP}₽"


def qty_text(qty: str) -> str:
    return format(Decimal(qty).normalize(), "f").replace(".", ",")


def fraction(text: str | None) -> Fraction | None:
    return None if text is None else Fraction(text)
