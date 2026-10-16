"""Independent computation of expected results for set04 (writes tests/golden/set04/expected.json).

Does NOT import backend/ or gen_set04.py: it reads only set04/data.json and applies the rules written in
set04/README.md. Money: integer kopecks only; percents: integer tenths of a percent (JSON: float with one decimal).
Run: python tests/golden/tools/compute_expected_set04.py
"""
import json
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "set04"
SOURCE_ORDER = ["bank", "vetmanager", "bot", "manual"]
D = date.fromisoformat
DATA = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
RATE_BP = DATA["clinic"]["acquiring_rate_bp"]
CATS = {c["name"]: c for c in DATA["categories"]}
NO_CATEGORY = "Без статьи"
ACQUIRING_LABEL = "Комиссия эквайринга"
OBLIGATIONS_LABEL = "Обязательства и амортизация"
EXPIRING_DAYS = 60
TURNOVER_WINDOW = 90
SHORT_PERIOD_DAYS = 7
REASONS = [("expired", "Истёк срок годности"), ("damaged", "Брак и бой"), ("other", "Другое")]
OPEN_CASES = [("2026-09", "2026-09-15"), ("2026-09", "2026-09-05")]   # running month; the second one is shorter than 7 days (short_period)
BUCKET_KEYS = {"60-89": "60_89", "90-179": "90_179", "180+": "180_plus"}   # API keys of the idle intervals
IDLE_PAGES = [("all", 10), ("all", 2), ("60_89", 10), ("90_179", 10), ("180_plus", 10), ("180_plus", 1)]   # (bucket, limit) of /stock/idle
MONTH_GENITIVE = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
MEMO_KEYS = {"writeoff"}                    # shown in the norm report, not a line of the P&L (see README, rule 7)


def div_round(n, d):
    if d < 0:
        n, d = -n, -d
    sign = -1 if n < 0 else 1
    return sign * ((abs(n) * 2 + d) // (d * 2))


def pct(part, whole):
    """percent with one decimal (half away from zero) computed on integers."""
    return div_round(part * 1000, whole) / 10


def ordered(sources):
    return [s for s in SOURCE_ORDER if s in sources]


def month_end(month):
    y, m = map(int, month.split("-"))
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return nxt - timedelta(days=1)


def counted(day, month, as_of):
    """The ISO date string belongs to the month and (for a running month) is not after as_of."""
    return day[:7] == month and (as_of is None or D(day) <= as_of)


def desc_sorted(pairs):
    return sorted(pairs, key=lambda p: (-p[1], p[0]))


def plural_days(n):
    """'1 день', '2 дня', '5 дней', '11 дней', '21 день'."""
    if n % 100 in range(11, 15):
        return f"{n} дней"
    return f"{n} " + ("день" if n % 10 == 1 else "дня" if n % 10 in (2, 3, 4) else "дней")


def open_headline(as_of):
    """Text the owner decided for a running month (design/screens/norm.md, 'Месяц идёт'): shares are not rated."""
    return (f"К {as_of.day} {MONTH_GENITIVE[as_of.month - 1]} доли статей посчитаны от выручки за {plural_days(as_of.day)}. "
            "Сравним с нормой, когда месяц закончится.")


def fig(value, breakdown, source):
    return {"value": value, "breakdown": dict(breakdown), "source": source}


# ---------------------------------------------------------------- month facts
def month_facts(month, as_of=None):
    revenue = {"service": 0, "good": 0}
    for s in DATA["sales"]:
        if s["status"] == "exec" and counted(s["date"], month, as_of):
            for ln in s["lines"]:
                revenue[ln["kind"]] += ln["amount"]
    card_by_day = {}
    for p in DATA["payments"]:
        if p["method"] == "card" and counted(p["date"], month, as_of):
            card_by_day[p["date"]] = card_by_day.get(p["date"], 0) + p["amount"]
    commission = sum(div_round(v * RATE_BP, 10_000) for v in card_by_day.values())
    by_cat, srcs, unclassified = {}, {}, []
    for t in DATA["transactions"]:
        if t["kind"] != "out" or t["status"] == "duplicate" or not counted(t["date"], month, as_of):
            continue
        name = t["category"] if t["category"] and t["status"] != "check" else NO_CATEGORY
        by_cat[name] = by_cat.get(name, 0) - t["amount"]
        srcs.setdefault(name, set()).add(t["source"])
        if name == NO_CATEGORY:
            unclassified.append(-t["amount"])
    charges = [c for c in DATA["obligation_charges"] if c["month"] == month]   # accrued for the whole month
    return revenue, commission, by_cat, srcs, unclassified, charges


def cat_type(name):
    return CATS[name]["type"] if name in CATS else "fixed"      # uncategorised operations are fixed costs


def first_month():
    days = [s["date"] for s in DATA["sales"]] + [t["date"] for t in DATA["transactions"]]
    return min(days)[:7]


def period(month, as_of):
    open_ = as_of is not None and as_of < month_end(month)
    return {"month": month, "status": "open" if open_ else "closed", "to": as_of.isoformat() if open_ else None,
            "first_month": first_month()}


def partial_reasons(month, as_of, revenue, kind):
    last = as_of if as_of is not None else month_end(month)
    out = []
    if revenue == 0:
        out.append("no_vetmanager")
    covered = D(DATA["bank_covered_to"]) if DATA.get("bank_covered_to") else None
    if covered is None or covered < min(last, month_end(month)):
        out.append("bank_gap")
    if as_of is not None and as_of < month_end(month) and (as_of - D(month + "-01")).days + 1 < SHORT_PERIOD_DAYS:
        out.append("short_period")
    if kind == "pnl" and not DATA["obligation_charges"]:
        out.append("no_obligations")
    if kind == "norm" and not DATA["benchmarks"]:
        out.append("no_benchmark")
    return out


def pnl(month, as_of=None):
    revenue, commission, by_cat, srcs, unclassified, charges = month_facts(month, as_of)
    rev = revenue["service"] + revenue["good"]
    variable = {n: v for n, v in by_cat.items() if cat_type(n) == "variable"}
    fixed = {n: v for n, v in by_cat.items() if cat_type(n) == "fixed"}
    tax = {n: v for n, v in by_cat.items() if cat_type(n) == "tax"}
    fixed_payroll = {n: v for n, v in fixed.items() if n in CATS and CATS[n]["payroll"]}
    fixed_other = {n: v for n, v in fixed.items() if n not in fixed_payroll}
    var_rows = list(variable.items()) + ([(ACQUIRING_LABEL, commission)] if commission else [])
    var_total, fixed_total, tax_total = sum(v for _, v in var_rows), sum(fixed.values()), sum(tax.values())
    pay_total, other_total = sum(fixed_payroll.values()), sum(fixed_other.values())
    obl_total = sum(c["amount"] for c in charges)
    marginal = rev - var_total
    net = marginal - fixed_total - tax_total - obl_total

    def src(names):
        out = set()
        for n in names:
            out |= srcs.get(n, set())
        return out

    var_src = src(variable) | ({"vetmanager"} if commission else set())
    rev_src = {"vetmanager"} if rev else set()
    all_src = rev_src | var_src | src(fixed) | src(tax) | ({"manual"} if charges else set())
    rows = [
        ("revenue", "Выручка", "revenue", rev, [("Услуги", revenue["service"]), ("Товары", revenue["good"])], rev_src or {"manual"}),
        ("variable", "Переменные расходы", "expense", var_total, desc_sorted(var_rows), var_src or {"manual"}),
        ("marginal_profit", "Маржинальная прибыль", "subtotal", marginal, [("Выручка", rev), ("Переменные расходы", -var_total)],
         rev_src | var_src or {"manual"}),
        ("fixed", "Постоянные расходы", "expense", fixed_total, [("ФОТ (оклады)", pay_total), ("Аренда и прочие постоянные", other_total)],
         src(fixed) or {"manual"}),
        ("taxes", "Налоги и взносы", "expense", tax_total, desc_sorted(tax.items()), src(tax) or {"manual"}),
        ("obligations", OBLIGATIONS_LABEL, "expense", obl_total, desc_sorted([(c["name"], c["amount"]) for c in charges]), {"manual"}),
        ("net_profit", "Чистая прибыль", "total", net,
         [("Выручка", rev), ("Переменные расходы", -var_total), ("Постоянные расходы", -fixed_total), ("Налоги и взносы", -tax_total),
          (OBLIGATIONS_LABEL, -obl_total)], all_src or {"manual"}),
    ]
    children = [
        ("fixed_payroll", "ФОТ (оклады)", pay_total, desc_sorted(fixed_payroll.items()), src(fixed_payroll)),
        ("fixed_other", "Аренда и прочие постоянные", other_total, desc_sorted(fixed_other.items()), src(fixed_other)),
    ]
    out_rows = []
    for key, label, kind, value, bd, sources in rows:
        row = {"key": key, "label": label, "kind": kind, "amount": fig(value, bd, ordered(sources))}
        if rev:
            row["share_pct"] = {"value": pct(value, rev)}
        if key == "fixed":
            row["children"] = []
            for ckey, clabel, cvalue, cbd, csrc in children:
                child = {"key": ckey, "label": clabel, "kind": "child", "amount": fig(cvalue, cbd, ordered(csrc) or ["manual"])}
                if rev:
                    child["share_pct"] = {"value": pct(cvalue, rev)}
                row["children"].append(child)
        out_rows.append(row)
    empty = rev == 0 and var_total + fixed_total + tax_total == 0 and not charges
    reasons = [] if empty else partial_reasons(month, as_of, rev, "pnl")
    return {"month": month, "as_of": as_of.isoformat() if as_of else None, "period": period(month, as_of),
            "status": "empty" if empty else "partial" if reasons else "ok", "partial_reasons": reasons, "rows": out_rows,
            "revenue": rev, "variable": var_total, "marginal": marginal, "fixed": fixed_total, "tax": tax_total,
            "obligations": obl_total, "net_profit": net, "commission": commission,
            "unclassified": {"count": len(unclassified), "amount": sum(unclassified)},
            "by_category": dict(sorted(by_cat.items())),
            "headline_numbers": {"net_profit": net, "share_pct": pct(net, rev) if rev else None, "norm_min": 12.0, "norm_max": 20.0}}


def direction_view(month, as_of=None):
    revenue, commission, by_cat, srcs, _, charges = month_facts(month, as_of)
    p = pnl(month, as_of)
    rev = p["revenue"]
    directions = []
    for key, label, kind in (("services", "Услуги", "service"), ("goods", "Товары", "good")):
        r = revenue[kind]
        costs = [(n, v) for n, v in by_cat.items() if n in CATS and CATS[n]["direction"] == key and CATS[n]["type"] == "variable"]
        cost = sum(v for _, v in costs)
        item = {"direction": key, "label": label, "revenue": fig(r, [(label, r)], ["vetmanager"] if r else ["manual"]),
                "direct_costs": cost, "direct_costs_breakdown": dict(desc_sorted(costs)), "margin": r - cost}
        if rev:
            item["revenue_share_pct"] = pct(r, rev)
        if r:
            item["margin_pct"] = pct(r - cost, r)
        directions.append(item)
    common = [(n, v) for n, v in by_cat.items() if cat_type(n) == "variable" and not (n in CATS and CATS[n]["direction"])]
    common += [(ACQUIRING_LABEL, commission)] if commission else []
    return {"month": month, "directions": directions,
            "common_variable": {"value": sum(v for _, v in common), "breakdown": dict(desc_sorted(common))},
            "variable": p["variable"], "marginal": p["marginal"], "revenue": rev}


# ---------------------------------------------------------------- norm
def norm(month, as_of=None):
    p = pnl(month, as_of)
    rev = p["revenue"]
    reasons = [] if rev == 0 else partial_reasons(month, as_of, rev, "norm")
    base = {"month": month, "as_of": as_of.isoformat() if as_of else None, "period": p["period"],
            "status": "empty" if rev == 0 else "partial" if reasons else "ok", "partial_reasons": reasons}
    if p["period"]["status"] == "open":
        # owner decision 2026-10-14: a running month is NOT rated. The statuses, tones and deviations below are what the month
        # would show if it were rated at this point; the API gives none of them (keys absent). Shares (`actual_pct`) and the norm
        # bounds are real.
        base["rated"] = False
        base["headline_open"] = open_headline(as_of)
    else:
        base["rated"] = True
    if not rev:
        return {**base, "items": []}
    by_cat = p["by_category"]
    expired = sum(w["amount"] for w in DATA["stock"]["writeoffs"] if counted(w["date"], month, as_of) and w["reason"] == "expired")
    items, grouped = [], 0
    for b in sorted(DATA["benchmarks"], key=lambda b: b["sort"]):
        key = b["key"]
        if key == "net_profit":
            continue
        cats = [c for c in DATA["categories"] if c["norm_key"] == key]
        if key == "acquiring":
            amount, parts = p["commission"], [(ACQUIRING_LABEL, p["commission"])]
        elif key == "writeoff":
            amount, parts = expired, [("Списано по сроку годности", expired)]
        else:
            parts = desc_sorted([(c["name"], by_cat.get(c["name"], 0)) for c in cats])   # biggest first, ties by name
            amount = sum(v for _, v in parts)
        if key not in MEMO_KEYS:
            grouped += amount
        items.append(norm_item(b, cats, amount, parts, rev, memo=key in MEMO_KEYS))
    # "other": everything the P&L spends that has no norm (groups + other + net profit = revenue)
    other_parts = [(n, v) for n, v in by_cat.items()
                   if cat_type(n) in ("variable", "fixed", "tax") and not (n in CATS and CATS[n]["norm_key"])]
    if p["obligations"]:
        other_parts.append((OBLIGATIONS_LABEL, p["obligations"]))
    other_amount = sum(v for _, v in other_parts)
    assert grouped + other_amount + p["net_profit"] == rev, "norm shares must add up to the revenue"
    items.append({"key": "other", "label": "Остальные статьи", "kind": "other", "memo": False, "status": "no_norm", "tone": "neutral",
                  "norm": None, "amount": other_amount, "amount_breakdown": dict(desc_sorted(other_parts)),
                  "actual_pct": pct(other_amount, rev)})
    net_b = next(b for b in DATA["benchmarks"] if b["key"] == "net_profit")
    items.append(norm_item(net_b, [], p["net_profit"], [("Чистая прибыль", p["net_profit"])], rev, memo=False))
    above = [(i["label"], i["deviation_rub"]) for i in items if i["status"] == "above" and i["kind"] == "expense"]
    return {**base, "revenue": rev, "items": items,
            "headline_numbers": {"above": dict(above), "above_total": sum(v for _, v in above)}}


def norm_item(b, cats, amount, parts, rev, memo):
    override = next((c for c in cats if c["norm_min_pct"] is not None and c["norm_max_pct"] is not None), None)
    lo, hi, source = (override["norm_min_pct"], override["norm_max_pct"], "clinic") if override else (b["min_pct"], b["max_pct"], "industry")
    lo_t, hi_t = round(lo * 10), round(hi * 10)
    if amount * 1000 > hi_t * rev:
        status, bound_t = "above", hi_t
    elif amount * 1000 < lo_t * rev:
        status, bound_t = "below", lo_t
    else:
        status, bound_t = "ok", None
    if bound_t is None:
        dev_rub, dev_pp, bound_rub = 0, 0.0, None
    else:
        bound_rub = div_round(rev * bound_t, 1000)
        dev_rub = amount - bound_rub
        dev_pp = div_round(amount * 1000 - bound_t * rev, rev) / 10      # percentage points on unrounded values
    profit = b["kind"] == "profit"
    tone = {"ok": "good", "above": "good" if profit else "bad", "below": "bad" if profit else "warn"}[status]
    return {"key": b["key"], "label": b["label"], "kind": b["kind"], "memo": memo, "status": status, "tone": tone,
            "norm": {"min_pct": lo, "max_pct": hi, "source": source}, "amount": amount, "amount_breakdown": dict(parts),
            "actual_pct": pct(amount, rev), "bound": bound_rub, "deviation_rub": dev_rub, "deviation_pp": dev_pp}


# ---------------------------------------------------------------- stock
def stock():
    st = DATA["stock"]
    as_of = D(st["as_of"])
    month = st["as_of"][:7]
    by_item = {i["id"]: {"item": i["name"], "last": D(i["last_movement"]), "qty": 0, "amount": 0} for i in st["items"]}
    expiring, expired = [], []
    for b in st["batches"]:
        if b["qty"] <= 0:
            continue
        row = by_item[b["item_id"]]
        amount = b["qty"] * b["unit_cost"]
        row["qty"] += b["qty"]
        row["amount"] += amount
        if b["expires_on"]:
            left = (D(b["expires_on"]) - as_of).days
            rec = {"item": row["item"], "expires_on": b["expires_on"], "days_left": left, "qty": b["qty"], "amount": amount}
            if 0 <= left <= EXPIRING_DAYS:
                expiring.append(rec)
            elif left < 0:
                expired.append(rec)
    expiring.sort(key=lambda r: (r["expires_on"], r["item"]))
    expired.sort(key=lambda r: (r["expires_on"], r["item"]))
    on_hand = [r for r in by_item.values() if r["qty"] > 0]
    buckets = {"60-89": 0, "90-179": 0, "180+": 0}
    frozen_items = []
    for r in on_hand:
        idle = (as_of - r["last"]).days
        if idle >= 180:
            b = "180+"
        elif idle >= 90:
            b = "90-179"
        elif idle >= 60:
            b = "60-89"
        else:
            continue
        buckets[b] += r["amount"]
        frozen_items.append({"item": r["item"], "qty": r["qty"], "amount": r["amount"], "idle_days": idle, "bucket": b})
    frozen_items.sort(key=lambda r: (-r["amount"], r["item"]))
    stock_total = sum(r["amount"] for r in on_hand)
    frozen_total = sum(buckets.values())

    def by_label(rows):
        agg = {}
        for r in rows:
            agg[r["item"]] = agg.get(r["item"], 0) + r["amount"]
        return desc_sorted(agg.items())

    bucket_positions = {k: 0 for k in BUCKET_KEYS.values()}
    bucket_amounts = {k: 0 for k in BUCKET_KEYS.values()}
    idle_list = []
    for r in on_hand:
        days = (as_of - r["last"]).days
        if days < 60:
            continue
        key = BUCKET_KEYS["180+" if days >= 180 else "90-179" if days >= 90 else "60-89"]
        bucket_positions[key] += 1
        bucket_amounts[key] += r["amount"]
        idle_list.append({"item": r["item"], "last_movement_on": r["last"].isoformat(), "idle_days": days, "bucket": key,
                          "qty": r["qty"], "amount": r["amount"]})
    idle_list.sort(key=lambda r: (-r["amount"], r["item"]))
    idle_pages = []
    for bucket, limit in IDLE_PAGES:
        rows = [r for r in idle_list if bucket == "all" or r["bucket"] == bucket]
        chunks = [rows[i:i + limit] for i in range(0, len(rows), limit)] or [[]]
        idle_pages.append({"bucket": bucket, "limit": limit, "total": len(rows),
                           "pages": [{"items": c, "has_next": n < len(chunks) - 1} for n, c in enumerate(chunks)]})
    wo = [w for w in st["writeoffs"] if w["date"][:7] == month and D(w["date"]) <= as_of]
    wo_items = sorted(({"item": w["item"], "date": w["date"], "qty": w["qty"], "reason": w["reason"], "amount": w["amount"]} for w in wo),
                      key=lambda w: (-w["amount"], w["item"], w["date"]))
    # norm of the write-off = the upper bound of the benchmark `writeoff` (tenths of a percent) of the revenue of the same month
    bench = next(b for b in DATA["benchmarks"] if b["key"] == "writeoff")
    bound_tenths = round(bench["max_pct"] * 10)
    month_revenue = pnl(month)["revenue"]
    expired_in_month = sum(w["amount"] for w in wo if w["reason"] == "expired")
    wo_norm = div_round(month_revenue * bound_tenths, 1000)
    wo_by_reason = [(label, sum(w["amount"] for w in wo if w["reason"] == key)) for key, label in REASONS]
    window_from = as_of - timedelta(days=TURNOVER_WINDOW - 1)
    consumption = sum(c["amount"] for c in st["consumption"] if window_from <= D(c["date"]) <= as_of)
    return {
        "as_of": st["as_of"],
        "stock_value": {"value": stock_total, "positions": len(on_hand)},
        "frozen": {"value": frozen_total, "breakdown": {"Без движения 60–89 дней": buckets["60-89"],
                                                       "Без движения 90–179 дней": buckets["90-179"],
                                                       "Без движения от 180 дней": buckets["180+"]}},
        "frozen_items": frozen_items,
        "expiring_60d": {"value": sum(r["amount"] for r in expiring), "breakdown": dict(by_label(expiring)), "rows": expiring},
        "expired_on_hand": {"value": sum(r["amount"] for r in expired), "breakdown": dict(by_label(expired)), "rows": expired},
        "written_off_month": {"value": sum(w["amount"] for w in wo), "breakdown": {l: v for l, v in wo_by_reason if v}},
        "written_off_items": wo_items,
        "written_off_norm": {"value": wo_norm, "norm_pct": bound_tenths / 10, "month": month, "revenue": month_revenue,
                             "expired": expired_in_month, "over_norm": max(0, expired_in_month - wo_norm)},
        "frozen_positions": {"value": len(idle_list), "breakdown_values": list(bucket_positions.values())},
        "idle_buckets": [{"key": k, "amount": bucket_amounts[k], "positions": bucket_positions[k]} for k in BUCKET_KEYS.values()],
        "idle_pages": idle_pages,
        "turnover_days": {"value": div_round(stock_total * TURNOVER_WINDOW, consumption),
                          "breakdown_values": [stock_total, consumption, TURNOVER_WINDOW]},
        "norm_turnover_days": 45,
    }


def alternatives():
    """Numbers of other treatments, kept for the owner's decisions (README, questions). Not asserted against the engine."""
    out = {"dashboard_profit": {}, "pnl_net_profit": {}, "pnl_net_profit_with_expired_writeoffs": {}}
    for m in DATA["months"]:
        p = pnl(m)
        cash_out = sum(-t["amount"] for t in DATA["transactions"]
                       if t["kind"] == "out" and t["status"] != "duplicate" and t["date"][:7] == m)
        out["dashboard_profit"][m] = p["revenue"] - cash_out  # stage-2 rule: invoices revenue minus all money out
        out["pnl_net_profit"][m] = p["net_profit"]
        expired = sum(w["amount"] for w in DATA["stock"]["writeoffs"] if w["date"][:7] == m and w["reason"] == "expired")
        out["pnl_net_profit_with_expired_writeoffs"][m] = p["net_profit"] - expired   # prototype v7 shows write-off as a P&L line
    bulk = next(t for t in DATA["transactions"] if "впрок" in t["description"])
    out["aug_net_profit_without_prepaid_purchase"] = pnl("2026-08")["net_profit"] + (-bulk["amount"])
    out["aug_prepaid_purchase"] = -bulk["amount"]
    return out


def main():
    months = DATA["months"] + ["2026-06"]  # 2026-06: a month before the first data (empty report)
    open_keys = [f"{m}@{a}" for m, a in OPEN_CASES]
    result = {
        "months": months,
        "open_cases": [{"key": k, "month": m, "as_of": a} for k, (m, a) in zip(open_keys, OPEN_CASES)],
        "pnl": {**{m: pnl(m) for m in months}, **{k: pnl(m, D(a)) for k, (m, a) in zip(open_keys, OPEN_CASES)}},
        "direction": {**{m: direction_view(m) for m in months}, **{k: direction_view(m, D(a)) for k, (m, a) in zip(open_keys, OPEN_CASES)}},
        "norm": {**{m: norm(m) for m in months}, **{k: norm(m, D(a)) for k, (m, a) in zip(open_keys, OPEN_CASES)}},
        "stock": stock(),
        "alternatives": alternatives(),
    }
    (BASE / "expected.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for m in months + open_keys:
        p = result["pnl"][m]
        print(m, "rev", p["revenue"], "var", p["variable"], "fix", p["fixed"], "tax", p["tax"], "obl", p["obligations"], "net", p["net_profit"],
              p["headline_numbers"]["share_pct"], p["status"], p["partial_reasons"])


if __name__ == "__main__":
    main()
