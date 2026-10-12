"""Figure: a number with its breakdown and source (see docs/api-contract.md)."""

from dataclasses import dataclass
from decimal import Decimal

SOURCE_ORDER = ("bank", "vetmanager", "bot", "manual", "calc")


@dataclass(frozen=True)
class FigureItem:
    label: str
    value: int
    unit: str = "rub"
    delta: bool = False  # the value is a change, not a summand of the total


@dataclass(frozen=True)
class Figure:
    value: int | Decimal  # int for rub/count/days; Decimal with one decimal for pct
    unit: str
    breakdown: tuple[FigureItem, ...]
    source: tuple[str, ...]
    note: str
    delta: bool = False  # the value is a change: the client shows a sign and a colour
    details: tuple[FigureItem, ...] = ()  # reference rows of the tooltip, not summands of the total


def ordered_sources(sources: set[str]) -> tuple[str, ...]:
    """Stable order of sources for deterministic output."""
    return tuple(s for s in SOURCE_ORDER if s in sources)
