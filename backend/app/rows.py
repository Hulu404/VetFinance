"""Row types returned by the data layer. Plain frozen dataclasses, ids are strings."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class ClinicRow:
    id: str
    name: str
    legal_entity: str | None
    tax_regime: str | None
    timezone: str
    safe_balance: int


@dataclass(frozen=True)
class AccountRow:
    id: str
    name: str
    kind: str  # "bank" | "cash"
    opening_balance: int
    opening_date: date
    number: str | None
    last_statement_to: date | None


@dataclass(frozen=True)
class CategoryRow:
    id: str
    name: str
    type: str  # income | variable | fixed | tax | obligation | capex | owner_draw
    norm_min_pct: float | None
    norm_max_pct: float | None
    norm_key: str | None = None  # row of the norm report the article belongs to
    direction: str | None = None  # services | goods: direct costs of a direction
    payroll: bool = False  # salaries of employees


@dataclass(frozen=True)
class RuleRow:
    id: str
    match: str  # "inn" | "text"
    value: str
    display_name: str | None
    direction: str | None
    category_id: str
    category_name: str
    created_at: datetime


@dataclass(frozen=True)
class TxRow:
    id: str
    date: date
    description: str
    amount: int
    kind: str
    source: str
    status: str
    account_id: str
    account_name: str
    category_id: str | None
    category_name: str | None
    category_source: str | None
    rule_id: str | None
    counterparty_inn: str
    counterparty_name: str
    duplicate_of: str | None
    duplicate_state: str | None
    duplicate_dismissed: bool
    created_at: datetime


@dataclass(frozen=True)
class NewTx:
    account_id: str
    date: date
    description: str
    amount: int
    kind: str
    source: str
    status: str
    external_id: str | None
    category_id: str | None
    category_source: str | None
    rule_id: str | None
    counterparty_inn: str = ""
    counterparty_name: str = ""
    doc_number: str | None = None
    transfer_group: str | None = None
    duplicate_of: str | None = None
    duplicate_state: str | None = None
    import_id: str | None = None
    dedup_hash: str | None = None


@dataclass(frozen=True)
class SummaryRow:
    date: date
    amount: int
    kind: str
    status: str
    category: str | None
    source: str


@dataclass(frozen=True)
class ConnectionRow:
    id: str
    type: str  # "vetmanager" | "bank"
    address: str | None
    key_hint: str | None


@dataclass(frozen=True)
class SyncRunRow:
    id: str
    connection_id: str
    status: str  # "running" | "success" | "partial" | "failed"
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    counts: dict[str, Any] | None  # {"new": int, "updated": int, "skipped_duplicates": int}


@dataclass(frozen=True)
class CardPaymentRow:
    date: date
    amount: int
    invoice_external_id: str | None


@dataclass(frozen=True)
class ReviewRow:
    sale_date: date
    note: str | None
