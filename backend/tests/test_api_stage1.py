import dataclasses
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.rows import SyncRunRow
from app.settings import Settings, get_settings
from tests.conftest import BANK_ID, CASH_ID, NOW, SECRET, FakeVetmanagerApi, make_token
from tests.memory_repo import MemoryRepo

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "set02"
AUTH = {"Authorization": f"Bearer {make_token()}"}
UNKNOWN = str(uuid.UUID(int=0xDEAD))


@pytest.fixture
def ids(repo: MemoryRepo) -> dict[str, str]:
    rent = repo.add_category("Аренда", "fixed")
    income = repo.add_category("Выручка", "income")
    return {"rent": rent.id, "income": income.id, "bank": BANK_ID, "cash": CASH_ID}


def post(client: TestClient, **body: Any) -> Any:
    payload = {"kind": "out", "account_id": "x", "date": "2026-09-10", "amount": 100, **body}
    return client.post("/v1/transactions", json=payload, headers=AUTH)


def account_uuid(repo: MemoryRepo, name: str) -> str:
    return next(a.id for a in repo.accounts if a.name == name)


# ------------------------------------------------------------------ authorisation
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/transactions"),
        ("GET", "/v1/transactions/counts"),
        ("GET", "/v1/transactions/summary?month=2026-09"),
        ("POST", "/v1/transactions"),
        ("PATCH", f"/v1/transactions/{UNKNOWN}"),
        ("GET", f"/v1/transactions/{UNKNOWN}/rule-preview?category_id={UNKNOWN}"),
        ("POST", f"/v1/transactions/{UNKNOWN}/resolve-duplicate"),
        ("GET", "/v1/category-rules"),
        ("DELETE", f"/v1/category-rules/{UNKNOWN}"),
        ("GET", "/v1/categories"),
        ("POST", "/v1/imports/bank-statement"),
        ("GET", "/v1/acquiring/reconciliation?month=2026-09"),
        ("GET", "/v1/acquiring/days/2026-09-01"),
        ("POST", "/v1/acquiring/days/2026-09-01/review"),
        ("GET", "/v1/connections"),
        ("PUT", "/v1/connections/vetmanager"),
        ("POST", f"/v1/connections/{UNKNOWN}/sync"),
        ("POST", "/v1/connections/vetmanager/import"),
    ],
)
def test_stage1_endpoints_require_a_token(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# ------------------------------------------------------------------ manual entry
def test_manual_entry_validation_reasons_by_field(client: TestClient, repo: MemoryRepo) -> None:
    account = account_uuid(repo, "Расчётный счёт")
    cases: list[tuple[dict[str, Any], dict[str, str]]] = [
        ({"amount": 0}, {"amount": "must_be_positive"}),
        ({"amount": -5}, {"amount": "must_be_positive"}),
        ({"amount": 1.5}, {"amount": "too_many_decimals"}),
        ({"amount": 10_000_000_001}, {"amount": "too_large"}),
        ({"comment": "я" * 201}, {"comment": "too_long"}),
        ({"date": "2026-10-01"}, {"date": "in_future"}),
        ({"date": "1999-12-31"}, {"date": "before_opening"}),
        ({"date": "2026-13-45"}, {"date": "invalid"}),
        ({"kind": "sideways"}, {"kind": "invalid"}),
        ({"unknown": 1}, {"unknown": "unknown_field"}),
    ]
    for extra, fields in cases:
        response = post(client, account_id=account, **extra)
        assert response.status_code == 422, extra
        error = response.json()["error"]
        assert error["code"] == "validation" and error["details"]["fields"] == fields, extra
    missing = client.post("/v1/transactions", json={}, headers=AUTH).json()["error"]["details"][
        "fields"
    ]
    assert missing == {k: "required" for k in ("kind", "account_id", "date", "amount")}


def test_manual_entry_unknown_account_or_category_is_404(
    client: TestClient, repo: MemoryRepo
) -> None:
    assert post(client, account_id=UNKNOWN).status_code == 404
    assert (
        post(client, account_id=account_uuid(repo, "Касса"), category_id=UNKNOWN).status_code == 404
    )
    assert client.get("/v1/transactions", headers=AUTH).json()["items"][0]["source"] == "bank"


def test_manual_entry_status_signs_and_comment_cleaning(
    client: TestClient, repo: MemoryRepo, ids: dict[str, str]
) -> None:
    cash = account_uuid(repo, "Касса")
    without = post(client, account_id=cash, comment="Такси, Иванов Иван Иванович")
    assert without.status_code == 201
    body = without.json()
    assert (body["status"], body["amount"], body["source"], body["kind"]) == (
        "check",
        -100,
        "manual",
        "out",
    )
    assert "Иванов" not in body["description"] and body["description"].startswith("Такси")
    assert body["figure"]["value"] == -100 and body["rule"] is None
    income = post(client, account_id=cash, kind="in", category_id=ids["income"], comment=None)
    assert income.json()["status"] == "ok" and income.json()["amount"] == 100
    assert income.json()["description"] == "Внесено вручную"
    assert income.json()["category"]["name"] == "Выручка"


def test_manual_entry_that_repeats_a_bank_row_is_a_duplicate(
    client: TestClient, repo: MemoryRepo
) -> None:
    bank = repo.add_tx(BANK_ID, date(2026, 9, 9), -540_000)
    created = post(client, account_id=BANK_ID, date="2026-09-11", amount=540_000).json()
    assert created["status"] == "duplicate" and created["duplicate_state"] == "pending"
    assert created["duplicate_of"]["id"] == bank.id
    assert "одинаковая сумма" in created["duplicate_reason"]
    far = post(client, account_id=BANK_ID, date="2026-09-20", amount=540_000).json()
    assert far["status"] == "check"


# ------------------------------------------------------------------ list
def test_list_validation_and_pagination(client: TestClient, repo: MemoryRepo) -> None:
    for day in range(1, 8):
        repo.add_tx(BANK_ID, date(2026, 9, day), -100 * day)
    for bad in (
        {"tab": "nonsense"},
        {"from": "not-a-date"},
        {"limit": "0"},
        {"limit": "abc"},
        {"limit": "201"},
    ):
        response = client.get("/v1/transactions", params=bad, headers=AUTH)
        assert response.status_code == 422 and response.json()["error"]["code"] == "validation", bad
    bad_cursor = client.get("/v1/transactions", params={"cursor": "###"}, headers=AUTH)
    assert bad_cursor.json()["error"]["details"]["fields"] == {"cursor": "invalid"}
    seen: list[str] = []
    cursor = None
    while True:
        page_params: dict[str, Any] = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        body = client.get("/v1/transactions", params=page_params, headers=AUTH).json()
        assert len(body["items"]) <= 3
        seen += [t["id"] for t in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 8
    dates = [
        t["date"]
        for t in client.get("/v1/transactions", params={"limit": 200}, headers=AUTH).json()["items"]
    ]
    assert dates == sorted(dates, reverse=True)
    window = client.get(
        "/v1/transactions", params={"from": "2026-09-02", "to": "2026-09-03"}, headers=AUTH
    )
    assert {t["date"] for t in window.json()["items"]} == {"2026-09-02", "2026-09-03"}


def test_tabs_and_counts(client: TestClient, repo: MemoryRepo, ids: dict[str, str]) -> None:
    repo.add_tx(BANK_ID, date(2026, 9, 1), -5, status="check")
    original = repo.add_tx(BANK_ID, date(2026, 9, 2), 7, source="manual")
    flagged = repo.add_tx(BANK_ID, date(2026, 9, 2), 7, status="duplicate")
    repo.add_tx(BANK_ID, date(2026, 9, 3), 9, status="duplicate")
    confirmed = repo.add_tx(BANK_ID, date(2026, 9, 4), 11, status="duplicate")
    for index, row in enumerate(repo.txs):
        if row.id == flagged.id:
            repo.txs[index] = dataclasses.replace(row, duplicate_of=original.id)
        if row.id == confirmed.id:
            repo.txs[index] = dataclasses.replace(row, duplicate_state="confirmed")
    counts = client.get("/v1/transactions/counts", headers=AUTH).json()
    assert counts == {
        "all": 6,
        "check": 1,
        "duplicates": 2,
    }  # a duplicate without a state counts as pending
    pending = client.get("/v1/transactions", params={"tab": "duplicates"}, headers=AUTH).json()[
        "items"
    ]
    assert len(pending) == 2 and all(t["status"] == "duplicate" for t in pending)
    assert {t["duplicate_state"] for t in pending} == {"pending"}
    assert next(t for t in pending if t["id"] == flagged.id)["duplicate_of"]["id"] == original.id
    assert (
        len(client.get("/v1/transactions", params={"tab": "check"}, headers=AUTH).json()["items"])
        == 1
    )
    assert len(client.get("/v1/transactions", headers=AUTH).json()["items"]) == 6


# ------------------------------------------------------------------ category edit, rules
def test_patch_validation_and_not_found(
    client: TestClient, repo: MemoryRepo, ids: dict[str, str]
) -> None:
    row = repo.add_tx(BANK_ID, date(2026, 9, 1), -5, status="check")
    body = {"category_id": ids["rent"], "create_rule": False}
    assert client.patch(f"/v1/transactions/{UNKNOWN}", json=body, headers=AUTH).status_code == 404
    assert (
        client.patch(
            f"/v1/transactions/{row.id}", json={**body, "category_id": UNKNOWN}, headers=AUTH
        ).status_code
        == 404
    )
    for bad in (
        {},
        {"category_id": 123},
        {"category_id": ids["rent"], "create_rule": "maybe"},
        {"unknown_field": 1},
    ):
        response = client.patch(f"/v1/transactions/{row.id}", json=bad, headers=AUTH)
        assert response.status_code == 422 and response.json()["error"]["code"] == "validation", bad
    assert client.patch("/v1/transactions/not-a-uuid", json=body, headers=AUTH).status_code == 422
    ok = client.patch(f"/v1/transactions/{row.id}", json=body, headers=AUTH)
    assert ok.status_code == 200 and ok.json()["status"] == "ok" and ok.json()["rule"] is None
    assert "выбрана вручную" in ok.json()["figure"]["note"]


def test_patch_transfer_has_no_category(
    client: TestClient, repo: MemoryRepo, ids: dict[str, str]
) -> None:
    row = repo.add_tx(BANK_ID, date(2026, 9, 1), -5, kind="transfer")
    response = client.patch(
        f"/v1/transactions/{row.id}",
        json={"category_id": ids["rent"], "create_rule": True},
        headers=AUTH,
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"] == {"category_id": "invalid"}


def test_rule_needs_a_counterparty_and_is_not_duplicated(
    client: TestClient, repo: MemoryRepo, ids: dict[str, str]
) -> None:
    anonymous = repo.add_tx(BANK_ID, date(2026, 9, 1), -5, status="check")
    preview = client.get(
        f"/v1/transactions/{anonymous.id}/rule-preview",
        params={"category_id": ids["rent"]},
        headers=AUTH,
    ).json()
    assert preview == {
        "can_create": False,
        "already_exists": False,
        "match_text": None,
        "matches_count": 0,
    }
    made = client.patch(
        f"/v1/transactions/{anonymous.id}",
        json={"category_id": ids["rent"], "create_rule": True},
        headers=AUTH,
    )
    assert made.json()["rule"] is None and repo.rules == []
    first = repo.add_tx(BANK_ID, date(2026, 9, 2), -7, status="check", inn="7701000011")
    second = repo.add_tx(BANK_ID, date(2026, 9, 3), -8, status="check", inn="7701000011")
    third = repo.add_tx(BANK_ID, date(2026, 9, 4), 9, kind="in", status="check", inn="7701000011")
    preview = client.get(
        f"/v1/transactions/{first.id}/rule-preview",
        params={"category_id": ids["rent"]},
        headers=AUTH,
    ).json()
    assert (
        preview["can_create"]
        and preview["matches_count"] == 1
        and preview["match_text"] == "ИНН 7701000011"
    )
    created = client.patch(
        f"/v1/transactions/{first.id}",
        json={"category_id": ids["rent"], "create_rule": True},
        headers=AUTH,
    ).json()
    assert created["rule"]["applied_count"] == 1 and len(repo.rules) == 1
    assert (
        repo.tx(second.id).category_id == ids["rent"]
        and repo.tx(second.id).category_source == "rule"
    )
    assert repo.tx(third.id).category_id is None  # other direction: not touched
    listing = client.get("/v1/category-rules", headers=AUTH).json()["items"]
    assert listing[0]["direction"] == "out" and listing[0]["applied_count"]["value"] == 1
    assert listing[0]["applied_count"]["breakdown"][0]["label"] == "В этом месяце"
    again = client.patch(
        f"/v1/transactions/{second.id}",
        json={"category_id": ids["rent"], "create_rule": True},
        headers=AUTH,
    ).json()
    assert again["rule"] is None and len(repo.rules) == 1
    exists = client.get(
        f"/v1/transactions/{second.id}/rule-preview",
        params={"category_id": ids["rent"]},
        headers=AUTH,
    ).json()
    assert exists["already_exists"] and not exists["can_create"]


def test_delete_rule(client: TestClient, repo: MemoryRepo, ids: dict[str, str]) -> None:
    rule = repo.add_rule("text", "аренда", None, ids["rent"])
    tagged = repo.add_tx(BANK_ID, date(2026, 9, 1), -5, category_id=ids["rent"])
    repo.txs[-1] = dataclasses.replace(tagged, rule_id=rule.id, category_source="rule")
    assert client.delete(f"/v1/category-rules/{UNKNOWN}", headers=AUTH).status_code == 404
    assert client.delete(f"/v1/category-rules/{rule.id}", headers=AUTH).status_code == 204
    assert client.get("/v1/category-rules", headers=AUTH).json()["items"] == []
    assert repo.tx(tagged.id).category_id == ids["rent"] and repo.tx(tagged.id).rule_id is None


def test_categories_list(client: TestClient, ids: dict[str, str]) -> None:
    body = client.get("/v1/categories", headers=AUTH).json()
    assert [c["name"] for c in body["items"]] == ["Выручка", "Аренда"]
    assert set(body["items"][0]) == {"id", "name", "type", "norm_min_pct", "norm_max_pct"}


def test_suggestion_from_rule_and_from_history(
    client: TestClient, repo: MemoryRepo, ids: dict[str, str]
) -> None:
    repo.add_tx(BANK_ID, date(2026, 8, 1), -5, category_id=ids["rent"], inn="7701000011")
    repo.add_tx(BANK_ID, date(2026, 8, 2), -5, category_id=ids["rent"], inn="7701000011")
    pending = repo.add_tx(BANK_ID, date(2026, 9, 1), -9, status="check", inn="7701000011")
    items = client.get("/v1/transactions", params={"tab": "check"}, headers=AUTH).json()["items"]
    suggestion = next(t for t in items if t["id"] == pending.id)["suggestion"]
    assert suggestion["category"]["name"] == "Аренда" and suggestion["reason"] == "similar"
    assert suggestion["text"].startswith("так же разнесено 2 операции")


# ------------------------------------------------------------------ duplicates
def test_resolve_duplicate_errors(client: TestClient, repo: MemoryRepo) -> None:
    original = repo.add_tx(BANK_ID, date(2026, 9, 1), 5, source="manual")
    stranger = repo.add_tx(BANK_ID, date(2026, 9, 9), 8)
    url = f"/v1/transactions/{original.id}/resolve-duplicate"
    assert (
        client.post(
            f"/v1/transactions/{UNKNOWN}/resolve-duplicate", json={"keep_both": True}, headers=AUTH
        ).status_code
        == 404
    )
    for body in ({}, {"keep_id": original.id, "keep_both": True}):
        assert client.post(url, json=body, headers=AUTH).status_code == 422
    unknown = client.post(url, json={"keep_id": UNKNOWN}, headers=AUTH)
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "not_found"
    outside = client.post(url, json={"keep_id": stranger.id}, headers=AUTH)
    assert outside.status_code == 422 and outside.json()["error"]["details"]["fields"] == {
        "keep_id": "invalid"
    }


def test_keep_both_restores_the_status_of_a_row_without_category(
    client: TestClient, repo: MemoryRepo
) -> None:
    original = repo.add_tx(BANK_ID, date(2026, 9, 1), 5, source="manual", status="check")
    flagged = repo.add_tx(BANK_ID, date(2026, 9, 1), 5, status="duplicate")
    repo.txs[-1] = dataclasses.replace(flagged, duplicate_of=original.id, duplicate_state="pending")
    response = client.post(
        f"/v1/transactions/{flagged.id}/resolve-duplicate", json={"keep_both": True}, headers=AUTH
    )
    assert response.status_code == 200
    assert {t["status"] for t in response.json()["kept"]} == {"check"} and response.json()[
        "duplicates"
    ] == []
    assert repo.tx(flagged.id).duplicate_dismissed is True


# ------------------------------------------------------------------ summary
@pytest.mark.parametrize("month", ["2026-9", "2026-13", "september", "", "2026-09-01"])
def test_summary_bad_month(client: TestClient, month: str) -> None:
    response = client.get("/v1/transactions/summary", params={"month": month}, headers=AUTH)
    assert response.status_code == 422 and "month" in response.json()["error"]["details"]["fields"]


def test_summary_requires_month_and_returns_figures(client: TestClient, repo: MemoryRepo) -> None:
    missing = client.get("/v1/transactions/summary", headers=AUTH)
    assert missing.json()["error"]["details"]["fields"] == {"month": "required"}
    repo.add_tx(BANK_ID, date(2026, 9, 1), 1000)
    repo.add_tx(BANK_ID, date(2026, 9, 2), -400, status="check")
    body = client.get("/v1/transactions/summary", params={"month": "2026-09"}, headers=AUTH).json()
    assert (body["income"]["value"], body["expense"]["value"], body["balance"]["value"]) == (
        1000,
        400,
        600,
    )
    assert body["expense"]["breakdown"] == [{"label": "Без статьи", "value": 400, "unit": "rub"}]


# ------------------------------------------------------------------ import of a statement
def upload(client: TestClient, data: bytes, **form: str) -> Any:
    return client.post(
        "/v1/imports/bank-statement",
        files={"file": ("s.txt", data, "text/plain")},
        data=form,
        headers=AUTH,
    )


def test_import_rejects_files_with_a_reason(client: TestClient) -> None:
    bad = upload(client, (GOLDEN / "bad_format_kl_to_1c.txt").read_bytes())
    error = bad.json()["error"]
    assert bad.status_code == 422 and error["code"] == "validation"
    assert error["details"]["reason"] == "unsupported_format" and "1С" in error["message"]
    assert upload(client, b"").json()["error"]["details"]["reason"] == "empty"
    assert upload(client, b"   \r\n ").json()["error"]["details"]["reason"] == "empty"
    large = upload(client, b"x" * (10 * 1024 * 1024 + 1)).json()["error"]["details"]["reason"]
    assert large == "too_large"
    assert client.post("/v1/imports/bank-statement", headers=AUTH).json()["error"]["details"][
        "fields"
    ] == {"file": "required"}


def test_import_for_accounts_the_clinic_does_not_have(client: TestClient, repo: MemoryRepo) -> None:
    data = (GOLDEN / "bank_statement_1.txt").read_bytes()
    response = upload(client, data)
    error = response.json()["error"]
    assert response.status_code == 422 and error["details"]["reason"] == "account_mismatch"
    assert len(error["details"]["account_tail"]) == 4
    assert len(repo.txs) == 1 and repo.raw_events == []  # nothing was stored


def test_import_with_a_selected_account_that_is_not_in_the_file(
    client: TestClient, repo: MemoryRepo
) -> None:
    repo.accounts[0] = dataclasses.replace(repo.accounts[0], number="40702810500000000555")
    response = upload(client, (GOLDEN / "bank_statement_2.txt").read_bytes(), account_id=BANK_ID)
    assert response.status_code == 422 or response.status_code == 404
    assert (
        upload(
            client, (GOLDEN / "bank_statement_2.txt").read_bytes(), account_id=UNKNOWN
        ).status_code
        == 404
    )


def test_import_is_rate_limited_per_clinic(client: TestClient, repo: MemoryRepo) -> None:
    for _ in range(10):
        repo.raw_events.append(
            {"source": "bank_statement", "created_at": NOW - timedelta(seconds=5)}
        )
    response = upload(client, b"")
    assert response.status_code == 429 and response.json()["error"]["code"] == "rate_limited"
    assert response.headers["retry-after"] == "60"
    repo.raw_events.clear()
    assert upload(client, b"").status_code == 422


# ------------------------------------------------------------------ connections
def vetmanager(client: TestClient) -> dict[str, Any]:
    items = client.get("/v1/connections", headers=AUTH).json()["items"]
    return next(c for c in items if c["type"] == "vetmanager")


def test_connections_list_shape_before_anything_is_connected(client: TestClient) -> None:
    items = client.get("/v1/connections", headers=AUTH).json()["items"]
    assert [c["type"] for c in items] == ["vetmanager", "bank"]
    vm, bank = items
    assert (
        vm["connected"] is False
        and vm["schedule"] is None
        and vm["runs"] == []
        and vm["last_run"] is None
    )
    assert vm["bank"] is None and vm["data_stale"] is False
    assert bank["connected"] is False and [
        a["account"]["name"] for a in bank["bank"]["accounts"]
    ] == ["Расчётный счёт"]


def test_saving_the_key_hides_it_and_starts_the_first_run(
    client: TestClient, repo: MemoryRepo, api: FakeVetmanagerApi
) -> None:
    key = "SECRET-KEY-4a7f"
    response = client.put(
        "/v1/connections/vetmanager",
        json={"address": "https://Aibolit.Vetmanager.ru/rest/", "key": key},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert key not in response.text and body["key_hint"] == "4a7f"
    assert body["address"] == "aibolit.vetmanager.ru" and body["connected"] is True
    assert body["schedule"] == {"kind": "nightly", "time": "04:00"}
    assert all(key not in cipher for cipher in repo.secrets.values()) and len(repo.secrets) == 1
    assert key not in client.get("/v1/connections", headers=AUTH).text
    run = vetmanager(client)["last_run"]
    assert run["status"] == "success" and run["counts"]["value"] == 0 and run["error_code"] is None
    assert api.calls[0] == ("aibolit.vetmanager.ru", "4a7f")
    # a change of the address alone keeps the stored key and does not start another run
    runs_before = len(repo.runs)
    again = client.put(
        "/v1/connections/vetmanager", json={"address": "clinic.vetmanager.cloud"}, headers=AUTH
    )
    assert (
        again.status_code == 200
        and again.json()["key_hint"] == "4a7f"
        and len(repo.runs) == runs_before
    )


def test_saving_validates_address_and_key(client: TestClient, api: FakeVetmanagerApi) -> None:
    def put(**body: str) -> Any:
        return client.put("/v1/connections/vetmanager", json=body, headers=AUTH)

    for address in (
        "evil.example.com",
        "vetmanager.ru",
        "localhost",
        "10.0.0.1",
        "a b.vetmanager.ru",
        "x.vetmanager.ru.evil.com",
    ):
        assert put(address=address, key="k" * 8).json()["error"]["details"]["fields"] == {
            "address": "unreachable"
        }
    assert put(address="aibolit.vetmanager.ru").json()["error"]["details"]["fields"] == {
        "key": "required"
    }
    api.ping_result = "invalid_key"
    assert put(address="aibolit.vetmanager.ru", key="bad-key").json()["error"]["details"][
        "fields"
    ] == {"key": "invalid"}
    api.ping_result = "unreachable"
    assert put(address="aibolit.vetmanager.ru", key="k" * 8).json()["error"]["details"][
        "fields"
    ] == {"address": "unreachable"}
    api.ping_result = "rate_limited"
    assert put(address="aibolit.vetmanager.ru", key="k" * 8).status_code == 422
    assert vetmanager(client)["connected"] is False
    extra = client.put(
        "/v1/connections/vetmanager", json={"address": "a.vetmanager.ru", "x": 1}, headers=AUTH
    )
    assert extra.json()["error"]["details"]["fields"] == {"x": "unknown_field"}


def connect(client: TestClient, repo: MemoryRepo) -> str:
    assert (
        client.put(
            "/v1/connections/vetmanager",
            json={"address": "a.vetmanager.ru", "key": "key-0001"},
            headers=AUTH,
        ).status_code
        == 200
    )
    # the first run was started "now"; move it back so that the next sync is allowed
    repo.runs[:] = [
        dataclasses.replace(r, started_at=r.started_at - timedelta(hours=1)) for r in repo.runs
    ]
    return next(c.id for c in repo.connections if c.type == "vetmanager")


def test_sync_runs_and_reports_the_error_code(
    client: TestClient, repo: MemoryRepo, api: FakeVetmanagerApi
) -> None:
    connection = connect(client, repo)
    api.error = "invalid_key"
    response = client.post(f"/v1/connections/{connection}/sync", headers=AUTH)
    assert response.status_code == 202 and response.json()["run"]["status"] == "running"
    run = vetmanager(client)["last_run"]
    assert (
        run["status"] == "failed" and run["error_code"] == "invalid_key" and run["counts"] is None
    )
    assert vetmanager(client)["last_success_at"] is not None  # the first run succeeded earlier


def test_sync_is_not_allowed_too_often_or_twice_at_once(
    client: TestClient, repo: MemoryRepo
) -> None:
    connection = connect(client, repo)
    repo.runs[:] = [
        dataclasses.replace(r, started_at=NOW - timedelta(minutes=2)) for r in repo.runs
    ]
    too_often = client.post(f"/v1/connections/{connection}/sync", headers=AUTH)
    assert too_often.status_code == 429 and too_often.json()["error"]["code"] == "rate_limited"
    assert 0 < int(too_often.headers["retry-after"]) <= 300
    repo.runs.append(
        SyncRunRow(
            repo.new_id(), connection, "running", NOW - timedelta(minutes=1), None, None, None
        )
    )
    busy = client.post(f"/v1/connections/{connection}/sync", headers=AUTH)
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "conflict"
    # a run that never ended is treated as lost after half an hour
    repo.runs[-1] = dataclasses.replace(repo.runs[-1], started_at=NOW - timedelta(hours=2))
    lost = next(r for r in vetmanager(client)["runs"] if r["id"] == repo.runs[-1].id)
    assert lost["status"] == "failed" and lost["error_code"] == "unknown" and lost["counts"] is None
    repo.runs[:] = [dataclasses.replace(r, started_at=NOW - timedelta(hours=3)) for r in repo.runs]
    assert client.post(f"/v1/connections/{connection}/sync", headers=AUTH).status_code == 202


def test_sync_of_other_connections(client: TestClient, repo: MemoryRepo) -> None:
    bank = next(c.id for c in repo.connections if c.type == "bank")
    response = client.post(f"/v1/connections/{bank}/sync", headers=AUTH)
    assert (
        response.status_code == 422
        and response.json()["error"]["details"]["reason"] == "not_syncable"
    )
    vetmanager_id = next(c.id for c in repo.connections if c.type == "vetmanager")
    assert (
        client.post(f"/v1/connections/{vetmanager_id}/sync", headers=AUTH).status_code == 422
    )  # not connected
    assert client.post(f"/v1/connections/{UNKNOWN}/sync", headers=AUTH).status_code == 404


def test_raw_import_endpoint_can_be_switched_off(client: TestClient) -> None:
    app = client.app
    off = Settings(supabase_jwt_secret=SecretStr(SECRET), vetmanager_import_enabled=False)
    app.dependency_overrides[get_settings] = lambda: off  # type: ignore[attr-defined]
    response = client.post("/v1/connections/vetmanager/import", json={"entities": {}}, headers=AUTH)
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"


def test_raw_import_ignores_client_and_pet_entities(client: TestClient, repo: MemoryRepo) -> None:
    entities = {
        "client": {"data": {"client": [{"id": "1", "last_name": "Секретов"}]}},
        "cassa": {"data": {"cassa": []}},
    }
    response = client.post(
        "/v1/connections/vetmanager/import", json={"entities": entities}, headers=AUTH
    )
    assert response.status_code == 200 and response.json()["run"]["status"] == "success"
    assert "Секретов" not in repr(vars(repo))


# ------------------------------------------------------------------ data_stale on the dashboard
def test_dashboard_data_stale_follows_the_connections(client: TestClient, repo: MemoryRepo) -> None:
    assert client.get("/v1/dashboard", headers=AUTH).json()["data_stale"] is False
    connection = connect(client, repo)
    assert (
        client.get("/v1/dashboard", headers=AUTH).json()["data_stale"] is False
    )  # synced a moment ago
    repo.runs[:] = [
        dataclasses.replace(
            r, started_at=NOW - timedelta(hours=40), finished_at=NOW - timedelta(hours=40)
        )
        for r in repo.runs
        if r.connection_id == connection
    ]
    assert vetmanager(client)["data_stale"] is True
    assert client.get("/v1/dashboard", headers=AUTH).json()["data_stale"] is True


def test_dashboard_bank_statement_age(client: TestClient, repo: MemoryRepo) -> None:
    repo.accounts[0] = dataclasses.replace(repo.accounts[0], last_statement_to=date(2026, 9, 20))
    assert client.get("/v1/dashboard", headers=AUTH).json()["data_stale"] is True
    repo.accounts[0] = dataclasses.replace(repo.accounts[0], last_statement_to=date(2026, 9, 29))
    assert client.get("/v1/dashboard", headers=AUTH).json()["data_stale"] is False
