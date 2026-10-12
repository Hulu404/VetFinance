"""Internal consistency of set03 (runs without the engine): data.json is sane, expected.json is coherent and agrees
with a second, differently written calculation (day-by-day simulation) on the main figures."""
from collections import defaultdict
from datetime import date, timedelta

import pytest

from set03_support import CASES, DATA, EXPECTED, MAIN_AS_OF, case

D = date.fromisoformat
ACCOUNTS = {a["id"]: a for a in DATA["accounts"]}


# ---------------------------------------------------------------- data.json
def test_all_money_is_integer_kopecks_and_some_have_kopecks():
    amounts = [t["amount"] for t in DATA["transactions"]] + [s["amount"] for s in DATA["sales"]] \
        + [ln["amount"] for s in DATA["sales"] for ln in s["lines"]] + [a["opening_balance"] for a in DATA["accounts"]]
    assert all(type(x) is int for x in amounts)
    assert sum(1 for x in amounts if x % 100) > 50


def test_invoice_amount_equals_sum_of_lines_and_drafts_exist():
    assert all(s["amount"] == sum(ln["amount"] for ln in s["lines"]) for s in DATA["sales"])
    assert {s["status"] for s in DATA["sales"]} == {"exec", "save"}


def test_transfers_net_zero_per_group_and_duplicates_have_an_original():
    groups = defaultdict(int)
    for t in DATA["transactions"]:
        if t["kind"] == "transfer":
            groups[t["transfer_group"]] += t["amount"]
    assert groups and all(v == 0 for v in groups.values())
    dups = [t for t in DATA["transactions"] if t["status"] == "duplicate"]
    assert len(dups) == 2
    for d in dups:
        assert any(o["amount"] == d["amount"] and o["source"] == "bot" and o["account_id"] == d["account_id"]
                   and abs((D(o["date"]) - D(d["date"])).days) <= 3 for o in DATA["transactions"])


def test_has_check_operations_future_operations_and_three_doctors():
    assert sum(1 for t in DATA["transactions"] if t["status"] == "check") == 2
    assert any(t["date"] > MAIN_AS_OF for t in DATA["transactions"])
    assert len(DATA["doctors"]) == 3
    assert {v["doctor_id"] for v in DATA["visits"]} == {d["id"] for d in DATA["doctors"]}


def test_no_account_goes_negative_on_any_day():
    bal = {a["id"]: a["opening_balance"] for a in DATA["accounts"]}
    by_day = defaultdict(list)
    for t in DATA["transactions"]:
        if t["status"] != "duplicate":
            by_day[t["date"]].append(t)
    day = D("2026-08-01")
    while day <= D("2026-09-21"):
        for t in by_day[day.isoformat()]:
            bal[t["account_id"]] += t["amount"]
        assert all(v >= 0 for v in bal.values()), (day, bal)
        day += timedelta(days=1)


def test_vacation_reduces_visits_of_doctor_d2():
    def count(doc, start, end):
        return sum(1 for v in DATA["visits"] if v["doctor_id"] == doc and start <= v["date"] <= end)
    assert count("D2", "2026-09-10", "2026-09-20") == 0 < count("D1", "2026-09-10", "2026-09-20")


# ---------------------------------------------------------------- expected.json is coherent
@pytest.mark.parametrize("c", CASES, ids=lambda c: c["as_of"])
def test_expected_breakdowns_add_up(c):
    bal = c["balance"]
    assert bal["total"]["value"] == bal["bank"]["value"] + bal["cash"]["value"]
    for k in ("total", "bank", "cash"):
        assert sum(bal[k]["breakdown"].values()) == bal[k]["value"]
    m = c["month"]
    for k in ("revenue", "expenses", "profit", "visits"):
        assert sum(m[k]["breakdown"].values()) == m[k]["value"], k
    assert m["profit"]["value"] == m["revenue"]["value"] - m["expenses"]["value"]
    assert c["balance_trend"][-1]["value"] == bal["total"]["value"]
    if c["week_change"]:
        assert sum(c["week_change"]["breakdown"].values()) == c["week_change"]["value"]
        assert c["week_change"]["previous"] + c["week_change"]["value"] == bal["total"]["value"]
    r = c["runway_days"]
    assert r["value"] == r["breakdown_values"][0] * r["breakdown_values"][3] // r["breakdown_values"][1]


def test_expected_trend_is_consecutive_days():
    for c in CASES:
        days = [D(p["date"]) for p in c["balance_trend"]]
        assert days[-1] == D(c["as_of"])
        assert all(b - a == timedelta(days=1) for a, b in zip(days, days[1:]))
        assert len(days) == min(14, (D(c["as_of"]) - D("2026-08-01")).days + 1)


def test_expected_advice_is_ordered_and_covers_all_severities_and_rules():
    rank = {"alert": 0, "warning": 1, "good": 2}
    for c in CASES:
        ranks = [rank[a["severity"]] for a in c["advice"]]
        assert ranks == sorted(ranks)
        assert all(a["why_amounts"] or a["why_numbers"] for a in c["advice"])
    all_advice = [a for c in CASES for a in c["advice"]]
    assert {a["severity"] for a in all_advice} == {"alert", "warning", "good"}
    assert {a["id"] for a in all_advice} == {"cash_runway", "drug_share", "revenue_drop", "margin_ok"}
    assert [a["id"] for a in case(MAIN_AS_OF)["advice"]] == ["cash_runway", "drug_share"]


# ---------------------------------------------------------------- second calculation (day by day), main date
def simulate(as_of):
    """Walks day by day instead of filtering lists: a deliberately different algorithm."""
    bal = {a["id"]: a["opening_balance"] for a in DATA["accounts"]}
    spent = defaultdict(int)
    revenue = {"service": 0, "good": 0}
    exp_by_day = {}
    by_date = defaultdict(list)
    for t in DATA["transactions"]:
        by_date[t["date"]].append(t)
    sales_by_date = defaultdict(list)
    for s in DATA["sales"]:
        sales_by_date[s["date"]].append(s)
    day, daily_total = D("2026-08-01"), {}
    while day <= as_of:
        out_today = 0
        for t in by_date[day.isoformat()]:
            if t["status"] == "duplicate":
                continue
            bal[t["account_id"]] += t["amount"]
            if t["kind"] == "out":
                out_today += -t["amount"]
                if day.month == as_of.month:
                    spent[t["category"] or "Без статьи"] += -t["amount"]
        exp_by_day[day] = out_today
        if day.month == as_of.month:
            for s in sales_by_date[day.isoformat()]:
                if s["status"] == "exec":
                    for ln in s["lines"]:
                        revenue[ln["kind"]] += ln["amount"]
        daily_total[day] = sum(bal.values())
        day += timedelta(days=1)
    return bal, spent, revenue, exp_by_day, daily_total


@pytest.mark.parametrize("c", CASES, ids=lambda c: c["as_of"])
def test_second_calculation_agrees_with_expected(c):
    as_of = D(c["as_of"])
    bal, spent, revenue, exp_by_day, daily_total = simulate(as_of)
    assert sum(bal.values()) == c["balance"]["total"]["value"]
    assert bal["S3-cash"] == c["balance"]["cash"]["value"]
    assert dict(spent) == c["month"]["expenses"]["breakdown"]
    assert revenue["service"] + revenue["good"] == c["month"]["revenue"]["value"]
    window = c["runway_days"]["window_days"]
    burn = sum(exp_by_day[as_of - timedelta(days=i)] for i in range(window))
    assert burn == c["runway_days"]["burn"]
    assert [p["value"] for p in c["balance_trend"]] == [daily_total[D(p["date"])] for p in c["balance_trend"]]


def test_main_case_headline_numbers_are_the_ones_in_the_readme():
    c = case(MAIN_AS_OF)
    assert (c["balance"]["total"]["value"], c["balance"]["cash"]["value"]) == (55_298_223, 17_974_625)
    assert c["week_change"]["value"] == 6_031_722 and c["week_change_pct"]["value"] == 12.2
    assert c["runway_days"]["value"] == 17 and c["alternatives"]["runway_days_month_to_date"] == 15
    m = c["month"]
    assert (m["revenue"]["value"], m["expenses"]["value"], m["profit"]["value"]) == (33_391_346, 32_947_540, 443_806)
    assert m["profit_margin_pct"]["value"] == 1.3 and m["visits"]["value"] == 73
    assert EXPECTED["parameters"]["runway_window_days"] == 28
