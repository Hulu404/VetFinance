"""Internal consistency of set04 (runs without the engine): data.json is sane, expected.json is coherent, agrees with hand-typed
design totals and with a second, differently written calculation (Decimal / Fraction arithmetic, per-day loops)."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

import pytest

from set04_support import DATA, EMPTY_MONTH, EXPECTED, MAIN_MONTH, MONTHS, STOCK_AS_OF, contains_amount, rub_text

D = date.fromisoformat
PNL, NORM, DIRECTION, STOCK = EXPECTED["pnl"], EXPECTED["norm"], EXPECTED["direction"], EXPECTED["stock"]
CATS = {c["name"]: c for c in DATA["categories"]}
OPEN = EXPECTED["open_cases"][0]            # {"key": "2026-09@2026-09-15", "month": "2026-09", "as_of": "2026-09-15"}
OPEN_CASES = EXPECTED["open_cases"]         # the second one is 2026-09@2026-09-05: shorter than 7 days (short_period)
OPEN_KEYS = [c["key"] for c in OPEN_CASES]
OPEN_AS_OF = {c["key"]: D(c["as_of"]) for c in OPEN_CASES}
ROW_KEYS = ["revenue", "variable", "marginal_profit", "fixed", "taxes", "obligations", "net_profit"]

# Hand-typed design totals (kopecks), see README "Что задумано". They come from the generator's design tables, not from code.
HAND = {
    "2026-07": {"services": 59_924_035, "goods": 47_190_610,
                "variable_designed": 23_588_040 + 9_654_000 + 4_461_525 + 15_200_000,
                "fixed": 8_700_000 + 5_000_000 + 8_500_000 + 2_431_860 + 3_800_000 + 1_874_230,
                "fixed_payroll": 8_700_000 + 5_000_000,
                "tax": 5_245_000,
                "obligations": 723_333 + 1_200_000 + 1_120_000 + 630_000 + 390_833},
    "2026-08": {"services": 63_257_520, "goods": 51_541_185,
                "variable_designed": 39_216_095 + 10_120_000 + 4_798_000 + 15_900_000,
                "fixed": 9_000_000 + 5_250_000 + 8_500_000 + 2_510_475 + 4_100_000 + 2_103_000 + 213_050,  # + 213 050: "Без статьи"
                "fixed_payroll": 9_000_000 + 5_250_000,
                "tax": 5_532_000,
                "obligations": 700_856 + 1_200_000 + 1_120_000 + 630_000 + 390_833 + 236_111},
    "2026-09": {"services": 64_132_070, "goods": 45_683_540,
                "variable_designed": 24_500_000 + 8_000_000 + 5_200_000 + 17_000_000,
                "fixed": 9_300_000 + 5_500_000 + 8_500_000 + 2_641_040 + 2_310_000 + 1_200_015 + 1_840_000,  # + 1 840 000: "Без статьи"
                "fixed_payroll": 9_300_000 + 5_500_000,
                "tax": 5_200_000,
                "obligations": 678_116 + 1_200_000 + 1_120_000 + 630_000 + 390_833 + 236_111},
}
HAND_STOCK = {"frozen": [14_980_000, 5_807_000, 17_040_000], "stock_value": 55_354_600, "positions": 15,
              "expiring_60d": 9_292_850, "expired_on_hand": 55_500, "written_off_sep": 3_410_000}


# ---------------------------------------------------------------- data.json
def test_all_money_is_integer_kopecks_and_some_have_kopecks():
    amounts = [t["amount"] for t in DATA["transactions"]] + [s["amount"] for s in DATA["sales"]] \
        + [ln["amount"] for s in DATA["sales"] for ln in s["lines"]] + [c["amount"] for c in DATA["obligation_charges"]] \
        + [b["qty"] * b["unit_cost"] for b in DATA["stock"]["batches"]] + [w["amount"] for w in DATA["stock"]["writeoffs"]]
    assert all(type(x) is int for x in amounts)
    assert sum(1 for x in amounts if x % 100) > 100


def test_invoices_lines_payments_agree_and_drafts_exist():
    assert all(s["amount"] == sum(ln["amount"] for ln in s["lines"]) for s in DATA["sales"])
    assert {s["status"] for s in DATA["sales"]} == {"exec", "save"}
    exec_sales = {s["id"]: s for s in DATA["sales"] if s["status"] == "exec"}
    assert len(DATA["payments"]) == len(exec_sales)
    for p in DATA["payments"]:
        s = exec_sales[p["invoice_id"]]
        assert (p["amount"], p["date"], p["method"]) == (s["amount"], s["date"], s["pay"])


def test_transfers_net_zero_and_duplicates_have_an_original_and_check_operations_exist():
    groups = defaultdict(int)
    for t in DATA["transactions"]:
        if t["kind"] == "transfer":
            groups[t["transfer_group"]] += t["amount"]
    assert len(groups) == 6 and all(v == 0 for v in groups.values())
    dups = [t for t in DATA["transactions"] if t["status"] == "duplicate"]
    assert len(dups) == 2
    for d in dups:
        assert any(o["amount"] == d["amount"] and o["source"] == "bot" and o["status"] == "ok"
                   and abs((D(o["date"]) - D(d["date"])).days) <= 3 for o in DATA["transactions"])
    checks = [t for t in DATA["transactions"] if t["status"] == "check"]
    assert sorted((t["kind"], t["category"]) for t in checks) == [("in", None), ("out", None), ("out", None)]


def test_traps_exist_in_the_data():
    """Operations that must NOT enter the P&L lines."""
    cats = {t["category"] for t in DATA["transactions"] if t["kind"] == "out"}
    assert {"Покупка оборудования", "Вывод средств владельца", "Платежи по кредитам и лизингу"} <= cats
    assert {CATS[c]["type"] for c in ("Покупка оборудования", "Вывод средств владельца", "Платежи по кредитам и лизингу")} \
        == {"capex", "owner_draw", "obligation"}
    assert any("впрок" in t["description"] for t in DATA["transactions"])
    credits = [t for t in DATA["transactions"] if t["category"] == "Выручка эквайринг"]
    assert any(D(t["date"]).weekday() == 0 for t in credits)
    # the salary group spans both types: percent to doctors (variable) + salaries (fixed)
    assert {CATS[c]["type"] for c in CATS if CATS[c]["norm_key"] == "payroll"} == {"variable", "fixed"}
    assert CATS["Оклады персонала"]["payroll"] and CATS["Оклады персонала"]["norm_key"] is None


def test_no_account_goes_negative_on_any_day():
    bal = {a["id"]: a["opening_balance"] for a in DATA["accounts"]}
    by_day = defaultdict(list)
    for t in DATA["transactions"]:
        if t["status"] != "duplicate":
            by_day[t["date"]].append(t)
    day = D("2026-07-01")
    while day <= D("2026-09-30"):
        for t in by_day[day.isoformat()]:
            bal[t["account_id"]] += t["amount"]
        assert all(v >= 0 for v in bal.values()), (day, bal)
        day += timedelta(days=1)


def test_three_doctors_and_every_category_used_is_declared():
    assert len(DATA["doctors"]) == 3 and {s["doctor_id"] for s in DATA["sales"]} == {d["id"] for d in DATA["doctors"]}
    used = {t["category"] for t in DATA["transactions"] if t["category"]}
    assert used <= set(CATS)


# ---------------------------------------------------------------- hand-typed design totals vs expected.json
@pytest.mark.parametrize("month", MONTHS)
def test_expected_lines_equal_hand_typed_design_totals(month):
    h, p = HAND[month], PNL[month]
    assert p["revenue"] == h["services"] + h["goods"]
    assert p["rows"][0]["amount"]["breakdown"] == {"Услуги": h["services"], "Товары": h["goods"]}
    assert p["variable"] == h["variable_designed"] + p["commission"]
    assert p["fixed"] == h["fixed"]
    assert p["rows"][3]["amount"]["breakdown"]["ФОТ (оклады)"] == h["fixed_payroll"]
    assert p["tax"] == h["tax"]
    assert p["obligations"] == h["obligations"]
    assert p["net_profit"] == h["services"] + h["goods"] - p["variable"] - h["fixed"] - h["tax"] - h["obligations"]


def test_hand_typed_stock_totals():
    assert list(STOCK["frozen"]["breakdown"].values()) == HAND_STOCK["frozen"]
    assert STOCK["frozen"]["value"] == sum(HAND_STOCK["frozen"])
    assert STOCK["stock_value"] == {"value": HAND_STOCK["stock_value"], "positions": HAND_STOCK["positions"]}
    assert STOCK["expiring_60d"]["value"] == HAND_STOCK["expiring_60d"]
    assert STOCK["expired_on_hand"]["value"] == HAND_STOCK["expired_on_hand"]
    assert STOCK["written_off_month"]["value"] == HAND_STOCK["written_off_sep"]


# ---------------------------------------------------------------- expected.json is coherent
ALL_PNL = MONTHS + [EMPTY_MONTH] + OPEN_KEYS


def fig_rows(key):
    return {r["key"]: r for r in PNL[key]["rows"]}


@pytest.mark.parametrize("key", ALL_PNL)
def test_pnl_identity_and_breakdowns_add_up(key):
    p, rows = PNL[key], fig_rows(key)
    assert [r["key"] for r in p["rows"]] == ROW_KEYS
    v = {k: r["amount"]["value"] for k, r in rows.items()}
    assert v["revenue"] - v["variable"] - v["fixed"] - v["taxes"] - v["obligations"] == v["net_profit"]
    assert v["marginal_profit"] == v["revenue"] - v["variable"]
    for k, r in rows.items():
        assert sum(r["amount"]["breakdown"].values()) == r["amount"]["value"], k
        assert r["amount"]["source"], k
    children = {c["key"]: c for c in rows["fixed"]["children"]}
    assert list(children) == ["fixed_payroll", "fixed_other"]
    assert sum(c["amount"]["value"] for c in children.values()) == v["fixed"]
    assert rows["fixed"]["amount"]["breakdown"] == {c["label"]: c["amount"]["value"] for c in children.values()}
    for c in children.values():
        assert sum(c["amount"]["breakdown"].values()) == c["amount"]["value"]
    if p["revenue"]:
        assert rows["revenue"]["share_pct"]["value"] == 100.0
    else:
        assert all("share_pct" not in r for r in rows.values())


@pytest.mark.parametrize("month", MONTHS)
def test_pnl_shares_by_decimal_arithmetic(month):
    rev = PNL[month]["revenue"]
    everything = [r for r in PNL[month]["rows"]] + PNL[month]["rows"][3]["children"]
    for r in everything:
        exact = Decimal(r["amount"]["value"]) * 100 / Decimal(rev)
        assert Decimal(str(r["share_pct"]["value"])) == exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), r["key"]


def simulate_pnl(month, as_of=None):
    """Second calculation: one pass over operations keyed by (type), Decimal commission."""
    last = as_of or D("2099-01-01")
    inside = lambda day: day.startswith(month) and D(day) <= last  # noqa: E731
    rev = 0
    for s in DATA["sales"]:
        if s["status"] == "exec" and inside(s["date"]):
            rev += sum(ln["amount"] for ln in s["lines"])
    card = defaultdict(int)
    for p in DATA["payments"]:
        if p["method"] == "card" and inside(p["date"]):
            card[p["date"]] += p["amount"]
    rate = Decimal(DATA["clinic"]["acquiring_rate_bp"]) / Decimal(10_000)
    commission = sum(int((Decimal(v) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP)) for v in card.values())
    by_type = defaultdict(int)
    for t in DATA["transactions"]:
        if inside(t["date"]) and t["kind"] == "out" and t["status"] in ("ok", "check"):
            kind = CATS[t["category"]]["type"] if t["category"] and t["status"] == "ok" else "fixed"
            by_type[kind] += -t["amount"]
    obl = sum(c["amount"] for c in DATA["obligation_charges"] if c["month"] == month)
    return rev, commission, by_type, obl


@pytest.mark.parametrize("key", ALL_PNL)
def test_second_pnl_calculation_agrees(key):
    month, as_of = key[:7], OPEN_AS_OF.get(key)
    rev, commission, by_type, obl = simulate_pnl(month, as_of)
    p = PNL[key]
    assert p["revenue"] == rev
    assert p["commission"] == commission
    assert p["variable"] == by_type["variable"] + commission
    assert p["fixed"] == by_type["fixed"]
    assert p["tax"] == by_type["tax"]
    assert p["obligations"] == obl
    assert p["net_profit"] == rev - by_type["variable"] - commission - by_type["fixed"] - by_type["tax"] - obl


def test_unclassified_counts_and_commission_per_day_differs_from_per_month_rounding_somewhere():
    assert [PNL[m]["unclassified"] for m in MONTHS] == [{"count": 0, "amount": 0}, {"count": 1, "amount": 213_050},
                                                         {"count": 1, "amount": 1_840_000}]
    differs = 0
    for m in MONTHS:
        card = defaultdict(int)
        for p in DATA["payments"]:
            if p["method"] == "card" and p["date"].startswith(m):
                card[p["date"]] += p["amount"]
        per_month = int((Decimal(sum(card.values())) * Decimal(190) / Decimal(10_000)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        differs += per_month != PNL[m]["commission"]
    assert differs >= 1, "the set should catch an engine that rounds the commission once per month instead of per day"


def test_period_status_and_partial_reasons_of_the_expected_cases():
    for m in MONTHS:
        assert PNL[m]["period"] == {"month": m, "status": "closed", "to": None, "first_month": "2026-07"}
        assert PNL[m]["status"] == "ok" and PNL[m]["partial_reasons"] == []
    assert PNL[EMPTY_MONTH]["status"] == "empty" and NORM[EMPTY_MONTH]["status"] == "empty"
    assert PNL[OPEN["key"]]["period"] == {"month": "2026-09", "status": "open", "to": OPEN["as_of"], "first_month": "2026-07"}
    assert PNL[OPEN["key"]]["status"] == "ok" and PNL[OPEN["key"]]["partial_reasons"] == []
    short = OPEN_CASES[1]
    assert short["as_of"] == "2026-09-05"
    assert PNL[short["key"]]["period"] == {"month": "2026-09", "status": "open", "to": "2026-09-05", "first_month": "2026-07"}
    assert PNL[short["key"]]["status"] == "partial" and PNL[short["key"]]["partial_reasons"] == ["short_period"], "5 days < 7"
    assert NORM[short["key"]]["partial_reasons"] == ["short_period"]


def test_open_month_cuts_cash_operations_at_as_of_but_accrues_obligations_for_the_whole_month():
    full, part = PNL[MAIN_MONTH], PNL[OPEN["key"]]
    assert part["revenue"] < full["revenue"] and part["fixed"] < full["fixed"]
    assert part["obligations"] == full["obligations"], "charges are accrued per calendar month"
    assert part["tax"] == 0 and full["tax"] > 0, "the tax payment of the 18th is not paid yet on the 15th (cash rule)"


@pytest.mark.parametrize("key", MONTHS + OPEN_KEYS)
def test_directions_bridge(key):
    v = DIRECTION[key]
    s, g = v["directions"]
    assert (s["direction"], g["direction"]) == ("services", "goods")
    assert s["revenue"]["value"] + g["revenue"]["value"] == v["revenue"] == PNL[key]["revenue"]
    assert s["direct_costs"] + g["direct_costs"] + v["common_variable"]["value"] == v["variable"] == PNL[key]["variable"]
    assert s["margin"] + g["margin"] - v["common_variable"]["value"] == v["marginal"] == PNL[key]["marginal"]
    assert sum(v["common_variable"]["breakdown"].values()) == v["common_variable"]["value"]
    for it in (s, g):
        assert it["revenue"]["value"] - it["direct_costs"] == it["margin"] and sum(it["direct_costs_breakdown"].values()) == it["direct_costs"]
    assert round(s["revenue_share_pct"] + g["revenue_share_pct"], 1) == 100.0


@pytest.mark.parametrize("key", MONTHS + OPEN_KEYS)
def test_norm_by_fraction_arithmetic(key):
    p = PNL[key]
    rev = p["revenue"]
    items = NORM[key]["items"]
    assert [i["key"] for i in items] == ["payroll", "drugs", "rent", "lab", "writeoff", "acquiring", "marketing", "other", "net_profit"]
    assert sum(i["amount"] for i in items if not i["memo"]) == rev, "groups + other + net profit = revenue"
    assert [i["key"] for i in items if i["memo"]] == ["writeoff"]
    tones = {("ok", False): "good", ("above", False): "bad", ("below", False): "warn", ("ok", True): "good",
             ("above", True): "good", ("below", True): "bad"}
    for i in items:
        assert sum(i["amount_breakdown"].values()) == i["amount"], i["key"]
        exact = Decimal(i["amount"]) * 100 / Decimal(rev)
        assert Decimal(str(i["actual_pct"])) == exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), i["key"]
        if i["status"] == "no_norm":
            assert i["key"] == "other" and i["tone"] == "neutral" and i["norm"] is None and "deviation_rub" not in i
            continue
        lo, hi = Fraction(str(i["norm"]["min_pct"])), Fraction(str(i["norm"]["max_pct"]))
        share = Fraction(i["amount"], rev) * 100
        status = "above" if share > hi else "below" if share < lo else "ok"
        assert i["status"] == status, i["key"]
        assert i["tone"] == tones[(status, i["kind"] == "profit")], i["key"]
        if status == "ok":
            assert i["deviation_rub"] == 0 and i["deviation_pp"] == 0
            continue
        bound = hi if status == "above" else lo
        assert (i["deviation_rub"] > 0) == (status == "above")
        exact_rub = Fraction(i["amount"]) - Fraction(rev) * bound / 100
        assert abs(Fraction(i["deviation_rub"]) - exact_rub) <= Fraction(1, 2), i["key"]       # rounded to a kopeck
        exact_pp = share - bound
        shown = Decimal(exact_pp.numerator) / Decimal(exact_pp.denominator)
        assert Decimal(str(i["deviation_pp"])) == shown.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), i["key"]
        # the rule of the screen: shown share minus shown bound = shown deviation within 0.1 pp
        shown_bound = Decimal(bound.numerator) / Decimal(bound.denominator)
        assert abs(Decimal(str(i["actual_pct"])) - shown_bound - Decimal(str(i["deviation_pp"]))) <= Decimal("0.1")
    by = {i["key"]: i for i in items}
    assert by["net_profit"]["amount"] == p["net_profit"] and by["acquiring"]["amount"] == p["commission"]
    assert by["marketing"]["norm"] == {"min_pct": 2.0, "max_pct": 6.0, "source": "clinic"}
    assert all(i["norm"]["source"] == "industry" for i in items if i["norm"] and i["key"] != "marketing")


def test_norm_statuses_cover_every_value_and_boundaries_are_exercised():
    statuses = {i["status"] for m in MONTHS for i in NORM[m]["items"]}
    assert statuses == {"ok", "above", "below", "no_norm"}
    by = lambda m: {i["key"]: i for i in NORM[m]["items"]}  # noqa: E731
    assert by("2026-07")["net_profit"]["status"] == "ok" and by("2026-07")["net_profit"]["actual_pct"] == 12.3  # just above 12.0
    assert by("2026-09")["net_profit"]["status"] == "below" and by("2026-09")["net_profit"]["actual_pct"] == 11.7  # just below
    assert by("2026-09")["net_profit"]["tone"] == "bad" and by("2026-08")["payroll"]["status"] == "below" and by("2026-08")["payroll"]["tone"] == "warn"
    assert by("2026-08")["writeoff"]["actual_pct"] == 0.8 and by("2026-08")["writeoff"]["status"] == "ok"  # shown 0.8, exact 0.775
    assert by("2026-09")["marketing"]["actual_pct"] == 2.1       # "ok" only thanks to the clinic's own norm 2-6% (industry 3-7%)
    assert by("2026-09")["payroll"]["amount"] == 17_000_000 + 9_300_000, "salary group = percent to doctors (variable) + salaries (fixed)"


def test_norm_headline_numbers():
    h = NORM[MAIN_MONTH]["headline_numbers"]
    assert set(h["above"]) == {"Аренда и коммуналка", "Списание по сроку"} and h["above_total"] == sum(h["above"].values())
    assert PNL[MAIN_MONTH]["headline_numbers"]["share_pct"] == 11.7


def test_norm_of_empty_month_is_empty():
    assert NORM[EMPTY_MONTH]["items"] == []


# ---------------------------------------------------------------- stock: second calculation (per item loops)
def test_second_stock_calculation_agrees():
    as_of = D(STOCK_AS_OF)
    items = {i["id"]: i for i in DATA["stock"]["items"]}
    qty, value = defaultdict(int), defaultdict(int)
    expiring = expired = 0
    for b in DATA["stock"]["batches"]:
        qty[b["item_id"]] += b["qty"]
        value[b["item_id"]] += b["qty"] * b["unit_cost"]
        if b["expires_on"]:
            left = (D(b["expires_on"]) - as_of).days
            expiring += b["qty"] * b["unit_cost"] if 0 <= left <= 60 else 0
            expired += b["qty"] * b["unit_cost"] if left < 0 else 0
    buckets = [0, 0, 0]
    for iid, it in items.items():
        if qty[iid] <= 0:
            continue
        idle = (as_of - D(it["last_movement"])).days
        for n, lo in enumerate((60, 90, 180)):
            hi = (90, 180, 10**9)[n]
            if lo <= idle < hi:
                buckets[n] += value[iid]
    assert buckets == list(STOCK["frozen"]["breakdown"].values())
    assert sum(value.values()) == STOCK["stock_value"]["value"] and sum(1 for v in qty.values() if v > 0) == STOCK["stock_value"]["positions"]
    assert expiring == STOCK["expiring_60d"]["value"] and expired == STOCK["expired_on_hand"]["value"]
    window = [c["amount"] for c in DATA["stock"]["consumption"] if as_of - timedelta(days=89) <= D(c["date"]) <= as_of]
    assert len(window) == 90
    assert STOCK["turnover_days"]["breakdown_values"] == [sum(value.values()), sum(window), 90]
    exact = Fraction(sum(value.values()) * 90, sum(window))
    assert STOCK["turnover_days"]["value"] == int(exact + Fraction(1, 2))  # half up (positive numbers)


def test_stock_boundaries_are_in_the_data():
    as_of = D(STOCK_AS_OF)
    idle = {i["name"]: (as_of - D(i["last_movement"])).days for i in DATA["stock"]["items"]}
    assert {60, 59, 90, 89, 180} <= set(idle.values())
    lefts = sorted((D(b["expires_on"]) - as_of).days for b in DATA["stock"]["batches"] if b["expires_on"])
    assert {-5, 0, 1, 60, 61, 62} <= set(lefts)
    assert any(i["id"] == "g15" for i in DATA["stock"]["items"]) and not any(b["item_id"] == "g15" for b in DATA["stock"]["batches"])
    rows = STOCK["expiring_60d"]["rows"]
    assert [r["days_left"] for r in rows] == sorted(r["days_left"] for r in rows) and rows[0]["days_left"] == 0 and rows[-1]["days_left"] == 60
    assert {i["item"] for i in STOCK["frozen_items"]} & {r["item"] for r in rows}, "one item is both frozen and expiring"


def test_stock_frozen_items_sum_to_buckets_and_are_sorted():
    items = STOCK["frozen_items"]
    assert sum(i["amount"] for i in items) == STOCK["frozen"]["value"]
    assert [i["amount"] for i in items] == sorted((i["amount"] for i in items), reverse=True)
    assert "Активированный уголь" not in {i["item"] for i in items}


def test_alternatives_show_why_dashboard_and_pnl_profit_differ():
    alt = EXPECTED["alternatives"]
    assert all(alt["dashboard_profit"][m] != alt["pnl_net_profit"][m] for m in MONTHS)
    assert alt["aug_net_profit_without_prepaid_purchase"] == PNL["2026-08"]["net_profit"] + alt["aug_prepaid_purchase"]
    assert all(alt["pnl_net_profit_with_expired_writeoffs"][m] < alt["pnl_net_profit"][m] for m in MONTHS)


def test_amount_text_matcher_used_by_export_checks():
    assert contains_amount("Выручка 1 071 146,45 ₽", 107_114_645) and not contains_amount("11 071 146,45", 107_114_645)
    assert contains_amount("итого 12 000 ₽", 1_200_000) and contains_amount("12 000,00", 1_200_000)
    assert not contains_amount("12 000,50", 1_200_000) and rub_text(1_200_000) == "12 000"
    assert MAIN_MONTH in MONTHS


# ---------------------------------------------------------------- running month: norm is not rated
@pytest.mark.parametrize("case", OPEN_CASES, ids=OPEN_KEYS)
def test_running_month_norm_is_marked_unrated_and_has_the_owner_headline(case):
    n = NORM[case["key"]]
    assert n["rated"] is False and all(NORM[m]["rated"] is True for m in MONTHS)
    days = int(case["as_of"][-2:])
    word = "дней"  # 15 and 5
    assert n["headline_open"] == f"К {days} сентября доли статей посчитаны от выручки за {days} {word}. Сравним с нормой, когда месяц закончится."
    assert "выше нормы" not in n["headline_open"] and "ниже нормы" not in n["headline_open"]
    rev = PNL[case["key"]]["revenue"]
    assert sum(i["amount"] for i in n["items"] if not i["memo"]) == rev, "the shares of a running month still add up"


def test_running_month_writeoff_counts_only_days_up_to_as_of():
    wo = {i["key"]: i for i in NORM[OPEN["key"]]["items"]}["writeoff"]
    hand = sum(w["amount"] for w in DATA["stock"]["writeoffs"]
               if w["reason"] == "expired" and "2026-09-01" <= w["date"] <= OPEN["as_of"])
    assert wo["amount"] == hand and hand < {i["key"]: i for i in NORM[MAIN_MONTH]["items"]}["writeoff"]["amount"]


# ---------------------------------------------------------------- stock: idle intervals, positions, write-off list and norm
HAND_IDLE = {"positions": [2, 2, 2], "amounts": [14_980_000, 5_807_000, 17_040_000]}
HAND_WRITEOFFS_SEP = [1_368_950, 805_050, 705_000, 420_000, 111_000]    # by amount, descending (typed from data.json by hand)


def test_hand_typed_idle_buckets_and_positions():
    assert [b["key"] for b in STOCK["idle_buckets"]] == ["60_89", "90_179", "180_plus"]
    assert [b["positions"] for b in STOCK["idle_buckets"]] == HAND_IDLE["positions"]
    assert [b["amount"] for b in STOCK["idle_buckets"]] == HAND_IDLE["amounts"] == list(STOCK["frozen"]["breakdown"].values())
    assert STOCK["frozen_positions"] == {"value": 6, "breakdown_values": HAND_IDLE["positions"]}
    assert len(STOCK["frozen_items"]) == STOCK["frozen_positions"]["value"]


def test_idle_buckets_by_a_second_calculation_per_item():
    as_of = D(STOCK_AS_OF)
    value, qty = defaultdict(int), defaultdict(int)
    for b in DATA["stock"]["batches"]:
        value[b["item_id"]] += b["qty"] * b["unit_cost"]
        qty[b["item_id"]] += b["qty"]
    counts, sums = [0, 0, 0], [0, 0, 0]
    for it in DATA["stock"]["items"]:
        idle = (as_of - D(it["last_movement"])).days
        n = 2 if idle >= 180 else 1 if idle >= 90 else 0 if idle >= 60 else None
        if n is not None and qty[it["id"]] > 0:
            counts[n] += 1
            sums[n] += value[it["id"]]
    assert counts == [b["positions"] for b in STOCK["idle_buckets"]]
    assert sums == [b["amount"] for b in STOCK["idle_buckets"]]


def test_written_off_items_are_the_month_list_sorted_by_amount():
    items = STOCK["written_off_items"]
    assert [i["amount"] for i in items] == HAND_WRITEOFFS_SEP
    assert sum(i["amount"] for i in items) == STOCK["written_off_month"]["value"] == HAND_STOCK["written_off_sep"]
    assert all(i["date"].startswith("2026-09") for i in items) and {i["reason"] for i in items} == {"expired", "damaged"}
    by_reason = {"expired": 0, "damaged": 0}
    for i in items:
        by_reason[i["reason"]] += i["amount"]
    assert list(STOCK["written_off_month"]["breakdown"].values()) == [by_reason["expired"], by_reason["damaged"]]


def test_written_off_norm_by_hand_and_by_fraction():
    n = STOCK["written_off_norm"]
    revenue = PNL[MAIN_MONTH]["revenue"]
    assert (n["month"], n["revenue"], n["norm_pct"]) == ("2026-09", revenue, 0.8)
    assert n["value"] == 878_525, "109 815 610 kop x 0,8% = 878 524,88 -> 878 525"
    assert n["value"] == int(Fraction(revenue * 8, 1000) + Fraction(1, 2))
    assert n["expired"] == 2_990_000 and n["over_norm"] == 2_111_475 == 2_990_000 - 878_525
    norm_row = {i["key"]: i for i in NORM[MAIN_MONTH]["items"]}["writeoff"]
    assert norm_row["amount"] == n["expired"] and norm_row["deviation_rub"] == n["over_norm"], "Stock and Norm tell one story"
    assert norm_row["amount"] < STOCK["written_off_month"]["value"], "written_off_month also has `damaged`; the Norm row counts only `expired`"


def test_idle_pages_walk_the_whole_list_once_in_the_right_order():
    frozen = STOCK["frozen_items"]
    to_key = {"60-89": "60_89", "90-179": "90_179", "180+": "180_plus"}
    for case in STOCK["idle_pages"]:
        flat = [i for pg in case["pages"] for i in pg["items"]]
        want = [i for i in frozen if case["bucket"] == "all" or to_key[i["bucket"]] == case["bucket"]]
        assert len(flat) == case["total"] == len(want), case["bucket"]
        assert [i["item"] for i in flat] == [i["item"] for i in want], "sorted by amount descending, ties by name"
        assert [i["amount"] for i in flat] == sorted((i["amount"] for i in flat), reverse=True)
        assert all(len(pg["items"]) <= case["limit"] for pg in case["pages"])
        assert [pg["has_next"] for pg in case["pages"]] == [True] * (len(case["pages"]) - 1) + [False]
        assert all(i["bucket"] in ("60_89", "90_179", "180_plus") and i["idle_days"] >= 60 for i in flat)
    keys = {(c["bucket"], c["limit"]) for c in STOCK["idle_pages"]}
    assert {("all", 10), ("all", 2), ("60_89", 10), ("90_179", 10), ("180_plus", 10)} <= keys
    assert any(len(c["pages"]) >= 3 for c in STOCK["idle_pages"]), "at least one case walks the cursor through 3 pages"
