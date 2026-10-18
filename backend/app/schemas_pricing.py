"""API models of stage 5: price list, service cost, techcard, efficiency (docs/api-contract.md, "Прайс услуг", "Аналитика").

Money is int kopecks, every metric is a Figure. Plain numbers are only inputs of the owner (the techcard, hours of
doctors, the average visit length), they are not metrics.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import FigureOut
from app.schemas_reports import PeriodOut

ServiceStatus = Literal["ok", "no_recipe", "partial"]
ServiceSource = Literal["vetmanager", "manual"]
PriceSource = Literal["sales", "manual"]
MinutesSource = Literal["own", "clinic_average"]
MissingCode = Literal["recipe", "hour_cost", "item_no_cost", "no_expenses"]
PartKey = Literal["doctor_pay", "drugs", "anesthesia", "supplies", "acquiring", "fixed", "taxes"]
RecipeGroup = Literal["drugs", "anesthesia", "supplies"]
LoadBy = Literal["rooms", "doctors"]
EfficiencyStatus = Literal["ok", "partial", "empty"]
EfficiencyReason = Literal["no_doctor_hours", "no_expenses"]
HourPartKey = Literal["hours", "busy_hours", "fixed", "obligations"]

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def _is_none(value: object) -> bool:
    return value is None


# ------------------------------------------------------------------ price list
class ServiceItemOut(BaseModel):
    id: str
    name: str
    group: str | None
    unit_label: str  # "раз" | "сутки"
    source: ServiceSource
    price: FigureOut
    visits_month: FigureOut  # how many times the service was provided in the basis month
    margin_pct: FigureOut | None  # null without a techcard
    monthly_profit: FigureOut | None  # null without a techcard
    status: ServiceStatus


class CountsOut(BaseModel):
    all: int
    loss: int
    no_recipe: int


class ServicesOut(BaseModel):
    basis_month: str = Field(pattern=MONTH_PATTERN)
    headline: str | None = Field(
        default=None, exclude_if=_is_none
    )  # omitted when there are no services
    counts: CountsOut
    items: list[ServiceItemOut]
    next_cursor: str | None


class ServiceRefOut(BaseModel):
    id: str
    name: str
    group: str | None
    unit_label: str
    source: ServiceSource
    price_source: PriceSource


class PartOut(BaseModel):
    key: PartKey
    label: str
    amount: FigureOut | None  # null: the part is not filled (no techcard, no hour cost)
    share_pct: FigureOut | None


class ServiceCostOut(BaseModel):
    service: ServiceRefOut
    status: ServiceStatus
    missing: list[MissingCode]
    basis_month: str = Field(pattern=MONTH_PATTERN)
    minutes: int  # the time of the service in the cabinet that is used in `fixed`
    minutes_source: MinutesSource
    price: FigureOut
    net_profit: FigureOut | None
    net_margin_pct: FigureOut | None
    parts: list[PartOut]  # seven, in the order of PartKey
    visits_month: FigureOut
    monthly_profit: FigureOut | None


# ------------------------------------------------------------------ service bodies (documentation of the request)
class ServiceCreateBody(BaseModel):
    name: str = Field(max_length=120)
    group: str | None = Field(default=None, max_length=80)
    price: int = Field(description="kopecks, more than 0")


class ServicePatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    group: str | None = Field(default=None, max_length=80)
    price: int | None = Field(default=None, description="kopecks, more than 0")


# ------------------------------------------------------------------ techcard
class RecipeServiceOut(BaseModel):
    id: str
    name: str


class RecipeItemOut(BaseModel):
    item_id: str
    name: str
    unit: str
    group: RecipeGroup
    qty: float
    unit_cost: FigureOut | None


class RecipeDefaultsOut(BaseModel):
    minutes: FigureOut  # the average visit length of the clinic
    doctor_pct: FigureOut | None  # null while the P&L has no percent to doctors


class RecipeOut(BaseModel):
    service: RecipeServiceOut
    has_recipe: bool  # false: no techcard is saved, the service is `no_recipe`
    minutes: int | None  # null: the average visit length of the clinic is used
    doctor_pct: float | None  # null: the clinic average is used
    items: list[RecipeItemOut]
    defaults: RecipeDefaultsOut


class RecipeItemBody(BaseModel):
    item_id: str
    group: RecipeGroup
    qty: float = Field(gt=0, description="up to three decimals")


class RecipeBody(BaseModel):
    minutes: int | None = Field(default=None, ge=1, le=1440)
    doctor_pct: float | None = Field(default=None, ge=0, le=100, description="up to two decimals")
    items: list[RecipeItemBody] = Field(max_length=30)


# ------------------------------------------------------------------ stock items for the techcard form
class StockItemOut(BaseModel):
    id: str
    name: str
    unit: str
    unit_cost: FigureOut | None  # null: no purchase price, the item is not counted


class StockItemsOut(BaseModel):
    items: list[StockItemOut]
    next_cursor: str | None


# ------------------------------------------------------------------ efficiency
class RoomLoadOut(BaseModel):
    id: str
    name: str
    load_pct: FigureOut
    busy_hours: FigureOut
    available_hours: FigureOut
    free_hours: FigureOut


class DoctorLoadOut(BaseModel):
    id: str
    name: str
    visits: FigureOut
    load_pct: FigureOut | None  # null: no hours per week
    busy_hours: FigureOut | None
    available_hours: FigureOut | None
    free_hours: FigureOut | None


class HourPartOut(BaseModel):
    key: HourPartKey
    label: str
    figure: FigureOut


class EfficiencyOut(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN)
    as_of: date
    data_as_of: datetime | None
    period: PeriodOut
    status: EfficiencyStatus
    partial_reasons: list[EfficiencyReason]
    headline: str | None = Field(default=None, exclude_if=_is_none)  # omitted when status = empty
    load_by: LoadBy
    visits: FigureOut
    load_pct: FigureOut | None
    avg_check: FigureOut | None
    rooms: list[RoomLoadOut]  # empty in the fallback mode
    doctors: list[DoctorLoadOut]  # empty in the rooms mode
    hour_cost: FigureOut | None
    hour_margin: FigureOut | None
    hour_cost_parts: list[HourPartOut]  # empty while there is no hour cost


class DoctorHoursOut(BaseModel):
    id: str
    name: str
    hours_per_week: float | None


class EfficiencySettingsOut(BaseModel):
    avg_visit_minutes: int
    doctors: list[DoctorHoursOut]


class DoctorHoursBody(BaseModel):
    id: str
    hours_per_week: float | None = Field(default=None, ge=0, le=80, description="step 0.5")


class EfficiencySettingsBody(BaseModel):
    avg_visit_minutes: int = Field(ge=5, le=240)
    doctors: list[DoctorHoursBody] | None = None
