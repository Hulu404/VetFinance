"""Turns data-layer rows into API models: figures, duplicate reasons and category suggestions."""

from collections.abc import Sequence
from typing import Any

from app.repo import Repository
from app.rows import RuleRow, TxRow
from app.schemas import figure_out
from app.schemas_tx import (
    NamedRefOut,
    SuggestionOut,
    TransactionBriefOut,
    TransactionOut,
)
from engine.rules import Rule, suggest
from engine.transactions import duplicate_reason, suggestion_text, transaction_figure


def engine_rules(rules: Sequence[RuleRow]) -> list[Rule]:
    """Rules for the engine: the category of a rule is the category id, the rule id travels along."""
    return [Rule(r.match, r.value, r.direction, r.category_id, r.id) for r in rules]


def rule_label(rule: RuleRow) -> str:
    """Counterparty name for an INN rule (the INN itself is not shown), the substring for a text rule."""
    return rule.display_name or rule.value


def op_view(row: TxRow) -> dict[str, Any]:
    """The fields the rule engine reads from a stored operation."""
    return {
        "kind": row.kind,
        "amount": row.amount,
        "description": row.description,
        "counterparty_inn": row.counterparty_inn,
        "category_id": row.category_id,
        "status": row.status,
    }


def _state(row: TxRow) -> str | None:
    if row.status != "duplicate":
        return None
    return "confirmed" if row.duplicate_state == "confirmed" else "pending"


def _brief_fields(row: TxRow, rule_names: dict[str, str]) -> dict[str, Any]:
    figure = transaction_figure(
        amount=row.amount,
        op_date=row.date,
        source=row.source,
        account_name=row.account_name,
        kind=row.kind,
        status=row.status,
        category_source=row.category_source,
        category_name=row.category_name,
        rule_name=rule_names.get(row.rule_id) if row.rule_id else None,
    )
    return {
        "id": row.id,
        "date": row.date,
        "description": row.description,
        "category": NamedRefOut(id=row.category_id, name=row.category_name)
        if row.category_id and row.category_name
        else None,
        "account": NamedRefOut(id=row.account_id, name=row.account_name),
        "source": row.source,
        "amount": row.amount,
        "kind": row.kind,
        "status": row.status,
        "duplicate_state": _state(row),
        "figure": figure_out(figure),
    }


async def _suggestions(
    repo: Repository, check_rows: Sequence[TxRow], rules: Sequence[RuleRow]
) -> dict[str, SuggestionOut]:
    if not check_rows:
        return {}
    categories = {c.id: c.name for c in await repo.list_categories()}
    inns = {r.counterparty_inn for r in check_rows if r.counterparty_inn}
    history = await repo.category_history(inns)
    engine = engine_rules(rules)
    result: dict[str, SuggestionOut] = {}
    for row in check_rows:
        found = suggest(op_view(row), engine, history)
        if found is None or found.category not in categories:
            continue
        result[row.id] = SuggestionOut(
            category=NamedRefOut(id=found.category, name=categories[found.category]),
            reason="rule" if found.reason == "rule" else "similar",
            text=suggestion_text(found.reason, found.count, row.counterparty_name),
        )
    return result


async def present_transactions(repo: Repository, rows: Sequence[TxRow]) -> list[TransactionOut]:
    """Full `Transaction` objects for a list of rows."""
    if not rows:
        return []
    rules = await repo.list_rules()
    rule_names = {r.id: rule_label(r) for r in rules}
    original_ids = sorted(
        {r.duplicate_of for r in rows if r.duplicate_of and r.status == "duplicate"}
    )
    originals = {t.id: t for t in await repo.get_transactions(original_ids)}
    suggestions = await _suggestions(repo, [r for r in rows if r.status == "check"], rules)
    items: list[TransactionOut] = []
    for row in rows:
        original = (
            originals.get(row.duplicate_of)
            if row.duplicate_of and row.status == "duplicate"
            else None
        )
        reason = (
            duplicate_reason(row.amount, original.date, row.date)
            if original is not None and row.status == "duplicate"
            else None
        )
        items.append(
            TransactionOut(
                **_brief_fields(row, rule_names),
                duplicate_of=TransactionBriefOut(**_brief_fields(original, rule_names))
                if original is not None
                else None,
                duplicate_reason=reason,
                suggestion=suggestions.get(row.id),
            )
        )
    return items
