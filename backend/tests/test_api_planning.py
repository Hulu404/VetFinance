"""Stage 4 endpoints over the in-memory repository loaded with golden set 5 (tests/golden/set05, read only).

Numbers are compared with expected.json (computed independently of this code); shapes, identities, validation,
authentication, the changes of obligations and the advice `cash_gap` are checked here.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.schemas import FigureOut
from app.secrets import FernetBox
from tests.conftest import FakeVetmanagerApi, build_app, make_token
from tests.memory_repo import MemoryRepo
from tests.set05_loader import EXPECTED, load_set05

HEADERS = {"Authorization": f"Bearer {make_token()}"}
UNKNOWN = "00000000-0000-4000-8000-000000000000"
AS_OF = EXPECTED["as_of"]
MAIN = EXPECTED["calendar"]["main"]
OBL = EXPECTED["obligations"]
LOAN = {
    "kind": "loan",
    "name": "Кредит",
    "principal": 10_000_000,
    "remaining": 10_000_000,
    "rate_pct": 12.0,
    "payment": 900_000,
    "payment_day": 15,
}
EQUIPMENT = {
    "kind": "equipment",
    "name": "Центрифуга",
    "cost": 3_600_000,
    "life_years": 3,
    "in_service_from": "2026-09-10",
}


def make_client(repo: MemoryRepo) -> TestClient:
    app = build_app(repo, FakeVetmanagerApi(), FernetBox(Fernet.generate_key().decode()))
    return TestClient(app)


@pytest.fixture
def repo() -> MemoryRepo:
    return load_set05()


@pytest.fixture
def client(repo: MemoryRepo) -> Iterator[TestClient]:
    with make_client(repo) as c:
        yield c


def get(client: TestClient, path: str, **params: Any) -> Any:
    r = client.get(path, params=params, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def figures(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if {"value", "unit", "breakdown"} <= set(node):
            yield node
        for v in node.values():
            yield from figures(v)
    elif isinstance(node, list):
        for v in node:
            yield from figures(v)


# ------------------------------------------------------------------ calendar
def test_calendar_equals_the_golden_set(client: TestClient) -> None:
    cal = get(client, "/v1/calendar", as_of=AS_OF)
    assert cal["window"] == {"from": AS_OF, "to": "2026-10-28"}
    assert cal["status"] == "ok" and cal["partial_reasons"] == [] and cal["history_days"] == 190
    assert cal["safe_balance"]["value"] == 15_000_000 and cal["safe_balance_set"] is True
    assert (
        cal["start_balance"]["value"]
        == MAIN["opening"]["value"]
        == cal["days"][0]["opening"]["value"]
    )
    for got, exp in zip(cal["days"], MAIN["days"], strict=True):
        assert (got["date"], got["opening"]["value"], got["income_forecast"]["value"]) == (
            exp["date"],
            exp["opening"],
            exp["income_forecast"],
        )
        assert got["closing"]["value"] == exp["closing"] and got["status"] == exp["status"]
        assert [
            (p["name"], p["amount"]["value"], p["source"], p["balance_after"]["value"])
            for p in got["payments"]
        ] == [(p["name"], p["amount"], p["source"], p["balance_after"]) for p in exp["payments"]]
    s, e = cal["summary"], MAIN["summary"]
    assert (s["income"]["value"], s["expense"]["value"], s["payments_count"]) == (
        e["income"],
        e["expense"],
        e["payments_count"],
    )
    assert s["lowest"]["date"] == e["lowest"]["date"] and s["lowest"]["status"] == "below_safe"


def test_alert_and_suggestion(client: TestClient) -> None:
    (alert,) = get(client, "/v1/calendar", as_of=AS_OF)["alerts"]
    exp = MAIN["alerts"][0]
    assert (alert["date"], alert["date_to"], alert["severity"]) == (
        exp["date"],
        exp["end_date"],
        "warning",
    )
    assert alert["shortfall"]["value"] == exp["shortfall"]
    s = alert["suggestion"]
    assert (s["payment_name"], s["amount"]["value"], s["from_date"], s["to_date"]) == (
        exp["suggestion"]["name"],
        exp["suggestion"]["amount"],
        exp["suggestion"]["from"],
        exp["suggestion"]["to"],
    )
    assert s["closes_gap"] is True and s["lowest_after"]["value"] == exp["after_lowest"]["closing"]
    assert alert["text"] and s["text"] not in alert["text"]


def test_every_figure_is_valid_and_adds_up(client: TestClient) -> None:
    for path in ("/v1/calendar", "/v1/obligations"):
        for fig in figures(get(client, path, as_of=AS_OF)):
            FigureOut.model_validate(fig)
            assert fig["note"] and fig["source"]
            rub = fig["unit"] == "rub" and all(b["unit"] == "rub" for b in fig["breakdown"])
            if rub and (fig["breakdown"] or fig["value"] != 0):
                assert sum(b["value"] for b in fig["breakdown"]) == fig["value"], fig["note"]


def test_preview_moves_the_payment_and_closes_the_gap(client: TestClient) -> None:
    cal = get(client, "/v1/calendar", as_of=AS_OF)
    sid = cal["alerts"][0]["suggestion"]["id"]
    prev = get(client, "/v1/calendar", as_of=AS_OF, preview=sid)
    assert [d["closing"]["value"] for d in prev["days"]] == [
        x["closing"] for x in MAIN["alerts"][0]["after"]
    ]
    assert prev["alerts"] == [] and prev["preview"]["suggestion_id"] == sid
    moved = [p for d in prev["days"] for p in d["payments"] if p.get("moved_from")]
    assert [p["moved_from"] for p in moved] == ["2026-10-07"]
    assert cal["preview"] is None


@pytest.mark.parametrize(
    "params", [{"days": "21"}, {"days": "x"}, {"as_of": "2026-13-01"}, {"preview": "nope"}]
)
def test_bad_parameters(client: TestClient, params: dict[str, str]) -> None:
    r = client.get("/v1/calendar", params=params, headers=HEADERS)
    assert r.status_code == 422 and set(r.json()["error"]["details"]["fields"]) == set(params)


def test_as_of_before_the_data_still_gives_22_consistent_days(client: TestClient) -> None:
    cal = get(client, "/v1/calendar", as_of="2020-01-01")
    assert len(cal["days"]) == 22
    for d in cal["days"]:
        paid = sum(p["amount"]["value"] for p in d["payments"])
        assert d["opening"]["value"] + d["income_forecast"]["value"] - paid == d["closing"]["value"]


def test_deferral_of_the_counterparty_changes_the_suggestion(client: TestClient) -> None:
    r = client.patch(
        "/v1/counterparties/5003012345", json={"max_deferral_days": 0}, headers=HEADERS
    )
    assert r.status_code == 200 and r.json() == {
        "id": "5003012345",
        "name": "ООО «Зоовет»",
        "max_deferral_days": 0,
    }
    alert = get(client, "/v1/calendar", as_of=AS_OF)["alerts"][0]
    assert (
        alert["suggestion"] is None
        and "Перенос одного платежа разрыв не закрывает" in alert["text"]
    )
    zoovet = [
        p["counterparty"]["id"]
        for d in get(client, "/v1/calendar", as_of=AS_OF)["days"]
        for p in d["payments"]
        if p["counterparty"]
    ]
    assert "5003012345" in zoovet


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"max_deferral_days": 31}, "out_of_range"),
        ({"max_deferral_days": "5"}, "invalid"),
        ({}, "required"),
    ],
)
def test_deferral_validation_and_unknown_counterparty(
    client: TestClient, body: dict[str, Any], reason: str
) -> None:
    r = client.patch("/v1/counterparties/5003012345", json=body, headers=HEADERS)
    assert (
        r.status_code == 422
        and r.json()["error"]["details"]["fields"]["max_deferral_days"] == reason
    )
    r = client.patch("/v1/counterparties/0000", json={"max_deferral_days": 1}, headers=HEADERS)
    assert r.status_code == 404


def test_manual_payment_lifecycle(client: TestClient) -> None:
    ok = {
        "name": "Реклама",
        "amount": 1_500_000,
        "date": "2026-10-10",
    }  # today in the tests is 2026-09-30
    r = client.post("/v1/calendar/payments", json=ok, headers=HEADERS)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["amount"]["value"] == 1_500_000 and created["source"] == "manual"
    cal = get(client, "/v1/calendar", as_of=AS_OF)
    hit = [p for d in cal["days"] for p in d["payments"] if p["id"] == created["id"]]
    assert len(hit) == 1 and hit[0]["source"] == "manual"
    assert (
        client.delete(f"/v1/calendar/payments/{created['id']}", headers=HEADERS).status_code == 204
    )
    assert (
        client.delete(f"/v1/calendar/payments/{created['id']}", headers=HEADERS).status_code == 404
    )
    assert client.delete(f"/v1/calendar/payments/{UNKNOWN}", headers=HEADERS).status_code == 404


def test_manual_payment_validation(client: TestClient) -> None:
    bad = {
        "name": "",
        "amount": 0,
        "date": "2027-01-01",
        "category_id": UNKNOWN,
        "max_deferral_days": 99,
    }
    r = client.post("/v1/calendar/payments", json=bad, headers=HEADERS)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["fields"] == {
        "name": "required",
        "amount": "must_be_positive",
        "max_deferral_days": "out_of_range",
        "date": "out_of_window",
        "category_id": "invalid",
    }


# ------------------------------------------------------------------ obligations
def test_obligations_equal_the_golden_set(client: TestClient) -> None:
    ob = get(client, "/v1/obligations", as_of=AS_OF)
    assert (
        ob["debt_total"]["value"],
        ob["monthly_payment"]["value"],
        ob["amortization_month"]["value"],
    ) == (
        OBL["debt_total"],
        OBL["monthly_payment"],
        OBL["amortization_month"],
    )
    assert ob["pnl_month"] == {"month": "2026-10", "amount": ob["pnl_month"]["amount"]}
    assert ob["pnl_month"]["amount"]["value"] == OBL["charges_month"]["total"]
    loans = {x["name"]: x for x in ob["loans"]}
    for e in OBL["loans"]:
        g = loans[e["name"]]
        assert (
            g["remaining"]["value"],
            g["payment"]["value"],
            g["paid_pct"]["value"],
            g["last_payment_month"],
        ) == (
            e["remaining"],
            e["payment"],
            e["paid_pct"],
            e["until"],
        )
        assert g["status"] == "active" and g["closed_from"] is None
    eq = {x["name"]: x for x in ob["equipment"]}
    assert eq["Автоклав"]["status"] == "paid"
    assert [x["status"] for x in ob["equipment"]][-1] == "paid"


def test_obligations_land_in_the_pnl_row(client: TestClient) -> None:
    for month, as_of in (("2026-10", AS_OF), ("2026-09", "2026-10-07")):
        pnl = get(client, "/v1/reports/pnl", month=month, as_of=as_of)
        row = {r["key"]: r for r in pnl["rows"]}["obligations"]
        assert row["amount"]["value"] == EXPECTED["pnl_obligations_row"][month]
        assert "warning" not in row


def test_create_equipment_changes_obligations_calendar_pnl(client: TestClient) -> None:
    before = get(client, "/v1/obligations", as_of=AS_OF)
    r = client.post("/v1/obligations", json=EQUIPMENT, headers=HEADERS)
    assert r.status_code == 201, r.text
    item = r.json()
    assert (
        item["kind"] == "equipment"
        and item["monthly"]["value"] == 100_000
        and item["status"] == "active"
    )
    after = get(client, "/v1/obligations", as_of=AS_OF)
    assert after["amortization_month"]["value"] - before["amortization_month"]["value"] == 100_000
    pnl = get(client, "/v1/reports/pnl", month="2026-10", as_of=AS_OF)
    assert {r["key"]: r for r in pnl["rows"]}["obligations"]["amount"]["value"] == OBL[
        "charges_month"
    ]["total"] + 100_000


def test_create_loan_stands_in_the_calendar_and_closing_removes_it(client: TestClient) -> None:
    item = client.post("/v1/obligations", json=LOAN, headers=HEADERS).json()
    assert (
        item["kind"] == "loan"
        and item["next_payment_date"] == "2026-10-15"
        and item["remaining"]["value"] == 10_000_000
    )
    before = get(client, "/v1/calendar", as_of=AS_OF)
    hits = [
        (d["date"], p) for d in before["days"] for p in d["payments"] if p["name"] == LOAN["name"]
    ]
    assert [h[0] for h in hits] == ["2026-10-15"] and hits[0][1]["source"] == "obligation"
    assert hits[0][1]["amount"]["value"] == 900_000
    assert client.delete(f"/v1/obligations/{item['id']}", headers=HEADERS).status_code == 204
    after = get(client, "/v1/calendar", as_of=AS_OF)
    assert not [p for d in after["days"] for p in d["payments"] if p["name"] == LOAN["name"]]
    closed = {x["id"]: x for x in get(client, "/v1/obligations", as_of=AS_OF)["loans"]}[item["id"]]
    assert (
        closed["status"] == "closed"
        and closed["closed_from"] == "2026-09"
        and closed["remaining"]["value"] == 0
    )
    assert client.delete(f"/v1/obligations/{item['id']}", headers=HEADERS).status_code == 404


def test_patch_keeps_the_past_months_of_the_report(client: TestClient) -> None:
    august = get(
        client, "/v1/reports/pnl", month="2026-08", as_of=AS_OF
    )  # today in the tests is 2026-09-30
    r = client.patch("/v1/obligations/S5-eq-us", json={"cost": 84_000_000}, headers=HEADERS)
    assert r.status_code == 200 and r.json()["monthly"]["value"] == 1_000_000
    assert get(client, "/v1/reports/pnl", month="2026-08", as_of=AS_OF)["rows"] == august["rows"]
    october = get(client, "/v1/reports/pnl", month="2026-10", as_of=AS_OF)
    assert {r["key"]: r for r in october["rows"]}["obligations"]["amount"]["value"] == OBL[
        "charges_month"
    ]["total"] - 1_000_000


def test_patch_debt_terms_validates_against_the_stored_loan(client: TestClient) -> None:
    r = client.patch("/v1/obligations/S5-loan", json={"payment": 100_000}, headers=HEADERS)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["fields"] == {"payment": "payment_below_interest"}
    assert r.json()["error"]["details"]["interest"] > 100_000


@pytest.mark.parametrize(
    ("body", "field", "reason"),
    [
        ({}, "kind", "required"),
        ({"kind": "mortgage"}, "kind", "invalid"),
        ({**EQUIPMENT, "cost": 0}, "cost", "must_be_positive"),
        ({**EQUIPMENT, "cost": 1.5}, "cost", "invalid"),
        ({**EQUIPMENT, "name": "я" * 81}, "name", "too_long"),
        ({**EQUIPMENT, "life_years": 31}, "life_years", "out_of_range"),
        ({**EQUIPMENT, "in_service_from": "2099-01-01"}, "in_service_from", "in_future"),
        ({**EQUIPMENT, "clinic_id": UNKNOWN}, "clinic_id", "unknown_field"),
        ({**LOAN, "payment_day": 32}, "payment_day", "out_of_range"),
        ({**LOAN, "rate_pct": 12.345}, "rate_pct", "too_many_decimals"),
        ({**LOAN, "remaining": 20_000_000}, "remaining", "remaining_gt_principal"),
        ({**LOAN, "payment": 50_000}, "payment", "payment_below_interest"),
    ],
)
def test_post_obligation_reasons(
    client: TestClient, body: dict[str, Any], field: str, reason: str
) -> None:
    r = client.post("/v1/obligations", json=body, headers=HEADERS)
    assert r.status_code == 422
    details = r.json()["error"]["details"]
    assert details["fields"][field] == reason
    if reason == "payment_below_interest":
        assert details["interest"] == 100_000  # 10 000 000 x 12% / 12


def test_unknown_obligation_is_404_and_patch_kind_is_invalid(client: TestClient) -> None:
    ghost = f"/v1/obligations/{UNKNOWN}"
    for r in (
        client.patch(ghost, json={"name": "x"}, headers=HEADERS),
        client.delete(ghost, headers=HEADERS),
    ):
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.patch("/v1/obligations/S5-eq-us", json={"kind": "loan"}, headers=HEADERS)
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"] == {"kind": "invalid"}


# ------------------------------------------------------------------ dashboard
def test_dashboard_has_the_cash_gap_advice_with_a_link(client: TestClient) -> None:
    dash = get(client, "/v1/dashboard", as_of=AS_OF)
    gap = next(a for a in dash["advice"] if a["id"] == "cash_gap")
    assert (
        gap["link"] == {"path": "/planning/calendar", "date": "2026-10-09"}
        and gap["icon"] == "\U0001f4c5"
    )
    alert = get(client, "/v1/calendar", as_of=AS_OF)["alerts"][0]
    assert (gap["title"], gap["why"], gap["severity"]) == (
        alert["title"],
        alert["why"],
        alert["severity"],
    )
    assert (
        gap["text"] == f"{alert['text']} {alert['suggestion']['text']}" and len(gap["text"]) <= 200
    )
    assert len(dash["advice"]) <= 5
    assert not [a for a in dash["advice"] if a["id"] != "cash_gap" and "link" in a]


def test_dashboard_without_a_gap_has_no_cash_gap() -> None:
    with make_client(load_set05(safe_balance=0)) as c:
        dash = get(c, "/v1/dashboard", as_of=AS_OF)
    assert all(a["id"] != "cash_gap" for a in dash["advice"])


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/v1/calendar"),
        ("get", "/v1/obligations"),
        ("delete", f"/v1/obligations/{UNKNOWN}"),
        ("patch", "/v1/counterparties/1"),
    ],
)
def test_planning_needs_a_token(client: TestClient, method: str, path: str) -> None:
    assert getattr(client, method)(path).status_code == 401
