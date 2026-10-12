"""The whole stage 1 flow over the API on golden set 2 (in-memory data layer).

Expected numbers come from tests/golden/set02/expected.json (computed independently of the engine).
The flow mirrors the contract scenario: manual entries, statement 1, a manual entry after the import,
a category edit with a rule, re-uploads, statement 2, Vetmanager cash and card payments, acquiring.
"""

import json
from collections import Counter
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.rows import ClinicRow
from tests.conftest import FakeVetmanagerApi, build_app, make_token
from tests.memory_repo import MemoryRepo

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "set02"
EXPECTED = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))
INITIAL = json.loads((GOLDEN / "initial.json").read_text(encoding="utf-8"))
SURNAMES = [s.casefold() for s in EXPECTED["pii"]["pii_surnames"]]
FIXED = {"Аренда", "Коммунальные услуги", "Налоги и взносы", "Зарплата", "Прочие расходы"}
HEADERS = {"Authorization": f"Bearer {make_token()}"}


def build_repo() -> MemoryRepo:
    from tests.conftest import NOW

    repo = MemoryRepo(ClinicRow("c2", INITIAL["clinic"]["name"], None, None, "Europe/Moscow", 0))
    repo.now = NOW
    repo.add_connections()
    for account in INITIAL["accounts"]:
        repo.add_account(
            name=account["name"],
            kind=account["kind"],
            opening_balance=account["opening_balance"],
            opening_date=date.fromisoformat(account["opening_date"]),
            number=account["number"],
        )
    for category in INITIAL["categories"]:
        name = category["name"]
        kind = (
            "income" if category["type"] == "income" else ("fixed" if name in FIXED else "variable")
        )
        repo.add_category(name, kind)
    ids = {c.name: c.id for c in repo.categories}
    for rule in INITIAL["starter_rules"]:
        repo.add_rule(rule["match"], rule["value"], rule["direction"], ids[rule["category"]])
    return repo


@pytest.fixture(scope="module")
def world() -> Iterator["World"]:
    repo = build_repo()
    api = FakeVetmanagerApi()
    from cryptography.fernet import Fernet

    from app.secrets import FernetBox

    app = build_app(repo, api, FernetBox(Fernet.generate_key().decode()))
    with TestClient(app) as client:
        yield World(repo, client)


class World:
    def __init__(self, repo: MemoryRepo, client: TestClient) -> None:
        self.repo = repo
        self.client = client
        self.cat = {c.name: c.id for c in repo.categories}
        self.acc = {a.name: a.id for a in repo.accounts}
        self.by_key = {a["key"]: self.acc[a["name"]] for a in INITIAL["accounts"]}

    def get(self, path: str, **params: Any) -> Any:
        response = self.client.get(path, params=params, headers=HEADERS)
        assert response.status_code == 200, response.text
        return response.json()

    def all_transactions(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = None
        while True:
            body = self.get("/v1/transactions", limit=50, **({"cursor": cursor} if cursor else {}))
            items += body["items"]
            cursor = body["next_cursor"]
            if not cursor:
                return items

    def upload(self, name: str) -> Any:
        data = (GOLDEN / name).read_bytes()
        return self.client.post(
            "/v1/imports/bank-statement",
            files={"file": ("statement.txt", data, "text/plain")},
            headers=HEADERS,
        )

    def post_manual(self, spec: dict[str, Any]) -> dict[str, Any]:
        body = {
            "account_id": self.by_key[spec["account"]],
            "date": spec["date"],
            "amount": abs(spec["amount"]),
            "kind": "in" if spec["amount"] > 0 else "out",
            "category_id": self.cat[spec["category"]],
            "comment": spec["description"],
        }
        response = self.client.post("/v1/transactions", json=body, headers=HEADERS)
        assert response.status_code == 201, response.text
        result: dict[str, Any] = response.json()
        return result


def find(items: list[dict[str, Any]], day: str, amount: int) -> list[dict[str, Any]]:
    return [t for t in items if t["date"] == day and t["amount"] == amount]


def snapshot(items: list[dict[str, Any]]) -> Counter[tuple[str, int, str, str | None]]:
    return Counter(
        (t["date"], t["amount"], t["status"], t["category"]["name"] if t["category"] else None)
        for t in items
    )


def expected_snapshot(include_vetmanager: bool) -> Counter[tuple[str, int, str, str | None]]:
    rows = EXPECTED["rows_final"].values()
    return Counter(
        (r["date"], r["amount"], r["status"], r["category"])
        for r in rows
        if include_vetmanager or r["source"] != "vetmanager"
    )


# ------------------------------------------------------------------ the scenario, step by step
def test_01_manual_entries_before_the_import(world: World) -> None:
    for spec in INITIAL["existing_transactions"]:
        created = world.post_manual(spec)
        assert created["status"] == "ok" and created["source"] == "manual"
        assert created["figure"]["value"] == spec["amount"]


def test_02_first_statement_counters(world: World) -> None:
    response = world.upload("bank_statement_1.txt")
    assert response.status_code == 200, response.text
    body = response.json()
    expected = EXPECTED["steps"]["import_file1"]
    assert body["loaded"] == expected["created"]
    assert body["duplicates"] == expected["duplicates"]
    assert body["to_check"] == expected["check"]
    assert body["already_loaded"] == expected["skipped_in_file"] + expected["skipped_existing"]
    assert body["skipped"] == 0
    assert body["period"] == {"from": "2026-09-01", "to": "2026-09-22"}
    assert body["account"]["name"] == "Расчётный счёт"


def test_03_duplicates_are_found_without_false_positives(world: World) -> None:
    items = world.all_transactions()
    flagged = sorted(
        (t["date"], t["amount"])
        for t in items
        if t["status"] == "duplicate" and t["source"] == "bank"
    )
    expected = sorted(
        (r["date"], r["amount"])
        for r in EXPECTED["rows_final"].values()
        if r["status"] == "duplicate" and r["source"] == "bank"
    )
    assert flagged == expected
    same_day = find(items, "2026-09-18", 850000)
    assert len(same_day) == 3 and all(t["status"] == "check" for t in same_day)
    for label in ("b3", "m1"):  # near misses stay as they were
        row = EXPECTED["rows_final"][label]
        assert all(
            t["status"] == "ok"
            for t in find(items, row["date"], row["amount"])
            if t["source"] == "manual"
        )


def test_04_duplicate_points_to_the_older_record(world: World) -> None:
    dups = world.get("/v1/transactions", tab="duplicates")["items"]
    assert len(dups) == EXPECTED["steps"]["import_file1"]["duplicates"]
    for dup in dups:
        original = dup["duplicate_of"]
        assert original is not None and original["source"] == "manual"
        assert original["amount"] == dup["amount"] and dup["duplicate_state"] == "pending"
        assert "одинаковая сумма" in dup["duplicate_reason"]


def test_05_manual_entry_after_the_import_becomes_a_duplicate(world: World) -> None:
    created = world.post_manual(INITIAL["manual_after_first_import"])
    assert created["status"] == EXPECTED["steps"]["manual_after_import"]["status"]
    assert created["duplicate_of"]["source"] == "bank"


def test_06_edit_with_rule_applies_to_uncategorised_only(world: World) -> None:
    items = world.all_transactions()
    d29 = find(items, "2026-09-11", -1100000)[0]
    by_hand = world.client.patch(
        f"/v1/transactions/{d29['id']}",
        json={"category_id": world.cat["Прочие расходы"], "create_rule": False},
        headers=HEADERS,
    )
    assert by_hand.status_code == 200 and by_hand.json()["rule"] is None
    d07 = find(items, "2026-09-04", -9432050)[0]
    preview = world.get(
        f"/v1/transactions/{d07['id']}/rule-preview", category_id=world.cat["Препараты"]
    )
    assert preview["can_create"] and not preview["already_exists"]
    assert preview["matches_count"] == len(EXPECTED["steps"]["rule_created"]["retro_applied"])
    rules_before = len(world.get("/v1/category-rules")["items"])
    patched = world.client.patch(
        f"/v1/transactions/{d07['id']}",
        json={"category_id": world.cat["Препараты"], "create_rule": True},
        headers=HEADERS,
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["status"] == "ok" and body["category"]["name"] == "Препараты"
    assert body["rule"]["applied_count"] == len(EXPECTED["steps"]["rule_created"]["retro_applied"])
    after = world.all_transactions()
    d28 = find(after, "2026-09-08", -2380000)[0]
    assert (d28["status"], d28["category"]["name"]) == ("ok", "Препараты")
    d29_after = find(after, "2026-09-11", -1100000)[0]
    assert (d29_after["status"], d29_after["category"]["name"]) == ("ok", "Прочие расходы")
    rules = world.get("/v1/category-rules")["items"]
    assert len(rules) == rules_before + 1 and rules[-1]["category"]["name"] == "Препараты"
    assert rules[-1]["applied_count"]["value"] == 1 and rules[-1]["match"] == "inn"
    again = world.get(
        f"/v1/transactions/{d07['id']}/rule-preview", category_id=world.cat["Препараты"]
    )
    assert again["already_exists"] and not again["can_create"]


def test_07_reupload_changes_nothing(world: World) -> None:
    before = snapshot(world.all_transactions())
    body = world.upload("bank_statement_1.txt").json()
    assert body["loaded"] == 0 and body["duplicates"] == 0 and body["to_check"] == 0
    expected = EXPECTED["steps"]["reimport_file1"]
    assert body["already_loaded"] == expected["skipped_existing"] + expected["skipped_in_file"]
    assert snapshot(world.all_transactions()) == before


def test_08_second_statement_uses_the_rule_and_skips_the_overlap(world: World) -> None:
    body = world.upload("bank_statement_2.txt").json()
    expected = EXPECTED["steps"]["import_file2"]
    assert (body["loaded"], body["already_loaded"], body["to_check"]) == (
        expected["created"],
        expected["skipped_existing"],
        expected["check"],
    )
    items = world.all_transactions()
    for day, amount in (("2026-09-24", -6178000), ("2026-09-28", -5000000)):
        row = find(items, day, amount)[0]
        assert row["status"] == "ok" and row["category"]["name"] == "Препараты"
        assert "правилом" in row["figure"]["note"]
    e4 = find(items, "2026-09-25", -1240000)[0]
    assert e4["status"] == "check" and e4["category"] is None
    assert world.upload("bank_statement_2.txt").json()["loaded"] == 0


def test_09_check_tab_and_counts(world: World) -> None:
    check = world.get("/v1/transactions", tab="check")["items"]
    assert len(check) == len(EXPECTED["check_final"])
    counts = world.get("/v1/transactions/counts")
    assert counts["check"] == len(check)
    assert counts["duplicates"] == len(EXPECTED["duplicate_pairs"])
    assert counts["all"] == len(world.all_transactions())
    # an uncategorised operation of a known counterparty is offered a category
    with_suggestion = [t for t in check if t["suggestion"]]
    assert all(t["suggestion"]["category"]["name"] for t in with_suggestion)


def test_10_transfers_stay_out_of_income_and_expense(world: World) -> None:
    transfers = [t for t in world.all_transactions() if t["kind"] == "transfer"]
    assert len(transfers) == 4 and sum(t["amount"] for t in transfers) == 0
    assert all(t["category"] is None and t["status"] == "ok" for t in transfers)


def test_11_snapshot_matches_expected_without_vetmanager(world: World) -> None:
    assert snapshot(world.all_transactions()) == expected_snapshot(include_vetmanager=False)


def test_12_no_owner_names_anywhere(world: World) -> None:
    blob = json.dumps(world.all_transactions(), ensure_ascii=False).casefold()
    blob += json.dumps(world.get("/v1/category-rules"), ensure_ascii=False).casefold()
    blob += json.dumps(world.repo.raw_events, ensure_ascii=False, default=str).casefold()
    blob += json.dumps(
        [vars(t) for t in world.repo.txs], ensure_ascii=False, default=str
    ).casefold()
    for surname in SURNAMES:
        assert surname not in blob, surname


def test_13_resolve_duplicate_keeps_the_chosen_row(world: World) -> None:
    dup = world.get("/v1/transactions", tab="duplicates")["items"][0]
    original = dup["duplicate_of"]
    income = world.get("/v1/transactions/summary", month="2026-09")["income"]["value"]
    kept = world.client.post(
        f"/v1/transactions/{dup['id']}/resolve-duplicate",
        json={"keep_id": dup["id"]},
        headers=HEADERS,
    )
    assert kept.status_code == 200, kept.text
    states = {t["id"]: t for t in world.all_transactions()}
    assert states[dup["id"]]["status"] != "duplicate"
    assert states[original["id"]]["status"] == "duplicate"
    assert states[original["id"]]["duplicate_state"] == "confirmed"
    assert world.get("/v1/transactions/summary", month="2026-09")["income"]["value"] == income
    pending = world.get("/v1/transactions", tab="duplicates")["items"]
    assert dup["id"] not in {t["id"] for t in pending} and original["id"] not in {
        t["id"] for t in pending
    }
    # the decision can be reverted
    back = world.client.post(
        f"/v1/transactions/{dup['id']}/resolve-duplicate",
        json={"keep_id": original["id"]},
        headers=HEADERS,
    )
    assert back.status_code == 200
    states = {t["id"]: t for t in world.all_transactions()}
    assert (
        states[original["id"]]["status"] != "duplicate"
        and states[dup["id"]]["status"] == "duplicate"
    )
    # "this is not a duplicate"
    both = world.client.post(
        f"/v1/transactions/{dup['id']}/resolve-duplicate", json={"keep_both": True}, headers=HEADERS
    )
    assert both.status_code == 200
    states = {t["id"]: t for t in world.all_transactions()}
    assert (
        states[original["id"]]["status"] != "duplicate"
        and states[dup["id"]]["status"] != "duplicate"
    )
    assert world.get("/v1/transactions/summary", month="2026-09")["income"]["value"] > income
    restored = world.client.post(  # the link survives "keep both": the choice can still be changed
        f"/v1/transactions/{dup['id']}/resolve-duplicate",
        json={"keep_id": original["id"]},
        headers=HEADERS,
    )
    assert restored.status_code == 200, restored.text
    states = {t["id"]: t for t in world.all_transactions()}
    assert (
        states[dup["id"]]["status"] == "duplicate"
        and states[original["id"]]["status"] != "duplicate"
    )
    assert world.get("/v1/transactions/summary", month="2026-09")["income"]["value"] == income


def test_14_vetmanager_load_gives_cash_operations_and_card_payments(world: World) -> None:
    entities = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in (GOLDEN / "vetmanager").glob("*.json")
    }
    response = world.client.post(
        "/v1/connections/vetmanager/import", json={"entities": entities}, headers=HEADERS
    )
    assert response.status_code == 200, response.text
    run = response.json()["run"]
    assert run["status"] == "success" and run["error_code"] is None
    assert run["counts"]["value"] > 0
    cash = [t for t in world.all_transactions() if t["source"] == "vetmanager"]
    assert sorted((t["date"], t["amount"]) for t in cash) == sorted(
        (c["date"], c["amount"]) for c in EXPECTED["vetmanager"]["cash_transactions"]
    )
    assert all(t["account"]["name"] == "Касса" and t["category"]["name"] == "Выручка" for t in cash)
    again = world.client.post(
        "/v1/connections/vetmanager/import", json={"entities": entities}, headers=HEADERS
    )
    assert again.json()["run"]["counts"]["value"] == 0
    assert len([t for t in world.all_transactions() if t["source"] == "vetmanager"]) == len(cash)


def test_15_summary_matches_golden_with_cash(world: World) -> None:
    body = world.get("/v1/transactions/summary", month="2026-09")
    expected = EXPECTED["summary_final"]
    assert (body["income"]["value"], body["expense"]["value"], body["balance"]["value"]) == (
        expected["income"],
        expected["expense"],
        expected["balance"],
    )
    assert {i["label"]: i["value"] for i in body["income"]["breakdown"]} == expected[
        "income_breakdown"
    ]
    assert {i["label"]: i["value"] for i in body["expense"]["breakdown"]} == expected[
        "expense_breakdown"
    ]
    assert snapshot(world.all_transactions()) == expected_snapshot(include_vetmanager=True)


def test_16_acquiring_matches_golden(world: World) -> None:
    body = world.get("/v1/acquiring/reconciliation", month="2026-09")
    assert body["settlement_days"] == {"min": 1, "max": 3}
    assert body["bank_covered_to"] == "2026-09-30" and body["rate_pct"] == 1.9
    rows = {r["date_from"]: r for r in body["days"]}
    assert [r["date"] for r in body["days"]] == sorted(rows, reverse=True)
    for expected in EXPECTED["acquiring"]:
        row = rows[expected["group_days"][0]]
        member = next(m for m in row["members"] if m["date"] == expected["sale_date"])
        assert member["card_payments"]["value"] == expected["card_total"]
        assert member["commission"]["value"] == expected["expected_commission"]
        assert member["expected"]["value"] == expected["expected_credit"]
        assert row["status"] == expected["status"]
        assert row["date_to"] == expected["group_days"][-1]
        assert row["card_payments"]["value"] == expected["group_gross"]
        assert row["expected"]["value"] == expected["group_expected_credit"]
        assert row["expected_by"] >= expected["expected_by"]
        if expected["diff"] is None:
            assert row["credited"] is None and row["discrepancy"] is None
        else:
            assert row["discrepancy"]["value"] == expected["diff"]
            assert row["credited"]["value"] == expected["credit_amount"]
    for row in body["days"]:
        assert (
            row["expected"]["value"] == row["card_payments"]["value"] - row["commission"]["value"]
        )
        for key in ("card_payments", "commission", "expected", "credited", "discrepancy"):
            figure = row[key]
            if figure:
                assert sum(i["value"] for i in figure["breakdown"]) == figure["value"], key
    summary = body["summary"]
    assert summary["card_payments"]["value"] == EXPECTED["vetmanager"]["card_payments_total"]
    assert summary["waiting"]["value"] == 882900


def test_17_acquiring_day_details_and_review(world: World) -> None:
    details = world.get("/v1/acquiring/days/2026-09-05")
    assert details["date_from"] == "2026-09-04" and details["date_to"] == "2026-09-06"
    assert sum(p["amount"] for p in details["payments"]) == 2200000
    assert [c["amount"] for c in details["credits"]] == [2158200]
    assert details["review"] == {"reviewed": False, "note": None}
    response = world.client.post(
        "/v1/acquiring/days/2026-09-14/review", json={"note": "написали в банк"}, headers=HEADERS
    )
    assert response.status_code == 200, response.text
    assert response.json()["reviewed"] is True and response.json()["status"] == "mismatch"
    again = world.client.post(
        "/v1/acquiring/days/2026-09-14/review", json={"note": None}, headers=HEADERS
    )
    assert again.status_code == 200
    assert world.get("/v1/acquiring/days/2026-09-14")["review"]["reviewed"] is True
    missing = world.client.get("/v1/acquiring/days/2026-09-13", headers=HEADERS)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_18_dashboard_balance_includes_everything_but_duplicates(world: World) -> None:
    body = world.get("/v1/dashboard", as_of="2026-09-30")
    assert body["data_stale"] is False
    bank = body["balance"]["bank"]
    assert {i["label"] for i in bank["breakdown"]} == {"Расчётный счёт", "Резервный счёт"}
    for account in INITIAL["accounts"]:
        expected = account["opening_balance"] + sum(
            r["amount"]
            for r in EXPECTED["rows_final"].values()
            if r["account"] == (account["number"] or "cash") and r["status"] != "duplicate"
        )
        item = next(
            i for i in body["balance"]["total"]["breakdown"] if i["label"] == account["name"]
        )
        assert item["value"] == expected, account["name"]
