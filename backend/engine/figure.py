"""Figure: a number with its breakdown and source (see docs/api-contract.md)."""

from dataclasses import dataclass

SOURCE_ORDER = ("bank", "vetmanager", "bot", "manual", "calc")


@dataclass(frozen=True)
class FigureItem:
    label: str
    value: int
    unit: str = "rub"


@dataclass(frozen=True)
class Figure:
    value: int
    unit: str
    breakdown: tuple[FigureItem, ...]
    source: tuple[str, ...]
    note: str


def ordered_sources(sources: set[str]) -> tuple[str, ...]:
    """Stable order of sources for deterministic output."""
    return tuple(s for s in SOURCE_ORDER if s in sources)
