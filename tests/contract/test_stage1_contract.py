"""Stage 1 contract tests: Transactions, category rules, summary, bank statement import (docs/api-contract.md).

Read-only part (tokens A and B of golden set01): schema, errors, pagination, isolation, rejected files.
Write part (needs a CLEAN clinic seeded from tests/golden/set02/initial.json): set VF_TOKEN_C and VF_SET02_CLEAN=1.
It uploads statements, so it must never run against clinics A/B.

Run:  eval "$(python tests/contract/get_tokens.py)" && pytest tests/contract/test_stage1_contract.py -rs
Endpoints that are not implemented yet (FastAPI default 404/405 body, no {"error": ...}) make a test skip, not fail.
Request-body field names that the contract does not fix are the tester's proposal (see docs/handoff.md, 2026-10-11).
"""
import json
import os
import uuid
from datetime import date
from pathlib import Path

import pytest

from test_stage0_contract import GOLDEN, SEEDED, assert_error, assert_figure, items_of

httpx = pytest.importorskip("httpx")

SET02 = Path(__file__).resolve().parents[1] / "golden" / "set02"
EXPECTED = json.loads((SET02 / "expected.json").read_text(encoding="utf-8"))
INITIAL = json.loads((SET02 / "initial.json").read_text(encoding="utf-8"))
SURNAMES = [s.casefold() for s in EXPECTED["pii"]["pii_surnames"]]
TX_KINDS, TX_STATUSES, TX_SOURCES = {"in", "out", "transfer"}, {"ok", "check", "duplicate"}, {"bank", "vetmanager", "bot", "manual"}
UNKNOWN = str(uuid.UUID(int=0xDEAD))


# ------------------------------------------------------------------ helpers
_PATHS = None


def _openapi_paths(base):
    global _PATHS
    if _PATHS is None:
        try:
            _PATHS = set(httpx.get(f"{base}/openapi.json", timeout=15).json()["paths"])
        except Exception:
            _PATHS = set()
    return _PATHS


def route_published(resp):
    """True when the route of this response is in the server's OpenAPI schema (or the schema is unavailable)."""
    import re
    paths = _openapi_paths(f"{resp.request.url.scheme}://{resp.request.url.netloc.decode()}")
    if not paths:
        return True
    return any(re.fullmatch(re.sub(r"\{[^/]+\}", "[^/]+", p), resp.request.url.path) for p in paths)


def implemented(resp):
    """Skip when the route is not in the server's OpenAPI schema yet (the 404 then comes from the router, not from the handler)."""
    if resp.status_code in (404, 405) and not route_published(resp):
        pytest.skip(f"{resp.request.method} {resp.request.url.path} is not implemented yet (not in /openapi.json)")
    return resp


def get_all(client, path="/v1/transactions", **params):
    items, cursor = [], None
    for _ in range(200):
        q = dict(params, limit=50)
        if cursor:
            q["cursor"] = cursor
        r = implemented(client.get(path, params=q))
        assert r.status_code == 200, r.text
        body = r.json()
        items += body["items"]
        cursor = body.get("next_cursor")
        if not cursor:
            return items
    pytest.fail("pagination does not terminate")


def assert_transaction(t, account_ids=None):
    assert isinstance(t.get("id"), str) and t["id"]
    assert date.fromisoformat(t["date"])
    assert isinstance(t.get("description"), str)
    assert t["category"] is None or (isinstance(t["category"].get("id"), str) and t["category"].get("name"))
    assert t["account"].get("id") and t["account"].get("name")
    if account_ids is not None:
        assert t["account"]["id"] in account_ids, "transaction points to an account of another clinic"
    assert t["source"] in TX_SOURCES and t["kind"] in TX_KINDS and t["status"] in TX_STATUSES
    assert type(t["amount"]) is int, "amount must be int kopecks"
    if t["kind"] == "in":
        assert t["amount"] > 0
    if t["kind"] == "out":
        assert t["amount"] < 0


def account_ids(client):
    return {a["id"] for a in items_of(client.get("/v1/accounts").json())}


@pytest.fixture(scope="module")
def client_c(base_url):
    token = os.environ.get("VF_TOKEN_C")
    if not token or os.environ.get("VF_SET02_CLEAN") != "1":
        pytest.skip("VF_TOKEN_C and VF_SET02_CLEAN=1 are needed (clean clinic seeded from golden set02)")
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60) as c:
        yield c


def upload(client, name_or_bytes, filename="statement.txt"):
    data = (SET02 / name_or_bytes).read_bytes() if isinstance(name_or_bytes, str) else name_or_bytes
    return implemented(client.post("/v1/imports/bank-statement", files={"file": (filename, data, "text/plain")}))


# ------------------------------------------------------------------ 401
ENDPOINTS = [("GET", "/v1/transactions"), ("GET", "/v1/transactions/summary?month=2026-09"), ("GET", "/v1/category-rules"),
             ("POST", "/v1/transactions"), ("PATCH", f"/v1/transactions/{UNKNOWN}"),
             ("POST", f"/v1/transactions/{UNKNOWN}/resolve-duplicate"), ("DELETE", f"/v1/category-rules/{UNKNOWN}"),
             ("POST", "/v1/imports/bank-statement")]


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_stage1_endpoints_require_token(anon, method, path):
    r = anon.request(method, path)
    if r.status_code in (404, 405):
        implemented(r)
    assert_error(r, 401, "unauthorized")


@pytest.mark.parametrize("method,path", ENDPOINTS[:3])
def test_stage1_garbage_token_is_401(anon, method, path):
    r = anon.request(method, path, headers={"Authorization": "Bearer not.a.jwt"})
    implemented(r)
    assert_error(r, 401, "unauthorized")


# ------------------------------------------------------------------ GET /v1/transactions
def test_transactions_list_schema_and_envelope(client_a):
    r = implemented(client_a.get("/v1/transactions", params={"limit": 5}))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"items", "next_cursor"}
    assert isinstance(body["items"], list) and len(body["items"]) <= 5
    ids = account_ids(client_a)
    for t in body["items"]:
        assert_transaction(t, ids)


def test_transactions_pagination_has_no_overlap(client_a):
    r1 = implemented(client_a.get("/v1/transactions", params={"limit": 3}))
    b1 = r1.json()
    if not b1["next_cursor"]:
        pytest.skip("fewer than 4 transactions: nothing to paginate")
    b2 = client_a.get("/v1/transactions", params={"limit": 3, "cursor": b1["next_cursor"]}).json()
    assert not ({t["id"] for t in b1["items"]} & {t["id"] for t in b2["items"]})


def test_transactions_are_sorted_by_date_desc_then_stable(client_a):
    items = get_all(client_a)
    dates = [t["date"] for t in items]
    assert dates == sorted(dates, reverse=True)
    assert len({t["id"] for t in items}) == len(items), "an operation appears on two pages"


def test_transactions_date_filter(client_a):
    items = get_all(client_a, **{"from": "2026-09-01", "to": "2026-09-10"})
    assert all("2026-09-01" <= t["date"] <= "2026-09-10" for t in items)


@pytest.mark.parametrize("tab,status", [("check", "check"), ("duplicates", "duplicate")])
def test_transactions_tabs_filter_by_status(client_a, tab, status):
    items = get_all(client_a, tab=tab)
    assert all(t["status"] == status for t in items)


def test_transactions_tab_all_contains_every_tab(client_a):
    all_ids = {t["id"] for t in get_all(client_a, tab="all")}
    for tab in ("check", "duplicates"):
        assert {t["id"] for t in get_all(client_a, tab=tab)} <= all_ids


@pytest.mark.parametrize("params", [{"tab": "nonsense"}, {"from": "not-a-date"}, {"limit": "-1"}, {"limit": "abc"}])
def test_transactions_bad_query_is_validation_error(client_a, params):
    r = implemented(client_a.get("/v1/transactions", params=params))
    assert_error(r, 422, "validation")


def test_transactions_isolation(client_a, client_b):
    a = {t["id"] for t in get_all(client_a)}
    b = {t["id"] for t in get_all(client_b)}
    assert not (a & b), "the same operation is visible to two clinics"
    assert {t["account"]["id"] for t in get_all(client_a)} <= account_ids(client_a)
    assert {t["account"]["id"] for t in get_all(client_b)} <= account_ids(client_b)


def test_clinic_id_in_query_does_not_switch_clinic(client_a):
    base = {t["id"] for t in get_all(client_a)}
    other = {t["id"] for t in get_all(client_a, clinic_id=str(uuid.uuid4()))}
    assert base == other


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET01=1 not set")
def test_set01_counts_for_check_and_duplicates(client_a, client_b):
    data = json.loads((GOLDEN / "data.json").read_text(encoding="utf-8"))
    for client, cid in ((client_a, "A"), (client_b, "B")):
        txs = [t for t in data["transactions"] if t["clinic_id"] == cid]
        assert len(get_all(client, tab="check")) == sum(1 for t in txs if t["status"] == "check")
        assert len(get_all(client, tab="duplicates")) == sum(1 for t in txs if t["status"] == "duplicate")


# ------------------------------------------------------------------ write endpoints: errors and isolation (no data is changed)
def test_patch_unknown_transaction_is_404(client_a):
    r = implemented(client_a.patch(f"/v1/transactions/{UNKNOWN}", json={"category_id": UNKNOWN, "create_rule": False}))
    assert_error(r, 404, "not_found")


def test_patch_foreign_transaction_is_404_and_not_changed(client_a, client_b):
    b_items = get_all(client_b)
    if not b_items:
        pytest.skip("clinic B has no operations")
    target = b_items[0]
    rules_b_before = items_of(client_b.get("/v1/category-rules").json())
    r = implemented(client_a.patch(f"/v1/transactions/{target['id']}", json={"category_id": UNKNOWN, "create_rule": True}))
    assert r.status_code in (404, 422), "a user of clinic A must not reach an operation of clinic B"
    if r.status_code == 404:
        assert_error(r, 404, "not_found")
    after = next(t for t in get_all(client_b) if t["id"] == target["id"])
    assert after == target
    assert items_of(client_b.get("/v1/category-rules").json()) == rules_b_before


def test_patch_with_invalid_body_is_validation_error(client_a):
    items = get_all(client_a)
    if not items:
        pytest.skip("no operations")
    for body in ({}, {"category_id": 123}, {"category_id": "x", "create_rule": "maybe"}, {"unknown_field": 1}):
        r = implemented(client_a.patch(f"/v1/transactions/{items[0]['id']}", json=body))
        assert r.status_code in (422, 404), (body, r.text)
        if r.status_code == 422:
            assert_error(r, 422, "validation")


def test_resolve_duplicate_unknown_and_foreign(client_a, client_b):
    r = implemented(client_a.post(f"/v1/transactions/{UNKNOWN}/resolve-duplicate", json={"keep_id": UNKNOWN}))
    assert_error(r, 404, "not_found")
    b_items = get_all(client_b)
    a_items = get_all(client_a)
    if b_items and a_items:
        r = client_a.post(f"/v1/transactions/{a_items[0]['id']}/resolve-duplicate", json={"keep_id": b_items[0]["id"]})
        assert r.status_code in (404, 422) and r.status_code != 200, "keep_id of another clinic must be rejected"


def test_post_transaction_validation(client_a):
    acc = next(iter(account_ids(client_a)))
    bad = [{}, {"account_id": acc}, {"account_id": acc, "date": "2026-13-45", "amount": 100, "kind": "in"},
           {"account_id": acc, "date": "2026-09-01", "amount": 1.5, "kind": "in"},
           {"account_id": acc, "date": "2026-09-01", "amount": 100, "kind": "sideways"},
           {"account_id": UNKNOWN, "date": "2026-09-01", "amount": 100, "kind": "in", "comment": "x"}]
    for body in bad:
        r = implemented(client_a.post("/v1/transactions", json=body))
        assert r.status_code in (404, 422), (body, r.status_code)
        if r.status_code == 422:
            assert_error(r, 422, "validation")


def test_post_transaction_to_foreign_account_is_rejected(client_a, client_b):
    b_acc = next(iter(account_ids(client_b)))
    before = len(get_all(client_b))
    r = implemented(client_a.post("/v1/transactions", json={"account_id": b_acc, "date": "2026-09-01", "amount": 100,
                                                            "kind": "in", "comment": "isolation probe"}))
    assert r.status_code in (403, 404, 422), "an account of clinic B accepted a write from clinic A"
    assert len(get_all(client_b)) == before


# ------------------------------------------------------------------ category rules
def test_category_rules_schema_and_isolation(client_a, client_b):
    ra = implemented(client_a.get("/v1/category-rules"))
    assert ra.status_code == 200, ra.text
    a, b = items_of(ra.json()), items_of(client_b.get("/v1/category-rules").json())
    for rule in a + b:
        assert rule.get("id") and rule.get("category", {}).get("name")
    assert not ({r["id"] for r in a} & {r["id"] for r in b})
    if b:
        r = client_a.delete(f"/v1/category-rules/{b[0]['id']}")
        assert r.status_code in (404, 403)
        assert b[0]["id"] in {x["id"] for x in items_of(client_b.get("/v1/category-rules").json())}


def test_delete_unknown_rule_is_404(client_a):
    assert_error(implemented(client_a.delete(f"/v1/category-rules/{UNKNOWN}")), 404, "not_found")


# ------------------------------------------------------------------ summary
def test_summary_schema(client_a):
    r = implemented(client_a.get("/v1/transactions/summary", params={"month": "2026-09"}))
    assert r.status_code == 200, r.text
    body = r.json()
    for name in ("income", "expense", "balance"):
        assert_figure(body[name], name)
    assert body["balance"]["value"] == body["income"]["value"] - body["expense"]["value"]
    assert body["income"]["value"] >= 0 and body["expense"]["value"] >= 0


@pytest.mark.parametrize("month", ["2026-9", "2026-13", "september", "", "2026-09-01"])
def test_summary_bad_month_is_validation_error(client_a, month):
    assert_error(implemented(client_a.get("/v1/transactions/summary", params={"month": month})), 422, "validation")


def test_summary_requires_month(client_a):
    assert_error(implemented(client_a.get("/v1/transactions/summary")), 422, "validation")


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET01=1 not set")
def test_summary_matches_set01(client_a, client_b):
    """Independent sum over set01/data.json: kind in/out, status != duplicate, transfers excluded."""
    data = json.loads((GOLDEN / "data.json").read_text(encoding="utf-8"))
    for client, cid in ((client_a, "A"), (client_b, "B")):
        txs = [t for t in data["transactions"] if t["clinic_id"] == cid and t["date"].startswith("2026-09")
               and t["status"] != "duplicate" and t["kind"] != "transfer"]
        inc = sum(t["amount"] for t in txs if t["amount"] > 0)
        exp = -sum(t["amount"] for t in txs if t["amount"] < 0)
        body = implemented(client.get("/v1/transactions/summary", params={"month": "2026-09"})).json()
        assert (body["income"]["value"], body["expense"]["value"], body["balance"]["value"]) == (inc, exp, inc - exp)


def test_summary_is_isolated(client_a, client_b):
    a = implemented(client_a.get("/v1/transactions/summary", params={"month": "2026-09"})).json()
    b = client_b.get("/v1/transactions/summary", params={"month": "2026-09"}).json()
    assert a != b or a["income"]["value"] == 0


# ------------------------------------------------------------------ import: rejected files (changes nothing, safe for A)
def test_import_wrong_format_is_rejected_with_russian_message_and_loads_nothing(client_a):
    before = get_all(client_a)
    r = upload(client_a, EXPECTED["bad_format"]["file"], "kl_to_1c.txt")
    assert_error(r, 422, EXPECTED["bad_format"]["error_code"])
    message = r.json()["error"]["message"]
    assert "1С" in message and any("а" <= ch.lower() <= "я" for ch in message), message
    assert get_all(client_a) == before


@pytest.mark.parametrize("payload", [b"", b"\x00\x01\x02\xff", "просто текст".encode("cp1251")])
def test_import_garbage_is_rejected(client_a, payload):
    before = len(get_all(client_a))
    assert_error(upload(client_a, payload), 422, "validation")
    assert len(get_all(client_a)) == before


def test_import_without_file_is_validation_error(client_a):
    assert_error(implemented(client_a.post("/v1/imports/bank-statement")), 422, "validation")


def test_import_unknown_account_number_is_rejected_not_silently_created(client_a):
    """A valid 1C file for accounts the clinic does not have must not create operations or accounts."""
    before_tx, before_acc = len(get_all(client_a)), account_ids(client_a)
    r = upload(client_a, "bank_statement_1.txt")
    assert r.status_code in (422, 404), "set02 statement was accepted by a clinic that has no such accounts"
    assert len(get_all(client_a)) == before_tx and account_ids(client_a) == before_acc


# ------------------------------------------------------------------ write flow on a clean clinic (set02)
class Flow:
    pass


def _find(items, **match):
    return [t for t in items if all(t.get(k) == v for k, v in match.items())]


@pytest.fixture(scope="module")
def flow(client_c):
    f = Flow()
    c = client_c
    f.accounts = {a["name"]: a["id"] for a in items_of(implemented(c.get("/v1/accounts")).json())}
    wanted = {a["name"] for a in INITIAL["accounts"]}
    if not wanted <= set(f.accounts):
        pytest.skip(f"clinic C has no accounts {sorted(wanted - set(f.accounts))}: seed it from set02/initial.json")
    if get_all(c):
        pytest.skip("clinic C is not clean (already has operations)")
    cats = items_of(implemented(c.get("/v1/categories")).json())
    f.cat = {x["name"]: x["id"] for x in cats}
    missing = {x["name"] for x in INITIAL["categories"]} - set(f.cat)
    if missing:
        pytest.skip(f"categories not seeded in clinic C: {sorted(missing)}")
    f.rules_before = len(items_of(c.get("/v1/category-rules").json()))
    acc_name = {a["key"]: a["name"] for a in INITIAL["accounts"]}

    def post_manual(spec):
        body = {"account_id": f.accounts[acc_name[spec["account"]]], "date": spec["date"], "amount": abs(spec["amount"]),
                "kind": "in" if spec["amount"] > 0 else "out", "category_id": f.cat[spec["category"]],
                "comment": spec["description"]}
        r = implemented(c.post("/v1/transactions", json=body))
        assert r.status_code in (200, 201), r.text
        return r.json()

    f.existing = {e["label"]: post_manual(e) for e in INITIAL["existing_transactions"]}
    f.imp1 = upload(c, "bank_statement_1.txt")
    f.after1 = get_all(c)
    f.manual_post = post_manual(INITIAL["manual_after_first_import"])
    d07 = _find(f.after1, date="2026-09-04", amount=-9432050)[0]
    f.d07_before = d07
    d29 = _find(f.after1, date="2026-09-11", amount=-1100000)[0]   # same supplier, categorised BY HAND before the rule
    f.d29_manual = implemented(c.patch(f"/v1/transactions/{d29['id']}", json={"category_id": f.cat["Прочие расходы"], "create_rule": False}))
    f.patched = implemented(c.patch(f"/v1/transactions/{d07['id']}", json={"category_id": f.cat["Препараты"], "create_rule": True}))
    f.rules_after = items_of(c.get("/v1/category-rules").json())
    f.after_rule = get_all(c)
    f.n_before_reimport = len(get_all(c))
    f.imp1_again = upload(c, "bank_statement_1.txt")
    f.n_after_reimport = len(get_all(c))
    f.imp2 = upload(c, "bank_statement_2.txt")
    f.after2 = get_all(c)
    f.imp2_again = upload(c, "bank_statement_2.txt")
    f.n_after_reimport2 = len(get_all(c))
    f.summary = c.get("/v1/transactions/summary", params={"month": "2026-09"}).json()
    return f


def _counters(resp):
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    for k in ("loaded", "already_loaded", "duplicates", "to_check", "skipped"):
        assert type(body.get(k)) is int, f"import response must contain int '{k}': {body}"
    # names from designer's handoff: loaded includes duplicates and to_check; already_loaded = rows seen before
    # (in the DB or repeated inside the file); skipped = unreadable rows
    return dict(created=body["loaded"], already=body["already_loaded"], duplicates=body["duplicates"],
                check=body["to_check"], skipped=body["skipped"])


def test_flow_first_import_counters(flow):
    got, exp = _counters(flow.imp1), EXPECTED["steps"]["import_file1"]
    assert (got["created"], got["already"], got["duplicates"], got["check"]) == \
        (exp["created"], exp["skipped_existing"] + exp["skipped_in_file"], exp["duplicates"], exp["check"])


def test_flow_duplicates_found_without_false_positives(flow):
    dups = [t for t in flow.after1 if t["status"] == "duplicate"]
    exp = [r for lab, r in EXPECTED["rows_final"].items() if r["status"] == "duplicate" and lab != "m_post"]
    assert sorted((t["date"], t["amount"]) for t in dups) == sorted((r["date"], r["amount"]) for r in exp)
    for lab in ("b3", "m1"):                     # near-misses must stay ok
        e = EXPECTED["rows_final"][lab]
        assert all(t["status"] != "duplicate" for t in _find(flow.after1, date=e["date"], amount=e["amount"]))
    same_day = [t for t in flow.after1 if t["date"] == "2026-09-18" and t["amount"] == 850000]
    assert len(same_day) == 3 and all(t["status"] == "check" for t in same_day)   # t1, t2, t3: three distinct payments


def test_flow_manual_entry_matching_a_bank_row_becomes_duplicate(flow):
    assert flow.manual_post["status"] == EXPECTED["steps"]["manual_after_import"]["status"]


def test_flow_edit_with_create_rule(flow):
    assert flow.patched.status_code == 200, flow.patched.text
    body = flow.patched.json()
    assert body["status"] == "ok" and body["category"]["name"] == "Препараты"
    assert len(flow.rules_after) == flow.rules_before + 1
    assert flow.d29_manual.status_code == 200 and len(flow.rules_after) == flow.rules_before + 1   # manual edit made no rule


def test_flow_new_rule_applies_to_already_loaded_uncategorised_operations(flow):
    """Owner decision: the rule also covers loaded operations without a category; hand-categorised ones are untouched."""
    d28 = _find(flow.after_rule, date="2026-09-08", amount=-2380000)[0]
    assert d28["status"] == "ok" and d28["category"]["name"] == "Препараты"
    d29 = _find(flow.after_rule, date="2026-09-11", amount=-1100000)[0]
    assert d29["status"] == "ok" and d29["category"]["name"] == "Прочие расходы"
    still_check = sorted(l for l in EXPECTED["check_after_import_file1"] if l not in ("d07", "d28", "d29"))
    assert sum(1 for t in flow.after_rule if t["status"] == "check") == len(still_check)
    body = flow.patched.json()
    if body.get("rule"):
        assert body["rule"].get("applied_count") == len(EXPECTED["steps"]["rule_created"]["retro_applied"])


def test_flow_reupload_changes_nothing(flow):
    assert _counters(flow.imp1_again)["created"] == 0
    assert flow.n_after_reimport == flow.n_before_reimport
    assert _counters(flow.imp2_again)["created"] == 0
    assert flow.n_after_reimport2 == len(flow.after2)


def test_flow_rule_applies_to_new_operations_of_second_file(flow):
    exp = EXPECTED["steps"]["import_file2"]
    got = _counters(flow.imp2)
    assert (got["created"], got["already"], got["check"]) == (exp["created"], exp["skipped_existing"] + exp["skipped_in_file"], exp["check"])
    for day, amount in (("2026-09-24", -6178000), ("2026-09-28", -5000000)):
        t = _find(flow.after2, date=day, amount=amount)[0]
        assert t["status"] == "ok" and t["category"]["name"] == "Препараты"
    e4 = _find(flow.after2, date="2026-09-25", amount=-1240000)[0]      # "Вет-Снаб Плюс": other INN
    assert e4["status"] == "check" and e4["category"] is None


def test_flow_transfers_are_not_income_or_expense(flow):
    transfers = [t for t in flow.after2 if t["kind"] == "transfer"]
    assert len(transfers) == 4 and sum(t["amount"] for t in transfers) == 0


def test_flow_summary_matches_expected(flow):
    """Expected without Vetmanager cash rows (the connection is not part of this flow)."""
    rows = [r for lab, r in EXPECTED["rows_final"].items() if r["source"] != "vetmanager"
            and r["status"] != "duplicate" and r["kind"] != "transfer" and r["date"].startswith("2026-09")]
    inc = sum(r["amount"] for r in rows if r["amount"] > 0)
    exp = -sum(r["amount"] for r in rows if r["amount"] < 0)
    for name in ("income", "expense", "balance"):
        assert_figure(flow.summary[name], name)
    assert (flow.summary["income"]["value"], flow.summary["expense"]["value"], flow.summary["balance"]["value"]) == (inc, exp, inc - exp)


def test_flow_resolve_duplicate_keeps_chosen_row_and_total(flow, client_c):
    dup = next(t for t in flow.after2 if t["status"] == "duplicate" and t["source"] == "bank")
    twin = next(t for t in flow.after2 if t["id"] == dup["duplicate_of"]["id"])   # dates may differ by up to 3 days
    r = implemented(client_c.post(f"/v1/transactions/{dup['id']}/resolve-duplicate", json={"keep_id": dup["id"]}))
    assert r.status_code == 200, r.text
    now = {t["id"]: t for t in get_all(client_c)}
    assert now[dup["id"]]["status"] == "ok" and now[twin["id"]]["status"] == "duplicate"
    after = client_c.get("/v1/transactions/summary", params={"month": "2026-09"}).json()
    assert after["income"]["value"] == flow.summary["income"]["value"], "choosing the other twin must not change the total"
    # restore: keep the original again
    client_c.post(f"/v1/transactions/{dup['id']}/resolve-duplicate", json={"keep_id": twin["id"]})


def test_flow_no_owner_names_in_api_output(flow, client_c):
    blob = json.dumps(get_all(client_c) + items_of(client_c.get("/v1/category-rules").json()),
                      ensure_ascii=False).casefold()
    for s in SURNAMES:
        assert s not in blob, f"owner surname '{s}' is present in API output"


def test_flow_delete_rule(flow, client_c):
    rule = flow.rules_after[-1] if flow.rules_after else None
    assert rule, "the created rule is not in the list"
    r = implemented(client_c.delete(f"/v1/category-rules/{rule['id']}"))
    assert r.status_code in (200, 204), r.text
    assert rule["id"] not in {x["id"] for x in items_of(client_c.get("/v1/category-rules").json())}


def test_flow_other_clinics_do_not_see_flow_data(flow, client_a, client_b):
    marker = {(t["date"], t["amount"], t["description"]) for t in flow.after2 if t["source"] == "bank"}
    for client in (client_a, client_b):
        seen = {(t["date"], t["amount"], t["description"]) for t in get_all(client)}
        assert not (marker & seen)


@pytest.mark.skipif(not os.environ.get("VF_DATABASE_URL"), reason="VF_DATABASE_URL (read-only DB role) is not set")
def test_flow_database_has_no_owner_names(flow):
    """Gate: owner names must not be in the DB. Scans every text column of public tables of the test database."""
    psycopg = pytest.importorskip("psycopg")
    patterns = [f"%{s}%" for s in SURNAMES]
    with psycopg.connect(os.environ["VF_DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("select table_name, column_name from information_schema.columns where table_schema='public' "
                    "and data_type in ('text','character varying','jsonb','json')")
        hits = []
        for table, column in cur.fetchall():
            cur.execute(f'select count(*) from public."{table}" where "{column}"::text ilike any(%s)', (patterns,))
            if cur.fetchone()[0]:
                hits.append(f"{table}.{column}")
    assert not hits, f"owner surnames found in: {hits}"


# ------------------------------------------------------------------ acquiring reconciliation (schema; shape from designer's handoff)
ACQ_STATUSES = {"matched", "mismatch", "waiting", "no_statement", "no_payments"}


def test_acquiring_reconciliation_schema(client_a):
    r = implemented(client_a.get("/v1/acquiring/reconciliation", params={"month": "2026-09"}))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"settlement_days", "summary", "days"}
    for name in ("card_payments", "commission", "credited", "discrepancy", "waiting"):
        assert_figure(body["summary"][name], f"summary.{name}")
    dates = [d["date"] for d in body["days"]]
    assert dates == sorted(dates, reverse=True), "days must go from new to old"
    for d in body["days"]:
        assert d["status"] in ACQ_STATUSES
        for name in ("card_payments", "commission", "expected"):
            assert_figure(d[name], f"days[].{name}")
        # expected = card_payments - commission, in kopecks, no float
        assert d["expected"]["value"] == d["card_payments"]["value"] - d["commission"]["value"]
        if d["credited"] is not None:
            assert_figure(d["credited"], "days[].credited")
            assert d["discrepancy"]["value"] == d["credited"]["value"] - d["expected"]["value"]
        if d["status"] == "matched":
            assert d["discrepancy"]["value"] == 0 or abs(d["discrepancy"]["value"]) <= 100
        if d["status"] == "waiting":
            assert d["credited"] is None and d["discrepancy"] is None


@pytest.mark.parametrize("month", ["2026-9", "2026-13", ""])
def test_acquiring_bad_month_is_validation_error(client_a, month):
    assert_error(implemented(client_a.get("/v1/acquiring/reconciliation", params={"month": month})), 422, "validation")


def test_acquiring_isolation(client_a, client_b):
    a = implemented(client_a.get("/v1/acquiring/reconciliation", params={"month": "2026-09"})).json()
    b = client_b.get("/v1/acquiring/reconciliation", params={"month": "2026-09"}).json()
    assert a["summary"]["card_payments"]["value"] != b["summary"]["card_payments"]["value"]         or a["summary"]["card_payments"]["value"] == 0


def test_acquiring_day_details_unknown_day_and_review_requires_token(client_a, anon):
    r = implemented(client_a.get("/v1/acquiring/days/2000-01-01"))
    assert r.status_code in (200, 404)
    assert_error(implemented(anon.post("/v1/acquiring/days/2026-09-02/review", json={"note": None})), 401, "unauthorized")


def test_flow_acquiring_matches_golden(flow, client_c):
    """Needs the Vetmanager card payments of set02 in clinic C (loaded through the Vetmanager connection / test fixture)."""
    body = implemented(client_c.get("/v1/acquiring/reconciliation", params={"month": "2026-09"})).json()
    if not body["days"] or body["summary"]["card_payments"]["value"] == 0:
        pytest.skip("clinic C has no Vetmanager card payments loaded (see docs/handoff.md: test loading of the Vetmanager export)")
    got = {d["date"]: d for d in body["days"]}
    for exp in EXPECTED["acquiring"]:
        d = got[exp["sale_date"]]
        assert d["card_payments"]["value"] == exp["card_total"]
        assert d["commission"]["value"] == exp["expected_commission"]
        assert d["expected"]["value"] == exp["expected_credit"]
        assert d["status"] == exp["status"], exp["sale_date"]
        assert d["expected_by"] == exp["expected_by"]
