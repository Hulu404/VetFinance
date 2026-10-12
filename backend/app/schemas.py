"""API models. Money is int kopecks."""

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from engine.figure import Figure as EngineFigure


class FigureItemOut(BaseModel):
    label: str
    value: int
    unit: Literal["rub", "pct", "count", "days"] = "rub"


class FigureOut(BaseModel):
    value: int
    unit: Literal["rub", "pct", "count", "days"]
    breakdown: list[FigureItemOut]
    source: list[Literal["bank", "vetmanager", "bot", "manual", "calc"]]
    note: str


def figure_out(f: EngineFigure) -> FigureOut:
    return FigureOut.model_validate(
        {
            "value": f.value,
            "unit": f.unit,
            "breakdown": [
                {"label": i.label, "value": i.value, "unit": i.unit} for i in f.breakdown
            ],
            "source": list(f.source),
            "note": f.note,
        }
    )


class ClinicOut(BaseModel):
    id: str
    name: str
    legal_entity: str | None
    tax_regime: str | None
    timezone: str
    safe_balance: int


class ClinicPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_entity: str | None = Field(default=None, max_length=300)
    tax_regime: str | None = Field(default=None, max_length=100)
    timezone: str | None = None
    safe_balance: StrictInt | None = Field(default=None, ge=0)

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


class DashboardBalanceOut(BaseModel):
    total: FigureOut
    bank: FigureOut


class DashboardOut(BaseModel):
    as_of: date
    data_as_of: datetime | None
    data_stale: bool
    balance: DashboardBalanceOut
