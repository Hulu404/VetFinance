"""Stage 5 flows: golden numbers through the API, recalculation after writes, empty clinic, Vetmanager lines."""

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from engine.vetmanager import normalize_vetmanager
from tests.memory_repo import MemoryRepo
from tests.set06_loader import EXPECTED, load_set06
from tests.test_api_pricing import HEADERS, get, items, make_client

MAIN = EXPECTED["cases"]["main"]
PARTS = ["doctor_pay", "drugs", "anesthesia", "supplies", "acquiring", "fixed", "taxes"]


@pytest.fixture
def repo() -> MemoryRepo:
    return load_set06()


@pytest.fixture
def client(repo: MemoryRepo) -> Iterator[TestClient]:
    with make_client(repo) as c:
        yield c


def by_name(client: TestClient) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in items(client, limit=200)}


def test_every_service_card_equals_the_golden_set(client: TestClient) -> None:
    rows = by_name(client)
    for want in MAIN["services"]:
        card = get(client, f"/v1/services/{rows[want['name']]['id']}/cost")
        got = {
            p["key"]: None if p["amount"] is None else p["amount"]["value"] for p in card["parts"]
        }
        assert got == {k: want["parts"][k] for k in PARTS}, want["name"]
        assert card["status"] == want["status"] and card["missing"] == want["missing"]
        assert (None if card["net_profit"] is None else card["net_profit"]["value"]) == want[
            "net_profit"
        ]


def test_the_hour_cost_and_the_load_equal_the_golden_set(client: TestClient) -> None:
    e = get(client, "/v1/efficiency")
    exp = MAIN["efficiency"]
    assert (e["hour_cost"]["value"], e["load_pct"]["value"], e["hour_margin"]["value"]) == (
        exp["hour_cost"], exp["load_pct"], exp["hour_margin"],
    )  # fmt: skip
    assert e["visits"]["value"] == exp["visits"] and e["avg_check"]["value"] == exp["avg_check"]


def test_a_saved_techcard_changes_the_card_and_the_list(client: TestClient) -> None:
    rows = by_name(client)
    s7 = rows["Чистка ушей"]
    assert s7["status"] == "no_recipe"
    stock = get(client, "/v1/stock/items", limit=200)["items"]
    glove = next(i for i in stock if i["unit_cost"] is not None)
    body = {
        "minutes": 20,
        "doctor_pct": 25,
        "items": [{"item_id": glove["id"], "group": "supplies", "qty": 2}],
    }
    assert (
        client.put(f"/v1/services/{s7['id']}/recipe", json=body, headers=HEADERS).status_code == 200
    )
    card = get(client, f"/v1/services/{s7['id']}/cost")
    assert card["status"] == "ok" and card["minutes"] == 20 and card["minutes_source"] == "own"
    assert card["net_profit"] is not None
    paid = (
        sum(p["amount"]["value"] for p in card["parts"] if p["amount"])
        + card["net_profit"]["value"]
    )
    assert paid == card["price"]["value"]
    assert by_name(client)["Чистка ушей"]["margin_pct"]["value"] == card["net_margin_pct"]["value"]
    assert get(client, "/v1/services")["counts"]["no_recipe"] == MAIN["counts"]["no_recipe"] - 1


def test_the_average_visit_length_recalculates_services_without_their_own_minutes(
    client: TestClient,
) -> None:
    rows = by_name(client)
    sid = rows["Выдача справки"]["id"]
    before = get(client, f"/v1/services/{sid}/cost")
    assert before["minutes"] == 30
    doctors = get(client, "/v1/efficiency/settings")["doctors"]
    body = {
        "avg_visit_minutes": 60,
        "doctors": [{"id": d["id"], "hours_per_week": d["hours_per_week"]} for d in doctors],
    }
    assert client.put("/v1/efficiency/settings", json=body, headers=HEADERS).status_code == 200
    after = get(client, f"/v1/services/{sid}/cost")
    assert after["minutes"] == 60
    fixed = {p["key"]: p["amount"]["value"] for p in after["parts"] if p["amount"]}["fixed"]
    assert fixed > {p["key"]: p["amount"]["value"] for p in before["parts"] if p["amount"]}["fixed"]


def test_doctor_hours_change_the_load_and_the_hour_cost(client: TestClient) -> None:
    rooms_off = get(client, "/v1/efficiency")
    assert rooms_off["load_by"] == "rooms"
    doctors = get(client, "/v1/efficiency/settings")["doctors"]
    cleared = {
        "avg_visit_minutes": 30,
        "doctors": [{"id": d["id"], "hours_per_week": None} for d in doctors],
    }
    assert client.put("/v1/efficiency/settings", json=cleared, headers=HEADERS).status_code == 200
    still = get(client, "/v1/efficiency")
    assert still["load_by"] == "rooms"  # rooms with schedules do not depend on the hours of doctors


def test_an_empty_clinic_has_no_services_and_no_crash() -> None:
    from app.rows import ClinicRow

    with make_client(MemoryRepo(ClinicRow("b", "Пустая", None, None, "Europe/Moscow", 0))) as c:
        body = get(c, "/v1/services")
        assert body["items"] == [] and body["counts"] == {"all": 0, "loss": 0, "no_recipe": 0}
        assert "headline" not in body
        e = get(c, "/v1/efficiency")
        assert (
            e["visits"]["value"] == 0
            and e["rooms"] == []
            and e["load_pct"] is None
            and e["avg_check"] is None
        )
        assert get(c, "/v1/efficiency/settings")["doctors"] == []


# ------------------------------------------------------------------ Vetmanager lines
RAW = {
    "good": {"data": {"good": [{"id": "7", "title": "Вакцинация", "is_service": "1", "group_id": "3"},
                               {"id": "8", "title": "Корм", "is_service": "0"}]}},
    "goodGroup": {"data": {"goodGroup": [{"id": "3", "title": "Терапия"}]}},
    "invoice": {"data": {"invoice": [{"id": "1", "status": "exec", "invoice_date": "2026-09-01", "amount": "3500.00"}]}},
    "invoiceDocument": {"data": {"invoiceDocument": [
        {"invoice_id": "1", "good_id": "7", "quantity": "2", "price": "1200.50"},
        {"invoice_id": "1", "good_id": "8", "quantity": "1", "price": "1099.00"},
    ]}},
}  # fmt: skip


def test_the_loader_keeps_the_name_quantity_and_price_of_service_lines() -> None:
    result = normalize_vetmanager(RAW)
    lines = result.sales[0].lines
    service, good = lines
    assert service.kind == "service" and service.amount == 240_100 and service.price == 120_050
    assert service.qty == Decimal(2) and service.name == "Вакцинация"
    assert service.service_external_id == "vetmanager:good:7"
    assert good.kind == "good" and good.service_external_id is None
    assert [(x.external_id, x.name, x.group) for x in result.services] == [
        ("vetmanager:good:7", "Вакцинация", "Терапия")
    ]


def test_old_responses_without_titles_still_load() -> None:
    raw = {**RAW, "good": {"data": {"good": [{"id": "7", "is_service": "1"}]}}}
    result = normalize_vetmanager(raw)
    assert result.services == () and result.sales[0].lines[0].amount == 240_100


async def test_the_synchronisation_stores_services_and_the_price_uses_them(
    repo: MemoryRepo,
) -> None:
    from app.services.vm_sync import store_normalized

    clean = MemoryRepo(repo.clinic)
    await store_normalized(clean, normalize_vetmanager(RAW))
    again = await store_normalized(clean, normalize_vetmanager(RAW))
    assert [s.name for s in clean.services] == ["Вакцинация"] and again[0].new == 0
    sales = await clean.list_pricing_sales(*_window())
    assert sales[0].lines[0].service_id == clean.services[0].id and sales[0].lines[
        0
    ].qty == Decimal(2)


def _window() -> tuple[Any, Any]:
    from datetime import date

    return date(2026, 1, 1), date(2026, 12, 31)


def test_a_month_without_a_statement_does_not_count_the_profit() -> None:
    repo = load_set06()
    repo.txs = []  # no bank operations and no accruals in the month: the P&L has no expenses
    repo.charges = []
    with make_client(repo) as c:
        body = get(c, "/v1/services", limit=200)
        assert body["counts"] == {"all": 11, "loss": 0, "no_recipe": 2}
        assert "Нет данных о расходах за сентябрь" in body["headline"]
        assert all(s["margin_pct"] is None and s["monthly_profit"] is None for s in body["items"])
        assert {s["status"] for s in body["items"]} == {"partial", "no_recipe"}
        card = get(c, f"/v1/services/{body['items'][0]['id']}/cost")
        assert "no_expenses" in card["missing"] and "hour_cost" in card["missing"]
        parts = {p["key"]: p for p in card["parts"]}
        assert (
            card["net_profit"] is None
            and card["net_margin_pct"] is None
            and card["monthly_profit"] is None
        )
        assert all(parts[k]["amount"] is None for k in ("acquiring", "taxes", "fixed"))
        assert get(c, "/v1/efficiency")["hour_cost"] is None


def test_the_price_of_a_list_row_has_one_line_and_the_card_has_the_split(
    client: TestClient,
) -> None:
    rows = by_name(client)
    s4 = rows["Кастрация кота"]
    assert [b["label"] for b in s4["price"]["breakdown"]] == ["Средняя цена по счетам за 90 дней"]
    assert s4["price"]["note"] == "Берём то, за сколько услугу продали, с учётом скидок."
    manual = rows["Консультация ортопеда"]
    assert [b["label"] for b in manual["price"]["breakdown"]] == ["Цена, введённая вручную"]
    assert manual["price"]["note"] == "Продаж по услуге за 90 дней нет."
    card = get(client, f"/v1/services/{s4['id']}/cost")
    assert len(card["price"]["breakdown"]) == 8 and card["price"]["value"] == s4["price"]["value"]
