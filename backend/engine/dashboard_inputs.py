"""Input rows of the dashboard engine (stage 2). Plain frozen dataclasses: no database, no network."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

SALE_EXEC = "exec"  # closed invoice: counts as revenue
SALE_DRAFT = "save"  # draft: not revenue
LINE_SERVICE = "service"
LINE_GOOD = "good"


@dataclass(frozen=True)
class SaleLineInput:
    kind: str  # "service" | "good"
    amount: int  # kopecks, after the discount
    # stage 5 (set by the Vetmanager loader; old rows have none)
    service_id: str | None = None  # external id of the service of a "service" line
    name: str = ""
    qty: int | Decimal = 1
    price: int = 0  # kopecks per unit before the discount
    doctor_id: str | None = None


@dataclass(frozen=True)
class SaleInput:
    date: date
    status: str  # "exec" | "save"
    lines: tuple[SaleLineInput, ...]
    id: str = ""


@dataclass(frozen=True)
class VisitInput:
    date: date
    doctor: str  # display name "Фамилия И."; never leaves the backend towards the AI layer
    doctor_id: str | None = None  # stage 5: the doctor of the visit; None: no doctor


@dataclass(frozen=True)
class NormsInput:
    """Clinic norms until the `benchmarks` table exists (stage 3). Whole percents."""

    drugs_category: str
    drugs_max_pct: int
    margin_min_pct: int
