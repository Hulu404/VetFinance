"""Input rows of the stage 5 engines (price list, service cost). Plain frozen dataclasses: no database, no network.

Sales, visits and stock items of earlier stages are reused where they carry what is needed
(`engine.dashboard_inputs.SaleInput`, `SaleLineInput`). The stock classes here are the PRICING view of the stock: exact
decimal quantities and the receipt date (the stock reports of stage 3 use whole units and have their own classes).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

PART_DRUGS = "drugs"
PART_ANESTHESIA = "anesthesia"
PART_SUPPLIES = "supplies"
LINE_KIND_MATERIALS = "materials"  # the fixed-cost article that is already inside the techcards


@dataclass(frozen=True)
class ManualServiceInput:
    id: str
    name: str
    price: int  # kopecks, entered by the owner


@dataclass(frozen=True)
class ServiceSettingInput:
    service_id: str
    name: str
    group: str | None
    minutes: int | None  # time in the cabinet; None: the clinic average
    doctor_pct_bp: (
        int | None
    )  # percent of the price to the doctor in basis points; None: the clinic average


@dataclass(frozen=True)
class TechcardLineInput:
    item_id: str
    qty: Decimal
    part: str  # PART_*


@dataclass(frozen=True)
class TechcardInput:
    service_id: str
    lines: tuple[
        TechcardLineInput, ...
    ]  # () is a recorded empty techcard; a missing record is "no techcard"


@dataclass(frozen=True)
class StockItemInput:
    id: str
    name: str
    unit: str
    last_movement: date | None = None


@dataclass(frozen=True)
class StockBatchInput:
    id: str
    item_id: str
    qty: Decimal  # numeric(14,3)
    unit_cost: int  # kopecks per unit
    received_on: date | None
    expires_on: date | None


@dataclass(frozen=True)
class PnlLineInput:
    name: str
    amount: int  # kopecks
    kind: str  # payroll | rent | marketing | other | materials for fixed lines


@dataclass(frozen=True)
class PnlMonthInput:
    """The totals of the P&L of one month that the stage 5 engines need (they come from engine/pnl.py)."""

    month: str  # 'YYYY-MM'
    revenue: int
    variable_total: int
    marginal_profit: int
    doctor_percent_payouts: int  # the article "Проценты врачам"
    acquiring_fee: int
    taxes: int
    fixed_lines: tuple[PnlLineInput, ...]
    obligation_lines: tuple[PnlLineInput, ...]
