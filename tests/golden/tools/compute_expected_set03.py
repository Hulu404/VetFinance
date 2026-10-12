"""Independent computation of expected results for set03 (writes tests/golden/set03/expected.json).

Does NOT import backend/ or gen_set03.py: it reads only set03/data.json and applies the rules written in
set03/README.md. Money: integer kopecks only; percents: integer tenths of a percent (JSON: float with one decimal).
Run: python tests/golden/tools/compute_expected_set03.py
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "set03"
SOURCE_ORDER = ["bank", "vetmanager", "bot", "manual"]
WINDOW_DAYS = 28          # burn-rate window for "enough for N days"
TREND_DAYS = 14           # points of balance_trend
WEEK = 7
MIN_DATA_DAYS = 7         # advice rules need at least a week of data
RUNWAY_ALERT_DAYS, RUNWAY_WARNING_DAYS = 14, 30
REVENUE_DROP_PCT = 85     # alert when revenue < 85% of the same days of the previous month

DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
D = date.fromisoformat
ACCOUNTS = DATA["accounts"]
TXS = DATA["transactions"]
OPENING = {a["id"]: D(a["opening_date"]) for a in ACCOUNTS}
FIRST_DAY = min(OPENING.values())
NORMS = DATA["norms"]
DOCTOR_NAME = {d["id"]: d["name"] for d in DATA["doctors"]}


def div_round(n, d):
    """Half away from zero (the rule of the money module)."""
    if d < 0:
        n, d = -n, -d
    sign = -1 if n < 0 else 1
    return sign * ((abs(n) * 2 + d) // (d * 2))


def ordered(sources):
    return [s for s in SOURCE_ORDER if s in sources]


def counted(t, as_of):
    """Operation takes part in balances/expenses: not a duplicate, inside [opening_date, as_of]."""
    return t["status"] != "duplicate" and OPENING[t["account_id"]] <= D(t["date"]) <= as_of


def balance_at(day):
    """{account_id: (value, sources)} at the end of `day`."""
    out = {}
    for a in ACCOUNTS:
        value, src = a["opening_balance"], set()
        if day >= OPENING[a["id"]]:
            for t in TXS:
                if t["account_id"] == a["id"] and counted(t, day):
                    value += t["amount"]
                    src.add(t["source"])
        out[a["id"]] = (value, src)
    return out


def fig_balance(bal, kinds):
    accs = sorted((a for a in ACCOUNTS if a["type"] in kinds), key=lambda a: (a["name"], a["id"]))
    src = set().union(*[bal[a["id"]][1] for a in accs]) if accs else set()
    return {"value": sum(bal[a["id"]][0] for a in accs),
            "breakdown": {a["name"]: bal[a["id"]][0] for a in accs},
            "source": ordered(src) or ["manual"]}


def pct1(part, whole):
    return div_round(part * 1000, whole) / 10


def fmt_pct(x):
    return f"{x:.1f}".replace(".", ",")


def month_range(as_of):
    start = as_of.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, (nxt - start).days


def sum_sales(start, end):
    rev = {"service": 0, "good": 0}
    n = 0
    for s in DATA["sales"]:
        if s["status"] == "exec" and start <= D(s["date"]) <= end:
            n += 1
            for ln in s["lines"]:
                rev[ln["kind"]] += ln["amount"]
    return rev, n


def visits_in(start, end):
    per = {}
    for v in DATA["visits"]:
        if start <= D(v["date"]) <= end:
            per[v["doctor_id"]] = per.get(v["doctor_id"], 0) + 1
    return per


def expense_ops(start, end):
    return [t for t in TXS if t["kind"] == "out" and counted(t, end) and D(t["date"]) >= start]


def sorted_breakdown(d):
    return dict(sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))


def compute_case(as_of):
    bal = balance_at(as_of)
    total, bank, cash = fig_balance(bal, {"bank", "cash"}), fig_balance(bal, {"bank"}), fig_balance(bal, {"cash"})
    data_days = (as_of - FIRST_DAY).days + 1

    # week change
    prev_day = as_of - timedelta(days=WEEK)
    week = week_pct = None
    if prev_day >= FIRST_DAY:
        prev = balance_at(prev_day)
        prev_total = sum(v for v, _ in prev.values())
        change = total["value"] - prev_total
        src = {t["source"] for t in TXS if counted(t, as_of) and prev_day < D(t["date"])}
        names = sorted(ACCOUNTS, key=lambda a: (a["name"], a["id"]))
        week = {"value": change, "breakdown": {a["name"]: bal[a["id"]][0] - prev[a["id"]][0] for a in names},
                "source": ordered(src) or ["manual"], "previous": prev_total}
        if prev_total > 0:
            week_pct = {"value": pct1(change, prev_total), "breakdown_values": [prev_total, total["value"]],
                        "source": week["source"]}

    # trend
    trend = []
    for k in range(TREND_DAYS - 1, -1, -1):
        day = as_of - timedelta(days=k)
        if day >= FIRST_DAY:
            trend.append({"date": day.isoformat(), "value": sum(v for v, _ in balance_at(day).values())})

    # runway
    window = min(WINDOW_DAYS, data_days)
    burn = sum(-t["amount"] for t in expense_ops(as_of - timedelta(days=window - 1), as_of))
    runway = None
    if burn > 0:
        value = 0 if total["value"] <= 0 else total["value"] * window // burn
        runway = {"value": value, "window_days": window, "burn": burn, "daily": div_round(burn, window),
                  "breakdown_values": [total["value"], burn, div_round(burn, window), window], "source": total["source"]}

    # month
    start, days_total = month_range(as_of)
    rev, n_inv = sum_sales(start, as_of)
    revenue = rev["service"] + rev["good"]
    ops = expense_ops(start, as_of)
    by_cat = {}
    for t in ops:
        key = t["category"] or "Без статьи"
        by_cat[key] = by_cat.get(key, 0) - t["amount"]
    expenses = sum(by_cat.values())
    profit = revenue - expenses
    rev_src = ["vetmanager"] if n_inv else ["manual"]
    exp_src = ordered({t["source"] for t in ops}) or ["manual"]
    both_src = ordered(set(rev_src) | set(exp_src))
    per_doc = visits_in(start, as_of)
    visits = sum(per_doc.values())
    margin = pct1(profit, revenue) if revenue > 0 else None
    month = {
        "days_passed": as_of.day, "days_total": days_total,
        "revenue": {"value": revenue, "breakdown": {"Услуги": rev["service"], "Товары": rev["good"]}, "source": rev_src},
        "expenses": {"value": expenses, "breakdown": sorted_breakdown(by_cat), "source": exp_src},
        "profit": {"value": profit, "breakdown": {"Выручка": revenue, "Расходы": -expenses}, "source": both_src},
        "profit_margin_pct": None if margin is None else {"value": margin, "breakdown_values": [profit, revenue], "source": both_src},
        "visits": {"value": visits, "breakdown": sorted_breakdown({DOCTOR_NAME[k]: v for k, v in per_doc.items() if v}),
                   "source": ["vetmanager"]},
        "avg_check": None if n_inv == 0 else {"value": div_round(revenue, n_inv), "breakdown_values": [revenue, n_inv],
                                              "invoices": n_inv, "source": ["vetmanager"]},
    }

    # alternative runway formula of prototype v6: month-to-date expenses / days passed (for the product owner)
    alt = None
    if expenses > 0 and total["value"] > 0:
        alt = total["value"] * as_of.day // expenses

    advice = build_advice(as_of, data_days, runway, month, start, by_cat)
    return {
        "as_of": as_of.isoformat(),
        "balance": {"total": total, "bank": bank, "cash": cash},
        "week_change": week, "week_change_pct": week_pct, "balance_trend": trend,
        "runway_days": runway, "month": month, "advice": advice,
        "alternatives": {"runway_days_month_to_date": alt},
    }


def build_advice(as_of, data_days, runway, month, start, by_cat):
    if data_days < MIN_DATA_DAYS:
        return []
    out = []
    revenue, expenses, profit = month["revenue"]["value"], month["expenses"]["value"], month["profit"]["value"]

    if runway and runway["value"] < RUNWAY_WARNING_DAYS:
        out.append({"id": "cash_runway", "severity": "alert" if runway["value"] < RUNWAY_ALERT_DAYS else "warning",
                    "why_amounts": [runway["breakdown_values"][0], runway["burn"], runway["daily"]],
                    "why_numbers": [runway["value"], runway["window_days"]], "why_pcts": [],
                    "facts": {"runway_days": runway["value"], "balance": runway["breakdown_values"][0],
                              "burn": runway["burn"], "window_days": runway["window_days"], "daily": runway["daily"]}})

    if as_of.day >= MIN_DATA_DAYS and revenue > 0:
        norm = NORMS["drugs"]
        drugs = by_cat.get(norm["category"], 0)
        if drugs * 100 > norm["max_pct"] * revenue:
            limit = div_round(revenue * norm["max_pct"], 100)
            purchases = [t for t in TXS if t["category"] == norm["category"] and t["kind"] == "out" and counted(t, as_of)
                         and D(t["date"]) >= start]
            big = min(purchases, key=lambda t: (t["amount"], t["date"], t["id"]))  # most negative first
            share = pct1(drugs, revenue)
            out.append({"id": "drug_share", "severity": "warning",
                        "why_amounts": [drugs, revenue, drugs - limit, -big["amount"]],
                        "why_numbers": [], "why_pcts": [fmt_pct(share), str(norm["max_pct"])],
                        "facts": {"drugs": drugs, "revenue": revenue, "share_pct": share, "norm_max_pct": norm["max_pct"],
                                  "excess": drugs - limit, "biggest_purchase": {"date": big["date"], "amount": -big["amount"], "id": big["id"]}}})

        prev_start = (start - timedelta(days=1)).replace(day=1)
        if prev_start >= FIRST_DAY:
            prev_end = min(prev_start + timedelta(days=as_of.day - 1), start - timedelta(days=1))
            prev_rev_parts, _ = sum_sales(prev_start, prev_end)
            prior = prev_rev_parts["service"] + prev_rev_parts["good"]
            if prior > 0 and revenue * 100 < prior * REVENUE_DROP_PCT:
                drop = pct1(prior - revenue, prior)
                v_now, v_prev = month["visits"]["value"], sum(visits_in(prev_start, prev_end).values())
                out.append({"id": "revenue_drop", "severity": "warning",
                            "why_amounts": [revenue, prior, prior - revenue], "why_numbers": [v_now, v_prev],
                            "why_pcts": [fmt_pct(drop)],
                            "facts": {"current": revenue, "prior": prior, "drop_pct": drop, "visits_now": v_now,
                                      "visits_prior": v_prev, "prior_from": prev_start.isoformat(), "prior_to": prev_end.isoformat()}})

        nm = NORMS["profit_margin"]
        margin_tenths = div_round(profit * 1000, revenue)
        if margin_tenths >= nm["min_pct"] * 10:
            out.append({"id": "margin_ok", "severity": "good",
                        "why_amounts": [profit, revenue, expenses], "why_numbers": [],
                        "why_pcts": [fmt_pct(margin_tenths / 10), str(nm["min_pct"])],
                        "facts": {"margin_pct": margin_tenths / 10, "norm_min_pct": nm["min_pct"], "norm_max_pct": nm["max_pct"],
                                  "above_norm": margin_tenths > nm["max_pct"] * 10}})

    rank = {"alert": 0, "warning": 1, "good": 2}
    order = {"cash_runway": 0, "drug_share": 1, "revenue_drop": 2, "margin_ok": 3}
    return sorted(out, key=lambda a: (rank[a["severity"]], order[a["id"]]))


def main():
    cases = [compute_case(D(x)) for x in DATA["as_of_cases"]]
    result = {"note": "Computed by tools/compute_expected_set03.py from data.json; see set03/README.md for the rules.",
              "parameters": {"runway_window_days": WINDOW_DAYS, "trend_days": TREND_DAYS, "week_days": WEEK,
                             "min_data_days": MIN_DATA_DAYS, "runway_alert_days": RUNWAY_ALERT_DAYS,
                             "runway_warning_days": RUNWAY_WARNING_DAYS, "revenue_drop_threshold_pct": REVENUE_DROP_PCT},
              "cases": cases}
    (BASE / "expected.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for c in cases:
        m = c["month"]
        print(c["as_of"], "total", c["balance"]["total"]["value"], "cash", c["balance"]["cash"]["value"],
              "| week", c["week_change"] and c["week_change"]["value"], "| runway", c["runway_days"] and c["runway_days"]["value"],
              "alt", c["alternatives"]["runway_days_month_to_date"],
              "| rev", m["revenue"]["value"], "exp", m["expenses"]["value"], "profit", m["profit"]["value"],
              "margin", m["profit_margin_pct"] and m["profit_margin_pct"]["value"], "visits", m["visits"]["value"],
              "| advice", [a["id"] + ":" + a["severity"] for a in c["advice"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
