"""Input rows of the dashboard engine (stage 2). Plain frozen dataclasses: no database, no network."""

from dataclasses import dataclass
from datetime import date

SALE_EXEC = "exec"  # closed invoice: counts as revenue
SALE_DRAFT = "save"  # draft: not revenue
LINE_SERVICE = "service"
LINE_GOOD = "good"


@dataclass(frozen=True)
class SaleLineInput:
    kind: str  # "service" | "good"
    amount: int  # kopecks


@dataclass(frozen=True)
class SaleInput:
    date: date
    status: str  # "exec" | "save"
    lines: tuple[SaleLineInput, ...]


@dataclass(frozen=True)
class VisitInput:
    date: date
    doctor: str  # display name "Фамилия И."; never leaves the backend towards the AI layer


@dataclass(frozen=True)
class NormsInput:
    """Clinic norms until the `benchmarks` table exists (stage 3). Whole percents."""

    drugs_category: str
    drugs_max_pct: int
    margin_min_pct: int
