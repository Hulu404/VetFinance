"""Validation of the request bodies of stage 5 (docs/api-contract.md, "Прайс услуг", "Аналитика").

Bodies arrive as raw JSON; every problem is collected into `details.fields` {"items.0.qty": "must_be_positive"}.
Money is int kopecks. Numbers of the owner (percent, quantity, hours) are JSON numbers with a limited number of decimals.
"""

import re
from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.errors import ApiError, validation_fields
from engine.pricing import normalize_name  # noqa: F401  (re-exported)

NAME_MAX = 120
GROUP_MAX = 80
PRICE_MAX = 10_000_000_000  # kopecks: 100 000 000 roubles
RECIPE_ITEMS_MAX = 30
QTY_MAX = Decimal(1_000_000)
RECIPE_GROUPS = ("drugs", "anesthesia", "supplies")
MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class ServiceCreate:
    name: str
    group: str | None
    price: int


@dataclass(frozen=True)
class ServicePatch:
    name: str | None
    group: str | None
    price: int | None
    group_given: bool


@dataclass(frozen=True)
class RecipeLine:
    item_id: str
    group: str
    qty: Decimal


@dataclass(frozen=True)
class RecipeInput:
    minutes: int | None
    doctor_pct: Decimal | None
    items: tuple[RecipeLine, ...]


@dataclass(frozen=True)
class DoctorHours:
    id: str
    hours_per_week: Decimal | None


@dataclass(frozen=True)
class SettingsInput:
    avg_visit_minutes: int
    doctors: tuple[DoctorHours, ...]


def _fail(fields: dict[str, str]) -> None:
    if fields:
        raise validation_fields(fields)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _decimals(value: int | float) -> int:
    exponent = Decimal(str(value)).normalize().as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _text(
    body: dict[str, Any], key: str, limit: int, required: bool, fields: dict[str, str]
) -> str | None:
    value = body.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            fields[key] = "required"
        return None
    if not isinstance(value, str):
        fields[key] = "invalid"
        return None
    value = value.strip()
    if len(value) > limit:
        fields[key] = "too_long"
        return None
    return value


def _price(body: dict[str, Any], fields: dict[str, str]) -> int | None:
    value = body.get("price")
    if value is None:
        fields["price"] = "required"
    elif not _is_int(value):
        fields["price"] = "invalid"
    elif value <= 0:
        fields["price"] = "must_be_positive"
    elif value > PRICE_MAX:
        fields["price"] = "too_large"
    else:
        return int(value)
    return None


def _object(
    body: Any, allowed: Collection[str], prefix: str, fields: dict[str, str]
) -> dict[str, Any]:
    if not isinstance(body, dict):
        fields[prefix.rstrip(".") or "body"] = "invalid"
        return {}
    for key in body:
        if key not in allowed:
            fields[f"{prefix}{key}"] = "unknown_field"
    return body


def parse_service_create(body: Any) -> ServiceCreate:
    fields: dict[str, str] = {}
    data = _object(body, ("name", "group", "price"), "", fields)
    name = _text(data, "name", NAME_MAX, True, fields)
    group = _text(data, "group", GROUP_MAX, False, fields)
    price = _price(data, fields)
    _fail(fields)
    assert name is not None and price is not None  # noqa: S101 (checked by _fail)
    return ServiceCreate(name, group, price)


def parse_service_patch(body: Any) -> ServicePatch:
    fields: dict[str, str] = {}
    data = _object(body, ("name", "group", "price"), "", fields)
    name = _text(data, "name", NAME_MAX, True, fields) if "name" in data else None
    group = _text(data, "group", GROUP_MAX, False, fields) if "group" in data else None
    price = _price(data, fields) if "price" in data else None
    _fail(fields)
    return ServicePatch(name, group, price, "group" in data)


def _qty(value: Any, key: str, fields: dict[str, str]) -> Decimal | None:
    if value is None:
        fields[key] = "required"
    elif not _is_number(value):
        fields[key] = "invalid"
    elif value <= 0:
        fields[key] = "must_be_positive"
    elif _decimals(value) > 3:
        fields[key] = "too_many_decimals"
    elif Decimal(str(value)) > QTY_MAX:
        fields[key] = "too_large"
    else:
        return Decimal(str(value))
    return None


def _recipe_lines(
    raw: Any, known_items: Collection[str], fields: dict[str, str]
) -> tuple[RecipeLine, ...]:
    if raw is None:
        fields["items"] = "required"
        return ()
    if not isinstance(raw, list):
        fields["items"] = "invalid"
        return ()
    if len(raw) > RECIPE_ITEMS_MAX:
        fields["items"] = "out_of_range"
    lines: list[RecipeLine] = []
    seen: set[str] = set()
    for n, row in enumerate(raw[:RECIPE_ITEMS_MAX]):
        prefix = f"items.{n}."
        data = _object(row, ("item_id", "group", "qty"), prefix, fields)
        item_id, group = data.get("item_id"), data.get("group")
        if not item_id:
            fields[f"{prefix}item_id"] = "required"
        elif not isinstance(item_id, str):
            fields[f"{prefix}item_id"] = "invalid"
        elif item_id in seen:
            fields[f"{prefix}item_id"] = "duplicate_item"
        elif item_id not in known_items:
            fields[f"{prefix}item_id"] = "unknown_item"
        if group is None:
            fields[f"{prefix}group"] = "required"
        elif group not in RECIPE_GROUPS:
            fields[f"{prefix}group"] = "invalid"
        qty = _qty(data.get("qty"), f"{prefix}qty", fields)
        if isinstance(item_id, str):
            seen.add(item_id)
        if qty is not None and isinstance(item_id, str) and group in RECIPE_GROUPS:
            lines.append(RecipeLine(item_id, group, qty))
    return tuple(lines)


def parse_recipe(body: Any, known_items: Collection[str]) -> RecipeInput:
    fields: dict[str, str] = {}
    data = _object(body, ("minutes", "doctor_pct", "items"), "", fields)
    minutes = data.get("minutes")
    if minutes is not None:
        if not _is_int(minutes):
            fields["minutes"] = "invalid"
        elif not 1 <= minutes <= 1440:
            fields["minutes"] = "out_of_range"
    pct = data.get("doctor_pct")
    doctor_pct: Decimal | None = None
    if pct is not None:
        if not _is_number(pct):
            fields["doctor_pct"] = "invalid"
        elif not 0 <= pct <= 100:
            fields["doctor_pct"] = "out_of_range"
        elif _decimals(pct) > 2:
            fields["doctor_pct"] = "too_many_decimals"
        else:
            doctor_pct = Decimal(str(pct))
    lines = _recipe_lines(data.get("items"), known_items, fields)
    _fail(fields)
    return RecipeInput(minutes if _is_int(minutes) else None, doctor_pct, lines)


HOURS_STEP = Decimal("0.5")


def _hours(value: Any, key: str, fields: dict[str, str]) -> Decimal | None:
    if value is None:
        return None
    if not _is_number(value):
        fields[key] = "invalid"
    elif not 0 <= value <= 80:
        fields[key] = "out_of_range"
    elif _decimals(value) > 1:
        fields[key] = "too_many_decimals"
    elif Decimal(str(value)) % HOURS_STEP != 0:
        fields[key] = "invalid"
    else:
        return Decimal(str(value))
    return None


def parse_settings(body: Any, known_doctors: Collection[str]) -> SettingsInput:
    fields: dict[str, str] = {}
    data = _object(body, ("avg_visit_minutes", "doctors"), "", fields)
    minutes = data.get("avg_visit_minutes")
    if minutes is None:
        fields["avg_visit_minutes"] = "required"
    elif not _is_int(minutes):
        fields["avg_visit_minutes"] = "invalid"
    elif not 5 <= minutes <= 240:
        fields["avg_visit_minutes"] = "out_of_range"
    raw = data.get("doctors")
    doctors: list[DoctorHours] = []
    if raw is not None and not isinstance(raw, list):
        fields["doctors"] = "invalid"
    seen: set[str] = set()
    for n, row in enumerate(raw if isinstance(raw, list) else []):
        prefix = f"doctors.{n}."
        entry = _object(row, ("id", "hours_per_week"), prefix, fields)
        doctor_id = entry.get("id")
        if not doctor_id:
            fields[f"{prefix}id"] = "required"
        elif not isinstance(doctor_id, str) or doctor_id in seen or doctor_id not in known_doctors:
            fields[f"{prefix}id"] = "invalid"
        hours = _hours(entry.get("hours_per_week"), f"{prefix}hours_per_week", fields)
        if isinstance(doctor_id, str):
            seen.add(doctor_id)
            doctors.append(DoctorHours(doctor_id, hours))
    _fail(fields)
    return SettingsInput(int(minutes), tuple(doctors))  # type: ignore[arg-type]


def parse_month(value: str | None) -> str | None:
    """'2026-09' or None; anything else is `invalid`."""
    if value is None:
        return None
    if not MONTH_RE.match(value):
        raise validation_fields({"month": "invalid"})
    return value


def month_in_future(month: str, last_closed: str) -> ApiError | None:
    """A month later than the last closed one cannot be shown: its expenses are not complete."""
    if month > last_closed:
        return validation_fields({"month": "in_future"})
    return None
