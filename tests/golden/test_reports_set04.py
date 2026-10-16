"""Golden tests of the report engines (stage 3), set04. Expected numbers come from set04/expected.json, computed
independently by tools/compute_expected_set04.py, never from the engine.

Interfaces under test (proposal, see docs/handoff.md "tester -> backend-developer (этап 3)"); field names follow
design/screens/pnl.md and design/screens/norm.md:
    engine.pnl.compute_pnl(...)            P&L of one month (function 14)
    engine.pnl.compute_direction_view(...) services vs goods (function 18)
    engine.norm.compute_norm(...)          norm report (function 15)
    engine.stock.compute_stock(...)        stock and expiry dates (function 17)
The tests skip while a module / function / input class does not exist.
"""
import inspect
from datetime import date

import pytest

from set04_support import (EMPTY_MONTH, EXPECTED, MAIN_MONTH, MONTHS, STOCK_AS_OF, build_inputs, contains_amount, engine_function,
                           items_by_key, labels, reversed_inputs, rows_by_key, run_norm, run_pnl, run_stock, snapshot)

PNL, NORM, DIRECTION, STOCK = EXPECTED["pnl"], EXPECTED["norm"], EXPECTED["direction"], EXPECTED["stock"]
OPEN = EXPECTED["open_cases"][0]
OPEN_AS_OF = date.fromisoformat(OPEN["as_of"])
OPEN_CASES = EXPECTED["open_cases"]          # 2026-09 as of the 15th and as of the 5th (shorter than 7 days)
OPEN_IDS = [c["key"] for c in OPEN_CASES]
RATING_KEYS = ("status", "tone", "deviation_pp", "deviation_rub")   # absent in a running month (owner decision 2026-10-14)
ROW_KEYS = ["revenue", "variable", "marginal_profit", "fixed", "taxes", "obligations", "net_profit"]
ALLOWED_SOURCES = {"bank", "vetmanager", "bot", "manual", "calc"}
ALL_MONTHS = MONTHS + [EMPTY_MONTH]
EXCLUDED_FROM_LINES = {"Покупка оборудования", "Вывод средств владельца", "Платежи по кредитам и лизингу",
                       "Выручка наличные", "Выручка эквайринг"}
PCT_UNITS = ("pct", "pp")


def assert_figure(fig, where, kind="rub"):
    if kind == "pct":
        assert fig["unit"] in PCT_UNITS, where
        assert round(fig["value"], 1) == fig["value"], f"{where}: pct must have one decimal"
    else:
        assert fig["unit"] == kind, where
        assert type(fig["value"]) is int, f"{where}: money / counts / days are int"
    assert isinstance(fig["note"], str) and fig["note"].strip(), f"{where}: note"
    assert fig["source"] and set(fig["source"]) <= ALLOWED_SOURCES, f"{where}: source"
    assert isinstance(fig["breakdown"], list), where
    assert fig["breakdown"] or fig["value"] == 0, f"{where}: empty breakdown only for zero"


def all_rows(result):
    """Rows of the P&L with the children of 'fixed' appended."""
    out = list(result["rows"])
    for r in result["rows"]:
        out.extend(r.get("children") or [])
    return out


# ================================================================== P&L (function 14)
@pytest.fixture(scope="module")
def pnl_fn():
    return engine_function("engine.pnl", "compute_pnl")


@pytest.fixture(scope="module")
def pnl(pnl_fn):
    inputs = build_inputs()
    return {m: run_pnl(pnl_fn, m, inputs) for m in ALL_MONTHS}


@pytest.mark.parametrize("month", ALL_MONTHS)
def test_rows_come_in_the_contract_order_with_the_obligations_line(pnl, month):
    assert [r["key"] for r in pnl[month]["rows"]] == ROW_KEYS
    assert pnl[month]["rows"][5]["label"] == "Обязательства и амортизация"
    assert [r["kind"] for r in pnl[month]["rows"]] == ["revenue", "expense", "subtotal", "expense", "expense", "expense", "total"]


@pytest.mark.parametrize("month", ALL_MONTHS)
def test_every_line_to_the_kopeck(pnl, month):
    got, exp = rows_by_key(pnl[month]), {r["key"]: r for r in PNL[month]["rows"]}
    for key in ROW_KEYS:
        fig = got[key]["amount"]
        assert type(fig["value"]) is int and fig["unit"] == "rub", key
        assert fig["value"] == exp[key]["amount"]["value"], key


@pytest.mark.parametrize("month", ALL_MONTHS)
def test_main_identity_revenue_minus_all_costs_equals_net_profit(pnl, month):
    """Computed from the engine's own rows, not from expected.json: the identity that the prototype v6 broke."""
    v = {k: r["amount"]["value"] for k, r in rows_by_key(pnl[month]).items()}
    assert v["revenue"] - v["variable"] - v["fixed"] - v["taxes"] - v["obligations"] == v["net_profit"]
    assert v["marginal_profit"] == v["revenue"] - v["variable"]


@pytest.mark.parametrize("month", MONTHS)
def test_breakdowns_equal_expected_and_add_up(pnl, month):
    got, exp = rows_by_key(pnl[month]), {r["key"]: r for r in PNL[month]["rows"]}
    for key in ROW_KEYS:
        fig = got[key]["amount"]
        assert list(labels(fig).items()) == list(exp[key]["amount"]["breakdown"].items()), key
        assert sum(b["value"] for b in fig["breakdown"]) == fig["value"], key


@pytest.mark.parametrize("month", MONTHS)
def test_fixed_costs_have_the_payroll_and_other_children(pnl, month):
    fixed = rows_by_key(pnl[month])["fixed"]
    exp = {r["key"]: r for r in PNL[month]["rows"]}["fixed"]["children"]
    assert [c["key"] for c in fixed["children"]] == ["fixed_payroll", "fixed_other"]
    for got, e in zip(fixed["children"], exp):
        assert got["label"] == e["label"] and got["kind"] == "child"
        assert got["amount"]["value"] == e["amount"]["value"], e["key"]
        assert list(labels(got["amount"]).items()) == list(e["amount"]["breakdown"].items()), e["key"]
        assert float(got["share_pct"]["value"]) == e["share_pct"]["value"], e["key"]
    assert sum(c["amount"]["value"] for c in fixed["children"]) == fixed["amount"]["value"]
    assert labels(fixed["amount"]) == {c["label"]: c["amount"]["value"] for c in exp}


@pytest.mark.parametrize("month", ALL_MONTHS)
def test_figure_shape_and_sources(pnl, month):
    exp = {r["key"]: r for r in PNL[month]["rows"]}
    for row in all_rows(pnl[month]):
        assert_figure(row["amount"], f"{month}.{row['key']}")
        if PNL[month]["revenue"] and row["key"] in exp:
            assert row["amount"]["source"] == exp[row["key"]]["amount"]["source"], row["key"]


@pytest.mark.parametrize("month", MONTHS)
def test_share_of_revenue_in_tenths_of_a_percent(pnl, month):
    exp = {r["key"]: r for r in PNL[month]["rows"]}
    exp.update({c["key"]: c for c in exp["fixed"]["children"]})
    revenue = PNL[month]["revenue"]
    for row in all_rows(pnl[month]):
        share = row["share_pct"]
        assert_figure(share, f"{month}.{row['key']}.share_pct", "pct")
        assert float(share["value"]) == exp[row["key"]]["share_pct"]["value"], row["key"]
        assert [b["value"] for b in share["breakdown"]] == [row["amount"]["value"], revenue], row["key"]


def test_empty_month_gives_zero_lines_without_shares_and_does_not_crash(pnl):
    res = pnl[EMPTY_MONTH]
    assert res["status"] == "empty"
    assert all(r["amount"]["value"] == 0 for r in all_rows(res))
    assert all(r.get("share_pct") is None for r in all_rows(res)), "no revenue: percent of revenue is undefined, the field is omitted"


@pytest.mark.parametrize("month", MONTHS)
def test_commission_is_rounded_per_day_and_shown_as_its_own_variable_row(pnl, month):
    labels_var = labels(rows_by_key(pnl[month])["variable"]["amount"])
    assert labels_var.get("Комиссия эквайринга") == PNL[month]["commission"]


@pytest.mark.parametrize("month", MONTHS)
def test_not_a_cost_of_the_period_are_kept_out_of_every_line(pnl, month):
    names = set()
    for r in all_rows(pnl[month]):
        names |= set(labels(r["amount"]))
    assert not (names & EXCLUDED_FROM_LINES), names & EXCLUDED_FROM_LINES
    assert "Перевод между счетами" not in names


def test_prepaid_purchase_counts_in_the_month_of_payment(pnl):
    drugs = labels(rows_by_key(pnl["2026-08"])["variable"]["amount"])["Препараты и расходники"]
    assert drugs == PNL["2026-08"]["by_category"]["Препараты и расходники"] == 39_216_095


def test_capex_appears_only_through_amortization(pnl):
    jul = labels(rows_by_key(pnl["2026-07"])["obligations"]["amount"])
    aug = labels(rows_by_key(pnl["2026-08"])["obligations"]["amount"])
    assert "Амортизация: Центрифуга" not in jul and aug["Амортизация: Центрифуга"] == 236_111
    assert "Центрифуга" not in str(labels(rows_by_key(pnl["2026-07"])["fixed"]["amount"]))


@pytest.mark.parametrize("month", MONTHS)
def test_unclassified_operations_are_reported(pnl_fn, month):
    res = run_pnl(pnl_fn, month)
    exp = PNL[month]["unclassified"]
    assert res["unclassified_count"] == exp["count"]
    assert res["unclassified"]["value"] == exp["amount"]
    if exp["count"]:
        other = next(c for c in rows_by_key(res)["fixed"]["children"] if c["key"] == "fixed_other")
        assert "Без статьи" in labels(other["amount"])


def test_same_input_twice_gives_identical_result(pnl_fn):
    inputs = build_inputs()
    assert run_pnl(pnl_fn, MAIN_MONTH, inputs) == run_pnl(pnl_fn, MAIN_MONTH, inputs)


def test_result_does_not_depend_on_the_order_of_input_rows(pnl_fn, pnl):
    assert run_pnl(pnl_fn, MAIN_MONTH, reversed_inputs(build_inputs())) == pnl[MAIN_MONTH]


def test_inputs_are_not_mutated(pnl_fn):
    inputs = build_inputs()
    before = snapshot(inputs)
    run_pnl(pnl_fn, MAIN_MONTH, inputs)
    assert inputs == before


def test_duplicates_in_the_input_do_not_change_the_report(pnl_fn, pnl):
    inputs = build_inputs()
    inputs["transactions"] = [t for t in inputs["transactions"] if t.status != "duplicate"]
    assert run_pnl(pnl_fn, "2026-08", inputs) == pnl["2026-08"]


def test_other_months_do_not_leak_into_the_month(pnl_fn, pnl):
    inputs = build_inputs()
    inputs["transactions"] = [t for t in inputs["transactions"] if t.date.strftime("%Y-%m") == MAIN_MONTH]
    inputs["sales"] = [s for s in inputs["sales"] if s.date.strftime("%Y-%m") == MAIN_MONTH]
    inputs["card_payments"] = [p for p in inputs["card_payments"] if p.date.strftime("%Y-%m") == MAIN_MONTH]
    res = run_pnl(pnl_fn, MAIN_MONTH, inputs)
    assert res["rows"] == pnl[MAIN_MONTH]["rows"] and res["status"] == "ok"   # (period.first_month depends on the data on purpose)


def test_a_different_tariff_changes_only_the_commission(pnl_fn, pnl):
    inputs = build_inputs()
    inputs["acquiring_rate_bp"] = 250
    res = rows_by_key(run_pnl(pnl_fn, MAIN_MONTH, inputs))
    base = rows_by_key(pnl[MAIN_MONTH])
    assert res["variable"]["amount"]["value"] > base["variable"]["amount"]["value"]
    assert res["fixed"]["amount"]["value"] == base["fixed"]["amount"]["value"]
    v = {k: r["amount"]["value"] for k, r in res.items()}
    assert v["revenue"] - v["variable"] - v["fixed"] - v["taxes"] - v["obligations"] == v["net_profit"]


# ------------------------------------------------------------------ period, status, partial data, running month
@pytest.mark.parametrize("month", ALL_MONTHS)
def test_period_and_status_of_closed_months(pnl, month):
    res = pnl[month]
    assert res["period"]["month"] == month and res["period"]["status"] == "closed" and res["period"].get("to") is None
    assert res["period"]["first_month"] == "2026-07"
    assert res["status"] == PNL[month]["status"] and res["partial_reasons"] == PNL[month]["partial_reasons"]


@pytest.mark.parametrize("case", OPEN_CASES, ids=OPEN_IDS)
def test_running_month_cuts_cash_at_as_of_and_accrues_obligations_for_the_whole_month(pnl_fn, case):
    res = run_pnl(pnl_fn, case["month"], as_of=date.fromisoformat(case["as_of"]))
    exp = {r["key"]: r for r in PNL[case["key"]]["rows"]}
    for key in ROW_KEYS:
        assert rows_by_key(res)[key]["amount"]["value"] == exp[key]["amount"]["value"], key
    assert list(labels(rows_by_key(res)["obligations"]["amount"]).items()) == list(exp["obligations"]["amount"]["breakdown"].items())
    assert rows_by_key(res)["taxes"]["amount"]["value"] == 0, "a tax paid after as_of is not counted yet"
    assert res["period"] == {"month": "2026-09", "status": "open", "to": case["as_of"], "first_month": "2026-07"}
    assert res["status"] == PNL[case["key"]]["status"] and res["partial_reasons"] == PNL[case["key"]]["partial_reasons"]
    v = {k: r["amount"]["value"] for k, r in rows_by_key(res).items()}
    assert v["revenue"] - v["variable"] - v["fixed"] - v["taxes"] - v["obligations"] == v["net_profit"]


def test_a_month_that_has_ended_is_closed_even_when_as_of_is_later(pnl_fn, pnl):
    res = run_pnl(pnl_fn, "2026-08", as_of=date(2026, 9, 15))
    assert res["period"]["status"] == "closed" and res["period"].get("to") is None
    assert rows_by_key(res)["net_profit"]["amount"]["value"] == rows_by_key(pnl["2026-08"])["net_profit"]["amount"]["value"]


PARTIAL_CASES = [
    ("no_obligations", {"charges": []}, None, ["no_obligations"]),
    ("no_vetmanager", {"sales": [], "card_payments": []}, None, ["no_vetmanager"]),
    ("bank_gap_date", {"bank_covered_to": date(2026, 9, 18)}, None, ["bank_gap"]),
    ("bank_gap_no_statement", {"bank_covered_to": None}, None, ["bank_gap"]),
    ("short_period", {}, date(2026, 9, 5), ["short_period"]),
    ("all_four_in_screen_order", {"sales": [], "card_payments": [], "bank_covered_to": None, "charges": []}, date(2026, 9, 5),
     ["no_vetmanager", "bank_gap", "short_period", "no_obligations"]),
]


@pytest.mark.parametrize("name,changes,as_of,reasons", PARTIAL_CASES, ids=[c[0] for c in PARTIAL_CASES])
def test_partial_data_reasons(pnl_fn, name, changes, as_of, reasons):
    inputs = {**build_inputs(), **changes}
    res = run_pnl(pnl_fn, MAIN_MONTH, inputs, as_of=as_of)
    assert res["partial_reasons"] == reasons
    assert res["status"] == "partial"
    v = {k: r["amount"]["value"] for k, r in rows_by_key(res).items()}
    assert v["revenue"] - v["variable"] - v["fixed"] - v["taxes"] - v["obligations"] == v["net_profit"], "amounts are never hidden"


def test_bank_covering_the_whole_month_is_not_a_gap(pnl_fn):
    inputs = {**build_inputs(), "bank_covered_to": date(2026, 9, 30)}
    assert "bank_gap" not in run_pnl(pnl_fn, MAIN_MONTH, inputs)["partial_reasons"]


def test_headline_when_present_names_the_net_profit_and_its_share(pnl):
    for month in MONTHS:
        headline = pnl[month].get("headline")
        if headline is None:
            pytest.skip("headline is not returned yet (requested by the designer: design/screens/pnl.md)")
        h = PNL[month]["headline_numbers"]
        assert contains_amount(headline, h["net_profit"]), (month, headline)
        assert f"{h['share_pct']:.1f}".replace(".", ",") in headline.replace(" ", " "), (month, headline)


# ================================================================== services vs goods (function 18)
@pytest.fixture(scope="module")
def direction_fn():
    return engine_function("engine.pnl", "compute_direction_view")


@pytest.mark.parametrize("key", MONTHS + OPEN_IDS)
def test_services_and_goods_revenue_direct_costs_and_margin(direction_fn, key):
    as_of = next((date.fromisoformat(c["as_of"]) for c in OPEN_CASES if c["key"] == key), None)
    res = run_pnl(direction_fn, key[:7], as_of=as_of)
    exp = DIRECTION[key]
    got = {d["direction"]: d for d in res["directions"]}
    assert [d["direction"] for d in res["directions"]] == ["services", "goods"]
    for e in exp["directions"]:
        g = got[e["direction"]]
        assert g["revenue"]["value"] == e["revenue"]["value"], e["direction"]
        assert g["direct_costs"]["value"] == e["direct_costs"], e["direction"]
        assert g["margin"]["value"] == e["margin"], e["direction"]
        assert float(g["margin_pct"]["value"]) == e["margin_pct"], e["direction"]
        assert float(g["revenue_share_pct"]["value"]) == e["revenue_share_pct"], e["direction"]
        assert labels(g["direct_costs"]) == e["direct_costs_breakdown"], e["direction"]
        assert g["revenue"]["value"] - g["direct_costs"]["value"] == g["margin"]["value"]
        for name in ("revenue", "direct_costs", "margin"):
            assert_figure(g[name], f"{e['direction']}.{name}")
    assert res["common_variable"]["value"] == exp["common_variable"]["value"]
    assert labels(res["common_variable"]) == exp["common_variable"]["breakdown"]


@pytest.mark.parametrize("month", MONTHS)
def test_bridge_directions_to_the_pnl(direction_fn, pnl, month):
    """margin(services) + margin(goods) - common = marginal profit; direct costs + common = variable; revenue adds up."""
    res = run_pnl(direction_fn, month)
    rows = rows_by_key(pnl[month])
    d = {x["direction"]: x for x in res["directions"]}
    common = res["common_variable"]["value"]
    assert d["services"]["revenue"]["value"] + d["goods"]["revenue"]["value"] == rows["revenue"]["amount"]["value"]
    assert d["services"]["direct_costs"]["value"] + d["goods"]["direct_costs"]["value"] + common == rows["variable"]["amount"]["value"]
    assert d["services"]["margin"]["value"] + d["goods"]["margin"]["value"] - common == rows["marginal_profit"]["amount"]["value"]


def test_direction_view_also_carries_the_pnl_rows(direction_fn, pnl):
    res = run_pnl(direction_fn, MAIN_MONTH)
    if "rows" not in res:
        pytest.skip("view=direction does not return rows yet (design/screens/pnl.md asks for the bridge rows)")
    assert res["rows"] == pnl[MAIN_MONTH]["rows"]


# ================================================================== norm (function 15)
@pytest.fixture(scope="module")
def norm_fn():
    return engine_function("engine.norm", "compute_norm")


@pytest.fixture(scope="module")
def norm(norm_fn):
    inputs = build_inputs()
    return {m: run_norm(norm_fn, m, inputs) for m in ALL_MONTHS}


@pytest.mark.parametrize("month", MONTHS)
def test_norm_items_order_status_tone_and_norm_values(norm, month):
    got, exp = norm[month]["items"], NORM[month]["items"]
    assert [i["key"] for i in got] == [e["key"] for e in exp] == \
        ["payroll", "drugs", "rent", "lab", "writeoff", "acquiring", "marketing", "other", "net_profit"]
    for g, e in zip(got, exp):
        assert g["status"] == e["status"], (month, g["key"])
        assert g["tone"] == e["tone"], (month, g["key"])
        assert g["label"] == e["label"]
        if e["norm"] is None:
            assert not g.get("norm")
            continue
        assert float(g["norm"]["min_pct"]) == e["norm"]["min_pct"] and float(g["norm"]["max_pct"]) == e["norm"]["max_pct"], g["key"]
        assert (g["norm"]["source"] == "clinic") == (e["norm"]["source"] == "clinic"), g["key"]


@pytest.mark.parametrize("month", MONTHS)
def test_actual_share_and_deviation_in_points_and_roubles(norm, month):
    for g, e in zip(norm[month]["items"], NORM[month]["items"]):
        assert_figure(g["actual_pct"], f"{g['key']}.actual_pct", "pct")
        assert float(g["actual_pct"]["value"]) == e["actual_pct"], g["key"]
        if e["status"] == "no_norm":
            assert g.get("deviation_pp") is None and g.get("deviation_rub") is None, "no norm: no deviation"
            continue
        assert_figure(g["deviation_rub"], f"{g['key']}.deviation_rub")
        assert g["deviation_rub"]["value"] == e["deviation_rub"], (month, g["key"])
        assert_figure(g["deviation_pp"], f"{g['key']}.deviation_pp", "pct")
        assert float(g["deviation_pp"]["value"]) == e["deviation_pp"], (month, g["key"])


@pytest.mark.parametrize("month", MONTHS)
def test_share_breakdown_lists_the_articles_it_is_made_of(norm, month):
    """design/screens/norm.md: the breakdown of 'Ваша доля' are the articles in roubles (sum = numerator); the revenue is in details."""
    for g, e in zip(norm[month]["items"], NORM[month]["items"]):
        fig = g["actual_pct"]
        assert list(labels(fig).items()) == list(e["amount_breakdown"].items()), (month, g["key"])   # biggest first, ties by name
        assert sum(b["value"] for b in fig["breakdown"]) == e["amount"], (month, g["key"])
        if fig.get("details"):
            assert PNL[month]["revenue"] in [d["value"] for d in fig["details"]], (month, g["key"])


@pytest.mark.parametrize("month", MONTHS)
def test_deviation_signs_follow_the_status(norm, month):
    for g in norm[month]["items"]:
        if g["status"] == "no_norm":
            continue
        value = g["deviation_rub"]["value"]
        assert (value > 0) == (g["status"] == "above") and (value < 0) == (g["status"] == "below") and (value == 0) == (g["status"] == "ok")


@pytest.mark.parametrize("month", MONTHS)
def test_shown_share_minus_shown_bound_equals_shown_deviation_within_a_tenth(norm, month):
    for g in norm[month]["items"]:
        if g["status"] not in ("above", "below"):
            continue
        bound = g["norm"]["max_pct"] if g["status"] == "above" else g["norm"]["min_pct"]
        assert abs(float(g["actual_pct"]["value"]) - float(bound) - float(g["deviation_pp"]["value"])) <= 0.1 + 1e-9, g["key"]


@pytest.mark.parametrize("month", MONTHS)
def test_groups_plus_other_plus_net_profit_equal_the_revenue(norm, month):
    """Computed from the engine's own output: the norm table accounts for the whole revenue (the write-off memo row is outside)."""
    total = sum(sum(b["value"] for b in g["actual_pct"]["breakdown"]) for g in norm[month]["items"] if not g.get("memo"))
    assert total == PNL[month]["revenue"]


def test_norm_amounts_agree_with_the_pnl(norm, pnl):
    """The norm report and the P&L must tell one story."""
    for m in MONTHS:
        items = items_by_key(norm[m])
        rows = rows_by_key(pnl[m])
        assert float(items["net_profit"]["actual_pct"]["value"]) == float(rows["net_profit"]["share_pct"]["value"])
        assert items["net_profit"]["actual_pct"]["breakdown"][0]["value"] == rows["net_profit"]["amount"]["value"]
        assert items["acquiring"]["actual_pct"]["breakdown"][0]["value"] == labels(rows["variable"]["amount"])["Комиссия эквайринга"]
        payroll_child = next(c for c in rows["fixed"]["children"] if c["key"] == "fixed_payroll")
        assert labels(items["payroll"]["actual_pct"]) == {
            "Проценты врачам": labels(rows["variable"]["amount"])["Проценты врачам"],
            "Оклады врачей": labels(payroll_child["amount"])["Оклады врачей"]}
        doctors = labels(rows["variable"]["amount"])["Проценты врачам"] + labels(payroll_child["amount"])["Оклады врачей"]
        assert sum(b["value"] for b in items["payroll"]["actual_pct"]["breakdown"]) == doctors


def test_the_write_off_row_is_a_memo_item_outside_the_hundred_percent(norm):
    items = items_by_key(norm[MAIN_MONTH])
    assert items["writeoff"].get("memo") is True and not items["drugs"].get("memo")


def test_clinic_norm_overrides_the_industry_one(norm):
    marketing = items_by_key(norm[MAIN_MONTH])["marketing"]
    assert marketing["norm"]["source"] == "clinic" and float(marketing["norm"]["min_pct"]) == 2.0
    assert marketing["status"] == "ok", "2.1% is below the industry 3% but inside the clinic's own 2-6%"


def test_norm_of_a_month_without_revenue_is_empty(norm):
    assert norm[EMPTY_MONTH]["items"] == [] and norm[EMPTY_MONTH]["status"] == "empty"


@pytest.mark.parametrize("case", OPEN_CASES, ids=OPEN_IDS)
def test_running_month_norm_has_shares_and_bounds_but_no_ratings(norm_fn, case):
    """Owner decision 2026-10-14: a running month is not compared with the norm. Shares are real, the norm bounds stay,
    the keys status / tone / deviation_pp / deviation_rub are ABSENT (not null)."""
    res = run_norm(norm_fn, case["month"], as_of=date.fromisoformat(case["as_of"]))
    exp = NORM[case["key"]]
    assert res["period"]["status"] == "open" and res["period"]["to"] == case["as_of"]
    assert res["partial_reasons"] == exp["partial_reasons"] and res["status"] == exp["status"]
    assert [i["key"] for i in res["items"]] == [e["key"] for e in exp["items"]]
    for g, e in zip(res["items"], exp["items"]):
        for key in RATING_KEYS:
            assert key not in g, f"{g['key']}: `{key}` must be absent in a running month"
        assert float(g["actual_pct"]["value"]) == e["actual_pct"], g["key"]
        assert list(labels(g["actual_pct"]).items()) == list(e["amount_breakdown"].items()), g["key"]
        if e["norm"] is not None:
            assert float(g["norm"]["min_pct"]) == e["norm"]["min_pct"] and float(g["norm"]["max_pct"]) == e["norm"]["max_pct"], g["key"]
    assert sum(sum(b["value"] for b in g["actual_pct"]["breakdown"]) for g in res["items"] if not g.get("memo")) == PNL[case["key"]]["revenue"]


def test_running_month_headline_when_present_is_the_owner_text(norm_fn):
    for case in OPEN_CASES:
        res = run_norm(norm_fn, case["month"], as_of=date.fromisoformat(case["as_of"]))
        if res.get("headline") is None:
            pytest.skip("headline is not returned by the engine (the API builds it from the engine result)")
        assert res["headline"] == NORM[case["key"]]["headline_open"]


def test_running_month_writeoff_row_counts_only_days_up_to_as_of(norm_fn):
    res = run_norm(norm_fn, OPEN["month"], as_of=OPEN_AS_OF)
    row = items_by_key(res)["writeoff"]
    assert row["memo"] is True
    assert sum(b["value"] for b in row["actual_pct"]["breakdown"]) == {i["key"]: i for i in NORM[OPEN["key"]]["items"]}["writeoff"]["amount"]


def test_missing_benchmarks_give_no_norm_everywhere(norm_fn):
    res = run_norm(norm_fn, MAIN_MONTH, {**build_inputs(), "benchmarks": []})
    assert "no_benchmark" in res["partial_reasons"] and res["status"] == "partial"
    assert all(i["status"] == "no_norm" for i in res["items"])


def test_norm_headline_when_present_names_the_amounts_above_the_norm(norm):
    headline = norm[MAIN_MONTH].get("headline")
    if headline is None:
        pytest.skip("headline is not returned yet (requested by the designer: design/screens/norm.md)")
    h = NORM[MAIN_MONTH]["headline_numbers"]
    for kop in h["above"].values():
        assert contains_amount(headline, kop), headline
    assert contains_amount(headline, h["above_total"]), headline


def test_norm_is_deterministic_and_order_independent(norm_fn, norm):
    assert run_norm(norm_fn, MAIN_MONTH, reversed_inputs(build_inputs())) == norm[MAIN_MONTH]
    assert run_norm(norm_fn, MAIN_MONTH) == run_norm(norm_fn, MAIN_MONTH)


# ================================================================== stock (function 17)
@pytest.fixture(scope="module")
def stock_fn():
    return engine_function("engine.stock", "compute_stock")


@pytest.fixture(scope="module")
def stock(stock_fn):
    return run_stock(stock_fn)


def test_frozen_buckets_use_calendar_days_and_include_the_boundaries(stock):
    fig = stock["frozen"]
    assert_figure(fig, "frozen")
    assert fig["value"] == STOCK["frozen"]["value"]
    assert labels(fig) == STOCK["frozen"]["breakdown"]
    assert list(labels(fig)) == list(STOCK["frozen"]["breakdown"])  # order 60-89, 90-179, 180+
    assert sum(b["value"] for b in fig["breakdown"]) == fig["value"]


def test_frozen_items_list(stock):
    got = [(i["item"], i["qty"], i["amount"], i["idle_days"]) for i in stock["frozen_items"]]
    exp = [(i["item"], i["qty"], i["amount"], i["idle_days"]) for i in STOCK["frozen_items"]]
    assert got == exp
    assert "Активированный уголь" not in {i["item"] for i in stock["frozen_items"]}, "nothing on hand: not frozen"
    assert "Бинт эластичный" not in {i["item"] for i in stock["frozen_items"]}, "idle 59 days: not frozen"


def test_expiring_within_60_days_includes_day_0_and_60_and_excludes_61_and_expired(stock):
    fig = stock["expiring_60d"]
    assert_figure(fig, "expiring_60d")
    assert fig["value"] == STOCK["expiring_60d"]["value"]
    assert labels(fig) == STOCK["expiring_60d"]["breakdown"]
    rows = stock["expiring"]
    assert [(r["item"], r["expires_on"], r["days_left"], r["qty"], r["amount"]["value"]) for r in rows] == \
        [(r["item"], r["expires_on"], r["days_left"], r["qty"], r["amount"]) for r in STOCK["expiring_60d"]["rows"]]
    assert [r["days_left"] for r in rows][0] == 0 and [r["days_left"] for r in rows][-1] == 60
    assert sum(r["amount"]["value"] for r in rows) == fig["value"]
    for r in rows:
        assert_figure(r["amount"], f"expiring.{r['item']}.amount")


def test_expired_batches_still_on_the_shelf_are_reported_separately(stock):
    assert stock["expired_on_hand"]["value"] == STOCK["expired_on_hand"]["value"] == 55_500
    assert labels(stock["expired_on_hand"]) == STOCK["expired_on_hand"]["breakdown"]


def test_written_off_in_the_month_of_as_of_with_reasons(stock):
    fig = stock["written_off_month"]
    assert_figure(fig, "written_off_month")
    assert fig["value"] == STOCK["written_off_month"]["value"]
    assert labels(fig) == STOCK["written_off_month"]["breakdown"]


def test_writeoffs_after_as_of_are_not_counted(stock_fn):
    inputs = build_inputs()
    res = run_stock(stock_fn, "2026-09-15", inputs)
    in_range = sum(w.amount for w in inputs["writeoffs"] if "2026-09-01" <= w.date.isoformat() <= "2026-09-15")
    assert res["written_off_month"]["value"] == in_range


def test_stock_value_and_turnover(stock):
    assert stock["stock_value"]["value"] == STOCK["stock_value"]["value"]
    t = stock["turnover_days"]
    assert t["unit"] == "days" and type(t["value"]) is int and t["value"] == STOCK["turnover_days"]["value"]
    assert [b["value"] for b in t["breakdown"]] == STOCK["turnover_days"]["breakdown_values"]
    assert stock["norm_turnover_days"] == STOCK["norm_turnover_days"] == 45


def test_stock_is_deterministic_and_order_independent(stock_fn, stock):
    assert run_stock(stock_fn, STOCK_AS_OF, reversed_inputs(build_inputs())) == stock
    assert run_stock(stock_fn) == run_stock(stock_fn)


def test_stock_inputs_are_not_mutated(stock_fn):
    inputs = build_inputs()
    before = snapshot(inputs)
    run_stock(stock_fn, STOCK_AS_OF, inputs)
    assert inputs == before


# ------------------------------------------------------------------ stock: idle intervals, positions, write-offs, write-off norm
def num(x):
    """The engine may return a Figure or a bare number; the expected value is a number."""
    return x["value"] if isinstance(x, dict) else x


def stock_field(stock, key):
    if key not in stock:
        pytest.skip(f"engine.stock result has no `{key}` yet (the API may build it from `frozen_items`; covered by the seeded contract test)")
    return stock[key]


def test_idle_buckets_amounts_and_positions(stock):
    got = stock_field(stock, "idle_buckets")
    assert [b["key"] for b in got] == [e["key"] for e in STOCK["idle_buckets"]] == ["60_89", "90_179", "180_plus"]
    for g, e in zip(got, STOCK["idle_buckets"]):
        assert num(g["amount"]) == e["amount"], e["key"]
        assert num(g["positions"]) == e["positions"], e["key"]
    assert sum(num(b["amount"]) for b in got) == stock["frozen"]["value"]


def test_frozen_positions_count_and_split_by_interval(stock):
    fig = stock_field(stock, "frozen_positions")
    assert num(fig) == STOCK["frozen_positions"]["value"] == 6
    if isinstance(fig, dict):
        assert fig["unit"] == "count" and [b["value"] for b in fig["breakdown"]] == STOCK["frozen_positions"]["breakdown_values"]


def test_written_off_items_of_the_month_by_amount(stock):
    got = stock_field(stock, "written_off_items")
    assert [(i["item"], i["date"], i["qty"], i["reason"], num(i["amount"])) for i in got] == \
        [(i["item"], i["date"], i["qty"], i["reason"], i["amount"]) for i in STOCK["written_off_items"]]
    assert sum(num(i["amount"]) for i in got) == stock["written_off_month"]["value"]


def test_written_off_norm_is_08_percent_of_the_revenue_of_the_same_month(stock_fn):
    if not {"month_revenue", "revenue"} & set(inspect.signature(stock_fn).parameters):
        pytest.skip("compute_stock does not take the month revenue (written_off_norm is built by the API from the P&L revenue)")
    exp = STOCK["written_off_norm"]
    res = run_stock(stock_fn, revenue=exp["revenue"], month_revenue=exp["revenue"])
    assert num(res["written_off_norm"]) == exp["value"] == 878_525
    assert exp["expired"] - exp["value"] == exp["over_norm"]


def test_engine_idle_list_feeds_the_pages_in_the_right_order(stock):
    """/stock/idle pages the same list: amount descending, ties by name; the first page of `all` with limit 2 holds the two biggest."""
    case = next(c for c in STOCK["idle_pages"] if c["bucket"] == "all" and c["limit"] == 2)
    assert [i["item"] for i in stock["frozen_items"][:2]] == [i["item"] for i in case["pages"][0]["items"]]
