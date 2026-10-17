"""API models of stage 4: payment calendar, obligations, counterparty terms (docs/api-contract.md, "Планирование").

Money is int kopecks, every amount is a Figure. `rate_pct` of an obligation is an input of the owner and the only
percentage that is a plain number (up to two decimals).
"""

from datetime import date as Day
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.schemas import FigureOut
from app.schemas_dash import WhyOut

Weekday = Literal["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
DayStatus = Literal["ok", "below_safe", "below_zero"]
ObligationStatus = Literal["active", "paid", "closed"]
PaymentSource = Literal["recurring", "obligation", "manual"]
CalendarStatus = Literal["ok", "partial", "empty"]
CalendarReason = Literal["short_history", "obligations_missing", "no_bank"]


def _is_none(value: object) -> bool:
    return value is None


class CategoryRefOut(BaseModel):
    id: str
    name: str


class CounterpartyRefOut(BaseModel):
    id: str  # opaque: the INN, or a key made of the name when the statement has no INN
    name: str


class WindowOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: Day = Field(alias="from")
    to: Day


class PaymentOut(BaseModel):
    id: str  # opaque; stable for the same data and as_of; manual payments: uuid
    name: str
    category: CategoryRefOut | None
    counterparty: CounterpartyRefOut | None  # recurring payments only
    amount: FigureOut
    source: PaymentSource
    balance_after: FigureOut
    max_deferral_days: int  # how many days the payment may be deferred (0: not movable)
    moved_from: Day | None = Field(default=None, exclude_if=_is_none)  # only in ?preview=


class DayOut(BaseModel):
    date: Day
    weekday: Weekday
    opening: FigureOut
    income_forecast: FigureOut
    payments: list[PaymentOut]  # by amount descending, then by name
    closing: FigureOut
    status: DayStatus
    note: str


class LowestOut(BaseModel):
    date: Day
    balance: FigureOut
    status: DayStatus


class CalendarSummaryOut(BaseModel):
    income: FigureOut
    expense: FigureOut
    payments_count: int
    lowest: LowestOut


class MoveSuggestionOut(BaseModel):
    id: str  # opaque; accepted by GET /v1/calendar?preview=
    payment_id: str
    payment_name: str
    amount: FigureOut
    from_date: Day
    to_date: Day
    delay_days: int
    closes_gap: bool  # false: a partial suggestion, the gap becomes smaller but stays
    lowest_after: FigureOut
    text: str


class CalendarAlertOut(BaseModel):
    id: str
    date: Day  # first red day of the run
    date_to: Day  # last red day of the run
    severity: Literal["alert", "warning"]
    icon: str
    title: str
    text: str  # without the suggestion; the client appends suggestion.text
    shortfall: FigureOut
    suggestion: MoveSuggestionOut | None
    why: WhyOut


class PreviewOut(BaseModel):
    suggestion_id: str
    payment_id: str
    from_date: Day
    to_date: Day


class CalendarOut(BaseModel):
    as_of: Day
    data_as_of: datetime | None
    window: WindowOut
    status: CalendarStatus
    partial_reasons: list[CalendarReason]
    history_days: int
    start_balance: FigureOut
    safe_balance: FigureOut
    safe_balance_set: bool
    preview: PreviewOut | None
    summary: CalendarSummaryOut
    alerts: list[CalendarAlertOut]  # one per run of red days, by date, at most 3
    days: list[DayOut]  # 22 days from as_of


class ManualPaymentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    amount: StrictInt
    date: Day
    category_id: str | None = None
    max_deferral_days: StrictInt = 0


class ManualPaymentOut(BaseModel):
    id: str
    date: Day
    name: str
    category: CategoryRefOut | None
    amount: FigureOut
    source: Literal["manual"] = "manual"
    max_deferral_days: int


# ------------------------------------------------------------------ obligations
class LoanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["loan"]
    name: str
    lender: str | None = None
    principal: StrictInt
    remaining: StrictInt
    rate_pct: float
    payment: StrictInt
    payment_day: StrictInt


class LeaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["lease"]
    name: str
    lender: str | None = None
    principal: StrictInt  # all payments of the contract together
    remaining: StrictInt  # payments still to pay
    payment: StrictInt
    payment_day: StrictInt


class EquipmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["equipment"]
    name: str
    cost: StrictInt
    in_service_from: Day
    life_years: StrictInt


class LoanOut(BaseModel):
    id: str
    kind: Literal["loan", "lease"]
    name: str
    lender: str | None
    principal: FigureOut
    remaining: FigureOut
    paid_pct: FigureOut
    payment: FigureOut
    rate_pct: float | None  # loans only
    payment_day: int
    next_payment_date: Day | None  # null when paid off
    last_payment_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    status: ObligationStatus  # paid: paid off / past its term; closed: closed by DELETE
    closed_from: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class EquipmentOut(BaseModel):
    id: str
    kind: Literal["equipment"] = "equipment"
    name: str
    cost: FigureOut
    life_years: int
    in_service_from: Day
    amortization_from: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amortization_to: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    monthly: FigureOut
    status: ObligationStatus  # paid: paid off / past its term; closed: closed by DELETE
    closed_from: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class PnlMonthOut(BaseModel):
    month: str
    amount: FigureOut


class ObligationsOut(BaseModel):
    as_of: Day
    debt_total: FigureOut
    monthly_payment: FigureOut
    monthly_payment_share_pct: FigureOut | None = Field(default=None, exclude_if=_is_none)
    amortization_month: FigureOut
    pnl_month: PnlMonthOut
    loans: list[LoanOut]  # active first, then paid off
    equipment: list[EquipmentOut]


# ------------------------------------------------------------------ counterparties
class CounterpartyOut(BaseModel):
    id: str
    name: str
    max_deferral_days: int


class CounterpartyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_deferral_days: StrictInt
