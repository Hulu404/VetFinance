"""API models of the Transactions screen, category rules, categories and the bank statement import."""

import datetime as dt
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.schemas import FigureOut

Source = Literal["bank", "vetmanager", "bot", "manual"]
Kind = Literal["in", "out", "transfer"]
Status = Literal["ok", "check", "duplicate"]
MAX_AMOUNT_KOPECKS = 100_000_000 * 100  # 100 000 000 rub
MAX_COMMENT = 200


class NamedRefOut(BaseModel):
    id: str
    name: str


class SuggestionOut(BaseModel):
    category: NamedRefOut
    reason: Literal["rule", "similar"]
    text: str


class TransactionBriefOut(BaseModel):
    id: str
    date: dt.date
    description: str
    category: NamedRefOut | None
    account: NamedRefOut
    source: Source
    amount: int
    kind: Kind
    status: Status
    duplicate_state: Literal["pending", "confirmed"] | None
    figure: FigureOut


class TransactionOut(TransactionBriefOut):
    duplicate_of: TransactionBriefOut | None
    duplicate_reason: str | None
    suggestion: SuggestionOut | None


class CreatedRuleOut(BaseModel):
    id: str
    match_text: str
    category: NamedRefOut
    applied_count: int


class TransactionPatchedOut(TransactionOut):
    rule: CreatedRuleOut | None


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None


class TabCountsOut(BaseModel):
    all: int
    check: int
    duplicates: int


class SummaryOut(BaseModel):
    income: FigureOut
    expense: FigureOut
    balance: FigureOut


class RulePreviewOut(BaseModel):
    can_create: bool
    already_exists: bool
    match_text: str | None
    matches_count: int


class ResolveDuplicateOut(BaseModel):
    kept: list[TransactionOut]
    duplicates: list[TransactionOut]


class CategoryRuleOut(BaseModel):
    id: str
    match: Literal["inn", "text"]
    match_text: str
    direction: Literal["in", "out"] | None
    category: NamedRefOut
    applied_count: FigureOut
    created_at: dt.datetime


class CategoryRulesOut(BaseModel):
    items: list[CategoryRuleOut]
    next_cursor: str | None = None


class CategoryOut(BaseModel):
    id: str
    name: str
    type: Literal["income", "variable", "fixed"]
    norm_min_pct: float | None
    norm_max_pct: float | None


class CategoriesOut(BaseModel):
    items: list[CategoryOut]
    next_cursor: str | None = None


class PeriodOut(BaseModel):
    # `from` is a keyword: the field is exposed under its contract name
    model_config = ConfigDict(populate_by_name=True)

    from_: dt.date = Field(alias="from")
    to: dt.date


class ImportOut(BaseModel):
    import_id: str
    account: NamedRefOut
    period: PeriodOut
    loaded: int
    duplicates: int
    to_check: int
    already_loaded: int
    skipped: int


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["in", "out"]
    account_id: UUID
    category_id: UUID | None = None
    date: dt.date
    amount: int = Field(gt=0, le=MAX_AMOUNT_KOPECKS)
    comment: str | None = Field(default=None, max_length=MAX_COMMENT)


class TransactionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID
    create_rule: StrictBool = False


class ResolveDuplicateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keep_id: UUID | None = None
    keep_both: StrictBool = False
