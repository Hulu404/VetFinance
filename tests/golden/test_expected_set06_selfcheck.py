"""Internal consistency of set06 (runs without the engine): data.json is sane, expected.json is coherent, agrees with hand-typed
values (README, «Что задумано» and «Ключевые числа») and with a second, differently written calculation (Decimal, integer
remainders, per-day loops)."""
from collections import Counter
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest

from set06_support import AS_OF, CASE_KEYS, DATA, EXPECTED, MONTH, PART_KEYS, SERVICE_CASES, by_id

D = date.fromisoformat
CASES = EXPECTED["cases"]
MAIN = CASES["main"]
PNL = DATA["pnl_month"]
WINDOW = (AS_OF - timedelta(days=90), AS_OF - timedelta(days=1))

# Hand-typed (kopecks), from the design tables of the generator and arithmetic done on paper, see README.
HAND_FIXED = 13_700_000 + 8_500_000 + 2_600_000 + 3_700_000                 # without «Расходные материалы» 9 100 000
HAND_OBLIGATIONS = 1_520_000 + 1_200_000 + 620_000
HAND_POOL = HAND_FIXED + HAND_OBLIGATIONS
HAND_HOURS = {"R1": (22 * 480 + 4 * 240) // 60, "R2": 138, "R3": 30 * 720 // 60}     # R2: 22 x 375 min = 137,5 h -> 138
HAND_DOCTOR_HOURS = {"D1": 154, "D2": 161, "D3": 103}                                # 36, 37,5 and 24 h a week x 30 / 7, rounded
HAND_UNITS_SEP = {"S1": 80, "S2": 50, "S3": 30, "S4": 18, "S5": 6, "S6": 12, "S7": 16, "S10": 25, "S11": 10}
HAND_S4 = {"doctor_pay": 450_000 * 30 // 100, "anesthesia": 45_001 + 25_300 * 3 // 10,    # 0,5 x 900,01 -> 450,005 -> 450,01
           "drugs": 4 * (480_000 + 255_000) // 150 + 2 * 1_950,
           "supplies": 2 * 21_500 + 3 * 7_800 + 2 * (60 * 2_800 + 40 * 3_100) // 100 + 4 * 150,
           "fixed": 46_145}                                                          # 31 840 000 / 690 h = 461,449 rub -> 461,45 x 60 / 60
HAND_S6 = {"doctor_pay": 240_000 * 20 // 100, "drugs": 2 * (24 * 7_450 + 6 * 7_900) // 30, "supplies": 5_900 + 3 * 11_000,
           "fixed": 46_145 * 180 // 60}
HAND_S1_SUPPLIES = (60 * 2_800 + 40 * 3_100) // 100 + 3 * 150 + 450                  # gloves average 29,20 + 3 wipes + syringe


def half_up(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def pct1(part, whole) -> float:
    return float((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def service_lines(statuses=("exec",), window=WINDOW):
    return [{**l, "date": s["date"]} for s in DATA["sales"] if s["status"] in statuses and window[0] <= D(s["date"]) <= window[1]
            for l in s["lines"] if l["kind"] == "service"]


# ---------------------------------------------------------------- data.json
def test_money_is_integer_kopecks_and_quantities_are_strings():
    assert all(type(s["amount"]) is int and all(type(l["amount"]) is int and type(l["price"]) is int for l in s["lines"])
               for s in DATA["sales"])
    assert all(type(b["qty"]) is str and type(b["unit_cost"]) is int for b in DATA["stock_batches"])
    assert all(type(t["qty"]) is str for tc in DATA["techcards"] for t in tc["lines"])
    assert all(type(x["amount"]) is int for x in PNL["fixed_lines"] + PNL["obligation_lines"])
    assert all(type(d["hours_per_week"]) is str for d in DATA["doctors"])


def test_sales_and_pnl_totals_agree():
    for s in DATA["sales"]:
        assert s["amount"] == sum(l["amount"] for l in s["lines"])
        assert all(l["amount"] <= l["qty"] * l["price"] for l in s["lines"])
    revenue = sum(s["amount"] for s in DATA["sales"] if s["status"] == "exec" and s["date"].startswith(MONTH))
    assert PNL["revenue"] == revenue and PNL["marginal_profit"] == revenue - PNL["variable_total"]
    assert {s["status"] for s in DATA["sales"]} == {"exec", "save"} and min(s["date"] for s in DATA["sales"]) < WINDOW[0].isoformat()
    assert max(s["date"] for s in DATA["sales"]) == "2026-09-30" and AS_OF == date(2026, 10, 1)


def test_designed_units_drafts_and_discounts():
    sep = Counter()
    for l in service_lines(window=(D("2026-09-01"), D("2026-09-30"))):
        sep[l["service_id"]] += l["qty"]
    assert dict(sep) == HAND_UNITS_SEP
    drafts = Counter(l["service_id"] for s in DATA["sales"] if s["status"] == "save" for l in s["lines"])
    assert drafts == {"S1": 3, "S3": 3, "S4": 2}
    discounted = [l for l in service_lines() if l["amount"] < l["qty"] * l["price"]]
    assert len(discounted) == 6 and {l["service_id"] for l in discounted} == {"S3"} and all(l["amount"] == 189_000 for l in discounted)


def test_boundary_sales_outside_the_window_exist():
    outside = [l for l in service_lines(window=(D("2026-01-01"), WINDOW[0] - timedelta(days=1)))]
    assert {(l["date"], l["service_id"]) for l in outside} == {("2026-06-20", "S8"), ("2026-07-02", "S8"), ("2026-06-25", "S12")}
    assert WINDOW[0].isoformat() == "2026-07-03"


def test_edge_cases_are_present():
    ids_sold = {l["service_id"] for l in service_lines()}
    settings = {s["service_id"] for s in DATA["service_settings"]}
    techcards = {t["service_id"]: t["lines"] for t in DATA["techcards"]}
    assert "S10" in ids_sold - settings and "S7" in ids_sold - set(techcards) and techcards["S11"] == []
    assert "S9" in (settings & set(techcards)) - ids_sold and "S12" not in ids_sold
    assert "S8" in ids_sold and not any(l["service_id"] == "S8" for l in service_lines(window=(D("2026-09-01"), D("2026-09-30"))))
    assert any(b["item_id"] == "i05" and b["expires_on"] < DATA["as_of"] for b in DATA["stock_batches"])      # expired batch
    assert any(b["expires_on"] == DATA["as_of"] for b in DATA["stock_batches"])                                 # expires on as_of
    assert not any(b["item_id"] == "i16" for b in DATA["stock_batches"]) and "i16" in {i["id"] for i in DATA["stock_items"]}
    assert all(Decimal(b["qty"]) == 0 for b in DATA["stock_batches"] if b["item_id"] == "i14")                  # exhausted item
    assert sum(1 for v in DATA["visits"] if v["doctor_id"] is None and v["date"].startswith(MONTH)) == 5


def test_hand_typed_pool_and_hours():
    assert PNL["fixed_lines"][-1]["kind"] == "materials" and HAND_POOL == 31_840_000
    assert sum(f["amount"] for f in PNL["fixed_lines"] if f["kind"] != "materials") == HAND_FIXED
    eff = MAIN["efficiency"]
    assert eff["pool"] == {"fixed": HAND_FIXED, "obligations": HAND_OBLIGATIONS, "total": HAND_POOL}
    assert {r["id"]: r["available_hours"] for r in eff["rooms"]} == HAND_HOURS
    assert eff["available_hours"] == sum(HAND_HOURS.values()) == 690 and eff["hour_cost"] == 46_145
    assert CASES["ward_no_schedule"]["efficiency"]["available_hours"] == sum(HAND_DOCTOR_HOURS.values()) == 418
    assert CASES["ward_no_schedule"]["hour_cost"] == 76_172 and CASES["doctor_no_hours"]["hour_cost"] == 101_079
    assert {x["id"]: x["available_hours"] for x in CASES["ward_no_schedule"]["efficiency"]["doctors"]} == HAND_DOCTOR_HOURS


# ---------------------------------------------------------------- expected.json against hand values
def test_s4_equals_the_hand_calculation():
    s = by_id(MAIN["services"])["S4"]
    p = s["parts"]
    assert (p["doctor_pay"], p["anesthesia"], p["drugs"], p["supplies"], p["fixed"]) == \
        (HAND_S4["doctor_pay"], HAND_S4["anesthesia"], HAND_S4["drugs"], HAND_S4["supplies"], HAND_S4["fixed"]) == \
        (135_000, 52_591, 23_500, 72_840, 46_145)
    assert s["price"] == 450_000 and s["visits_month"] == 18
    assert HAND_S4["anesthesia"] == 45_001 + 7_590       # 0,5 ml x 900,01 rub = 450,005 rub: half up (banker's rounding gives 450,00)
    assert p["acquiring"] == 8_494 and p["taxes"] == 18_776      # 450 000 x 950 000 / 50 330 000 = 8 493,9; x 2 100 000 / ... = 18 776,1
    assert s["net_profit"] == 450_000 - sum(p.values()) == 92_654 and s["monthly_profit"] == 92_654 * 18


def test_s6_is_the_loss_making_service_by_hand():
    s = by_id(MAIN["services"])["S6"]
    p = s["parts"]
    assert (p["doctor_pay"], p["drugs"], p["supplies"], p["fixed"]) == \
        (HAND_S6["doctor_pay"], HAND_S6["drugs"], HAND_S6["supplies"], HAND_S6["fixed"]) == (48_000, 15_080, 38_900, 138_435)
    assert s["net_profit"] == 240_000 - (48_000 + 4_530 + 10_014 + 15_080 + 0 + 38_900 + 138_435) == -14_959
    assert MAIN["services"][0]["id"] == "S6" and MAIN["counts"]["loss"] == 1
    assert by_id(CASES["ward_no_schedule"]["services"])["S6"]["net_profit"] == -105_040      # the fallback makes the loss deeper


def test_s1_and_the_clinic_average_doctor_percent_by_hand():
    s = by_id(MAIN["services"])["S1"]
    assert s["parts"]["supplies"] == HAND_S1_SUPPLIES == 3_820 and s["parts"]["doctor_pay"] == 54_000
    assert s["parts"]["fixed"] == 23_073                 # 461,45 rub x 30 / 60 = 230,725 -> 230,73
    s7 = by_id(MAIN["services"])["S7"]
    service_revenue = sum(l["amount"] for l in service_lines(window=(D("2026-09-01"), D("2026-09-30"))))
    assert service_revenue == 47_014_000
    assert s7["parts"]["doctor_pay"] == half_up(Decimal(60_000) * PNL["doctor_percent_payouts"] / service_revenue) == 16_208


def test_price_average_over_90_days_with_a_price_change_and_discounts():
    s2 = [l for l in service_lines() if l["service_id"] == "S2"]
    cheap = sum(l["qty"] for l in s2 if l["price"] == 120_000)
    dear = sum(l["qty"] for l in s2 if l["price"] == 130_000)
    assert cheap + dear == 40 + 45 + 50 and dear > 0
    assert by_id(MAIN["services"])["S2"]["price"] == half_up(Decimal(cheap * 120_000 + dear * 130_000) / (cheap + dear)) == 122_741
    s3 = by_id(MAIN["services"])["S3"]
    assert s3["price"] == half_up(Decimal(83 * 210_000 - 6 * 21_000) / 83) == 208_482      # 25 + 28 + 30 invoices, 6 with 10% off


def test_efficiency_headline_by_hand():
    e = MAIN["efficiency"]
    assert e["revenue"] == 50_330_000 and e["visits"] == 254 and e["avg_check"] == half_up(Decimal(50_330_000) / 254)
    assert e["marginal_profit"] == 50_330_000 - 25_400_000 == 24_930_000
    assert e["hour_margin"] == half_up(Decimal(24_930_000) / e["busy_hours"])
    assert e["hour_cost_lines"] == {"fixed": 41_304, "obligations": 4_841} and sum(e["hour_cost_lines"].values()) == e["hour_cost"]
    assert e["load_pct"] == pct1(e["busy_hours"], 690)


# ---------------------------------------------------------------- coherence
@pytest.mark.parametrize("case", SERVICE_CASES)
def test_parts_and_profit_add_up_to_the_price_and_shares_to_exactly_100(case):
    for s in CASES[case]["services"]:
        if s["status"] == "no_recipe":
            assert s["net_profit"] is None and s["shares"] is None and s["monthly_profit"] is None
            assert all(s["parts"][k] is None for k in ("drugs", "anesthesia", "supplies"))
            continue
        known = [a for a in s["parts"].values() if a is not None]
        assert sum(known) == s["cost_total"] and s["cost_total"] + s["net_profit"] == s["price"]
        assert round((sum(s["shares"].values()) + s["net_margin_pct"]) * 10) == 1000
        assert s["monthly_profit"] == s["net_profit"] * s["visits_month"]
        assert set(s["parts"]) == set(PART_KEYS)


@pytest.mark.parametrize("case", SERVICE_CASES)
def test_order_counts_and_statuses(case):
    sv = CASES[case]["services"]
    rated = [s for s in sv if s["net_profit"] is not None]
    assert sv[:len(rated)] == rated and all(s["status"] == "no_recipe" for s in sv[len(rated):])
    keys = [(s["net_profit"] / s["price"], s["name"]) for s in rated]
    assert keys == sorted(keys)
    nulls = [s["name"] for s in sv[len(rated):]]
    assert nulls == sorted(nulls)
    assert CASES[case]["counts"] == {"all": len(sv), "loss": sum(1 for s in rated if s["net_profit"] < 0),
                                     "no_recipe": len(sv) - len(rated)}
    for s in sv:
        order = ["recipe", "hour_cost", "item_no_cost"]
        assert s["missing"] == sorted(s["missing"], key=order.index)
        assert s["status"] == ("no_recipe" if "recipe" in s["missing"] else "partial" if s["missing"] else "ok")


def test_modes_per_case():
    assert [CASES[k]["mode"] for k in CASE_KEYS] == ["rooms", "doctors", "doctors", "doctors", "rooms"]
    assert [CASES[k]["efficiency"]["status"] for k in CASE_KEYS] == ["ok", "ok", "ok", "partial", "partial"]
    no_hours = CASES["no_hours"]
    assert no_hours["hour_cost"] is None and no_hours["efficiency"]["partial_reasons"] == ["no_doctor_hours"]
    assert all(s["parts"]["fixed"] is None for s in no_hours["services"])
    assert all("hour_cost" in s["missing"] for s in no_hours["services"])
    assert all(r == [] for r in (CASES[k]["efficiency"]["rooms"] for k in CASE_KEYS[1:4]))


def test_month_without_a_statement_has_the_load_but_no_hour_cost():
    e = CASES["no_expenses"]["efficiency"]
    assert CASES["no_expenses"].get("efficiency_only") and "services" not in CASES["no_expenses"]
    assert (e["partial_reasons"], e["hour_cost"], e["hour_margin"], e["hour_cost_lines"]) == (["no_expenses"], None, None, None)
    assert e["pool"]["total"] == 0 and e["load_pct"] == MAIN["efficiency"]["load_pct"] == 21.2 and len(e["rooms"]) == 3


def test_the_unrounded_and_the_rounded_hour_cost_differ_by_a_kopeck():
    alt = EXPECTED["alternatives"]
    assert alt["fixed_s1_from_unrounded_hour_cost"] == 23_072 and alt["fixed_s1_from_rounded_hour_cost"] == 23_073
    assert alt["materials_s4_last_batch_price"] != alt["materials_s4_average"]


# ---------------------------------------------------------------- a second calculation (Decimal, integer remainders)
def largest_remainder(amounts: list, price: int) -> list:
    """Tenths of a percent; the sum is exactly 1000: floor division + the leftover to the biggest remainders (earlier part wins ties)."""
    base = [a * 1000 // price for a in amounts]
    rest = [a * 1000 % price for a in amounts]
    for i in sorted(range(len(amounts)), key=lambda i: (-rest[i], i))[:1000 - sum(base)]:
        base[i] += 1
    return base


def second_calculation(case_key):
    hour_cost = CASES[case_key]["hour_cost"]
    lines = service_lines()
    service_revenue = sum(l["amount"] for l in lines if l["date"].startswith(MONTH))
    out = {}
    sold = {" ".join(l["name"].split()).casefold().replace("ё", "е") for l in lines}
    manual_ids = {m["id"] for m in DATA["manual_services"] if " ".join(m["name"].split()).casefold().replace("ё", "е") not in sold}
    for sid in {l["service_id"] for l in lines} | manual_ids:
        mine = [l for l in lines if l["service_id"] == sid]
        st = next((x for x in DATA["service_settings"] if x["service_id"] == sid), None)
        tc = next((t for t in DATA["techcards"] if t["service_id"] == sid), None)
        price = half_up(Decimal(sum(l["amount"] for l in mine)) / sum(l["qty"] for l in mine)) if mine else             next(m["price"] for m in DATA["manual_services"] if m["id"] == sid)
        parts = {k: 0 for k in PART_KEYS}
        parts["doctor_pay"] = half_up(Decimal(price) * st["doctor_pct_bp"] / 10_000) if st and st["doctor_pct_bp"] is not None \
            else half_up(Decimal(price) * PNL["doctor_percent_payouts"] / service_revenue)
        parts["acquiring"] = half_up(Decimal(price) * PNL["acquiring_fee"] / PNL["revenue"])
        parts["taxes"] = half_up(Decimal(price) * PNL["taxes"] / PNL["revenue"])
        no_cost = False
        for line in (tc["lines"] if tc else []):
            batches = [b for b in DATA["stock_batches"] if b["item_id"] == line["item_id"]]
            live = [b for b in batches if Decimal(b["qty"]) > 0 and b["expires_on"] >= DATA["as_of"]]
            if live:
                unit = sum(Decimal(b["qty"]) * b["unit_cost"] for b in live) / sum(Decimal(b["qty"]) for b in live)
            elif batches:
                unit = Decimal(sorted(batches, key=lambda b: b["received_on"])[-1]["unit_cost"])
            else:
                unit, no_cost = Decimal(0), True
            parts[line["part"]] += half_up(Decimal(line["qty"]) * unit)
        if tc is None:
            for k in ("drugs", "anesthesia", "supplies"):
                parts[k] = None
        minutes = st["minutes"] if st and st["minutes"] is not None else DATA["clinic"]["avg_visit_minutes"]   # decision 12
        parts["fixed"] = half_up(Decimal(hour_cost) * minutes / 60) if hour_cost is not None else None
        known = {k: a for k, a in parts.items() if a is not None}
        net = price - sum(known.values())
        shares = largest_remainder(list(known.values()) + [net], price) if tc is not None else None
        out[sid] = {"price": price, "parts": parts, "net": net if tc is not None else None, "shares": shares, "no_cost": no_cost}
    return out


@pytest.mark.parametrize("case", SERVICE_CASES)
def test_every_part_price_and_share_matches_the_second_calculation(case):
    got = second_calculation(case)
    for s in CASES[case]["services"]:
        g = got[s["id"]]
        assert s["price"] == g["price"] and s["parts"] == g["parts"], (case, s["id"])
        assert s["net_profit"] == g["net"], (case, s["id"])
        if g["shares"] is not None:
            tenths_expected = [round(s["shares"][k] * 10) for k in PART_KEYS if s["parts"][k] is not None] + \
                [round(s["net_margin_pct"] * 10)]
            assert tenths_expected == g["shares"], (case, s["id"])


@pytest.mark.parametrize("case", ["main", "ward_no_schedule", "doctor_no_hours"])
def test_hour_cost_and_load_by_the_second_calculation(case):
    e = CASES[case]["efficiency"]
    assert e["hour_cost"] == half_up(Decimal(HAND_POOL) / e["available_hours"])
    assert e["load_pct"] == pct1(e["busy_hours"], e["available_hours"])
    assert e["free_hours"] == e["available_hours"] - e["busy_hours"]
    rows = e["rooms"] or [x for x in e["doctors"] if x["available_hours"]]
    assert sum(r["available_hours"] for r in rows) == e["available_hours"] and sum(r["busy_hours"] for r in rows) == e["busy_hours"]
    for r in rows:
        assert r["load_pct"] == pct1(r["busy_hours"], r["available_hours"])


def test_busy_hours_are_recounted_from_bookings_and_visits():
    minutes = Counter()
    for b in DATA["room_bookings"]:
        if b["date"].startswith(MONTH):
            minutes[b["room_id"]] += b["minutes"]
    assert {r["id"]: r["busy_hours"] for r in MAIN["efficiency"]["rooms"]} == {k: half_up(Decimal(m) / 60) for k, m in minutes.items()}
    visits = Counter(v["doctor_id"] for v in DATA["visits"] if v["date"].startswith(MONTH))
    docs = {x["id"]: x for x in CASES["ward_no_schedule"]["efficiency"]["doctors"]}
    assert all(docs[k]["busy_hours"] == half_up(Decimal(visits[k] * 30) / 60) and docs[k]["visits"] == visits[k] for k in docs)
    assert MAIN["efficiency"]["visits"] == sum(visits.values()) == 254


# ---------------------------------------------------------------- owner's decisions 2026-10-18 (manual services, average duration)
def test_manual_services_and_average_duration_by_hand():
    items = by_id(MAIN["services"])
    assert [(m["id"], m["price"]) for m in DATA["manual_services"]] == [("M1", 250_000), ("M2", 70_000)]
    m1, s7, s10 = items["M1"], items["S7"], items["S10"]
    assert (m1["price"], m1["visits_month"], m1["price_basis"], m1["source"]) == (250_000, 0, "manual", "manual")
    assert m1["parts"]["fixed"] == 30_763 == half_up(Decimal(46_145) * 40 / 60)             # 461,45 rub x 40 min / 60 = 307,63
    assert (s7["price"], s7["visits_month"], s7["price_basis"], s7["source"]) == (60_000, 16, "sales", "vetmanager")   # not the entered 700 rub
    assert "M2" not in items and s7["name"] == "Чистка ушей" and s7["parts"]["fixed"] == 11_536     # absorbed by name; 15 min: 115,36
    assert s10["minutes_source"] == "clinic_average" and s10["minutes"] == 30 and s10["parts"]["fixed"] == 23_073
    assert s10["missing"] == ["recipe"] and all(s["minutes_source"] == "own" for k, s in items.items() if k != "S10")
    assert MAIN["counts"] == {"all": 11, "loss": 1, "no_recipe": 2}
