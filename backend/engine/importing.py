"""Plan of a bank statement import: what to insert, with which category and status.

Pure: takes the operations of the file, what is already stored, the rules and the candidates for
duplicate pairing, returns the rows to insert and the counters. The caller (the API layer) only stores
the result, so a repeated upload plans nothing and the same file always gives the same plan.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from engine.bank_1c import NewOperation
from engine.dedup import TxRef, dedupe_incoming, find_duplicate_pairs
from engine.rules import Rule, matching_rule

STATUS_OK = "ok"
STATUS_CHECK = "check"
STATUS_DUPLICATE = "duplicate"
SOURCE_BANK = "bank"


@dataclass(frozen=True)
class PlannedRow:
    op: NewOperation
    account_id: str
    category: str | None  # rule.category of the matching rule
    rule_id: str | None
    status: str
    duplicate_of: str | None  # id of an already stored record


@dataclass(frozen=True)
class ImportPlan:
    rows: tuple[PlannedRow, ...]
    skipped_existing: int
    skipped_in_file: int

    @property
    def loaded(self) -> int:
        return len(self.rows)

    @property
    def duplicates(self) -> int:
        return sum(1 for r in self.rows if r.status == STATUS_DUPLICATE)

    @property
    def to_check(self) -> int:
        return sum(1 for r in self.rows if r.status == STATUS_CHECK)

    @property
    def already_loaded(self) -> int:
        return self.skipped_existing + self.skipped_in_file


def plan_import(
    operations: Sequence[NewOperation],
    own_accounts: Mapping[str, str],
    existing_external_ids: Collection[str],
    rules: Sequence[Rule],
    candidates: Sequence[TxRef],
    window_days: int = 3,
) -> ImportPlan:
    """`own_accounts`: statement account number -> clinic account id; `candidates`: stored records that
    may be the original of a new one (not duplicates, not transfers, not paired yet)."""
    split = dedupe_incoming(list(operations), existing_external_ids)
    fresh: list[NewOperation] = sorted(split.new, key=lambda o: (o.date, o.number))
    refs = [
        TxRef(o.external_id, own_accounts[o.account_number], o.date, o.amount, SOURCE_BANK, o.kind)
        for o in fresh
    ]
    originals = {
        p.duplicate_id: p.original_id for p in find_duplicate_pairs(refs, candidates, window_days)
    }
    rows: list[PlannedRow] = []
    for op in fresh:
        rule = matching_rule(op, rules)
        category = rule.category if rule else None
        original = originals.get(op.external_id)
        if original is not None:
            status = STATUS_DUPLICATE
        elif category is None and op.kind != "transfer":
            status = STATUS_CHECK
        else:
            status = STATUS_OK
        rows.append(
            PlannedRow(
                op=op,
                account_id=own_accounts[op.account_number],
                category=category,
                rule_id=rule.rule_id if rule else None,
                status=status,
                duplicate_of=original,
            )
        )
    return ImportPlan(tuple(rows), len(split.skipped_existing), len(split.skipped_in_file))
