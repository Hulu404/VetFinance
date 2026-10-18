"""Independent computation of expected results for set06 (writes tests/golden/set06/expected.json).

Does NOT import backend/ or gen_set06.py: it reads only set06/data.json and applies the numbered rules of set06/README.md
(the rule number is quoted next to the code). Money: integer kopecks; exact fractions until the one rounding of a figure
(div_round: half away from zero, the same as engine/money.py).
Run: python tests/golden/tools/compute_expected_set06.py
"""
import json
import math
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "set06"
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
D = date.fromisoformat
AS_OF = D(DATA["as_of"])
MONTH = DATA["month"]
PNL = DATA["pnl_month"]
WINDOW_FROM, WINDOW_TO = AS_OF - timedelta(days=90), AS_OF - timedelta(days=1)                      # rule P1
DAYS_IN_MONTH = 30
SHARE_ORDER = ["doctor_pay", "drugs", "anesthesia", "supplies", "acquiring", "fixed", "taxes", "net"]
MATERIAL_PARTS = ["drugs", "anesthesia", "supplies"]


def div_round(n, d):
    """n / d rounded half away from zero, integers only (rule 20)."""
    if d < 0:
        n, d = -n, -d
    sign = -1 if n < 0 else 1
    return sign * ((abs(n) * 2 + d) // (d * 2))


def round_fraction(x: Fraction) -> int:
    return div_round(x.numerator, x.denominator)


def tenths(part, whole):
    """percent with one decimal as a number: 26.6."""
    return div_round(part * 1000, whole) / 10


def shares_largest_remainder(amounts: dict, price: int) -> dict:
    """Rule P12: shares of the price in tenths of a percent, the sum is exactly 100.0 (largest remainder, ties: earlier part)."""
    exact = {k: Fraction(a * 1000, price) for k, a in amounts.items()}
    floors = {k: math.floor(x) for k, x in exact.items()}
    left = 1000 - sum(floors.values())
    order = sorted(exact, key=lambda k: (-(exact[k] - floors[k]), SHARE_ORDER.index(k)))
    for k in order[:left]:
        floors[k] += 1
    return {k: floors[k] / 10 for k in SHARE_ORDER if k in floors}


# ---------------------------------------------------------------- items (rule P6)
def item_costs():
    out = {}
    for item in DATA["stock_items"]:
        batches = [b for b in DATA["stock_batches"] if b["item_id"] == item["id"]]
        live = [b for b in batches if Fraction(b["qty"]) > 0 and (b["expires_on"] is None or D(b["expires_on"]) >= AS_OF)]
        if live:
            qty = sum(Fraction(b["qty"]) for b in live)
            out[item["id"]] = {"basis": "average", "unit_cost": sum(Fraction(b["qty"]) * b["unit_cost"] for b in live) / qty}
        elif batches:
            last = max(batches, key=lambda b: (b["received_on"] or "", b["id"]))
            out[item["id"]] = {"basis": "last_batch", "unit_cost": Fraction(last["unit_cost"])}
        else:
            out[item["id"]] = {"basis": "none", "unit_cost": None}
    return out


# ---------------------------------------------------------------- efficiency (rules E1..E6)
def schedule_minutes(schedule):
    total, day = 0, D(MONTH + "-01")
    while day.strftime("%Y-%m") == MONTH:
        total += sum(s["to_min"] - s["from_min"] for s in schedule if s["weekday"] == day.weekday())
        day += timedelta(days=1)
    return total


def month_visits():
    return [v for v in DATA["visits"] if v["date"].startswith(MONTH)]


def efficiency(case):
    rooms = DATA["rooms"]
    rooms_ok = bool(rooms) and all(r["id"] not in case["drop_room_schedules"] for r in rooms) \
        and any(b["date"].startswith(MONTH) for b in DATA["room_bookings"])                                     # rule E1
    visits = month_visits()
    revenue = PNL["revenue"]
    no_expenses = bool(case.get("no_expenses"))                                                                # rule E4: no statement
    fixed_nm = 0 if no_expenses else sum(f["amount"] for f in PNL["fixed_lines"] if f["kind"] != "materials")  # rule E4
    obligations = 0 if no_expenses else sum(o["amount"] for o in PNL["obligation_lines"])
    pool = fixed_nm + obligations
    by_doctor = {d["id"]: sum(1 for v in visits if v["doctor_id"] == d["id"]) for d in DATA["doctors"]}
    out = {"revenue": revenue, "visits": len(visits), "visits_by_doctor": by_doctor,
           "visits_without_doctor": sum(1 for v in visits if v["doctor_id"] is None),
           "avg_check": div_round(revenue, len(visits)) if visits else None,                                    # rule E6
           "pool": {"fixed": fixed_nm, "obligations": obligations, "total": pool}, "marginal_profit": PNL["marginal_profit"]}
    rooms_out, doctors_out = [], []
    if rooms_ok:
        for r in rooms:
            avail = div_round(schedule_minutes(r["schedule"]), 60)                                              # rule E2
            busy = div_round(sum(b["minutes"] for b in DATA["room_bookings"]
                                 if b["room_id"] == r["id"] and b["date"].startswith(MONTH)), 60)
            rooms_out.append({"id": r["id"], "name": r["name"], "available_hours": avail, "busy_hours": busy,
                              "free_hours": avail - busy, "load_pct": tenths(busy, avail) if avail else None})
        avail, busy = sum(r["available_hours"] for r in rooms_out), sum(r["busy_hours"] for r in rooms_out)
        out.update(mode="rooms", load_by="rooms", partial_reasons=[])
    else:
        for d in DATA["doctors"]:
            hpw = None if d["id"] in case["drop_doctor_hours"] or d["hours_per_week"] is None else Fraction(d["hours_per_week"])
            avail = round_fraction(hpw * DAYS_IN_MONTH / 7) if hpw is not None else None                        # rule E2
            busy = div_round(by_doctor[d["id"]] * DATA["clinic"]["avg_visit_minutes"], 60)
            doctors_out.append({"id": d["id"], "name": d["name"], "visits": by_doctor[d["id"]], "available_hours": avail,
                                "busy_hours": busy, "free_hours": None if avail is None else avail - busy,
                                "load_pct": tenths(busy, avail) if avail else None})
        counted = [x for x in doctors_out if x["available_hours"]]
        avail, busy = sum(x["available_hours"] for x in counted), sum(x["busy_hours"] for x in counted)
        out.update(mode="doctors", load_by="doctors", status="ok", partial_reasons=[] if counted else ["no_doctor_hours"])
    out["rooms"], out["doctors"] = rooms_out, doctors_out
    out["available_hours"], out["busy_hours"] = avail, busy
    if avail:
        out["free_hours"] = avail - busy
        out["load_pct"] = tenths(busy, avail)                                                                   # rule E3
    else:
        out.update(free_hours=None, load_pct=None)
    if avail and not no_expenses:
        out["hour_cost"] = div_round(pool, avail)                                                               # rule E4
        fixed_per_hour = div_round(fixed_nm, avail)
        out["hour_cost_lines"] = {"fixed": fixed_per_hour, "obligations": out["hour_cost"] - fixed_per_hour}
        out["hour_margin"] = div_round(PNL["marginal_profit"], busy) if busy else None                          # rule E5
    else:
        out.update(hour_cost=None, hour_cost_lines=None, hour_margin=None)
    if no_expenses:
        out["partial_reasons"] = out["partial_reasons"] + ["no_expenses"]
    out["status"] = "partial" if out["partial_reasons"] else "ok"
    return out


# ---------------------------------------------------------------- price list (rules P1..P14)
def norm_name(name):
    """Rule P2a: trim, collapse spaces, case, ё = е."""
    return " ".join(name.split()).casefold().replace("ё", "е")


def service_lines():
    rows = []
    for sale in DATA["sales"]:
        if sale["status"] == "exec" and WINDOW_FROM <= D(sale["date"]) <= WINDOW_TO:
            for line in sale["lines"]:
                if line["kind"] == "service":
                    rows.append({**line, "date": sale["date"]})
    return rows


def price_list(hour_cost, costs):
    settings = {s["service_id"]: s for s in DATA["service_settings"]}
    techcards = {t["service_id"]: t["lines"] for t in DATA["techcards"]}
    lines = service_lines()
    month_lines = [l for l in lines if l["date"].startswith(MONTH)]
    service_revenue = sum(l["amount"] for l in month_lines)
    out = []
    sold_names = {norm_name(l["name"]) for l in lines}                                                           # rule P2a
    manual = {m["id"]: m for m in DATA["manual_services"] if norm_name(m["name"]) not in sold_names}         # matched ones are absorbed
    for sid in sorted({l["service_id"] for l in lines} | set(manual)):                                           # rule P2
        mine = [l for l in lines if l["service_id"] == sid]
        st = settings.get(sid)
        if mine:
            price = div_round(sum(l["amount"] for l in mine), sum(l["qty"] for l in mine))                       # rule P3
        else:
            price = manual[sid]["price"]                                                                         # rule P2b: entered price
        visits_month = sum(l["qty"] for l in month_lines if l["service_id"] == sid)                              # rule P4
        pct = st["doctor_pct_bp"] if st else None
        parts = {"doctor_pay": div_round(price * pct, 10000) if pct is not None
                 else div_round(price * PNL["doctor_percent_payouts"], service_revenue)}                         # rule P5
        parts["acquiring"] = div_round(price * PNL["acquiring_fee"], PNL["revenue"])                             # rule P8
        parts["taxes"] = div_round(price * PNL["taxes"], PNL["revenue"])
        missing, tc_lines = [], []
        if sid not in techcards:                                                                                 # rule P10
            missing.append("recipe")
            parts.update(drugs=None, anesthesia=None, supplies=None)
        else:
            parts.update(drugs=0, anesthesia=0, supplies=0)
            for tl in techcards[sid]:
                unit = costs[tl["item_id"]]["unit_cost"]
                if unit is None:
                    cost = 0
                    if "item_no_cost" not in missing:
                        missing.append("item_no_cost")
                else:
                    cost = round_fraction(Fraction(tl["qty"]) * unit)                                            # rule P7
                tc_lines.append({"item_id": tl["item_id"], "qty": tl["qty"], "part": tl["part"], "cost": cost,
                                 "no_cost": unit is None})
                parts[tl["part"]] += cost
        minutes = st["minutes"] if st else None
        average_duration = minutes is None                                                                       # rule P9
        if average_duration:
            minutes = DATA["clinic"]["avg_visit_minutes"]
        if hour_cost is None:
            parts["fixed"] = None
            missing.append("hour_cost")
        else:
            parts["fixed"] = div_round(hour_cost * minutes, 60)
        missing.sort(key=["recipe", "hour_cost", "item_no_cost"].index)
        status = "no_recipe" if "recipe" in missing else ("partial" if missing else "ok")
        name = " ".join(manual[sid]["name"].split()) if sid in manual else (st["name"] if st else mine[-1]["name"])
        item = {"id": sid, "name": name, "source": "manual" if sid in manual else "vetmanager",
                "price_basis": "sales" if mine else "manual", "minutes_source": "clinic_average" if average_duration else "own", "minutes": minutes,
                "group": st["group"] if st else None, "price": price,
                "visits_month": visits_month, "parts": parts, "status": status, "missing": missing, "techcard_lines": tc_lines}
        if status == "no_recipe":                                                                                # rule P11
            item.update(net_profit=None, net_margin_pct=None, monthly_profit=None, shares=None, cost_total=None)
        else:
            known = {k: a for k, a in parts.items() if a is not None}
            net = price - sum(known.values())
            shares = shares_largest_remainder({**known, "net": net}, price)                                      # rule P12
            item.update(net_profit=net, net_margin_pct=shares["net"], monthly_profit=net * visits_month,
                        shares={k: x for k, x in shares.items() if k != "net"}, cost_total=sum(known.values()))
        out.append(item)
    return out


def sort_services(items, key):
    """Rule P14: worst first; no value (no_recipe) at the end; ties by name."""
    def margin_key(s):
        return (s["net_profit"] is None, Fraction(s["net_profit"], s["price"]) if s["net_profit"] is not None else 0, s["name"])

    def profit_key(s):
        return (s["monthly_profit"] is None, s["monthly_profit"] or 0, s["name"])
    return sorted(items, key=margin_key if key == "margin" else profit_key)


def alternatives(costs):
    """Numbers of alternatives that the owner can choose (README, questions)."""
    techcards = {t["service_id"]: t["lines"] for t in DATA["techcards"]}
    last = {}
    for item in DATA["stock_items"]:
        batches = [b for b in DATA["stock_batches"] if b["item_id"] == item["id"]]
        if batches:
            last[item["id"]] = max(batches, key=lambda b: (b["received_on"] or "", b["id"]))["unit_cost"]
    main = efficiency(DATA["cases"][0])
    return {
        "materials_s4_last_batch_price": sum(round_fraction(Fraction(tl["qty"]) * last[tl["item_id"]]) for tl in techcards["S4"]),
        "materials_s4_average": sum(round_fraction(Fraction(tl["qty"]) * costs[tl["item_id"]]["unit_cost"]) for tl in techcards["S4"]),
        "fixed_s1_from_unrounded_hour_cost": div_round(main["pool"]["total"] * 30, main["available_hours"] * 60),
        "fixed_s1_from_rounded_hour_cost": div_round(main["hour_cost"] * 30, 60),
    }


def main():
    costs = item_costs()
    cases = {}
    for case in DATA["cases"]:
        eff = efficiency(case)
        if case.get("efficiency_only"):
            cases[case["key"]] = {"mode": eff["mode"], "hour_cost": eff["hour_cost"], "efficiency": eff, "efficiency_only": True}
            continue
        items = price_list(eff["hour_cost"], costs)
        by_margin, by_profit = sort_services(items, "margin"), sort_services(items, "profit")
        cases[case["key"]] = {
            "mode": eff["mode"], "hour_cost": eff["hour_cost"], "efficiency": eff, "services": by_margin,
            "order_by_profit": [s["id"] for s in by_profit],
            "counts": {"all": len(items), "loss": sum(1 for s in items if s["net_profit"] is not None and s["net_profit"] < 0),
                       "no_recipe": sum(1 for s in items if s["status"] == "no_recipe")},
        }
    expected = {
        "as_of": DATA["as_of"], "month": MONTH,
        "item_costs": {i: {"basis": c["basis"], "unit_cost": None if c["unit_cost"] is None
                           else f"{c['unit_cost'].numerator}/{c['unit_cost'].denominator}"} for i, c in costs.items()},
        "cases": cases, "alternatives": alternatives(costs),
    }
    (BASE / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {BASE / 'expected.json'}")


if __name__ == "__main__":
    main()
