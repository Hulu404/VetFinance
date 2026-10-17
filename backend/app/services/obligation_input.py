"""Validation of the bodies of POST and PATCH /v1/obligations (docs/api-contract.md, "Обязательства").

Pure functions: they turn a JSON body into per-field reason codes. The interest check uses engine/money.py.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError

from app.errors import ApiError, validation_fields
from app.schemas_planning import EquipmentBody, LeaseBody, LoanBody
from engine.money import div_round, pct_to_rate_bp

NAME_MAX = 80
MONEY_MAX = 10**12  # kopecks: 10 billion roubles
MONTHLY_RATE_DIVISOR = 12 * 10_000  # interest of a month = remaining x rate_bp / (12 x 10 000)
BODIES: dict[str, type[BaseModel]] = {
    "loan": LoanBody,
    "lease": LeaseBody,
    "equipment": EquipmentBody,
}
MONEY_FIELDS = ("principal", "remaining", "payment", "cost")
PYDANTIC_REASONS = {
    "missing": "required",
    "string_too_short": "required",
    "extra_forbidden": "unknown_field",
}


class ObligationPatch(BaseModel):
    """Any subset of the fields of the three bodies; `kind` may only repeat the current one."""

    model_config = ConfigDict(extra="forbid")

    kind: str | None = None
    name: str | None = None
    lender: str | None = None
    principal: StrictInt | None = None
    remaining: StrictInt | None = None
    rate_pct: float | None = None
    payment: StrictInt | None = None
    payment_day: StrictInt | None = None
    cost: StrictInt | None = None
    in_service_from: date | None = None
    life_years: StrictInt | None = None


def _pydantic_fields(exc: ValidationError) -> dict[str, str]:
    fields: dict[str, str] = {}
    for e in exc.errors():
        name = ".".join(str(p) for p in e["loc"]) or "body"
        fields.setdefault(name, PYDANTIC_REASONS.get(e["type"], "invalid"))
    return fields


def _decimals_over_two(value: float) -> bool:
    exponent = Decimal(repr(value)).as_tuple().exponent
    return isinstance(exponent, int) and exponent < -2


def check_ranges(data: dict[str, Any], today: date) -> dict[str, str]:
    """Reason codes for values that have a type but break a rule of the contract."""
    fields: dict[str, str] = {}
    name = data.get("name")
    if isinstance(name, str):
        if not name.strip():
            fields["name"] = "required"
        elif len(name) > NAME_MAX:
            fields["name"] = "too_long"
    lender = data.get("lender")
    if isinstance(lender, str) and len(lender) > NAME_MAX:
        fields["lender"] = "too_long"
    for key in MONEY_FIELDS:
        value = data.get(key)
        if value is None:
            continue
        if value < 0 or (value == 0 and key != "remaining"):
            fields[key] = "must_be_positive"
        elif value > MONEY_MAX:
            fields[key] = "too_large"
    rate = data.get("rate_pct")
    if rate is not None:
        if rate < 0 or rate > 100:
            fields["rate_pct"] = "out_of_range"
        elif _decimals_over_two(rate):
            fields["rate_pct"] = "too_many_decimals"
    for key, low, high in (("payment_day", 1, 31), ("life_years", 1, 30)):
        value = data.get(key)
        if value is not None and not low <= value <= high:
            fields[key] = "out_of_range"
    served = data.get("in_service_from")
    if served is not None and served > today:
        fields["in_service_from"] = "in_future"
    return fields


def check_cross(data: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    """Rules that compare two fields. Returns reason codes and extra `details` (interest in kopecks)."""
    fields: dict[str, str] = {}
    extra: dict[str, Any] = {}
    principal, remaining = data.get("principal"), data.get("remaining")
    if principal is not None and remaining is not None and remaining > principal:
        fields["remaining"] = "remaining_gt_principal"
    rate, payment = data.get("rate_pct"), data.get("payment")
    if (
        remaining is not None
        and rate is not None
        and payment is not None
        and "payment" not in fields
    ):
        interest = div_round(remaining * pct_to_rate_bp(repr(rate)), MONTHLY_RATE_DIVISOR)
        if payment <= interest:
            fields["payment"] = "payment_below_interest"
            extra["interest"] = interest
    return fields, extra


def validate_create(body: object, today: date) -> dict[str, Any]:
    """Parsed body of POST, or ApiError 422 with `details.fields`."""
    if not isinstance(body, dict):
        raise validation_fields({"body": "invalid"})
    kind = body.get("kind")
    if kind is None:
        raise validation_fields({"kind": "required", **_unknown(body)})
    model = BODIES.get(kind) if isinstance(kind, str) else None
    if model is None:
        raise validation_fields({"kind": "invalid"})
    try:
        data = model.model_validate(body).model_dump()
    except ValidationError as exc:
        raise validation_fields(_pydantic_fields(exc)) from exc
    return _finish(data, today)


def validate_patch(body: object, current_kind: str, today: date) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise validation_fields({"body": "invalid"})
    try:
        data = ObligationPatch.model_validate(body).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise validation_fields(_pydantic_fields(exc)) from exc
    if data.pop("kind", current_kind) != current_kind:
        raise validation_fields({"kind": "invalid"})
    return _finish(data, today)


def _unknown(body: dict[str, Any]) -> dict[str, str]:
    allowed = set(ObligationPatch.model_fields)
    return {k: "unknown_field" for k in body if k not in allowed}


def _finish(data: dict[str, Any], today: date) -> dict[str, Any]:
    fields = check_ranges(data, today)
    cross, extra = check_cross({k: v for k, v in data.items() if k not in fields})
    fields.update(cross)
    if fields:
        error: ApiError = validation_fields(fields)
        error.details.update(extra)
        raise error
    return data
