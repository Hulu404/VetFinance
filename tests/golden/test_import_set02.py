"""Golden tests, set02: 1C statement parsing, idempotent import, duplicates, rules, Vetmanager, acquiring, summary.

Expected numbers come from set02/expected.json (tools/compute_expected_set02.py), never from the engine.
Modules do not exist yet -> tests skip with the reason (see docs/handoff.md, interfaces proposed by tester).
"""
import json
from datetime import date

import pytest

from set02_support import (ACCOUNTS, BASE, EXPECTED, INITIAL, NUM2LABEL, TRUTH, Db, as_date, engine, import_statement,
                           leg_label, plain, read, seed_db, vetmanager_raw)

FILE1, FILE2 = "bank_statement_1.txt", "bank_statement_2.txt"


def _bank():
    return engine("bank_1c", "parse_1c_statement", "statement_to_operations", "StatementFormatError")


def _dedup():
    return engine("dedup", "dedupe_incoming", "find_duplicate_pairs", "TxRef")


def _rules():
    return engine("rules", "Rule", "classify", "rule_from_edit")


def _all():
    return _bank(), _dedup(), _rules()


# ---------------------------------------------------------------- parser
@pytest.mark.parametrize("name", [FILE1, FILE2])
def test_parser_sections_and_balances(name):
    bank = _bank()
    exp = EXPECTED["statements"][name]
    parsed = plain(bank.parse_1c_statement(read(name)))
    got = [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in s.items() if k in exp["sections"][0]}
           for s in parsed["sections"]]
    assert got == exp["sections"]
    for s in parsed["sections"]:
        assert s["opening_balance"] + s["total_in"] - s["total_out"] == s["closing_balance"]


@pytest.mark.parametrize("name", [FILE1, FILE2])
def test_parser_documents_amounts_types_and_repeats(name):
    bank = _bank()
    exp = EXPECTED["statements"][name]
    docs = plain(bank.parse_1c_statement(read(name)))["documents"]
    assert len(docs) == exp["sections_count"]
    assert len({d["number"] for d in docs}) == exp["unique_documents"]
    assert [(d["number"], d["doc_type"], d["amount"]) for d in docs] == \
        [(d["number"], d["type"], d["amount"]) for d in exp["documents"]]
    assert all(type(d["amount"]) is int and d["amount"] > 0 for d in docs)


def test_parser_dates_inn_and_comma_amount():
    bank = _bank()
    docs = {d["number"]: d for d in plain(bank.parse_1c_statement(read(FILE1)))["documents"]}
    d10 = docs[TRUTH["numbers"]["d10"]]            # amount written with a comma, document type "Платежное требование"
    assert d10["amount"] == 2246018 and d10["doc_type"] == "Платежное требование"
    d15 = docs[TRUTH["numbers"]["d15"]]            # document date differs from the bank posting date
    assert as_date(d15["doc_date"]) == date(2026, 9, 12) and as_date(d15["credit_date"]) == date(2026, 9, 14)
    d06 = docs[TRUTH["numbers"]["d06"]]
    assert d06["receiver_inn"] == "7701000011" and as_date(d06["debit_date"]) == date(2026, 9, 2)
    assert d06["payer_inn"] == "7799000100"
    t1 = docs["218"]                               # INN given in ПлательщикИНН and in "ИНН ... Название"
    assert t1["payer_inn"] == "7705000088" and "Зоопитомник" in t1["payer_name"] and not t1["payer_name"].startswith("ИНН")
    d13 = docs[TRUTH["numbers"]["d13"]]            # an individual: no INN
    assert not d13["payer_inn"]


def test_parser_is_deterministic():
    bank = _bank()
    assert plain(bank.parse_1c_statement(read(FILE1))) == plain(bank.parse_1c_statement(read(FILE1)))


def test_parser_rejects_wrong_format_with_readable_error():
    bank = _bank()
    with pytest.raises(bank.StatementFormatError) as err:
        bank.parse_1c_statement(read(EXPECTED["bad_format"]["file"]))
    assert "1С" in str(err.value) or "1C" in str(err.value)


def test_parser_rejects_empty_and_garbage():
    bank = _bank()
    for raw in (b"", b"\x00\x01\x02", "просто текст\r\nвторая строка".encode("cp1251")):
        with pytest.raises(bank.StatementFormatError):
            bank.parse_1c_statement(raw)


# ---------------------------------------------------------------- legs, ids, PII
def _ops(bank, name):
    parsed = bank.parse_1c_statement(read(name))
    return [plain(o) for o in bank.statement_to_operations(parsed, ACCOUNTS)]


def test_operations_signs_kinds_dates_and_transfers():
    bank = _bank()
    ops = _ops(bank, FILE1)
    by_label = {}
    for o in ops:
        by_label.setdefault(leg_label(o), []).append(o)
    # the document repeated by the bank is still two items here: de-duplication is a separate step
    assert len(by_label[NUM2LABEL[TRUTH["numbers"]["d09"]]]) == 2
    rows = EXPECTED["rows_final"]
    for lab, items in by_label.items():
        exp = rows[lab]
        o = items[0]
        assert (o["amount"], as_date(o["date"]).isoformat(), o["kind"]) == (exp["amount"], exp["date"], exp["kind"]), lab
    transfers = [o for o in ops if o["kind"] == "transfer"]
    assert len(transfers) == 4
    groups = {}
    for o in transfers:
        groups.setdefault(o["transfer_group"], []).append(o["amount"])
    assert len(groups) == 2 and all(len(v) == 2 and sum(v) == 0 for v in groups.values())
    assert all(o["transfer_group"] is None for o in ops if o["kind"] != "transfer")


def test_file2_has_legs_only_for_accounts_present_in_the_file():
    bank = _bank()
    assert {o["account_number"] for o in _ops(bank, FILE2)} == {next(iter(ACCOUNTS))}


def test_external_id_is_stable_across_files_and_unique_per_leg():
    bank = _bank()
    first = {leg_label(o): o["external_id"] for o in _ops(bank, FILE1)}
    second = {leg_label(o): o["external_id"] for o in _ops(bank, FILE2)}
    common = set(first) & set(second)
    steps = EXPECTED["steps"]
    assert len(common) == steps["import_file2"]["skipped_existing"]      # the overlap of the two files
    assert all(first[k] == second[k] for k in common)
    ids = list(first.values()) + [v for k, v in second.items() if k not in first]
    assert len(set(first.values())) == steps["import_file1"]["created"]
    assert len(set(ids)) == steps["import_file1"]["created"] + steps["import_file2"]["created"]
    # the three same-day, same-amount payments of t1/t2/t3 are NOT collapsed
    assert len({first["t1"], first["t2"], first["t3"]}) == 3


def test_no_owner_names_in_operations():
    bank = _bank()
    blob = json.dumps([o for n in (FILE1, FILE2) for o in _ops(bank, n)], ensure_ascii=False, default=str).casefold()
    for s in EXPECTED["pii"]["pii_surnames"]:
        assert s.casefold() not in blob, f"owner surname {s} leaked into operations"
    # legal-entity counterparties are not personal data and are kept
    assert "7702000022" in blob


# ---------------------------------------------------------------- rules
def test_starter_rules_classify_and_user_rule_is_inn_based():
    bank, _, rules = _bank(), _dedup(), _rules()
    db = seed_db(rules)
    ops = {leg_label(o): o for o in _ops(bank, FILE1)}
    for lab in ("d06", "d09", "d10", "d11", "d12", "d08", "acq03", "d13", "d14"):
        assert rules.classify(ops[lab], db.rules) == TRUTH["legs"][lab]["category"], lab
    for lab in ("d07", "d18", "d26", "d27", "t1", "t2", "t3"):
        assert rules.classify(ops[lab], db.rules) is None, lab
    new_rule = rules.rule_from_edit(ops["d07"], "Препараты")
    assert (new_rule.match, new_rule.value, new_rule.category) == ("inn", "7702000022", "Препараты")


def test_rule_does_not_leak_to_similar_counterparty():
    bank, _, rules = _bank(), _dedup(), _rules()
    db = seed_db(rules)
    ops1 = {leg_label(o): o for o in _ops(bank, FILE1)}
    ops2 = {leg_label(o): o for o in _ops(bank, FILE2)}
    db.rules.append(rules.rule_from_edit(ops1["d07"], "Препараты"))
    assert rules.classify(ops2["e2"], db.rules) == "Препараты"
    assert rules.classify(ops2["e3"], db.rules) == "Препараты"
    assert rules.classify(ops2["e4"], db.rules) is None     # "Вет-Снаб Плюс", other INN


def test_rule_priority_acquiring_credit_is_not_bank_fee():
    bank, _, rules = _bank(), _dedup(), _rules()
    db = seed_db(rules)
    ops = {leg_label(o): o for o in _ops(bank, FILE1)}
    # the acquiring order mentions "комиссия" and comes from the same bank as the fees
    assert rules.classify(ops["acq07"], db.rules) == "Выручка (эквайринг)"


# ---------------------------------------------------------------- duplicates
def test_find_duplicate_pairs_window_sign_account_and_one_to_one():
    dedup = _dedup()
    T = dedup.TxRef

    def ref(i, d, amount, source="bank", account="A1", kind=None):
        return T(id=i, account=account, date=date(2026, 9, d), amount=amount, source=source,
                 kind=kind or ("in" if amount > 0 else "out"))

    existing = [ref("e", 10, 1000, "bot")]
    pairs = lambda new, ex=existing: [(p["duplicate_id"], p["original_id"]) for p in map(plain, dedup.find_duplicate_pairs(new, ex, window_days=3))]
    assert pairs([ref("n", 13, 1000)]) == [("n", "e")]               # +3 days: inside
    assert pairs([ref("n", 14, 1000)]) == []                          # +4 days: outside
    assert pairs([ref("n", 7, 1000)]) == [("n", "e")]                # -3 days
    assert pairs([ref("n", 10, -1000)]) == []                         # opposite sign
    assert pairs([ref("n", 10, 1000, account="A2")]) == []            # other account
    assert pairs([ref("n", 10, 1000, source="bot")]) == []            # same source never duplicates itself
    assert pairs([ref("n", 10, 1001)]) == []                          # amount differs by a kopeck
    assert pairs([ref("n", 10, 1000, kind="transfer")]) == []         # transfers are never duplicates
    two = [ref("n1", 10, 1000), ref("n2", 10, 1000)]
    assert pairs(two) == [("n1", "e")]                                # one original pairs once; the other stays
    assert pairs([ref("n", 10, 1000)], [ref("e1", 12, 1000, "bot"), ref("e2", 10, 1000, "bot")]) == [("n", "e2")]


def test_dedupe_incoming_counts():
    bank, dedup = _bank(), _dedup()
    ops = _ops(bank, FILE1)
    res = plain(dedup.dedupe_incoming(ops, set()))
    st = EXPECTED["steps"]["import_file1"]
    assert (len(res["new"]), len(res["skipped_in_file"]), len(res["skipped_existing"])) == (st["created"], st["skipped_in_file"], 0)
    known = {o["external_id"] for o in ops}
    res = plain(dedup.dedupe_incoming(ops, known))
    assert (len(res["new"]), len(res["skipped_existing"])) == (0, st["created"])


# ---------------------------------------------------------------- scenario on the in-memory pipeline
def _scenario():
    bank, dedup, rules = _all()
    db = seed_db(rules)
    steps = {}
    steps["import_file1"] = import_statement(db, read(FILE1), bank, dedup, rules)
    snapshot_file1 = {r["label"]: (r["status"], r["category"], r["duplicate_of"]) for r in db.rows}
    # manual entry after the import: becomes a duplicate of the bank row
    m = INITIAL["manual_after_first_import"]
    row = db.add_row(label=m["label"], account=next(iter(ACCOUNTS)), date=m["date"], amount=m["amount"], source="manual",
                     kind="in", category=m["category"])
    bank_rows = [r for r in db.rows if r["source"] == "bank" and r["label"] not in db.paired and r["status"] != "duplicate"]
    for p in map(plain, dedup.find_duplicate_pairs(
            [dedup.TxRef(id=row["label"], account=row["account"], date=as_date(row["date"]), amount=row["amount"], source="manual", kind="in")],
            [dedup.TxRef(id=r["label"], account=r["account"], date=as_date(r["date"]), amount=r["amount"], source="bank", kind=r["kind"]) for r in bank_rows],
            window_days=3)):
        db.paired.add(p["original_id"])
        row["status"], row["duplicate_of"] = "duplicate", p["original_id"]
    mc = INITIAL["manual_category_before_rule"]
    db.row(mc["label"]).update(category=mc["category"], status="ok")          # categorised by hand, no rule
    ur = INITIAL["user_rule_from_edit"]
    db.row(ur["created_from"]).update(category=ur["category"], status="ok")
    new_rule = rules.Rule(match=ur["match"], value=ur["value"], direction=ur["direction"], category=ur["category"])
    db.rules.append(new_rule)
    # owner decision: the new rule also applies to already loaded operations that have no category (status check);
    # hand-categorised operations are not touched. Composition of classify() only; the backend may offer a helper.
    db.retro = []
    for r in db.rows:
        if r["label"] != ur["created_from"] and r["kind"] != "transfer" and r["category"] is None and r["status"] == "check":
            cat = rules.classify(r, [new_rule])
            if cat:
                r.update(category=cat, status="ok")
                db.retro.append(r["label"])
    rows_before = len(db.rows)
    steps["reimport_file1"] = import_statement(db, read(FILE1), bank, dedup, rules)
    assert len(db.rows) == rows_before
    steps["import_file2"] = import_statement(db, read(FILE2), bank, dedup, rules)
    rows_mid = len(db.rows)
    steps["reimport_file2"] = import_statement(db, read(FILE2), bank, dedup, rules)
    assert len(db.rows) == rows_mid
    return db, steps, snapshot_file1


KEYS = ("parsed_documents", "skipped_in_file", "skipped_existing", "created", "duplicates", "check", "rule_applied", "transfers")


@pytest.mark.parametrize("step", ["import_file1", "reimport_file1", "import_file2", "reimport_file2"])
def test_import_step_counters(step):
    _, steps, _ = _scenario()
    exp = EXPECTED["steps"][step]
    assert {k: steps[step][k] for k in KEYS} == {k: exp[k] for k in KEYS}


def test_reupload_creates_nothing():
    _, steps, _ = _scenario()
    for step in ("reimport_file1", "reimport_file2"):
        assert steps[step]["created"] == 0 and steps[step]["duplicates"] == 0 and steps[step]["check"] == 0


def test_final_statuses_categories_and_duplicate_pairs():
    db, _, _ = _scenario()
    exp = EXPECTED["rows_final"]
    bank_rows = {r["label"]: r for r in db.rows if r["source"] == "bank" or r["label"] in ("m_post",)}
    for lab, e in exp.items():
        if lab not in bank_rows:
            continue
        r = bank_rows[lab]
        assert (r["status"], r["category"], r["duplicate_of"]) == (e["status"], e["category"], e["duplicate_of"]), lab
    pairs = sorted((r["label"], r["duplicate_of"]) for r in db.rows if r["status"] == "duplicate")
    assert pairs == sorted((p["duplicate"], p["original"]) for p in EXPECTED["duplicate_pairs"])


def test_no_false_duplicates():
    db, _, _ = _scenario()
    for lab in EXPECTED["not_duplicates"]:
        assert db.row(lab)["status"] != "duplicate", f"{lab} is a false duplicate"
    assert sum(1 for r in db.rows if r["status"] == "duplicate") == len(EXPECTED["duplicate_pairs"])
    # two bank payments (d22, d23) for one bot payment: exactly one is flagged, the earlier document
    flagged = [l for l in ("d22", "d23") if db.row(l)["status"] == "duplicate"]
    assert flagged == [TRUTH["ambiguity_pair"]["kept_pair"]]


def test_check_list_and_rule_application_to_second_file():
    db, _, snap = _scenario()
    assert sorted(l for l, v in snap.items() if v[0] == "check") == EXPECTED["check_after_import_file1"]
    assert sorted(r["label"] for r in db.rows if r["status"] == "check") == EXPECTED["check_final"]
    assert db.row("e2")["category"] == db.row("e3")["category"] == "Препараты"
    assert db.row("e4")["status"] == "check"


def test_rule_from_edit_applies_retroactively_to_uncategorised_only():
    db, _, _ = _scenario()
    assert sorted(db.retro) == EXPECTED["steps"]["rule_created"]["retro_applied"]
    assert (db.row("d28")["status"], db.row("d28")["category"]) == ("ok", "Препараты")     # was check, same supplier
    assert (db.row("d29")["status"], db.row("d29")["category"]) == ("ok", "Прочие расходы")  # by hand: untouched
    assert db.row("d27")["status"] == "check"                                               # other counterparty


def test_import_order_does_not_change_the_result():
    bank, dedup, rules = _all()

    def run(order):
        db = seed_db(rules)
        for n in order:
            import_statement(db, read(n), bank, dedup, rules)
        return {r["label"]: (r["status"], r["category"], r["duplicate_of"]) for r in db.rows}

    assert run([FILE1, FILE2]) == run([FILE2, FILE1])


def test_no_owner_names_in_stored_rows():
    db, _, _ = _scenario()
    blob = json.dumps(db.rows, ensure_ascii=False, default=str).casefold()
    for s in EXPECTED["pii"]["pii_surnames"]:
        assert s.casefold() not in blob


# ---------------------------------------------------------------- Vetmanager
def test_vetmanager_totals_and_no_personal_data():
    vm = engine("vetmanager", "normalize_vetmanager")
    res = plain(vm.normalize_vetmanager(vetmanager_raw()))
    exp = EXPECTED["vetmanager"]
    assert len(res["visits"]) == exp["visits"]
    by_doc = {}
    for v in res["visits"]:
        by_doc[v["doctor_external_id"]] = by_doc.get(v["doctor_external_id"], 0) + 1
    assert sorted(by_doc.values(), reverse=True) == sorted(exp["visits_by_doctor"].values(), reverse=True)
    sales = res["sales"]
    execd = [s for s in sales if s["status"] == "exec"]
    assert len(execd) == exp["invoices_exec"] and sum(s["amount"] for s in execd) == exp["sales_exec"]
    drafts = [s for s in sales if s["status"] == "save"]
    assert len(drafts) == exp["invoices_draft"] and sum(s["amount"] for s in drafts) == exp["drafts_total"]
    assert len(sales) == exp["invoices_exec"] + exp["invoices_draft"]          # deleted invoices are dropped
    lines = [l for s in execd for l in s["lines"]]
    assert sum(l["amount"] for l in lines if l["kind"] == "service") == exp["lines_service"]
    assert sum(l["amount"] for l in lines if l["kind"] == "good") == exp["lines_good"]
    assert all(sum(l["amount"] for l in s["lines"]) == s["amount"] for s in sales)
    for method, e in exp["payments"].items():
        ps = [p for p in res["payments"] if p["method"] == method]
        assert (len(ps), sum(p["amount"] for p in ps)) == (e["count"], e["total"]), method
    cash = {p["external_id"]: p for p in res["payments"] if p["method"] == "cash"}
    assert sorted(cash) == sorted(c["external_id"] for c in exp["cash_transactions"])
    assert all(type(p["amount"]) is int for p in res["payments"])
    blob = json.dumps(res, ensure_ascii=False, default=str)
    for key in ("pii_surnames", "pii_phones", "pii_addresses", "pii_emails"):
        for token in EXPECTED["pii"][key]:
            assert token.casefold() not in blob.casefold(), f"{key}: {token} leaked"
    assert "вялость" not in blob      # free-text visit notes are not carried over


# ---------------------------------------------------------------- acquiring
def test_acquiring_reconciliation_day_by_day():
    acq = engine("acquiring", "reconcile_acquiring", "CardPayment", "BankCredit", "AcquiringParams")
    raw = vetmanager_raw()
    cassa = {c["id"]: c["type"] for c in raw["cassa"]["data"]["cassa"]}
    card = [acq.CardPayment(date=date.fromisoformat(p["create_date"][:10]),
                            amount=int(round(float(p["amount"]) * 100)))
            for p in raw["payment"]["data"]["payment"] if cassa[p["cassa_id"]] == "card"]
    credits = [acq.BankCredit(id=l, date=date.fromisoformat(r["date"]), amount=r["amount"])
               for l, r in EXPECTED["rows_final"].items() if r["category"] == "Выручка (эквайринг)"]
    params = acq.AcquiringParams(**EXPECTED["acquiring_params"])
    ctx = EXPECTED["acquiring_context"]
    res = [plain(s) for s in acq.reconcile_acquiring(card, credits, params, as_of=date.fromisoformat(ctx["as_of"]),
                                                     bank_covered_to=date.fromisoformat(ctx["bank_covered_to"]))]
    assert sum(c.amount for c in card) == EXPECTED["vetmanager"]["card_payments_total"]
    assert len(res) == len(EXPECTED["acquiring"])           # one result per sale day
    for got, exp in zip(res, EXPECTED["acquiring"]):
        assert as_date(got["sale_date"]).isoformat() == exp["sale_date"]
        for k in ("card_total", "expected_commission", "expected_credit", "credit_id", "credit_amount", "group_gross",
                  "group_expected_credit", "diff", "actual_commission", "actual_rate_bp", "delay_business_days", "status"):
            assert got[k] == exp[k], (exp["sale_date"], k)
        assert [as_date(d).isoformat() for d in got["group_days"]] == exp["group_days"]
        assert as_date(got["expected_by"]).isoformat() == exp["expected_by"]
    statuses = {r["sale_date"]: r["status"] for r in EXPECTED["acquiring"]}
    assert set(statuses.values()) == {"matched", "mismatch", "waiting"}


def test_acquiring_statuses_waiting_no_statement_and_missing_credit():
    acq = engine("acquiring", "reconcile_acquiring", "CardPayment", "BankCredit", "AcquiringParams")
    card = [acq.CardPayment(date=date(2026, 9, 2), amount=2100000)]
    credits = [acq.BankCredit(id="c", date=date(2026, 9, 3), amount=2060100)]
    params = acq.AcquiringParams(**EXPECTED["acquiring_params"])

    def run(cr, as_of, covered):
        return plain(acq.reconcile_acquiring(card, cr, params, as_of=as_of, bank_covered_to=covered))[0]

    first = run(credits, date(2026, 9, 30), date(2026, 9, 30))
    assert first == plain(acq.reconcile_acquiring(card, credits, params, as_of=date(2026, 9, 30), bank_covered_to=date(2026, 9, 30)))[0]
    assert first["status"] == "matched" and first["diff"] == 0 and first["expected_credit"] == 2060100
    # nothing arrived, the waiting window (3 business days -> 07.09) is still open
    w = run([], date(2026, 9, 4), date(2026, 9, 4))
    assert (w["status"], w["credit_amount"], w["diff"]) == ("waiting", None, None)
    # window is over, but the statement ends before it: we cannot judge
    n = run([], date(2026, 10, 10), date(2026, 9, 5))
    assert n["status"] == "no_statement"
    # window is over and the statement covers it: the bank did not pay -> mismatch with credited 0
    m = run([], date(2026, 10, 10), date(2026, 9, 30))
    assert (m["status"], m["credit_amount"], m["diff"]) == ("mismatch", 0, -2060100)
    # a credit of exactly +1 ruble is inside the tolerance, +1.01 is not
    assert run([acq.BankCredit(id="c", date=date(2026, 9, 3), amount=2060100 + 100)], date(2026, 9, 30), date(2026, 9, 30))["status"] == "matched"
    assert run([acq.BankCredit(id="c", date=date(2026, 9, 3), amount=2060100 + 101)], date(2026, 9, 30), date(2026, 9, 30))["status"] == "mismatch"


# ---------------------------------------------------------------- summary
def _summary_rows(stage):
    """Rows as the API would hold them. Stage 'final' uses expected.rows_final; vetmanager cash included."""
    rows = [dict(date=as_date(r["date"]), amount=r["amount"], kind=r["kind"], status=r["status"],
                 category=r["category"], source=r["source"]) for r in EXPECTED["rows_final"].values()]
    return rows


def test_summary_final_matches_expected_and_breakdown_adds_up():
    tx = engine("transactions", "summarize")
    res = plain(tx.summarize(_summary_rows("final"), "2026-09"))
    exp = EXPECTED["summary_final"]
    for k in ("income", "expense", "balance"):
        assert res[k]["value"] == exp[k], k
        assert type(res[k]["value"]) is int
    assert {b["label"]: b["value"] for b in res["income"]["breakdown"]} == exp["income_breakdown"]
    assert {b["label"]: b["value"] for b in res["expense"]["breakdown"]} == exp["expense_breakdown"]
    assert sum(b["value"] for b in res["income"]["breakdown"]) == res["income"]["value"]
    assert sum(b["value"] for b in res["expense"]["breakdown"]) == res["expense"]["value"]
    assert res["balance"]["value"] == res["income"]["value"] - res["expense"]["value"]
    again = plain(tx.summarize(_summary_rows("final"), "2026-09"))
    assert again == res


def test_summary_ignores_other_months():
    tx = engine("transactions", "summarize")
    rows = _summary_rows("final") + [dict(date=date(2026, 10, 1), amount=999999, kind="in", status="ok",
                                          category="Выручка", source="bank")]
    assert plain(tx.summarize(rows, "2026-09"))["income"]["value"] == EXPECTED["summary_final"]["income"]
