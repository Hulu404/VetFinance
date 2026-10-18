"""Golden tests of the stage 5 engines (service cost and margin, price split, load of rooms/doctors, hour cost), set06.

Expected numbers come from set06/expected.json, computed independently by tools/compute_expected_set06.py, never from the engine.
Interfaces under test: see set06_support.py and docs/handoff.md ("tester -> backend-developer (этап 5)"). The tests skip
while engine.pricing / engine.efficiency or the input classes are missing (the engine does not exist yet).
"""
import copy
from collections import Counter

import pytest

from set06_support import (CASE_KEYS, DATA, SERVICE_CASES, EXPECTED, PART_KEYS, by_id, engine_function, figure_lines, hour_parts, inputs_for,
                           parts_of, rows_by_id, run_efficiency, run_price, shares_of, v)

CASES = EXPECTED["cases"]
SERVICE_IDS = [s["id"] for s in CASES["main"]["services"]]


def shuffled(inputs):
    return {k: (x[::-1] if isinstance(x, list) else x) for k, x in inputs.items()}


# ================================================================== price list and cost (functions 11, 12)
@pytest.fixture(scope="module")
def price_fn():
    return engine_function("engine.pricing", "compute_price_list")


@pytest.fixture(scope="module")
def prices(price_fn):
    return {key: run_price(key, price_fn) for key in SERVICE_CASES}


@pytest.mark.parametrize("case", SERVICE_CASES)
def test_list_order_counts_and_services(prices, case):
    got = [s["id"] for s in prices[case]["items"]]
    assert got == [s["id"] for s in CASES[case]["services"]]
    assert "S9" not in got and "S12" not in got          # never sold in the 90 days: no price, not in the list
    counts = prices[case]["counts"]
    assert {k: counts[k] for k in ("all", "loss", "no_recipe")} == CASES[case]["counts"]
    assert counts["all"] == len(got)


@pytest.mark.parametrize("case", SERVICE_CASES)
@pytest.mark.parametrize("sid", SERVICE_IDS)
def test_service_numbers_to_the_kopeck(prices, case, sid):
    got, exp = by_id(prices[case]["items"])[sid], by_id(CASES[case]["services"])[sid]
    assert v(got["price"]) == exp["price"]
    assert v(got["visits_month"]) == exp["visits_month"]
    assert parts_of(got) == {k: exp["parts"][k] for k in PART_KEYS}
    assert v(got["margin_pct"]) == exp["net_margin_pct"]
    assert v(got["monthly_profit"]) == exp["monthly_profit"]
    if "net_profit" in got:
        assert v(got["net_profit"]) == exp["net_profit"]
    assert got["status"] == exp["status"]
    assert got["missing"] == exp["missing"]


@pytest.mark.parametrize("case", SERVICE_CASES)
@pytest.mark.parametrize("sid", SERVICE_IDS)
def test_price_is_the_sum_of_the_parts_and_the_profit(prices, case, sid):
    s = by_id(prices[case]["items"])[sid]
    if s["status"] == "no_recipe":
        pytest.skip("no techcard: the profit is not computed")
    known = [a for a in parts_of(s).values() if a is not None]
    assert sum(known) + v(s["net_profit"]) == v(s["price"])


@pytest.mark.parametrize("case", ["main", "ward_no_schedule", "no_hours"])
@pytest.mark.parametrize("sid", SERVICE_IDS)
def test_shares_sum_to_exactly_100(prices, case, sid):
    s = by_id(prices[case]["items"])[sid]
    exp = by_id(CASES[case]["services"])[sid]
    if exp["shares"] is None:
        pytest.skip("no techcard: the bar is not drawn, shares are null")
    shares = shares_of(s)
    assert {k: x for k, x in shares.items() if x is not None} == {k: x for k, x in exp["shares"].items() if x is not None}
    assert round(sum(x for x in shares.values() if x is not None) * 10) + round(v(s["net_margin_pct"]) * 10) == 1000


@pytest.mark.parametrize("sid", SERVICE_IDS)
def test_service_card_equals_the_list_row(prices, sid):
    card_fn = engine_function("engine.pricing", "compute_service_cost")
    card = run_price("main", card_fn, service_id=sid)
    row = by_id(prices["main"]["items"])[sid]
    assert parts_of(card) == parts_of(row)
    assert (v(card["price"]), v(card["net_profit"]), v(card["monthly_profit"])) == \
        (v(row["price"]), v(row["net_profit"]), v(row["monthly_profit"]))
    assert card["status"] == row["status"] and card["missing"] == row["missing"]


def test_loss_making_service_has_negative_profit_and_percent_and_is_first(prices):
    first = prices["main"]["items"][0]
    assert first["id"] == "S6"
    assert v(first["margin_pct"]) < 0 and v(first["monthly_profit"]) < 0
    assert prices["main"]["counts"]["loss"] == 1


def test_service_without_techcard_has_no_profit_and_materials_are_null(prices):
    s = by_id(prices["main"]["items"])["S7"]
    assert s["status"] == "no_recipe" and s["missing"] == ["recipe"]
    parts = parts_of(s)
    assert (parts["drugs"], parts["anesthesia"], parts["supplies"]) == (None, None, None)
    assert v(s["margin_pct"]) is None and v(s["monthly_profit"]) is None
    assert [x["id"] for x in prices["main"]["items"][-2:]] == ["S10", "S7"]      # services without a margin go last, by name


def test_recorded_empty_techcard_is_a_service_without_materials_not_a_missing_recipe(prices):
    s = by_id(prices["main"]["items"])["S11"]
    assert s["status"] == "ok" and parts_of(s)["supplies"] == 0 and v(s["margin_pct"]) is not None


def test_partial_services_name_what_is_missing_and_leave_the_part_empty(prices):
    s = by_id(prices["main"]["items"])["S5"]
    assert s["status"] == "partial" and s["missing"] == ["item_no_cost"]       # i16 has no purchase price: not counted
    assert parts_of(s)["fixed"] is not None
    s10 = by_id(prices["main"]["items"])["S10"]
    assert s10["missing"] == ["recipe"] and parts_of(s10)["fixed"] == 23_073       # no duration: the clinic average 30 min is used


def test_manual_services_price_matching_and_flags(prices):
    items = by_id(prices["main"]["items"])
    m1, s7 = items["M1"], items["S7"]
    assert (v(m1["price"]), v(m1["visits_month"]), v(m1["monthly_profit"])) == (250_000, 0, 0)      # entered price, no sales
    assert v(s7["price"]) == 60_000 and v(s7["visits_month"]) == 16 and "M2" not in items            # same name: absorbed, actual price
    assert m1.get("source", "manual") == "manual" and s7.get("source", "vetmanager") == "vetmanager"


def test_duration_of_a_service_without_minutes_is_the_clinic_average(prices):
    exp = by_id(CASES["main"]["services"])["S10"]
    assert exp["minutes_source"] == "clinic_average" and exp["minutes"] == 30
    got = by_id(prices["main"]["items"])["S10"]
    if "minutes_source" in got:
        assert got["minutes_source"] == "clinic_average"


def test_service_sold_only_before_this_month_keeps_its_price_and_has_zero_profit(prices):
    s = by_id(prices["main"]["items"])["S8"]                   # July only, with older sales outside the 90 days
    assert v(s["price"]) == 190_000 and v(s["visits_month"]) == 0 and v(s["monthly_profit"]) == 0


def test_price_is_the_average_of_the_90_days_after_discounts(prices):
    s = by_id(prices["main"]["items"])
    assert (v(s["S2"]["price"]), v(s["S3"]["price"])) == (122_741, 208_482)


def test_half_kopeck_rounds_up_and_expired_batch_is_ignored(prices):
    assert parts_of(by_id(prices["main"]["items"])["S4"])["anesthesia"] == 45_001 + 7_590     # 0.5 ml x 900,01 rub: half up


def test_exhausted_item_costs_the_last_received_batch_and_expiry_on_as_of_is_still_good(prices):
    items = by_id(prices["main"]["items"])
    assert parts_of(items["S5"])["anesthesia"] == 3 * 64_500
    assert parts_of(items["S6"])["drugs"] == 15_080            # (24 x 74,50 + 6 x 79) / 30 x 2; the 6 flasks expire on as_of


def test_same_input_twice_and_any_input_order_give_the_same_answer(price_fn):
    a = run_price("main", price_fn)
    assert a == run_price("main", price_fn)
    assert a == run_price("main", price_fn, inputs=shuffled(inputs_for("main")))


def test_clinic_without_sales_and_without_manual_services_has_an_empty_list(price_fn):
    inputs = inputs_for("main")
    inputs.update(sales=[], visits=[], manual_services=[])
    got = run_price("main", price_fn, inputs=inputs)
    assert got["items"] == [] and got["counts"]["all"] == 0


def test_manual_services_are_listed_even_when_there_are_no_sales(price_fn):
    """Owner's decision 1: a service entered by hand is in the list without sales, at its entered price (the list is not empty)."""
    inputs = inputs_for("main")
    inputs.update(sales=[], visits=[])
    got = run_price("main", price_fn, inputs=inputs)
    assert sorted((s["id"], v(s["price"]), v(s["visits_month"])) for s in got["items"]) == [("M1", 250_000, 0), ("M2", 70_000, 0)]
    assert got["counts"]["all"] == 2


def test_month_without_a_statement_gives_no_profit_to_any_service(price_fn):
    """Owner's decision 14: no expenses in the P&L of the month -> no profit, margin or shares for any service (hour cost is null)."""
    got = run_price("no_expenses", price_fn)
    assert got["items"]
    for s in got["items"]:
        assert v(s["margin_pct"]) is None and v(s["monthly_profit"]) is None, s["id"]
        assert s["status"] in ("partial", "no_recipe") and ("no_expenses" in s["missing"] or s["status"] == "no_recipe"), s["id"]
        parts = parts_of(s)
        assert all(parts[k] is None for k in ("acquiring", "taxes", "fixed")), s["id"]       # taken from the empty P&L: not zero, null
        assert all((parts[k] is None) == (x is None) for k, x in shares_of(s).items()), s["id"]
    assert got["counts"]["loss"] == 0


def test_sort_by_monthly_profit(price_fn):
    got = run_price("main", price_fn, sort="profit")
    assert [s["id"] for s in got["items"]] == CASES["main"]["order_by_profit"]


# ================================================================== efficiency (functions 33, 34)
@pytest.fixture(scope="module")
def eff_fn():
    return engine_function("engine.efficiency", "compute_efficiency")


@pytest.fixture(scope="module")
def effs(eff_fn):
    return {key: run_efficiency(key, eff_fn) for key in CASE_KEYS}


@pytest.mark.parametrize("case", CASE_KEYS)
def test_headline_numbers(effs, case):
    got, exp = effs[case], CASES[case]["efficiency"]
    assert got["load_by"] == exp["load_by"]
    assert v(got["visits"]) == exp["visits"] and v(got["avg_check"]) == exp["avg_check"]
    assert v(got["load_pct"]) == exp["load_pct"]
    assert v(got["hour_cost"]) == exp["hour_cost"]
    if "hour_margin" in got:
        assert v(got["hour_margin"]) == exp["hour_margin"]


@pytest.mark.parametrize("case", ["main", "ward_no_schedule", "doctor_no_hours"])
def test_hours_and_hour_cost_lines(effs, case):
    exp = CASES[case]["efficiency"]
    assert (v(effs[case]["busy_hours"]), v(effs[case]["available_hours"])) == (exp["busy_hours"], exp["available_hours"])
    lines = figure_lines(effs[case]["hour_cost"])
    assert lines == [exp["hour_cost_lines"]["fixed"], exp["hour_cost_lines"]["obligations"]]
    assert sum(lines) == v(effs[case]["hour_cost"])


@pytest.mark.parametrize("case", ["main", "ward_no_schedule"])
def test_hour_cost_parts_table(effs, case):
    exp = CASES[case]["efficiency"]
    assert hour_parts(effs[case]) == {"hours": exp["available_hours"], "busy_hours": exp["busy_hours"],
                                      "fixed": exp["pool"]["fixed"], "obligations": exp["pool"]["obligations"]}


def test_rooms_mode_has_rooms_with_hours_and_load(effs):
    got, exp = rows_by_id(effs["main"]["rooms"]), {r["id"]: r for r in CASES["main"]["efficiency"]["rooms"]}
    assert set(got) == set(exp) and effs["main"]["doctors"] == []
    for rid, row in exp.items():
        assert v(got[rid]["load_pct"]) == row["load_pct"]
        for key in ("busy_hours", "available_hours", "free_hours"):
            if key in got[rid]:
                assert v(got[rid][key]) == row[key], (rid, key)


def test_half_an_hour_of_a_room_schedule_rounds_up(effs):
    assert {r["id"]: r["available_hours"] for r in CASES["main"]["efficiency"]["rooms"]}["R2"] == 138      # 137,5 h


@pytest.mark.parametrize("case", ["ward_no_schedule", "doctor_no_hours", "no_hours"])
def test_one_room_without_schedule_switches_everything_to_doctors(effs, case):
    assert effs[case]["rooms"] == [] and effs[case]["load_by"] == "doctors"


@pytest.mark.parametrize("case", ["ward_no_schedule", "doctor_no_hours", "no_hours"])
def test_doctor_rows(effs, case):
    got = rows_by_id(effs[case]["doctors"])
    for exp in CASES[case]["efficiency"]["doctors"]:
        row = got[exp["id"]]
        assert v(row["load_pct"]) == exp["load_pct"]
        if exp["available_hours"] is None:
            assert v(row.get("available_hours")) is None
        else:
            assert (v(row["available_hours"]), v(row["busy_hours"])) == (exp["available_hours"], exp["busy_hours"])


def test_month_without_a_statement_keeps_the_load_and_has_no_hour_cost(effs):
    e, exp = effs["no_expenses"], CASES["no_expenses"]["efficiency"]
    assert e["status"] == "partial" and e["partial_reasons"] == ["no_expenses"] == exp["partial_reasons"]
    assert v(e["load_pct"]) == exp["load_pct"] == CASES["main"]["efficiency"]["load_pct"]
    assert v(e["hour_cost"]) is None and v(e.get("hour_margin")) is None


def test_without_any_hours_nothing_is_computed_and_the_screen_is_partial(effs):
    e = effs["no_hours"]
    assert v(e["load_pct"]) is None and v(e["hour_cost"]) is None
    assert e["status"] == "partial" and e["partial_reasons"] == ["no_doctor_hours"]
    assert v(e["visits"]) == CASES["no_hours"]["efficiency"]["visits"]


def test_visits_without_a_doctor_are_counted_but_do_not_load_anybody(effs):
    exp = CASES["ward_no_schedule"]["efficiency"]
    assert exp["visits_without_doctor"] == 5
    assert exp["visits"] == sum(exp["visits_by_doctor"].values()) + 5


def test_efficiency_is_repeatable_and_ignores_the_input_order(eff_fn):
    a = run_efficiency("main", eff_fn)
    assert a == run_efficiency("main", eff_fn) == run_efficiency("main", eff_fn, inputs=shuffled(inputs_for("main")))


def test_no_visits_gives_no_average_check_and_no_crash(eff_fn):
    inputs = inputs_for("main")
    inputs.update(visits=[], sales=[])
    e = run_efficiency("main", eff_fn, inputs=inputs)
    assert v(e["visits"]) == 0 and v(e["avg_check"]) in (0, None)


def test_the_engines_do_not_mutate_the_data(price_fn):
    before = copy.deepcopy(DATA["sales"][:5])
    run_price("main", price_fn)
    assert DATA["sales"][:5] == before and Counter(s["status"] for s in DATA["sales"])["save"] == 8
