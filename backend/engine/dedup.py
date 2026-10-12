"""Idempotent import and possible duplicates.

Two different things:
- `dedupe_incoming` drops operations that are already stored or repeated inside the file (same
  `external_id`): this is idempotency, nothing is flagged.
- `find_duplicate_pairs` finds the same payment that came from two sources (bank statement and manual
  entry, bot or Vetmanager): the newer record is flagged as a duplicate of the older one.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

DEFAULT_WINDOW_DAYS = 3


@dataclass(frozen=True)
class DedupeResult:
    new: tuple[Any, ...]
    skipped_existing: tuple[Any, ...]
    skipped_in_file: tuple[Any, ...]


@dataclass(frozen=True)
class TxRef:
    id: str
    account: str
    date: date
    amount: int  # signed kopecks
    source: str
    kind: str


@dataclass(frozen=True)
class DuplicatePair:
    duplicate_id: str
    original_id: str


def _external_id(op: Any) -> str:
    value = op.get("external_id") if isinstance(op, Mapping) else getattr(op, "external_id", None)
    return str(value)


def dedupe_incoming(ops: Sequence[Any], existing_external_ids: Collection[str]) -> DedupeResult:
    """Split incoming operations into new ones and those that are already known.

    A repeat inside the file goes to `skipped_in_file` (the first occurrence is kept or, if the id is
    already stored, counted in `skipped_existing`). The order of `new` is the order of the file.
    """
    known = set(existing_external_ids)
    seen: set[str] = set()
    fresh: list[Any] = []
    existing: list[Any] = []
    repeated: list[Any] = []
    for op in ops:
        key = _external_id(op)
        if key in seen:
            repeated.append(op)
            continue
        seen.add(key)
        (existing if key in known else fresh).append(op)
    return DedupeResult(tuple(fresh), tuple(existing), tuple(repeated))


def find_duplicate_pairs(
    new: Sequence[TxRef], existing: Sequence[TxRef], window_days: int = DEFAULT_WINDOW_DAYS
) -> list[DuplicatePair]:
    """Pairs (new record, older record) that look like one payment.

    Rule: the same account, the same signed amount, dates at most `window_days` apart, different
    sources, neither is a transfer. One to one: an `existing` record is taken once. `new` is handled in
    the given order; among several candidates the nearest date wins, then the earlier in `existing`.
    The caller must not pass records that are already duplicates or already paired in `existing`.
    """
    taken: set[str] = set()
    pairs: list[DuplicatePair] = []
    for item in new:
        if item.kind == "transfer":
            continue
        best: tuple[int, int, str] | None = None
        for position, candidate in enumerate(existing):
            if not _fits(item, candidate, window_days) or candidate.id in taken:
                continue
            gap = abs((candidate.date - item.date).days)
            if best is None or (gap, position) < best[:2]:
                best = (gap, position, candidate.id)
        if best is not None:
            taken.add(best[2])
            pairs.append(DuplicatePair(duplicate_id=item.id, original_id=best[2]))
    return pairs


def _fits(item: TxRef, candidate: TxRef, window_days: int) -> bool:
    return (
        candidate.kind != "transfer"
        and candidate.source != item.source
        and candidate.account == item.account
        and candidate.amount == item.amount
        and abs((candidate.date - item.date).days) <= window_days
    )
