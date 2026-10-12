"""Categorisation rules: the first matching rule in list order wins.

A rule matches an operation by the INN of the counterparty (`inn`) or by a substring of the purpose of
payment (`text`, case-insensitive) and may be limited to a direction (`in` or `out`). Transfers between
the clinic's own accounts are never classified. Pure functions over plain values: an operation is a
mapping (or an object) with `kind`, `amount`, `description`, `counterparty_inn`.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MATCH_INN = "inn"
MATCH_TEXT = "text"
REASON_RULE = "rule"
REASON_SIMILAR = "similar"
_DIGITS_AND_SIGNS = re.compile(r"[\d№#]+")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Rule:
    match: str  # "inn" | "text"
    value: str
    direction: str | None  # "in" | "out" | None (any)
    category: str  # a category name or id: the engine does not care
    rule_id: str | None = None  # database id, carried through for the caller


@dataclass(frozen=True)
class Suggestion:
    category: str
    reason: str  # "rule" | "similar"
    count: int  # operations of the same counterparty with this category (0 for a rule)


def _get(op: Any, name: str, default: Any = None) -> Any:
    if isinstance(op, Mapping):
        return op.get(name, default)
    return getattr(op, name, default)


def direction_of(op: Any) -> str | None:
    """`in` or `out`; None for transfers and when it cannot be told."""
    kind = _get(op, "kind")
    if kind == "transfer":
        return None
    if kind in ("in", "out"):
        return str(kind)
    amount = _get(op, "amount")
    if isinstance(amount, int) and amount != 0:
        return "in" if amount > 0 else "out"
    return None


def normalize_text(text: str) -> str:
    """Lower-case purpose without digits, numbers and extra spaces: stable between payments."""
    return _SPACES.sub(" ", _DIGITS_AND_SIGNS.sub(" ", text.casefold())).strip(" ,.;:-")


def matching_rule(op: Any, rules: Sequence[Rule]) -> Rule | None:
    """The first rule that fits the operation, or None."""
    if _get(op, "kind") == "transfer":
        return None
    direction = direction_of(op)
    inn = str(_get(op, "counterparty_inn") or "").strip()
    text = str(_get(op, "description") or "").casefold()
    for rule in rules:
        if rule.direction is not None and rule.direction != direction:
            continue
        if rule.match == MATCH_INN:
            if inn and inn == rule.value.strip():
                return rule
        elif rule.match == MATCH_TEXT and rule.value and rule.value.casefold() in text:
            return rule
    return None


def classify(op: Any, rules: Sequence[Rule]) -> str | None:
    """Category of the first matching rule, or None."""
    rule = matching_rule(op, rules)
    return rule.category if rule else None


def rule_from_edit(op: Any, category: str) -> Rule:
    """The rule made by a manual edit: by the INN of the counterparty, else by the normalised purpose.

    The rule is limited to the direction of the edited operation, so a refund from the same supplier
    is not put into an expense category.
    """
    direction = direction_of(op)
    inn = str(_get(op, "counterparty_inn") or "").strip()
    if inn:
        return Rule(match=MATCH_INN, value=inn, direction=direction, category=category)
    text = normalize_text(str(_get(op, "description") or ""))
    return Rule(match=MATCH_TEXT, value=text, direction=direction, category=category)


def can_make_rule(op: Any) -> bool:
    """A rule is offered only for operations with a known counterparty (INN)."""
    return _get(op, "kind") != "transfer" and bool(str(_get(op, "counterparty_inn") or "").strip())


def retro_matches(rule: Rule, rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Already loaded rows the new rule applies to: no category and status "check", not transfers.

    Rows that have a category (including those categorised by hand) are never touched.
    """
    result: list[Mapping[str, Any]] = []
    for row in rows:
        has_category = row.get("category") is not None or row.get("category_id") is not None
        if has_category or row.get("status") != "check" or row.get("kind") == "transfer":
            continue
        if matching_rule(row, [rule]) is not None:
            result.append(row)
    return result


def suggest(
    op: Any, rules: Sequence[Rule], history: Mapping[str, Mapping[str, int]]
) -> Suggestion | None:
    """A category for an uncategorised operation.

    `history` maps the INN of a counterparty to {category: number of operations already put there}.
    A matching rule wins; otherwise the most frequent category of the same counterparty (ties go to
    the category that sorts first, so the answer is stable).
    """
    rule = matching_rule(op, rules)
    if rule is not None:
        return Suggestion(category=rule.category, reason=REASON_RULE, count=0)
    inn = str(_get(op, "counterparty_inn") or "").strip()
    seen = history.get(inn) if inn else None
    if not seen:
        return None
    counts = Counter(dict(seen))
    best = min(counts.items(), key=lambda item: (-item[1], item[0]))
    return Suggestion(category=best[0], reason=REASON_SIMILAR, count=best[1])
