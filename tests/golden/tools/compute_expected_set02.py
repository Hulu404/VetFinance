"""Independent computation of expected results for set02 (writes tests/golden/set02/expected.json).

Does NOT import backend/ or gen_set02.py. It re-parses the generated files (1C text in windows-1251, Vetmanager JSON)
with its own small parser, simulates the import pipeline by the rules written in set02/README.md, and cross-checks the
outcome against the hand-written labels in truth.json. A mismatch stops the script (exit 1).

Money: integer kopecks only (Decimal for parsing).
Run: python tests/golden/tools/compute_expected_set02.py
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "set02"
WINDOW_DAYS = 3
MONTH = "2026-09"
AS_OF = "2026-09-30"


def kop(text):
    return int((Decimal(text.replace(",", ".")) * 100).to_integral_value())


def pdate(text):
    return datetime.strptime(text, "%d.%m.%Y").date() if text else None


# ---------------------------------------------------------------- 1C parser (own)
def parse_1c(raw):
    text = raw.decode("cp1251")
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    assert lines[0].strip() == "1CClientBankExchange", "not a 1C file"
    sections, docs, cur, kind = [], [], None, None
    for ln in lines[1:]:
        if ln.startswith("СекцияРасчСчет"):
            cur, kind = {}, "sec"
        elif ln.startswith("КонецРасчСчет"):
            sections.append(cur); cur = None
        elif ln.startswith("СекцияДокумент="):
            cur, kind = {"type": ln.split("=", 1)[1]}, "doc"
        elif ln.startswith("КонецДокумента"):
            docs.append(cur); cur = None
        elif cur is not None and "=" in ln:
            k, v = ln.split("=", 1)
            cur[k] = v
    return sections, docs


def party(doc, prefix):
    inn = doc.get(prefix + "ИНН", "")
    name = doc.get(prefix + "1") or doc.get(prefix, "")
    if not inn:
        m = re.match(r"ИНН (\d+) ", doc.get(prefix, ""))
        inn = m.group(1) if m else ""
    return inn, name


def legs_of(doc, file_accounts, own_accounts):
    pa, ra = doc["ПлательщикСчет"], doc["ПолучательСчет"]
    amount = kop(doc["Сумма"])
    pinn, _ = party(doc, "Плательщик")
    rinn, _ = party(doc, "Получатель")
    transfer = pa in own_accounts and ra in own_accounts
    legs = []
    if pa in file_accounts:
        legs.append(dict(account=pa, amount=-amount, date=pdate(doc["ДатаСписано"]).isoformat(),
                         cp_inn="" if transfer else rinn, kind="transfer" if transfer else "out"))
    if ra in file_accounts:
        legs.append(dict(account=ra, amount=amount, date=pdate(doc["ДатаПоступило"]).isoformat(),
                         cp_inn="" if transfer else pinn, kind="transfer" if transfer else "in"))
    for lg in legs:
        lg["number"] = doc["Номер"]
        lg["purpose"] = doc["НазначениеПлатежа"]
        lg["key"] = f'{lg["account"]}|{doc["Номер"]}|{lg["date"]}|{lg["amount"]}|{lg["cp_inn"]}'
        lg["external_id"] = "1c:" + sha256(lg["key"].encode()).hexdigest()[:32]
    return legs


# ---------------------------------------------------------------- pipeline simulation
class State:
    def __init__(self, initial, truth):
        self.truth = truth
        self.acc_by_number = {a["number"]: a["key"] for a in initial["accounts"] if a["number"]}
        self.own = set(self.acc_by_number)
        self.rules = list(initial["starter_rules"])
        self.rows = []
        self.num2label = {v: k for k, v in truth["numbers"].items()}

    def label_of(self, leg):
        lab = self.num2label[leg["number"]]
        return f'{lab}/{leg["account"][-3:]}' if leg["kind"] == "transfer" else lab

    def classify(self, leg):
        if leg["kind"] == "transfer":
            return None
        for r in self.rules:
            if r["direction"] and r["direction"] != leg["kind"]:
                continue
            if r["match"] == "inn" and leg["cp_inn"] == r["value"]:
                return r["category"]
            if r["match"] == "text" and r["value"] in leg["purpose"].casefold():
                return r["category"]
        return None

    def find_original(self, new_row, ordered_free):
        best = None
        for r in self.rows:
            if (r["account"] == new_row["account"] and r["amount"] == new_row["amount"]
                    and r["kind"] != "transfer" and r["status"] != "duplicate" and r["source"] != new_row["source"]
                    and not r.get("paired") and abs((date.fromisoformat(r["date"]) - date.fromisoformat(new_row["date"])).days) <= WINDOW_DAYS):
                dist = abs((date.fromisoformat(r["date"]) - date.fromisoformat(new_row["date"])).days)
                if best is None or dist < best[0]:
                    best = (dist, r)
        return best[1] if best else None

    def import_file(self, raw):
        sections, docs = parse_1c(raw)
        file_accounts = {s["РасчСчет"] for s in sections}
        res = dict(parsed_documents=len(docs), skipped_in_file=0, skipped_existing=0, created=0, duplicates=0,
                   check=0, rule_applied=0, transfers=0, created_labels=[])
        seen, new = set(), []
        for doc in docs:
            for leg in legs_of(doc, file_accounts, self.own):
                if leg["key"] in seen:
                    res["skipped_in_file"] += 1
                    continue
                seen.add(leg["key"])
                new.append(leg)
        res["unique_legs"] = len(new)
        existing = {r["external_id"] for r in self.rows if r.get("external_id")}
        fresh = []
        for leg in new:
            if leg["external_id"] in existing:
                res["skipped_existing"] += 1
            else:
                fresh.append(leg)
        fresh.sort(key=lambda l: (l["date"], l["number"]))
        for leg in fresh:
            row = dict(label=self.label_of(leg), account=leg["account"], date=leg["date"], amount=leg["amount"],
                       source="bank", kind=leg["kind"], external_id=leg["external_id"], status="ok", dup_of=None,
                       category=self.classify(leg), cp_inn=leg["cp_inn"], purpose=leg["purpose"])
            if row["kind"] == "transfer":
                res["transfers"] += 1
            else:
                if row["category"]:
                    res["rule_applied"] += 1
                else:
                    row["status"] = "check"
                orig = self.find_original(row, None)
                if orig:
                    orig["paired"] = True
                    row["status"], row["dup_of"] = "duplicate", orig["label"]
            self.rows.append(row)
            res["created"] += 1
            res["created_labels"].append(row["label"])
        res["duplicates"] = sum(1 for l in res["created_labels"] if self.row(l)["status"] == "duplicate")
        res["check"] = sum(1 for l in res["created_labels"] if self.row(l)["status"] == "check")
        return res

    def row(self, label):
        return next(r for r in self.rows if r["label"] == label)

    def add_manual(self, spec):
        row = dict(label=spec["label"], account=self.acc_number(spec["account"]), date=spec["date"],
                   amount=spec["amount"], source=spec["source"], kind="in" if spec["amount"] > 0 else "out",
                   external_id=None, status="ok", dup_of=None, category=spec["category"], cp_inn="")
        # a new manual/bot row is matched against bank rows that are not paired yet
        orig = None
        for r in self.rows:
            if (r["source"] == "bank" and r["account"] == row["account"] and r["amount"] == row["amount"]
                    and r["status"] != "duplicate" and not r.get("paired")
                    and abs((date.fromisoformat(r["date"]) - date.fromisoformat(row["date"])).days) <= WINDOW_DAYS):
                orig = r
                break
        if orig:
            orig["paired"] = True
            row["status"], row["dup_of"] = "duplicate", orig["label"]
        self.rows.append(row)
        return row

    def acc_number(self, key):
        for n, k in self.acc_by_number.items():
            if k == key:
                return n
        return key  # cash

    def summary(self, month):
        inc, exp = {}, {}
        for r in self.rows:
            if r["status"] == "duplicate" or r["kind"] == "transfer" or not r["date"].startswith(month):
                continue
            cat = r["category"] if r["status"] == "ok" or r["category"] else "Без статьи"
            if r["status"] == "check":
                cat = "Без статьи"
            if r["amount"] > 0:
                inc[cat] = inc.get(cat, 0) + r["amount"]
            else:
                exp[cat] = exp.get(cat, 0) + (-r["amount"])
        i, e = sum(inc.values()), sum(exp.values())
        return dict(income=i, expense=e, balance=i - e, income_breakdown=dict(sorted(inc.items())),
                    expense_breakdown=dict(sorted(exp.items())))

    def snapshot(self):
        return {r["label"]: dict(status=r["status"], category=r["category"], dup_of=r["dup_of"]) for r in self.rows}


# ---------------------------------------------------------------- Vetmanager (own)
def vm_load(name):
    return json.loads((BASE / "vetmanager" / f"{name}.json").read_text(encoding="utf-8"))["data"][name]


def vm_expected():
    dec = Decimal
    users = sorted(vm_load("user"), key=lambda u: int(u["id"]))
    code = {u["id"]: f"D{i + 1}" for i, u in enumerate(users)}
    goods = {g["id"]: g for g in vm_load("good")}
    cassa = {c["id"]: c["type"] for c in vm_load("cassa")}
    invoices = vm_load("invoice")
    lines = vm_load("invoiceDocument")
    per_inv = {}
    for ln in lines:
        amount = int((dec(ln["quantity"]) * dec(ln["price"]) * 100).to_integral_value())
        per_inv.setdefault(ln["invoice_id"], []).append((goods[ln["good_id"]]["is_service"], amount))
    out = dict(visits=0, visits_by_doctor={}, invoices_exec=0, invoices_draft=0, invoices_deleted=0, sales_exec=0,
               drafts_total=0, lines_service=0, lines_good=0, payments={})
    for a in vm_load("admission"):
        if a["status"] != "delete":
            out["visits"] += 1
            d = code[a["user_id"]]
            out["visits_by_doctor"][d] = out["visits_by_doctor"].get(d, 0) + 1
    for inv in invoices:
        amt = int((dec(inv["amount"]) * 100).to_integral_value())
        assert sum(a for _, a in per_inv[inv["id"]]) == amt, "lines do not sum to invoice"
        if inv["status"] == "exec":
            out["invoices_exec"] += 1
            out["sales_exec"] += amt
            for is_svc, a in per_inv[inv["id"]]:
                out["lines_service" if is_svc == "1" else "lines_good"] += a
        elif inv["status"] == "save":
            out["invoices_draft"] += 1
            out["drafts_total"] += amt
        else:
            out["invoices_deleted"] += 1
    cash_rows, card = [], []
    for p in vm_load("payment"):
        amt = int((dec(p["amount"]) * 100).to_integral_value())
        method = cassa[p["cassa_id"]]
        o = out["payments"].setdefault(method, dict(count=0, total=0))
        o["count"] += 1
        o["total"] += amt
        d = p["create_date"][:10]
        (cash_rows if method == "cash" else card).append(dict(external_id=f'vetmanager:payment:{p["id"]}', date=d, amount=amt))
    assert out["lines_service"] + out["lines_good"] == out["sales_exec"]
    return out, cash_rows, card


def next_business_day(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def add_business_days(d, n):
    for _ in range(n):
        d = next_business_day(d)
    return d


def business_days_between(a, b):
    """Business days after `a` up to and including `b`."""
    n, d = 0, a
    while d < b:
        d = next_business_day(d)
        n += 1
    return n


def half_up(num, den):
    return (2 * num + den) // (2 * den)


def acquiring(card, rows, params, as_of, bank_covered_to):
    """Day-by-day reconciliation. Algorithm (see set02/README.md):
    for the earliest unmatched sale day i, look at credits in window [next business day, i + max_delay business days]:
    1) try runs of 1..max_group_days consecutive unmatched sale days whose summed expected net equals a credit within tolerance;
    2) otherwise the nearest credit in the window whose amount is within mismatch_search_pct of the expected net is a mismatch;
    3) otherwise no credit: `waiting` while as_of <= deadline (expected_by); after that `no_statement` if the statement
       covers dates only up to before the deadline (bank_covered_to < expected_by), else `mismatch` with credited 0."""
    rate = params["rate_bp"]
    gross = {}
    for p in card:
        gross[date.fromisoformat(p["date"])] = gross.get(date.fromisoformat(p["date"]), 0) + p["amount"]
    days = sorted(gross)
    net = {d: gross[d] - half_up(gross[d] * rate, 10000) for d in days}
    credits = sorted((r for r in rows if r["category"] == "Выручка (эквайринг)" and r["kind"] == "in"),
                     key=lambda r: (r["date"], r["label"]))
    used, matched, i = set(), {}, 0
    as_of_d = date.fromisoformat(as_of)
    out = []
    while i < len(days):
        d0 = days[i]
        lo, hi = next_business_day(d0), add_business_days(d0, params["max_delay_business_days"])
        window = [c for c in credits if c["label"] not in used and lo <= date.fromisoformat(c["date"]) <= hi]
        hit = None
        for length in range(1, params["max_group_days"] + 1):
            grp = days[i:i + length]
            if len(grp) < length:
                break
            want = sum(net[x] for x in grp)
            for c in window:
                if abs(c["amount"] - want) <= params["tolerance_kop"]:
                    hit = (grp, c, "matched")
                    break
            if hit:
                break
        if not hit:
            near = [c for c in window if abs(c["amount"] - net[d0]) * 100 <= net[d0] * params["mismatch_search_pct"]]
            if near:
                hit = ([d0], near[0], "mismatch")
        if hit:
            grp, c, status = hit
            used.add(c["label"])
            g_gross = sum(gross[x] for x in grp)
            g_exp = sum(net[x] for x in grp)
            impl = g_gross - c["amount"]
            for x in grp:
                out.append(dict(sale_date=x.isoformat(), card_total=gross[x], expected_commission=gross[x] - net[x],
                                expected_credit=net[x], group_days=[y.isoformat() for y in grp], credit_id=c["label"],
                                credit_date=c["date"], credit_amount=c["amount"], group_gross=g_gross,
                                group_expected_credit=g_exp, diff=c["amount"] - g_exp, actual_commission=impl,
                                actual_rate_bp=half_up(impl * 10000, g_gross),
                                delay_business_days=business_days_between(grp[-1], date.fromisoformat(c["date"])),
                                expected_by=add_business_days(x, params["max_delay_business_days"]).isoformat(),
                                status=status))
            i += len(grp)
        else:
            if as_of_d <= hi:
                status, credited, diff = "waiting", None, None
            elif date.fromisoformat(bank_covered_to) < hi:
                status, credited, diff = "no_statement", None, None
            else:
                status, credited, diff = "mismatch", 0, -net[d0]
            out.append(dict(sale_date=d0.isoformat(), card_total=gross[d0], expected_commission=gross[d0] - net[d0],
                            expected_credit=net[d0], group_days=[d0.isoformat()], credit_id=None, credit_date=None,
                            credit_amount=credited, group_gross=gross[d0], group_expected_credit=net[d0], diff=diff,
                            actual_commission=None, actual_rate_bp=None, delay_business_days=None,
                            expected_by=hi.isoformat(), status=status))
            i += 1
    return out


# ---------------------------------------------------------------- main
def main():
    initial = json.loads((BASE / "initial.json").read_text(encoding="utf-8"))
    truth = json.loads((BASE / "truth.json").read_text(encoding="utf-8"))
    f1 = (BASE / "bank_statement_1.txt").read_bytes()
    f2 = (BASE / "bank_statement_2.txt").read_bytes()
    st = State(initial, truth)

    for e in initial["existing_transactions"]:
        row = dict(label=e["label"], account=st.acc_number(e["account"]), date=e["date"], amount=e["amount"],
                   source=e["source"], kind="in" if e["amount"] > 0 else "out", external_id=None, status="ok",
                   dup_of=None, category=e["category"], cp_inn="")
        st.rows.append(row)
    vm, cash_rows, card = vm_expected()
    for c in cash_rows:
        st.rows.append(dict(label=c["external_id"], account="cash", date=c["date"], amount=c["amount"], source="vetmanager",
                            kind="in", external_id=c["external_id"], status="ok", dup_of=None, category="Выручка", cp_inn=""))

    steps = {}
    s_before = len(st.rows)
    steps["import_file1"] = st.import_file(f1)
    summary_after_file1 = st.summary(MONTH)
    snap_file1 = st.snapshot()
    m = st.add_manual(initial["manual_after_first_import"])
    steps["manual_after_import"] = dict(status=m["status"], duplicate_of=m["dup_of"])
    ur = initial["user_rule_from_edit"]
    mc = initial["manual_category_before_rule"]
    st.row(mc["label"]).update(category=mc["category"], status="ok", manual=True)
    d07 = st.row(ur["created_from"])
    d07["category"], d07["status"] = ur["category"], "ok"
    new_rule = {k: ur[k] for k in ("match", "value", "direction", "category")}
    st.rules.append(new_rule)
    # owner decision 5: the new rule also applies to already loaded operations WITHOUT a category (status check);
    # operations categorised by hand are not touched
    retro = []
    for r in st.rows:
        if r is d07 or r["kind"] == "transfer" or r["category"] is not None or r["status"] != "check":
            continue
        probe = dict(kind=r["kind"], cp_inn=r["cp_inn"], purpose=r["purpose"])
        saved = st.rules
        st.rules = [new_rule]
        cat = st.classify(probe)
        st.rules = saved
        if cat:
            r["category"], r["status"] = cat, "ok"
            retro.append(r["label"])
    steps["rule_created"] = dict(retro_applied=sorted(retro))
    count_before = len(st.rows)
    steps["reimport_file1"] = st.import_file(f1)
    assert len(st.rows) == count_before
    steps["import_file2"] = st.import_file(f2)
    count_mid = len(st.rows)
    steps["reimport_file2"] = st.import_file(f2)
    assert len(st.rows) == count_mid
    summary_final = st.summary(MONTH)

    # cross-check with hand-written labels
    problems = []
    for lab, t in truth["legs"].items():
        keys = [r for r in st.rows if r["label"] == lab or r["label"].startswith(lab + "/")]
        if not keys:
            problems.append(f"no row for label {lab}")
        for r in keys:
            if (r["status"], r["category"], r["dup_of"]) != (t["status"], t["category"], t["dup_of"]):
                problems.append(f"{lab}: sim={(r['status'], r['category'], r['dup_of'])} truth={(t['status'], t['category'], t['dup_of'])}")
    if problems:
        print("MISMATCH between simulation and labels:\n" + "\n".join(problems))
        sys.exit(1)

    sections1, docs1 = parse_1c(f1)
    sections2, docs2 = parse_1c(f2)

    def sec(s):
        return dict(account_number=s["РасчСчет"], date_from=pdate(s["ДатаНачала"]).isoformat(),
                    date_to=pdate(s["ДатаКонца"]).isoformat(), opening_balance=kop(s["НачальныйОстаток"]),
                    total_in=kop(s["ВсегоПоступило"]), total_out=kop(s["ВсегоСписано"]),
                    closing_balance=kop(s["КонечныйОстаток"]))
    for s in sections1 + sections2:
        assert kop(s["НачальныйОстаток"]) + kop(s["ВсегоПоступило"]) - kop(s["ВсегоСписано"]) == kop(s["КонечныйОстаток"])

    def doc_summary(docs):
        return [dict(number=d["Номер"], type=d["type"], amount=kop(d["Сумма"]),
                     label=st.num2label[d["Номер"]]) for d in docs]

    final_rows = {r["label"]: dict(date=r["date"], amount=r["amount"], source=r["source"], kind=r["kind"],
                                   status=r["status"], category=r["category"], duplicate_of=r["dup_of"],
                                   account=r["account"]) for r in st.rows}
    steps_out = {k: {kk: vv for kk, vv in v.items() if kk != "created_labels"} for k, v in steps.items() if "created" in v}
    steps_out["manual_after_import"] = steps["manual_after_import"]
    steps_out["rule_created"] = steps["rule_created"]
    steps_out["import_file1"]["created_labels"] = steps["import_file1"]["created_labels"]
    steps_out["import_file2"]["created_labels"] = steps["import_file2"]["created_labels"]

    pairs = sorted((r["label"], r["dup_of"]) for r in st.rows if r["status"] == "duplicate")
    expected = {
        "_comment": "Computed by tools/compute_expected_set02.py from the generated files; money in kopecks. Do not edit by hand.",
        "assumptions": {
            "duplicate_window_days": WINDOW_DAYS,
            "dedup_rule": "same account, same signed amount, |date diff| <= 3 days, different source, 1:1; the newly inserted row becomes status=duplicate, duplicate_of = older row; tie -> smallest date distance, then file order (date, number)",
            "idempotency_key": "account|number|booked_date|signed_amount|counterparty_inn",
            "rules": "first matching rule in list order; direction-aware; text = casefold substring of purpose; created-by-edit rule is appended and applies to new operations only",
            "summary": "income/expense: kind in/out, status != duplicate (check included), transfers excluded; balance = income - expense; missing category -> 'Без статьи'",
        },
        "pii": {k: truth[k] for k in ("pii_surnames", "pii_phones", "pii_addresses", "pii_emails")},
        "statements": {
            "bank_statement_1.txt": dict(sections=[sec(s) for s in sections1], documents=doc_summary(docs1),
                                         sections_count=len(docs1), unique_documents=len({d["Номер"] for d in docs1}),
                                         repeated_in_file=len(docs1) - len({d["Номер"] for d in docs1})),
            "bank_statement_2.txt": dict(sections=[sec(s) for s in sections2], documents=doc_summary(docs2),
                                         sections_count=len(docs2), unique_documents=len({d["Номер"] for d in docs2}),
                                         repeated_in_file=0),
        },
        "bad_format": {"file": "bad_format_kl_to_1c.txt", "error_code": "validation", "created": 0},
        "steps": steps_out,
        "duplicate_pairs": [dict(duplicate=a, original=b) for a, b in pairs],
        "not_duplicates": ["b3", "d16", "m1", "d17", "d23", "t1", "t2", "t3", "d24/101", "d24/102", "d25/101", "d25/102"],
        "check_after_import_file1": sorted(l for l, v in snap_file1.items() if v["status"] == "check"),
        "check_final": sorted(r["label"] for r in st.rows if r["status"] == "check"),
        "rows_final": final_rows,
        "summary_after_file1": summary_after_file1,
        "summary_final": summary_final,
        "summary_final_after_reupload": summary_final,
        "vetmanager": {**vm, "cash_transactions": cash_rows, "card_payments_total": sum(p["amount"] for p in card)},
        "acquiring_params": initial["acquiring"],
        "acquiring_context": {"as_of": AS_OF, "bank_covered_to": AS_OF},
        "acquiring": acquiring(card, st.rows, initial["acquiring"], AS_OF, AS_OF),
        "total_rows_final": len(st.rows),
        "row_counts_by_status_final": {s: sum(1 for r in st.rows if r["status"] == s) for s in ("ok", "check", "duplicate")},
    }
    (BASE / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("ok: expected.json written;", len(st.rows), "rows;", "pairs:", pairs)
    print("steps:", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "created_labels"} for k, v in steps_out.items()}, ensure_ascii=False))
    print("summary_final:", summary_final["income"], summary_final["expense"], summary_final["balance"])


if __name__ == "__main__":
    main()
