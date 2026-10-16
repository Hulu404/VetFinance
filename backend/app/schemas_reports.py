"""API models of the stage 3 reports: P&L, norm, stock (docs/api-contract.md, "Отчёты").

Money is int kopecks, shares are numbers with one decimal, percentage points use unit `pp`.
Expense rows are positive numbers (kind = expense); profit and loss carry their sign.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import FigureItemOut, FigureOut

ReportStatus = Literal["ok", "partial", "empty"]
PartialReason = Literal[
    "no_vetmanager",
    "bank_gap",
    "short_period",
    "no_obligations",
    "no_benchmark",
    "missing_expiry",
    "short_history",
    "stale_stock",
]
Tone = Literal["good", "warn", "bad", "neutral"]


def _is_none(value: object) -> bool:
    return value is None


class PeriodOut(BaseModel):
    """`to` is null for a closed month; for a running month it is the last day of the data (`as_of`)."""

    model_config = ConfigDict(populate_by_name=True)

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    status: Literal["closed", "open"]
    from_: date = Field(alias="from")
    to: date | None
    first_month: str | None  # month of the earliest sale or transaction; null without data


# ------------------------------------------------------------------ P&L
class PnlRowOut(BaseModel):
    key: str  # revenue, variable, marginal_profit, fixed, taxes, obligations, net_profit; children: fixed_*
    label: str  # the total reads "Чистый убыток" when the month is a loss
    kind: Literal["revenue", "expense", "subtotal", "total", "child"]
    amount: FigureOut
    share_pct: FigureOut | None = Field(
        default=None, exclude_if=_is_none
    )  # omitted without revenue
    warning: Literal["no_obligations"] | None = Field(default=None, exclude_if=_is_none)
    children: list["PnlRowOut"] | None = Field(default=None, exclude_if=_is_none)  # only `fixed`


class PnlDirectionOut(BaseModel):
    direction: Literal["services", "goods"]
    label: str
    revenue: FigureOut
    revenue_share_pct: FigureOut
    direct_costs: FigureOut
    margin: FigureOut
    margin_pct: FigureOut


class PnlOut(BaseModel):
    month: str
    view: Literal["clinic", "direction"]
    as_of: date
    data_as_of: datetime | None
    period: PeriodOut
    status: ReportStatus
    partial_reasons: list[PartialReason]
    headline: str | None = Field(default=None, exclude_if=_is_none)  # omitted when status = empty
    rows: list[PnlRowOut]  # the same rows in both views
    unclassified: FigureOut  # amount of operations without a category (inside "fixed")
    unclassified_count: int
    directions: list[PnlDirectionOut] | None = Field(default=None, exclude_if=_is_none)
    common_variable: FigureOut | None = Field(default=None, exclude_if=_is_none)  # view=direction


# ------------------------------------------------------------------ norm
class NormBoundsOut(BaseModel):
    min_pct: float | None  # either border may be null ("до 0,8%", "от 12%")
    max_pct: float | None
    source: Literal["industry", "clinic"]
    breakdown: list[FigureItemOut] | None = Field(default=None, exclude_if=_is_none)
    note: str | None = Field(default=None, exclude_if=_is_none)


class NormItemOut(BaseModel):
    key: str
    label: str
    kind: Literal["expense", "other", "profit"]
    memo: bool  # a reference row, not part of the 100% (write-off by expiry date)
    # status and tone are absent in a running month: the norm is not assessed until the month is over
    status: Literal["ok", "above", "below", "no_norm"] | None = Field(
        default=None, exclude_if=_is_none
    )
    tone: Tone | None = Field(default=None, exclude_if=_is_none)
    norm: NormBoundsOut | None = Field(default=None, exclude_if=_is_none)  # omitted for no_norm
    actual_pct: FigureOut  # unit pct; breakdown in roubles = the articles the share is made of
    deviation_pp: FigureOut | None = Field(default=None, exclude_if=_is_none)  # unit pp, delta
    deviation_rub: FigureOut | None = Field(default=None, exclude_if=_is_none)  # unit rub, delta


class NormOut(BaseModel):
    month: str
    as_of: date
    data_as_of: datetime | None
    period: PeriodOut
    status: ReportStatus
    partial_reasons: list[PartialReason]
    headline: str | None = Field(default=None, exclude_if=_is_none)
    items: list[NormItemOut]


# ------------------------------------------------------------------ stock
class AtRiskOut(BaseModel):
    qty: int
    amount: FigureOut


class ExpiringRowOut(BaseModel):
    item: str
    expires_on: date
    days_left: int  # 0 = expires today; negative only in `expired_items`
    qty: int
    amount: FigureOut
    at_risk: AtRiskOut | None = Field(
        default=None, exclude_if=_is_none
    )  # reserved, see the contract


class IdleBucketOut(BaseModel):
    key: Literal["60_89", "90_179", "180_plus"]
    label: str
    amount: FigureOut
    positions: FigureOut  # unit count


class WrittenOffRowOut(BaseModel):
    item: str
    date: date
    qty: int
    reason: Literal["expired", "damaged", "other"]
    amount: FigureOut


class StockOut(BaseModel):
    as_of: date
    data_as_of: datetime | None
    month: str  # the month of `written_off_*`
    status: ReportStatus
    partial_reasons: list[PartialReason]
    headline: str | None = Field(default=None, exclude_if=_is_none)
    stock_value: FigureOut
    frozen: FigureOut
    frozen_positions: FigureOut
    idle_buckets: list[IdleBucketOut]
    expiring_60d: FigureOut
    expiring_at_risk: FigureOut | None = Field(default=None, exclude_if=_is_none)  # reserved
    expiring: list[ExpiringRowOut]
    expired_on_hand: FigureOut
    expired_items: list[ExpiringRowOut]
    written_off_month: FigureOut
    written_off_norm: FigureOut
    written_off_items: list[WrittenOffRowOut]
    turnover_days: FigureOut
    norm_turnover_days: int
    missing_expiry_count: int | None = Field(default=None, exclude_if=_is_none)  # reserved


class IdleItemOut(BaseModel):
    item: str
    last_movement_on: date
    idle_days: int
    bucket: Literal["60_89", "90_179", "180_plus"]
    qty: int
    amount: FigureOut


class StockIdleOut(BaseModel):
    items: list[IdleItemOut]
    next_cursor: str | None
    total: FigureOut  # unit count: positions of the requested bucket
