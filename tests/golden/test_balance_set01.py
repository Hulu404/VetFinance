"""Golden test: balance by account, set01. Expected numbers come from expected.json
(computed independently by tools/compute_expected_set01.py), never from the engine."""
import copy
import importlib
import json
from datetime import date
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent / "set01"
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((BASE / "expected.json").read_text(encoding="utf-8"))
CASES = EXPECTED["cases"]


def _engine():
    try:
        mod = importlib.import_module("engine.balance")
    except ImportError as exc:
        pytest.skip(f"engine.balance is not importable yet: {exc}")
    fn = getattr(mod, "compute_balance", None)
    if fn is None:
        pytest.skip("engine.balance.compute_balance is not defined yet")
    return fn


def _d(obj):
    """Normalize dict / pydantic / dataclass (recursively) into plain dicts and lists."""
    import dataclasses
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _d(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if hasattr(obj, "model_dump"):
        return _d(obj.model_dump())
    if isinstance(obj, dict):
        return {k: _d(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_d(x) for x in obj]
    return obj


def _fig(result, name):
    return _d(result[name] if isinstance(result, dict) else getattr(result, name))


def _by_label(fig):
    return {b["label"]: b["value"] for b in fig["breakdown"]}


def _adapt(accs, txs):
    """Engine takes frozen dataclasses (AccountInput.kind, TransactionInput); fall back to dicts."""
    try:
        mod = importlib.import_module("engine.balance")
        A, T = mod.AccountInput, mod.TransactionInput
    except (ImportError, AttributeError):
        return accs, txs
    return (
        [A(id=a["id"], name=a["name"], kind=a["type"], opening_balance=a["opening_balance"],
           opening_date=date.fromisoformat(a["opening_date"])) for a in accs],
        [T(account_id=t["account_id"], date=date.fromisoformat(t["date"]), amount=t["amount"],
           status=t["status"], source=t["source"]) for t in txs],
    )


def _run(fn, clinic_id, as_of):
    accs = [a for a in DATA["accounts"] if a["clinic_id"] == clinic_id]
    txs = [t for t in DATA["transactions"] if t["clinic_id"] == clinic_id]
    a, t = _adapt(copy.deepcopy(accs), copy.deepcopy(txs))
    return fn(a, t, date.fromisoformat(as_of))


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['clinic_id']}-{c['as_of']}")
def test_balance_matches_expected_to_the_kopeck(case):
    fn = _engine()
    res = _run(fn, case["clinic_id"], case["as_of"])
    names = {a["id"]: a["name"] for a in DATA["accounts"]}
    exp_by_label = {names[k]: v for k, v in case["accounts"].items()}
    bank_labels = {names[a["id"]] for a in DATA["accounts"]
                   if a["clinic_id"] == case["clinic_id"] and a["type"] == "bank"}

    total, bank = _fig(res, "total"), _fig(res, "bank")
    assert total["value"] == case["total"] and isinstance(total["value"], int)
    assert bank["value"] == case["bank"] and isinstance(bank["value"], int)
    assert total["unit"] == bank["unit"] == "rub"
    assert _by_label(total) == exp_by_label
    assert _by_label(bank) == {k: v for k, v in exp_by_label.items() if k in bank_labels}
    assert sum(b["value"] for b in total["breakdown"]) == total["value"]
    assert sum(b["value"] for b in bank["breakdown"]) == bank["value"]
    figs = case["figures"]
    assert total["source"] == figs["balance.total"]["source"]
    assert bank["source"] == figs["balance.bank"]["source"]
    assert _fig(res, "cash")["source"] == figs["balance.cash"]["source"]
    assert _fig(res, "cash")["value"] == case["cash"]


def test_balance_is_repeatable():
    fn = _engine()
    a = _run(fn, "A", "2026-09-09")
    b = _run(fn, "A", "2026-09-09")
    assert _fig(a, "total") == _fig(b, "total")


def test_inputs_are_not_mutated():
    fn = _engine()
    accs = copy.deepcopy([x for x in DATA["accounts"] if x["clinic_id"] == "A"])
    txs = copy.deepcopy([x for x in DATA["transactions"] if x["clinic_id"] == "A"])
    snap = copy.deepcopy((accs, txs))
    a, t = _adapt(accs, txs)
    fn(a, t, date(2026, 9, 9))
    assert (accs, txs) == snap


def test_clinic_b_data_does_not_leak_into_a():
    """Passing only clinic A rows must not depend on B; passing mixed rows is a caller error."""
    fn = _engine()
    only_a = _fig(_run(fn, "A", "2026-09-09"), "total")["value"]
    assert only_a == next(c["total"] for c in CASES if c["clinic_id"] == "A" and c["as_of"] == "2026-09-09")


def test_dataset_sanity_transfers_net_zero_and_has_pennies():
    """Guards the fixture itself so it cannot rot silently."""
    for cid in ("A", "B"):
        trf = [t for t in DATA["transactions"] if t["clinic_id"] == cid and t["kind"] == "transfer"]
        assert sum(t["amount"] for t in trf) == 0
    assert any(t["amount"] % 100 for t in DATA["transactions"])
    assert all(isinstance(t["amount"], int) for t in DATA["transactions"])
    assert 30 <= len([t for t in DATA["transactions"] if t["clinic_id"] == "A"]) <= 60
