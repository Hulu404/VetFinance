"""API models. Money is int kopecks."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
)

from engine.figure import Figure as EngineFigure
from engine.figure import FigureItem


def _is_empty(value: object) -> bool:
    """Optional keys are left out of the JSON when they carry nothing (None, False, empty list)."""
    return not value


class FigureItemOut(BaseModel):
    label: str
    value: int | float  # float only for pct and pp
    unit: Literal["rub", "pct", "pp", "count", "days"] = "rub"
    delta: bool | None = Field(default=None, exclude_if=_is_empty)  # a change; key omitted if not


class FigureOut(BaseModel):
    value: int | float  # int for rub/count/days, a number with one decimal for pct and pp
    unit: Literal["rub", "pct", "pp", "count", "days"]
    breakdown: list[FigureItemOut]
    source: list[Literal["bank", "vetmanager", "bot", "manual", "calc"]]
    note: str
    delta: bool | None = Field(default=None, exclude_if=_is_empty)
    details: list[FigureItemOut] | None = Field(default=None, exclude_if=_is_empty)


def _item_data(i: FigureItem) -> dict[str, Any]:
    value = float(i.value) if isinstance(i.value, Decimal) else i.value
    return {"label": i.label, "value": value, "unit": i.unit, "delta": i.delta or None}


def figure_out(f: EngineFigure) -> FigureOut:
    return FigureOut.model_validate(
        {
            "value": float(f.value) if isinstance(f.value, Decimal) else f.value,
            "unit": f.unit,
            "breakdown": [_item_data(i) for i in f.breakdown],
            "source": list(f.source),
            "note": f.note,
            "delta": f.delta or None,
            "details": [_item_data(i) for i in f.details] or None,
        }
    )


class ClinicOut(BaseModel):
    id: str
    name: str
    legal_entity: str | None
    tax_regime: str | None
    timezone: str
    safe_balance: int


SAFE_BALANCE_MAX = 10_000_000_000  # kopecks: 100 000 000 roubles


class ClinicPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_entity: str | None = Field(default=None, max_length=300)
    tax_regime: str | None = Field(default=None, max_length=100)
    timezone: str | None = None
    safe_balance: StrictInt | None = Field(default=None, ge=0, le=SAFE_BALANCE_MAX)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown timezone") from exc
        return v


class AccountOut(BaseModel):
    id: str
    name: str
    kind: Literal["bank", "cash"]
    opening_balance: int
    opening_date: date


class AccountsOut(BaseModel):
    items: list[AccountOut]
    next_cursor: str | None = None
