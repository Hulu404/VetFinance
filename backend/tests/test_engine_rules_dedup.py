from datetime import date
from typing import Any

from engine.dedup import TxRef, dedupe_incoming, find_duplicate_pairs
from engine.rules import (
    Rule,
    can_make_rule,
    classify,
    matching_rule,
    normalize_text,
    retro_matches,
    rule_from_edit,
    suggest,
)


def op(**fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "out",
        "amount": -100,
        "description": "",
        "counterparty_inn": "",
    }
    return {**base, **fields}


# ------------------------------------------------------------------ rules
def test_first_matching_rule_wins_and_direction_is_respected() -> None:
    rules = [
        Rule("text", "эквайринга", "in", "Эквайринг"),
        Rule("text", "оплата", None, "Прочее"),
        Rule("text", "оплата", None, "Не должно сработать"),
    ]
    assert classify(op(kind="in", amount=5, description="Оплата ЭКВАЙРИНГА"), rules) == "Эквайринг"
    assert classify(op(kind="out", description="комиссия эквайринга"), rules) is None
    assert classify(op(description="оплата услуг"), rules) == "Прочее"


def test_inn_rule_needs_exact_inn_and_ignores_text() -> None:
    rules = [Rule("inn", "7702000022", None, "Препараты")]
    assert classify(op(counterparty_inn="7702000022"), rules) == "Препараты"
    assert classify(op(counterparty_inn="7702000033"), rules) is None
    assert classify(op(description="7702000022"), rules) is None


def test_transfers_are_never_classified() -> None:
    rules = [Rule("text", "перевод", None, "Прочее")]
    assert classify(op(kind="transfer", description="перевод средств"), rules) is None


def test_direction_is_read_from_amount_when_kind_is_missing() -> None:
    rules = [Rule("text", "x", "in", "Доход")]
    assert classify({"amount": 10, "description": "x"}, rules) == "Доход"
    assert classify({"amount": -10, "description": "x"}, rules) is None


def test_matching_rule_returns_the_rule_with_its_id() -> None:
    rule = Rule("inn", "1", None, "A", rule_id="r-1")
    assert matching_rule(op(counterparty_inn="1"), [rule]) is rule


def test_rule_from_edit_prefers_inn_and_keeps_direction() -> None:
    rule = rule_from_edit(op(counterparty_inn="7702000022", description="за препараты"), "A")
    assert (rule.match, rule.value, rule.direction, rule.category) == (
        "inn",
        "7702000022",
        "out",
        "A",
    )


def test_rule_from_edit_falls_back_to_normalised_text() -> None:
    rule = rule_from_edit(op(description="Оплата по счёту № 123 от 05.09.2026"), "A")
    assert rule.match == "text" and rule.value == "оплата по счёту от"
    assert normalize_text("  Счёт  №45, 10.09  ") == "счёт"


def test_can_make_rule_only_with_a_known_counterparty() -> None:
    assert can_make_rule(op(counterparty_inn="7702000022"))
    assert not can_make_rule(op())
    assert not can_make_rule(op(kind="transfer", counterparty_inn="7702000022"))


def test_retro_matches_touch_only_uncategorised_checks() -> None:
    rule = Rule("inn", "7702000022", "out", "Препараты")
    rows: list[dict[str, Any]] = [
        {
            "id": "1",
            "kind": "out",
            "status": "check",
            "category_id": None,
            "counterparty_inn": "7702000022",
        },
        {
            "id": "2",
            "kind": "out",
            "status": "ok",
            "category_id": "x",
            "counterparty_inn": "7702000022",
        },
        {
            "id": "3",
            "kind": "out",
            "status": "check",
            "category_id": None,
            "counterparty_inn": "7702000033",
        },
        {
            "id": "4",
            "kind": "in",
            "status": "check",
            "category_id": None,
            "counterparty_inn": "7702000022",
            "amount": 5,
        },
        {
            "id": "5",
            "kind": "transfer",
            "status": "check",
            "category_id": None,
            "counterparty_inn": "7702000022",
        },
        {
            "id": "6",
            "kind": "out",
            "status": "duplicate",
            "category_id": None,
            "counterparty_inn": "7702000022",
        },
    ]
    assert [r["id"] for r in retro_matches(rule, rows)] == ["1"]


def test_suggest_prefers_a_rule_then_the_most_frequent_category() -> None:
    rules = [Rule("inn", "1", None, "ByRule")]
    history = {"1": {"Other": 5}, "2": {"B": 2, "A": 2, "C": 1}}
    first = suggest(op(counterparty_inn="1"), rules, history)
    assert first is not None and (first.category, first.reason) == ("ByRule", "rule")
    second = suggest(op(counterparty_inn="2"), rules, history)
    assert second is not None and (second.category, second.reason, second.count) == (
        "A",
        "similar",
        2,
    )
    assert suggest(op(counterparty_inn="3"), rules, history) is None
    assert suggest(op(), rules, history) is None


# ------------------------------------------------------------------ dedup
def test_dedupe_incoming_keeps_order_and_separates_the_three_groups() -> None:
    ops = [{"external_id": e} for e in ("a", "b", "a", "c", "b", "d")]
    result = dedupe_incoming(ops, {"b", "z"})
    assert [o["external_id"] for o in result.new] == ["a", "c", "d"]
    assert [o["external_id"] for o in result.skipped_existing] == ["b"]
    assert [o["external_id"] for o in result.skipped_in_file] == ["a", "b"]


def test_duplicate_pairs_pick_the_nearest_date_and_use_each_original_once() -> None:
    def ref(i: str, day: int, source: str = "bank", amount: int = 500) -> TxRef:
        return TxRef(i, "acc", date(2026, 9, day), amount, source, "in")

    existing = [ref("far", 8, "manual"), ref("near", 11, "manual")]
    pairs = find_duplicate_pairs([ref("n1", 10), ref("n2", 10)], existing)
    assert [(p.duplicate_id, p.original_id) for p in pairs] == [("n1", "near"), ("n2", "far")]
    assert find_duplicate_pairs([ref("n", 10)], [ref("m", 10, "manual", 501)]) == []


def test_two_bank_payments_never_flag_each_other() -> None:
    first = TxRef("a", "acc", date(2026, 9, 1), 100, "bank", "in")
    second = TxRef("b", "acc", date(2026, 9, 1), 100, "bank", "in")
    assert find_duplicate_pairs([second], [first]) == []
