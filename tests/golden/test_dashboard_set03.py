"""Golden tests of the dashboard engine (stage 2), set03. Expected numbers come from set03/expected.json,
computed independently by tools/compute_expected_set03.py, never from the engine.

Interface under test (proposal, see docs/handoff.md "tester -> backend-developer (этап 2)"):
    engine.dashboard.compute_dashboard(accounts, transactions, sales, visits, norms, as_of) -> DashboardResult
The tests skip while the module (or a proposed input class) does not exist.
"""
from datetime import date

import pytest

from set03_support import (CASES, MAIN_AS_OF, build_inputs, case, contains_amount, contains_number, engine_dashboard,
                           run, run_shuffled, snapshot, why_text)

AS_OF = [c["as_of"] for c in CASES]
ALLOWED_SOURCES = {"bank", "vetmanager", "bot", "manual", "calc"}


@pytest.fixture(scope="module")
def mod():
    return engine_dashboard()


@pytest.fixture(scope="module")
def results(mod):
    return {a: run(mod, a) for a in AS_OF}


def get(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def labels(fig):
    return {b["label"]: b["value"] for b in fig["breakdown"]}


def balance_field(res, name):
    return (res.get("balance") or {}).get(name)


# ---------------------------------------------------------------- balance (function 1)
@pytest.mark.parametrize("as_of", AS_OF)
def test_balance_total_bank_cash_to_the_kopeck(results, as_of):
    exp, res = case(as_of)["balance"], results[as_of]["balance"]
    for key in ("total", "bank", "cash"):
        fig = res[key]
        assert type(fig["value"]) is int and fig["unit"] == "rub"
        assert fig["value"] == exp[key]["value"], key
        assert labels(fig) == exp[key]["breakdown"], key
        assert fig["source"] == exp[key]["source"], key
        assert sum(b["value"] for b in fig["breakdown"]) == fig["value"]


@pytest.mark.parametrize("as_of", AS_OF)
def test_week_change_and_percent(results, as_of):
    exp = case(as_of)
    res = results[as_of]
    change, pct = balance_field(res, "week_change"), balance_field(res, "week_change_pct")
    if exp["week_change"] is None:
        assert change is None, "history is shorter than a week: no week_change"
        assert pct is None
        return
    assert change["value"] == exp["week_change"]["value"] and type(change["value"]) is int
    assert labels(change) == exp["week_change"]["breakdown"]
    assert sum(b["value"] for b in change["breakdown"]) == change["value"]
    assert change["source"] == exp["week_change"]["source"]
    assert pct is not None and pct["unit"] == "pct"
    assert float(pct["value"]) == exp["week_change_pct"]["value"]
    assert [b["value"] for b in pct["breakdown"]] == exp["week_change_pct"]["breakdown_values"]


@pytest.mark.parametrize("as_of", AS_OF)
def test_balance_trend_is_a_daily_series_ending_at_total(results, as_of):
    exp, res = case(as_of), results[as_of]
    assert res["balance_trend"] == exp["balance_trend"]
    assert res["balance_trend"][-1]["value"] == res["balance"]["total"]["value"]
    assert all(type(p["value"]) is int for p in res["balance_trend"])


# ---------------------------------------------------------------- runway ("хватит на N дней")
@pytest.mark.parametrize("as_of", AS_OF)
def test_runway_days(results, as_of):
    exp = case(as_of)["runway_days"]
    fig = balance_field(results[as_of], "runway_days")
    assert fig is not None and exp is not None
    assert type(fig["value"]) is int and fig["unit"] == "days"
    assert fig["value"] == exp["value"]
    assert [b["value"] for b in fig["breakdown"]] == exp["breakdown_values"], \
        "breakdown: balance, expenses for the window, expenses per day, window (days)"
    assert fig["source"] == exp["source"]


def test_runway_is_floor_not_round(results):
    """17.6 days must be shown as 17: 'enough for N days' never overstates."""
    exp = case(MAIN_AS_OF)["runway_days"]
    balance, burn, _, window = exp["breakdown_values"]
    assert balance * window % burn != 0  # the case really has a fractional result
    assert results[MAIN_AS_OF]["balance"]["runway_days"]["value"] == balance * window // burn


# ---------------------------------------------------------------- month (function 2)
@pytest.mark.parametrize("as_of", AS_OF)
def test_month_money_figures(results, as_of):
    exp, res = case(as_of)["month"], results[as_of]["month"]
    assert (res["days_passed"], res["days_total"]) == (exp["days_passed"], exp["days_total"])
    for key in ("revenue", "expenses", "profit"):
        fig = res[key]
        assert type(fig["value"]) is int and fig["unit"] == "rub", key
        assert fig["value"] == exp[key]["value"], key
        assert labels(fig) == exp[key]["breakdown"], key
        assert fig["source"] == exp[key]["source"], key
        assert sum(b["value"] for b in fig["breakdown"]) == fig["value"], key
    assert res["profit"]["value"] == res["revenue"]["value"] - res["expenses"]["value"]


@pytest.mark.parametrize("as_of", AS_OF)
def test_month_margin_visits_and_average_check(results, as_of):
    exp, res = case(as_of)["month"], results[as_of]["month"]
    margin = res["profit_margin_pct"]
    assert margin["unit"] == "pct" and float(margin["value"]) == exp["profit_margin_pct"]["value"]
    assert [b["value"] for b in margin["breakdown"]] == exp["profit_margin_pct"]["breakdown_values"]
    visits = res["visits"]
    assert type(visits["value"]) is int and visits["unit"] == "count"
    assert visits["value"] == exp["visits"]["value"] and labels(visits) == exp["visits"]["breakdown"]
    assert sum(b["value"] for b in visits["breakdown"]) == visits["value"]
    avg = res["avg_check"]
    assert type(avg["value"]) is int and avg["unit"] == "rub" and avg["value"] == exp["avg_check"]["value"]
    assert [b["value"] for b in avg["breakdown"]] == exp["avg_check"]["breakdown_values"]


def test_drafts_duplicates_and_future_operations_are_not_counted(results):
    """09-09: 'save' invoices are not revenue; the duplicate and the 09-10 salary advance are not expenses."""
    exp = case(MAIN_AS_OF)["month"]
    res = results[MAIN_AS_OF]["month"]
    assert res["expenses"]["value"] == exp["expenses"]["value"]
    assert "Зарплата" not in labels(res["expenses"]), "salary advance dated 2026-09-10 is after as_of"
    assert labels(res["expenses"])["Без статьи"] == 124_000, "the 'check' debit is an expense without a category"
    assert labels(res["expenses"])["Корма для перепродажи"] == 5_400_000, "only the bot copy, not the bank duplicate"


# ---------------------------------------------------------------- advice (functions 3-4)
@pytest.mark.parametrize("as_of", AS_OF)
def test_advice_ids_severity_and_order(results, as_of):
    exp, res = case(as_of)["advice"], results[as_of]["advice"]
    assert [(a["id"], a["severity"]) for a in res] == [(a["id"], a["severity"]) for a in exp]


@pytest.mark.parametrize("as_of", AS_OF)
def test_advice_shape_and_why_block(results, as_of):
    for a in results[as_of]["advice"]:
        assert a["severity"] in {"alert", "warning", "good"}
        assert all(isinstance(a[k], str) and a[k].strip() for k in ("id", "icon", "title", "text")), a["id"]
        why = a["why"]
        assert isinstance(why["summary"], str) and why["summary"].strip()
        assert isinstance(why["steps"], list) and len(why["steps"]) >= 2
        assert all(isinstance(s, str) and s.strip() for s in why["steps"])
        assert isinstance(why["sources"], list) and why["sources"] and all(isinstance(s, str) and s for s in why["sources"])


@pytest.mark.parametrize("as_of", AS_OF)
def test_why_steps_contain_the_numbers_of_the_calculation(results, as_of):
    """'Почему?' is built from the engine result: every number of the calculation must be in the text."""
    by_id = {a["id"]: a for a in results[as_of]["advice"]}
    for exp in case(as_of)["advice"]:
        text = why_text(by_id[exp["id"]])
        for kop in exp["why_amounts"]:
            assert contains_amount(text, kop), f"{exp['id']}: amount {kop} is not in why: {text!r}"
        for n in exp["why_numbers"]:
            assert contains_number(text, str(n)), f"{exp['id']}: number {n} is not in why: {text!r}"
        for p in exp["why_pcts"]:
            assert contains_number(text, p), f"{exp['id']}: percent {p} is not in why: {text!r}"


def test_main_case_has_at_least_two_rule_based_advices_with_why(results):
    ids = [a["id"] for a in results[MAIN_AS_OF]["advice"]]
    assert ids == ["cash_runway", "drug_share"]


def test_revenue_drop_fires_only_when_the_same_days_of_previous_month_are_known(results):
    assert "revenue_drop" not in [a["id"] for a in results[MAIN_AS_OF]["advice"]], "09-09: -4% is inside the 15% threshold"
    assert "revenue_drop" not in [a["id"] for a in results["2026-08-31"]["advice"]], "August has no previous month in the data"
    assert "revenue_drop" in [a["id"] for a in results["2026-09-20"]["advice"]]


def test_no_advice_with_less_than_a_week_of_data(results):
    assert results["2026-08-04"]["advice"] == []


# ---------------------------------------------------------------- every number: breakdown and source (rule 4)
def figures(node, path=""):
    if isinstance(node, dict):
        if {"value", "unit", "breakdown"} <= set(node):
            yield path, node
        for k, v in node.items():
            yield from figures(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from figures(v, f"{path}[{i}]")


@pytest.mark.parametrize("as_of", AS_OF)
def test_every_figure_has_breakdown_source_and_note(results, as_of):
    found = list(figures(results[as_of]))
    assert len(found) >= 10, "balance (3) + runway (1) + month (6) are expected, week_change (2) when history allows"
    for path, fig in found:
        assert fig["unit"] in {"rub", "pct", "count", "days"}, path
        assert fig["breakdown"], f"{path}: empty breakdown"
        assert fig["source"] and set(fig["source"]) <= ALLOWED_SOURCES, f"{path}: source"
        assert isinstance(fig["note"], str) and fig["note"].strip(), f"{path}: note"
        if fig["unit"] in {"rub", "count", "days"}:
            assert type(fig["value"]) is int, f"{path}: value must be int, not float"
        order = ["bank", "vetmanager", "bot", "manual", "calc"]
        assert fig["source"] == sorted(set(fig["source"]), key=order.index), f"{path}: order or duplicates in source"


# ---------------------------------------------------------------- determinism and purity (rule 3)
def test_two_runs_give_identical_results(mod, results):
    assert run(mod, MAIN_AS_OF) == results[MAIN_AS_OF]


def test_result_does_not_depend_on_input_order(mod, results):
    assert run_shuffled(mod, MAIN_AS_OF) == results[MAIN_AS_OF]


def test_inputs_are_not_mutated(mod):
    inputs = build_inputs(mod)
    before = snapshot(inputs)
    mod.compute_dashboard(*inputs, date.fromisoformat(MAIN_AS_OF))
    assert snapshot(inputs) == before


def test_balance_part_agrees_with_stage0_engine(mod, results):
    """The dashboard must not recompute the balance differently from engine.balance.compute_balance (stage 0)."""
    import importlib
    from datetime import date
    try:
        bal = importlib.import_module("engine.balance")
    except ImportError:
        pytest.skip("engine.balance is not importable (reference override)")
    accounts, txs, *_ = build_inputs(mod)
    ref = bal.compute_balance(accounts, txs, date.fromisoformat(MAIN_AS_OF))
    assert results[MAIN_AS_OF]["balance"]["total"]["value"] == ref.total.value
    assert results[MAIN_AS_OF]["balance"]["cash"]["value"] == ref.cash.value
