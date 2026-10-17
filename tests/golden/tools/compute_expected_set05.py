"""Independent computation of expected results for set05 (writes tests/golden/set05/expected.json).

Does NOT import backend/ or gen_set05.py: it reads only set05/data.json and applies the numbered rules of set05/README.md
(the rule number is quoted next to the code). Money: integer kopecks only, rounding half up in one place (div_round).
Run: python tests/golden/tools/compute_expected_set05.py
"""
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "set05"
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
D = date.fromisoformat
CAT_TYPE = {c["name"]: c["type"] for c in DATA["categories"]}
DEFERRAL = {c["inn"]: c["max_deferral_days"] for c in DATA["counterparties"]}
WINDOW_DAYS = DATA["window_days"]
PROFILE_WEEKS = 12                                   # rule 5
REGULAR_MONTHS = 3                                   # rule 7
ANALYSIS_MONTHS = 6                                  # rule 6
AMOUNT_TOLERANCE_PCT = 25                            # rule 8
DETECTED_TYPES = {"variable", "fixed", "tax", None}  # rule 6: None = operation without an article
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTH_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
NBSP = " "


def div_round(n, d):
    """n / d rounded half away from zero, integers only (rule 24)."""
    if d < 0:
        n, d = -n, -d
    sign = -1 if n < 0 else 1
    return sign * ((abs(n) * 2 + d) // (d * 2))


def is_workday(d):                                   # rule 4
    return d.weekday() < 5


def shift_off_day(d, direction):                     # rule 11
    step = timedelta(days=-1 if direction == "prev" else 1)
    while not is_workday(d):
        d += step
    return d


def month_key(d):
    return f"{d.year}-{d.month:02d}"


def add_months(month, n):
    y, m = map(int, month.split("-"))
    k = y * 12 + m - 1 + n
    return f"{k // 12}-{k % 12 + 1:02d}"


def last_day(month):
    return D(add_months(month, 1) + "-01") - timedelta(days=1)


def nominal_date(month, day):
    return D(f"{month}-01").replace(day=min(day, last_day(month).day))


def median3(values):
    return sorted(values)[len(values) // 2]


def rub(kopecks):
    """'108 500 ₽', '16 033,77 ₽', '−1 200 ₽' with no-break spaces (texts, rule 25)."""
    sign = "−" if kopecks < 0 else ""
    r, k = divmod(abs(kopecks), 100)
    body = f"{r:,}".replace(",", NBSP) + (f",{k:02d}" if k else "")
    return f"{sign}{body}{NBSP}₽"


def day_text(d):
    return f"{d.day} {MONTH_GEN[d.month - 1]}"


def pct1(part, whole):
    return div_round(part * 1000, whole) / 10


# ================================================================== opening balance (rule 2)
def opening_balance(as_of):
    by_account = []
    for acc in DATA["accounts"]:
        if D(acc["opening_date"]) > as_of:          # not opened yet on the morning of as_of
            by_account.append({"label": acc["name"], "value": 0})
            continue
        value = acc["opening_balance"]
        for t in DATA["transactions"]:
            if t["account_id"] != acc["id"] or t["status"] == "duplicate":
                continue
            if D(acc["opening_date"]) <= D(t["date"]) < as_of:
                value += t["amount"]
        by_account.append({"label": acc["name"], "value": value})
    return {"value": sum(b["value"] for b in by_account), "breakdown": by_account}


# ================================================================== income forecast by weekday (rule 5)
def income_profile(as_of):
    start = max(as_of - timedelta(days=PROFILE_WEEKS * 7), D(DATA["history"]["from"]))
    end = as_of - timedelta(days=1)
    sums, counts = [0] * 7, [0] * 7
    d = start
    while d <= end:
        counts[d.weekday()] += 1
        d += timedelta(days=1)
    excluded = []
    for t in DATA["transactions"]:
        td = D(t["date"])
        if not (start <= td <= end) or t["kind"] != "in":
            continue
        if t["status"] == "duplicate" or CAT_TYPE.get(t["category"]) != "income":
            excluded.append({"id": t["id"], "date": t["date"], "amount": t["amount"],
                             "reason": "duplicate" if t["status"] == "duplicate" else "not_revenue"})
            continue
        sums[td.weekday()] += t["amount"]
    by_weekday = [{"weekday": i, "label": WEEKDAYS[i], "sum": sums[i], "days": counts[i],
                   "average": div_round(sums[i], counts[i]) if counts[i] else 0} for i in range(7)]
    return {"from": start.isoformat(), "to": end.isoformat(), "weeks": PROFILE_WEEKS, "by_weekday": by_weekday,
            "excluded": excluded}


def income_profile_designer(as_of):
    """Alternative of design/screens/calendar.md (not our rule 5): 90 days as_of-89 .. as_of, every `in` operation of the bank
    and the cash desk without transfers and duplicates (check included, any article)."""
    start, end = as_of - timedelta(days=89), as_of
    first_open = min(D(a["opening_date"]) for a in DATA["accounts"])
    sums, counts = [0] * 7, [0] * 7
    d = max(start, first_open)
    while d <= end:
        counts[d.weekday()] += 1
        d += timedelta(days=1)
    for t in DATA["transactions"]:
        if t["kind"] == "in" and t["status"] != "duplicate" and start <= D(t["date"]) <= end:
            sums[D(t["date"]).weekday()] += t["amount"]
    return [{"weekday": i, "label": WEEKDAYS[i], "sum": sums[i], "days": counts[i],
             "average": div_round(sums[i], counts[i]) if counts[i] else 0} for i in range(7)]


# ================================================================== regular payments (rules 6-11)
def analysis_months(as_of):
    first_history = month_key(D(DATA["history"]["from"]))
    months = [add_months(month_key(as_of), -n) for n in range(ANALYSIS_MONTHS, 0, -1)]
    return [m for m in months if m >= first_history]


def series_key(t):
    return (t["counterparty_inn"] or t["counterparty_name"], t["category"])


def detect_recurring(as_of):
    months = analysis_months(as_of)
    last3 = months[-REGULAR_MONTHS:]
    groups = defaultdict(list)
    for t in DATA["transactions"]:
        if t["kind"] != "out" or t["status"] == "duplicate" or CAT_TYPE.get(t["category"]) not in DETECTED_TYPES:
            continue
        if month_key(D(t["date"])) in months:
            groups[series_key(t)].append(t)
    regular, rejected = [], []
    for key in sorted(groups, key=lambda k: (k[0], k[1] or "")):
        ops = sorted(groups[key], key=lambda t: (t["date"], t["id"]))
        name = ops[-1]["counterparty_name"]
        per_month = defaultdict(list)
        for t in ops:
            per_month[month_key(D(t["date"]))].append(t)
        counts = [len(per_month[m]) for m in last3]
        if min(counts) == 0:
            rejected.append({"key": list(key), "name": name, "reason": "not_every_month",
                             "months": sorted(per_month)})
            continue
        if len(set(counts)) != 1:
            rejected.append({"key": list(key), "name": name, "reason": "unstable_count", "counts": counts})
            continue
        slots_n = counts[0]
        slots, failed = [], None
        for s in range(slots_n):
            hist = [per_month[m][s] for m in months if len(per_month[m]) == slots_n]
            last_amounts = [-per_month[m][s]["amount"] for m in last3]
            med = median3(last_amounts)
            if any(abs(a - med) * 100 > AMOUNT_TOLERANCE_PCT * med for a in last_amounts):
                failed = {"key": list(key), "name": name, "reason": "amount_varies", "slot": s + 1, "last_amounts": last_amounts}
                break
            days = Counter(D(t["date"]).day for t in hist)
            top = max(days.values())
            day = max(d for d, c in days.items() if c == top)          # rule 9: tie -> the larger day
            slots.append({"slot": s + 1, "day": day, "amount": med, "last_amounts": last_amounts,
                          "days_seen": [D(t["date"]).day for t in hist]})
        if failed:
            rejected.append(failed)
            continue
        inn, category = key
        regular.append({"key": f"{inn}|{category or ''}", "inn": ops[-1]["counterparty_inn"], "name": name,
                        "category": category, "type": CAT_TYPE.get(category), "slots": slots,
                        "shift": "next" if CAT_TYPE.get(category) == "tax" else "prev",
                        "max_deferral_days": DEFERRAL.get(ops[-1]["counterparty_inn"], 0)})
    return regular, rejected


def recurring_payments(as_of, window_end, regular):
    out = []
    month = month_key(as_of)
    months = []
    while month <= month_key(window_end):
        months.append(month)
        month = add_months(month, 1)
    for ser in regular:
        inn_or_name = ser["inn"] or ser["name"]
        paid_this_month = sum(1 for t in DATA["transactions"]
                              if t["kind"] == "out" and t["status"] != "duplicate"
                              and (t["counterparty_inn"] or t["counterparty_name"]) == inn_or_name
                              and t["category"] == ser["category"]
                              and month_key(D(t["date"])) == month_key(as_of) and D(t["date"]) < as_of)
        for m in months:
            for slot in ser["slots"]:
                if m == month_key(as_of) and slot["slot"] <= paid_this_month:     # rule 11: already paid
                    continue
                nom = nominal_date(m, slot["day"])
                pay = shift_off_day(nom, ser["shift"])
                if as_of <= pay <= window_end:
                    out.append({"date": pay.isoformat(), "nominal_date": nom.isoformat(), "name": ser["name"],
                                "amount": slot["amount"], "source": "recurring", "category": ser["category"],
                                "series": ser["key"], "slot": slot["slot"], "max_deferral_days": ser["max_deferral_days"]})
    return out


# ================================================================== obligations (rule 22)
def loan_schedule(ob):
    """Payments of a loan (rule 22): interest on the balance of the 1st day of the payment month, the rest repays the
    principal; the last of payments_total payments is the balance plus its interest (it absorbs the rounding)."""
    first = D(ob["first_payment_date"])
    balance, rows = ob["principal"], []
    for n in range(ob["payments_total"]):
        month = add_months(month_key(first), n)
        interest = div_round(balance * ob["annual_rate_bp"], 10000 * 12)
        last = n == ob["payments_total"] - 1 or balance + interest <= ob["payment"]
        payment = balance + interest if last else ob["payment"]
        principal = payment - interest
        rows.append({"month": month, "date": shift_off_day(nominal_date(month, ob["payment_day"]), "prev").isoformat(),
                     "payment": payment, "interest": interest, "principal": principal, "balance_before": balance,
                     "balance_after": balance - principal})
        balance -= principal
        if balance == 0:
            break
    return rows


def lease_schedule(ob):
    first = D(ob["first_payment_date"])
    rows = []
    for n in range(ob["payments_total"]):
        month = add_months(month_key(first), n)
        rows.append({"month": month, "date": shift_off_day(nominal_date(month, ob["payment_day"]), "prev").isoformat(),
                     "payment": ob["payment"]})
    return rows


def amortization_rows(ob):
    n = ob["life_years"] * 12
    monthly = div_round(ob["cost"], n)
    start = add_months(month_key(D(ob["in_service_date"])), 1)
    return [{"month": add_months(start, i), "amount": monthly if i < n - 1 else ob["cost"] - monthly * (n - 1)} for i in range(n)]


def charges(month):
    items = []
    for ob in DATA["obligations"]:
        if ob["kind"] == "loan":
            for r in loan_schedule(ob):
                if r["month"] == month:
                    items.append({"obligation_id": ob["id"], "name": ob["name"], "kind": "loan_interest", "amount": r["interest"]})
        elif ob["kind"] == "lease":
            for r in lease_schedule(ob):
                if r["month"] == month:
                    items.append({"obligation_id": ob["id"], "name": ob["name"], "kind": "lease", "amount": r["payment"]})
        else:
            for r in amortization_rows(ob):
                if r["month"] == month:
                    items.append({"obligation_id": ob["id"], "name": ob["name"], "kind": "amortization", "amount": r["amount"]})
    return {"month": month, "items": items, "total": sum(i["amount"] for i in items)}


def obligation_payments(as_of, window_end):
    out = []
    for ob in DATA["obligations"]:
        if ob["kind"] not in ("loan", "lease"):
            continue
        rows = loan_schedule(ob) if ob["kind"] == "loan" else lease_schedule(ob)
        for r in rows:
            if as_of <= D(r["date"]) <= window_end:
                out.append({"date": r["date"], "nominal_date": nominal_date(r["month"], ob["payment_day"]).isoformat(),
                            "name": ob["name"], "amount": r["payment"], "source": "obligation", "category": None,
                            "obligation_id": ob["id"], "max_deferral_days": 0})
    return out


def obligations_summary(as_of):
    loans, equipment = [], []
    month = month_key(as_of)
    for ob in DATA["obligations"]:
        if ob["kind"] in ("loan", "lease"):
            rows = loan_schedule(ob) if ob["kind"] == "loan" else lease_schedule(ob)
            paid = [r for r in rows if D(r["date"]) < as_of]
            left = [r for r in rows if D(r["date"]) >= as_of]
            if ob["kind"] == "loan":
                remaining = rows[len(paid)]["balance_before"] if left else 0
                paid_pct = pct1(ob["principal"] - remaining, ob["principal"])
            else:
                remaining = sum(r["payment"] for r in left)
                paid_pct = pct1(len(paid), len(rows))
            loans.append({"id": ob["id"], "kind": ob["kind"], "name": ob["name"], "lender": ob["lender"],
                          "until": rows[-1]["month"], "paid_pct": paid_pct, "remaining": remaining,
                          "payment": ob["payment"], "payment_day": ob["payment_day"],
                          "next_payment_date": left[0]["date"] if left else None,
                          "payments_made": len(paid), "payments_total": len(rows)})
        else:
            rows = amortization_rows(ob)
            this = [r["amount"] for r in rows if r["month"] == month]
            equipment.append({"id": ob["id"], "name": ob["name"], "cost": ob["cost"], "life_years": ob["life_years"],
                              "monthly": div_round(ob["cost"], ob["life_years"] * 12), "in_service": ob["in_service_date"],
                              "amortization_from": rows[0]["month"], "amortization_to": rows[-1]["month"],
                              "this_month": this[0] if this else 0})
    ch = charges(month)
    return {
        "as_of": as_of.isoformat(), "month": month,
        "debt_total": sum(x["remaining"] for x in loans),
        "monthly_payment": sum(x["payment"] for x in loans if x["remaining"] > 0),
        "amortization_month": sum(e["this_month"] for e in equipment),
        "charges_month": ch,
        "loans": loans, "equipment": equipment,
    }


# ================================================================== the calendar (rules 1-3, 12-21)
def build_days(start, opening, profile, payments, safe):
    """Rules 3, 14, 16: payments first (by amount, descending), income at the end of the day; balance after each payment."""
    days, bal = [], opening
    for i in range(WINDOW_DAYS):
        d = start + timedelta(days=i)
        pays, running = [], bal
        for p in sorted([p for p in payments if p["date"] == d.isoformat()], key=lambda p: (-p["amount"], p["name"])):
            running -= p["amount"]
            pays.append(dict(p, balance_after=running))
        income = profile[d.weekday()]["average"]
        closing = running + income
        lowest_in_day = min([closing] + [p["balance_after"] for p in pays])
        status = "below_zero" if lowest_in_day < 0 else "below_safe" if closing < safe else "ok"
        days.append({"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "opening": bal, "income_forecast": income,
                     "payments": pays, "closing": closing, "status": status, "below_safe": status != "ok"})
        bal = closing
    return days


def episodes(days):
    out, cur = [], None
    for i, d in enumerate(days):
        if d["below_safe"]:
            cur = cur or [i, i]
            cur[1] = i
        elif cur:
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return out


def moved(payments, p, to):
    return [dict(q, date=to.isoformat(), moved_from=q["date"]) if q is p else q for q in payments]


def suggest(start, opening, profile, payments, safe, days, ep, window_end):
    """Rule 20: one payment moved within its allowed deferral; the smallest delay that closes the gap."""
    first, last = ep
    ep_dates = {days[i]["date"] for i in range(first, last + 1)}
    base_min = min(days[i]["closing"] for i in range(first, last + 1))
    candidates = []
    for p in payments:
        if p["max_deferral_days"] <= 0 or D(p["date"]) > D(days[last]["date"]):
            continue
        for k in range(1, p["max_deferral_days"] + 1):
            to = D(p["date"]) + timedelta(days=k)
            if not is_workday(to) or to > window_end:
                continue
            after = build_days(start, opening, profile, moved(payments, p, to), safe)
            ep_min = min(a["closing"] for a in after if a["date"] in ep_dates)
            new_red = [a["date"] for a, b in zip(after, days) if a["below_safe"] and not b["below_safe"]]
            closes = all(not a["below_safe"] for a in after if a["date"] in ep_dates) and not new_red
            candidates.append({"name": p["name"], "source": p["source"], "amount": p["amount"], "from": p["date"],
                               "to": to.isoformat(), "shift_days": k, "closes_gap": closes, "episode_min_after": ep_min,
                               "new_below_safe": new_red, "after": after})
    order = lambda c: (c["shift_days"], c["amount"], c["from"], c["name"])            # noqa: E731
    closing = sorted([c for c in candidates if c["closes_gap"]], key=order)
    if closing:
        best = closing[0]
    else:
        better = [c for c in candidates if c["episode_min_after"] > base_min and not c["new_below_safe"]]
        best = sorted(better, key=lambda c: (-c["episode_min_after"],) + order(c))[0] if better else None
    return best, [{k: v for k, v in c.items() if k != "after"} for c in candidates]


def alert_texts(safe, days, ep, best):
    """Rule 19: warning (below the safe balance) or alert (money runs out: below zero after a payment or in the evening)."""
    first, last = ep
    low_i = min(range(first, last + 1), key=lambda i: (days[i]["closing"], i))
    low = days[low_i]
    run = days[first:last + 1]
    if any(d["status"] == "below_zero" for d in run):
        severity = "alert"
        worst = min(min([d["closing"]] + [p["balance_after"] for p in d["payments"]]) for d in run)
        shortfall = -worst
        title = f"{day_text(D(days[first]['date']))}: не хватит {rub(shortfall)} на платежи"
    else:
        severity = "warning"
        shortfall = safe - low["closing"]
        title = f"{day_text(D(days[first]['date']))}: остаток ниже безопасного запаса на {rub(shortfall)}"
    text = f"Вечером {day_text(D(low['date']))} останется {rub(low['closing'])} при запасе {rub(safe)}."
    sug_text = None
    if best:
        frm, to = D(best["from"]), D(best["to"])
        if best["closes_gap"]:
            sug_text = (f"Перенесите платёж {best['name']} на {rub(best['amount'])} с {day_text(frm)} на {day_text(to)}: "
                        f"разрыва не будет.")
        else:
            sug_text = (f"Перенос платежа {best['name']} на {rub(best['amount'])} с {day_text(frm)} на {day_text(to)} "
                        f"уменьшит разрыв, но не закроет его.")
        text += " " + sug_text
    return low, shortfall, title, text, sug_text, severity


def weeks_breakdown(days, field):
    groups = []
    for d in days:
        dd = D(d["date"])
        if not groups or dd.weekday() == 0:
            groups.append([dd, dd, 0])
        groups[-1][1] = dd
        groups[-1][2] += d[field] if field == "income_forecast" else sum(p["amount"] for p in d["payments"])
    out = []
    for a, b, v in groups:
        label = (f"{a.day}–{b.day} {MONTH_GEN[b.month - 1]}" if a.month == b.month
                 else f"{day_text(a)} – {day_text(b)}") if a != b else day_text(a)
        out.append({"label": label, "value": v})
    return out


def calendar(case, start_offset=0):
    """start_offset = 0: the window starts on as_of (rule 1); 1: on the day after (designer's variant, alternatives)."""
    as_of, safe = D(case["as_of"]), case["safe_balance"]
    start = as_of + timedelta(days=start_offset)
    window_end = start + timedelta(days=WINDOW_DAYS - 1)
    opening = opening_balance(start)
    profile = income_profile(as_of)
    regular, rejected = detect_recurring(as_of)
    recurring = [p for p in recurring_payments(as_of, window_end, regular) if D(p["date"]) >= start]
    payments = recurring + obligation_payments(start, window_end) + [
        {"date": p["date"], "nominal_date": p["date"], "name": p["name"], "amount": p["amount"], "source": "manual",
         "category": None, "planned_id": p["id"], "max_deferral_days": p["max_deferral_days"]}
        for p in DATA["planned_payments"] if start <= D(p["date"]) <= window_end]
    payments.sort(key=lambda p: (p["date"], -p["amount"], p["name"]))
    days = build_days(start, opening["value"], profile["by_weekday"], payments, safe)
    low = min(days, key=lambda d: (d["closing"], d["date"]))                                       # rule 17
    alerts = []
    for ep in episodes(days):
        best, tried = suggest(start, opening["value"], profile["by_weekday"], payments, safe, days, ep, window_end)
        low_day, shortfall, title, text, sug_text, severity = alert_texts(safe, days, ep, best)
        alert = {"date": days[ep[0]]["date"], "end_date": days[ep[1]]["date"], "severity": severity, "icon": "\U0001F4C5",
                 "lowest_date": low_day["date"],
                 "lowest": low_day["closing"], "shortfall": shortfall, "title": title, "text": text,
                 "days_below": [days[i]["date"] for i in range(ep[0], ep[1] + 1)], "candidates": tried,
                 "suggestion": None}
        if best:
            alert["suggestion"] = {k: best[k] for k in ("name", "source", "amount", "from", "to", "shift_days", "closes_gap")}
            alert["suggestion"]["text"] = sug_text
            alert["after"] = [{"date": a["date"], "closing": a["closing"], "below_safe": a["below_safe"]} for a in best["after"]]
            alert["after_lowest"] = min(({"date": a["date"], "closing": a["closing"]} for a in best["after"]),
                                        key=lambda x: (x["closing"], x["date"]))
        alerts.append(alert)
    return {
        "key": case["key"], "as_of": as_of.isoformat(),
        "window": {"from": start.isoformat(), "to": window_end.isoformat(), "days": WINDOW_DAYS},
        "safe_balance": safe, "opening": opening, "income_profile": profile,
        "recurring": regular, "not_recurring": rejected,
        "days": days,
        "summary": {"income": sum(d["income_forecast"] for d in days),
                    "expense": sum(p["amount"] for d in days for p in d["payments"]),
                    "payments_count": sum(len(d["payments"]) for d in days),
                    "lowest": {"date": low["date"], "balance": low["closing"]},
                    "income_by_week": weeks_breakdown(days, "income_forecast"),
                    "expense_by_week": weeks_breakdown(days, "payments")},
        "alerts": alerts,
    }


def alternatives(as_of):
    """Numbers of the variants the owner may choose instead of ours (docs/handoff.md, questions marked "≠ designer")."""
    tomorrow = calendar(DATA["cases"][0], start_offset=1)
    short = {"window": tomorrow["window"], "opening": tomorrow["opening"]["value"],
             "red_days": [d["date"] for d in tomorrow["days"] if d["below_safe"]],
             "closings": [{"date": d["date"], "closing": d["closing"]} for d in tomorrow["days"]],
             "lowest": tomorrow["summary"]["lowest"], "payments_count": tomorrow["summary"]["payments_count"],
             "alerts": [{k: a[k] for k in ("date", "end_date", "severity", "shortfall", "suggestion")} for a in tomorrow["alerts"]],
             # forecast for as_of in our variant, neither in the bank yet nor in the window that starts tomorrow
             "lost_payments": [{"date": p["date"], "name": p["name"], "amount": p["amount"]}
                               for p in calendar(DATA["cases"][0])["days"][0]["payments"]]}
    designer_profile = income_profile_designer(as_of)
    return {"window_from_tomorrow": short,
            "income_profile_90_days_all_in": {"from": (as_of - timedelta(days=89)).isoformat(), "to": as_of.isoformat(),
                                              "by_weekday": designer_profile,
                                              "window_income": sum(designer_profile[(as_of + timedelta(days=i)).weekday()]["average"]
                                                                   for i in range(WINDOW_DAYS))}}


def main():
    cases = {c["key"]: calendar(c) for c in DATA["cases"]}
    as_of = D(DATA["as_of"])
    obligations = obligations_summary(as_of)
    loan = next(o for o in DATA["obligations"] if o["kind"] == "loan")
    expected = {
        "as_of": DATA["as_of"],
        "calendar": cases,
        "obligations": obligations,
        "charges_by_month": {m: charges(m) for m in DATA["charge_months"]},
        "loan_schedule": [r for r in loan_schedule(loan) if r["month"] <= "2026-12"],
        "pnl_obligations_row": {m: charges(m)["total"] for m in DATA["charge_months"]},
        "dashboard_balance_at_as_of": opening_balance(as_of + timedelta(days=1))["value"],
        "alternatives": alternatives(as_of),
    }
    (BASE / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    main_case = cases["main"]
    print("opening", main_case["opening"]["value"], "lowest", main_case["summary"]["lowest"])
    for d in main_case["days"]:
        print(d["date"], d["weekday"], d["opening"], d["income_forecast"], [(p["name"], p["amount"]) for p in d["payments"]],
              d["closing"], "RED" if d["below_safe"] else "")
    for k, c in cases.items():
        for a in c["alerts"]:
            print(k, a["date"], a["end_date"], a["shortfall"], a["suggestion"])
    print("rejected", [(r["name"], r["reason"]) for r in main_case["not_recurring"]])
    print("obligations", {k: v for k, v in obligations.items() if k not in ("loans", "equipment")})


if __name__ == "__main__":
    main()
