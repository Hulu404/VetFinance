"""Input rows of the report engines of stage 3 (P&L, norm, stock). Plain frozen dataclasses: no database, no network.

Transactions, sales and card payments reuse the inputs of earlier stages (`engine.balance.TransactionInput`,
`engine.dashboard_inputs.SaleInput`, `engine.acquiring.CardPayment`).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

TYPE_INCOME = "income"
TYPE_VARIABLE = "variable"
TYPE_FIXED = "fixed"
TYPE_TAX = "tax"
# obligation (a loan or lease payment), capex (equipment) and owner_draw are bank payments that are not
# costs of the period: the P&L takes interest and amortization from the obligation charges instead.
TYPE_OBLIGATION = "obligation"
TYPE_CAPEX = "capex"
TYPE_OWNER_DRAW = "owner_draw"

DIRECTION_SERVICES = "services"
DIRECTION_GOODS = "goods"

REASON_EXPIRED = "expired"
REASON_DAMAGED = "damaged"
REASON_OTHER = "other"


@dataclass(frozen=True)
class CategoryInput:
    name: str
    type: str  # TYPE_*
    norm_key: str | None = None  # row of the norm report the article belongs to
    direction: str | None = (
        None  # DIRECTION_*: direct costs of a direction (variable articles only)
    )
    norm_min_pct: Decimal | None = (
        None  # the clinic's own norm of the article, beats the industry one
    )
    norm_max_pct: Decimal | None = None
    payroll: bool = False  # salaries of employees: the "ФОТ (оклады)" child of the fixed costs
    in_service_recipes: bool = False  # stage 5: already inside the techcards, not in the hour cost
    doctor_percent: bool = False  # stage 5: "Проценты врачам"


@dataclass(frozen=True)
class ObligationChargeInput:
    month: str  # 'YYYY-MM'
    obligation_id: str
    name: str
    kind: str  # loan_interest | lease | amortization
    amount: int  # kopecks, the charge for the whole month


@dataclass(frozen=True)
class BenchmarkInput:
    key: str
    label: str
    kind: str  # expense | profit
    min_pct: Decimal | None
    max_pct: Decimal | None
    source: str  # description of the origin of the norm
    sort: int


@dataclass(frozen=True)
class WriteoffInput:
    date: date
    item: str
    qty: int
    amount: int  # kopecks, at the purchase price
    reason: str  # REASON_*


@dataclass(frozen=True)
class StockItemInput:
    id: str
    name: str
    last_movement: date | None  # last sale or write-off at a visit; None: unknown


@dataclass(frozen=True)
class StockBatchInput:
    item_id: str
    qty: int
    unit_cost: int  # kopecks per unit
    expires_on: date | None


@dataclass(frozen=True)
class ConsumptionInput:
    date: date
    amount: int  # kopecks at the purchase price: sales and use at visits
