"""API models of the acquiring reconciliation and of the connections."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import FigureOut
from app.schemas_tx import NamedRefOut

AcquiringStatus = Literal["matched", "mismatch", "waiting", "no_statement", "no_payments"]
MAX_NOTE = 200


class SettlementDaysOut(BaseModel):
    min: int
    max: int


class AcquiringMemberOut(BaseModel):
    date: dt.date
    card_payments: FigureOut
    commission: FigureOut
    expected: FigureOut


class AcquiringRowOut(BaseModel):
    date: dt.date
    date_from: dt.date
    date_to: dt.date
    card_payments: FigureOut
    commission: FigureOut
    expected: FigureOut
    credited: FigureOut | None
    discrepancy: FigureOut | None
    status: AcquiringStatus
    expected_by: dt.date | None
    reviewed: bool
    members: list[AcquiringMemberOut]


class AcquiringSummaryOut(BaseModel):
    card_payments: FigureOut
    commission: FigureOut
    credited: FigureOut
    discrepancy: FigureOut
    waiting: FigureOut


class AcquiringOut(BaseModel):
    settlement_days: SettlementDaysOut
    rate_pct: float
    bank_covered_to: dt.date | None
    summary: AcquiringSummaryOut
    days: list[AcquiringRowOut]


class AcquiringPaymentOut(BaseModel):
    date: dt.date
    description: str
    amount: int


class AcquiringCreditOut(BaseModel):
    date: dt.date
    description: str
    amount: int
    transaction_id: str | None


class ReviewOut(BaseModel):
    reviewed: bool
    note: str | None


class AcquiringDayOut(BaseModel):
    date_from: dt.date
    date_to: dt.date
    payments: list[AcquiringPaymentOut]
    credits: list[AcquiringCreditOut]
    review: ReviewOut


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=MAX_NOTE)


# ---------------------------------------------------------------- connections
class SyncRunOut(BaseModel):
    id: str
    status: Literal["running", "success", "partial", "failed"]
    started_at: dt.datetime
    finished_at: dt.datetime | None
    error_code: Literal["invalid_key", "unreachable", "rate_limited", "unknown"] | None
    counts: FigureOut | None


class ScheduleOut(BaseModel):
    kind: Literal["nightly"]
    time: str


class BankAccountStatusOut(BaseModel):
    account: NamedRefOut
    last_statement_to: dt.date | None


class BankInfoOut(BaseModel):
    accounts: list[BankAccountStatusOut]


class ConnectionOut(BaseModel):
    id: str
    type: Literal["vetmanager", "bank"]
    connected: bool
    address: str | None
    key_hint: str | None
    schedule: ScheduleOut | None
    data_stale: bool
    last_success_at: dt.datetime | None
    last_run: SyncRunOut | None
    runs: list[SyncRunOut]
    bank: BankInfoOut | None


class ConnectionsOut(BaseModel):
    items: list[ConnectionOut]
    next_cursor: str | None = None


class RunStartedOut(BaseModel):
    run: SyncRunOut


class VetmanagerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=1, max_length=300)
    key: str | None = Field(default=None, min_length=1, max_length=300, repr=False)


class VetmanagerImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: dict[str, dict[str, object]]
