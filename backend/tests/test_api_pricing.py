"""Stage 5 endpoints over the in-memory repository loaded with golden set 6 (tests/golden/set06, read only):
identities, Figures, validation, error codes, writes, isolation."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.clock import get_now
from app.pricing_input import parse_month
from app.secrets import FernetBox
from tests.conftest import FakeVetmanagerApi, build_app, make_token
from tests.memory_repo import MemoryRepo
from tests.set06_loader import EXPECTED, load_set06

HEADERS = {"Authorization": f"Bearer {make_token()}"}
UNKNOWN = "00000000-0000-4000-8000-000000000000"
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
MAIN = EXPECTED["cases"]["main"]
PART_KEYS = ["doctor_pay", "drugs", "anesthesia", "supplies", "acquiring", "fixed", "taxes"]


def make_client(repo: MemoryRepo) -> TestClient:
    app = build_app(repo, FakeVetmanagerApi(), FernetBox(Fernet.generate_key().decode()))
    app.dependency_overrides[get_now] = lambda: NOW
    return TestClient(app)


@pytest.fixture
def repo() -> MemoryRepo:
    return load_set06()


@pytest.fixture
def client(repo: MemoryRepo) -> Iterator[TestClient]:
    with make_client(repo) as c:
        yield c


def get(client: TestClient, path: str, **params: Any) -> Any:
    r = client.get(path, params=params, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def fields_of(r: Any) -> dict[str, str]:
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation"
    fields: dict[str, str] = r.json()["error"]["details"]["fields"]
    return fields


def figures(node: Any) -> Any:
    if isinstance(node, dict):
        if {"value", "unit", "breakdown", "source", "note"} <= set(node):
            yield node
        for v in node.values():
            yield from figures(v)
    elif isinstance(node, list):
        for v in node:
            yield from figures(v)


def items(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = get(client, "/v1/services", **params)["items"]
    return rows


def test_every_figure_has_a_breakdown_that_adds_up(client: TestClient) -> None:
    cards = [get(client, f"/v1/services/{s['id']}/cost") for s in items(client)]
    bodies = [
        get(client, "/v1/services"),
        get(client, "/v1/efficiency"),
        get(client, "/v1/stock/items"),
        *cards,
    ]
    count = 0
    for fig in (f for body in bodies for f in figures(body)):
        count += 1
        assert fig["note"].strip() and fig["source"]
        assert fig["breakdown"] or (fig["unit"] == "rub" and fig["value"] == 0)
        if (
            fig["unit"] in ("rub", "count")
            and all(b["unit"] == fig["unit"] for b in fig["breakdown"])
            and fig["breakdown"]
        ):
            assert sum(b["value"] for b in fig["breakdown"]) == fig["value"], fig
    assert count > 200


def test_cost_cards_add_up_to_the_price_and_shares_to_100(client: TestClient) -> None:
    for s in items(client):
        c = get(client, f"/v1/services/{s['id']}/cost")
        assert [p["key"] for p in c["parts"]] == PART_KEYS
        if c["net_profit"] is None:
            assert (
                c["status"] == "no_recipe"
                and c["net_margin_pct"] is None
                and c["monthly_profit"] is None
            )
            continue
        amounts = [p["amount"]["value"] for p in c["parts"] if p["amount"] is not None]
        assert sum(amounts) + c["net_profit"]["value"] == c["price"]["value"]
        shares = sum(p["share_pct"]["value"] for p in c["parts"] if p["share_pct"] is not None)
        assert round((shares + c["net_margin_pct"]["value"]) * 10) == 1000
        assert c["net_margin_pct"]["value"] == s["margin_pct"]["value"]
        assert c["monthly_profit"]["value"] == c["net_profit"]["value"] * s["visits_month"]["value"]
        assert [b["value"] for b in c["price"]["breakdown"]][-1] == c["net_profit"]["value"]


def test_status_and_missing_agree_with_the_cards(client: TestClient) -> None:
    for s in items(client):
        c = get(client, f"/v1/services/{s['id']}/cost")
        assert c["status"] == s["status"]
        assert (c["status"] == "ok") == (c["missing"] == [])
        assert (c["status"] == "no_recipe") == ("recipe" in c["missing"])
        assert c["minutes_source"] in ("own", "clinic_average")
    by_name = {s["name"]: s for s in items(client)}
    assert (
        get(client, f"/v1/services/{by_name['Выдача справки']['id']}/cost")["minutes_source"]
        == "clinic_average"
    )


def test_list_envelope_counts_and_default_order(client: TestClient) -> None:
    body = get(client, "/v1/services")
    assert (
        body["counts"] == {"all": 11, "loss": 1, "no_recipe": 2}
        and body["basis_month"] == "2026-09"
    )
    assert body["headline"] and body["next_cursor"] is None
    rated = [s for s in body["items"] if s["margin_pct"] is not None]
    assert body["items"][: len(rated)] == rated
    margins = [s["margin_pct"]["value"] for s in rated]
    assert margins == sorted(margins)
    assert all(s["margin_pct"] is None for s in body["items"][len(rated) :])
    assert all((s["margin_pct"] is None) == (s["status"] == "no_recipe") for s in body["items"])


def test_desc_order_keeps_services_without_margin_last(client: TestClient) -> None:
    desc = items(client, order="desc")
    rated = [s for s in desc if s["margin_pct"] is not None]
    values = [s["margin_pct"]["value"] for s in rated]
    assert values == sorted(values, reverse=True) and desc[len(rated) :] == [
        s for s in desc if s["margin_pct"] is None
    ]
    by_profit = items(client, sort="profit")
    profits = [s["monthly_profit"]["value"] for s in by_profit if s["monthly_profit"] is not None]
    assert profits == sorted(profits)


def test_filters_search_and_paging(client: TestClient) -> None:
    assert [s["name"] for s in items(client, filter="loss")] == ["Стационар, сутки"]
    assert all(s["status"] == "no_recipe" for s in items(client, filter="no_recipe"))
    assert [s["name"] for s in items(client, q="  чистка   УШЕЙ ")] == ["Чистка ушей"]
    whole = items(client, limit=200)
    first = get(client, "/v1/services", limit=4)
    second = get(client, "/v1/services", limit=4, cursor=first["next_cursor"])
    third = get(client, "/v1/services", limit=4, cursor=second["next_cursor"])
    assert third["next_cursor"] is None
    assert [s["id"] for s in first["items"] + second["items"] + third["items"]] == [
        s["id"] for s in whole
    ]


@pytest.mark.parametrize(
    "bad,field",
    [
        ({"as_of": "2026-13-01"}, "as_of"),
        ({"as_of": "вчера"}, "as_of"),
        ({"sort": "price;drop"}, "sort"),
        ({"sort": "-"}, "sort"),
        ({"order": "up"}, "order"),
        ({"filter": "всё"}, "filter"),
        ({"limit": "0"}, "limit"),
        ({"limit": "x"}, "limit"),
        ({"limit": "201"}, "limit"),
        ({"cursor": "abc"}, "cursor"),
    ],
)
def test_invalid_list_parameters(client: TestClient, bad: dict[str, str], field: str) -> None:
    r = client.get("/v1/services", params=bad, headers=HEADERS)
    assert field in fields_of(r)


def test_unknown_service_is_404_and_no_token_is_401(client: TestClient) -> None:
    for path in (
        f"/v1/services/{UNKNOWN}/cost",
        f"/v1/services/{UNKNOWN}/recipe",
        "/v1/services/нет-такой/cost",
    ):
        r = client.get(path, headers=HEADERS)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    for method, path in (
        ("GET", "/v1/services"),
        ("POST", "/v1/services"),
        ("PUT", f"/v1/services/{UNKNOWN}/recipe"),
        ("PATCH", f"/v1/services/{UNKNOWN}"),
        ("DELETE", f"/v1/services/{UNKNOWN}"),
        ("GET", "/v1/efficiency"),
        ("PUT", "/v1/efficiency/settings"),
        ("GET", "/v1/stock/items"),
    ):
        r = client.request(method, path, json={})
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized", (method, path)


# ------------------------------------------------------------------ manual services
@pytest.mark.parametrize(
    "body,field,reason",
    [
        ({"price": 100_000}, "name", "required"),
        ({"name": "", "price": 100_000}, "name", "required"),
        ({"name": "я" * 121, "price": 100_000}, "name", "too_long"),
        ({"name": "Т", "group": "г" * 81, "price": 1}, "group", "too_long"),
        ({"name": "Т"}, "price", "required"),
        ({"name": "Т", "price": 0}, "price", "must_be_positive"),
        ({"name": "Т", "price": -5}, "price", "must_be_positive"),
        ({"name": "Т", "price": 10.5}, "price", "invalid"),
        ({"name": "Т", "price": 10**13}, "price", "too_large"),
        ({"name": "Т", "price": 1, "x": 1}, "x", "unknown_field"),
        ({"name": "  чистка УШЕЙ ", "price": 1}, "name", "duplicate_name"),
    ],
)
def test_post_service_validation(
    client: TestClient, body: dict[str, Any], field: str, reason: str
) -> None:
    assert fields_of(client.post("/v1/services", json=body, headers=HEADERS))[field] == reason


def test_post_service_answers_201_with_a_list_item(client: TestClient) -> None:
    r = client.post(
        "/v1/services",
        json={"name": "Груминг: стрижка", "group": "Груминг", "price": 180_000},
        headers=HEADERS,
    )
    assert r.status_code == 201
    body = r.json()
    assert (
        body["source"] == "manual" and body["status"] == "no_recipe" and body["margin_pct"] is None
    )
    assert body["price"]["value"] == 180_000 and body["visits_month"]["value"] == 0 and body["id"]


def test_only_manual_services_can_be_changed(client: TestClient) -> None:
    by_name = {s["name"]: s for s in items(client)}
    vm, manual = by_name["Стационар, сутки"], by_name["Консультация ортопеда"]
    assert manual["source"] == "manual" and vm["source"] == "vetmanager"
    for r in (
        client.delete(f"/v1/services/{vm['id']}", headers=HEADERS),
        client.patch(f"/v1/services/{vm['id']}", json={"price": 1}, headers=HEADERS),
    ):
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    path = f"/v1/services/{manual['id']}"
    assert (
        fields_of(client.patch(path, json={"price": 0}, headers=HEADERS))["price"]
        == "must_be_positive"
    )
    assert (
        fields_of(client.patch(path, json={"name": "ЧИСТКА ушей"}, headers=HEADERS))["name"]
        == "duplicate_name"
    )
    assert (
        client.patch(f"/v1/services/{UNKNOWN}", json={"price": 1}, headers=HEADERS).status_code
        == 404
    )
    assert (
        client.patch(
            path, json={"price": 150_000, "name": "Консультация ортопеда 2"}, headers=HEADERS
        ).status_code
        == 204
    )
    changed = next(s for s in items(client) if s["id"] == manual["id"])
    assert changed["price"]["value"] == 150_000 and changed["name"] == "Консультация ортопеда 2"
    assert client.delete(path, headers=HEADERS).status_code == 204
    assert manual["id"] not in [s["id"] for s in items(client)]
    assert client.delete(path, headers=HEADERS).status_code == 404


def test_created_service_is_in_the_list_and_duplicates_are_refused(client: TestClient) -> None:
    body = {"name": "Груминг: стрижка", "group": "Груминг", "price": 180_000}
    r = client.post("/v1/services", json=body, headers=HEADERS)
    assert r.status_code == 201
    row = next(s for s in items(client) if s["id"] == r.json()["id"])
    assert (
        row["price"]["value"] == 180_000
        and row["status"] == "no_recipe"
        and row["source"] == "manual"
    )
    assert (
        fields_of(client.post("/v1/services", json=body, headers=HEADERS))["name"]
        == "duplicate_name"
    )
    assert get(client, "/v1/services")["counts"]["all"] == MAIN["counts"]["all"] + 1


# ------------------------------------------------------------------ techcard
def recipe_target(client: TestClient) -> tuple[str, str]:
    s4 = next(s for s in items(client) if s["name"] == "Кастрация кота")["id"]
    stock = get(client, "/v1/stock/items")["items"][0]["id"]
    return s4, stock


def test_get_recipe_has_the_defaults_and_priced_items(client: TestClient) -> None:
    sid, _ = recipe_target(client)
    r = get(client, f"/v1/services/{sid}/recipe")
    assert (
        r["has_recipe"] and r["minutes"] == 60 and r["doctor_pct"] == 30.0 and len(r["items"]) == 8
    )
    assert r["defaults"]["minutes"]["value"] == 30 and r["defaults"]["doctor_pct"]["unit"] == "pct"
    assert all(i["unit_cost"] is not None for i in r["items"])
    none = next(s for s in items(client) if s["name"] == "Выдача справки")["id"]
    empty = get(client, f"/v1/services/{none}/recipe")
    assert not empty["has_recipe"] and empty["minutes"] is None and empty["items"] == []


@pytest.mark.parametrize(
    "body,key,reason",
    [
        ({"minutes": 0, "items": []}, "minutes", "out_of_range"),
        ({"minutes": 1441, "items": []}, "minutes", "out_of_range"),
        ({"minutes": 12.5, "items": []}, "minutes", "invalid"),
        ({"items": []} | {"doctor_pct": 101}, "doctor_pct", "out_of_range"),
        ({"doctor_pct": 10.123, "items": []}, "doctor_pct", "too_many_decimals"),
        ({"minutes": 5}, "items", "required"),
        (
            {"items": [{"item_id": UNKNOWN, "group": "drugs", "qty": 1}]},
            "items.0.item_id",
            "unknown_item",
        ),
        (
            {"items": [{"item_id": UNKNOWN, "group": "sweets", "qty": 1}]},
            "items.0.group",
            "invalid",
        ),
        (
            {"items": [{"item_id": UNKNOWN, "group": "drugs", "qty": 0}]},
            "items.0.qty",
            "must_be_positive",
        ),
        (
            {"items": [{"item_id": UNKNOWN, "group": "drugs", "qty": 1.2345}]},
            "items.0.qty",
            "too_many_decimals",
        ),
        ({"items": [{"item_id": UNKNOWN, "group": "drugs"}]}, "items.0.qty", "required"),
        (
            {"items": [{"item_id": UNKNOWN, "group": "drugs", "qty": 1, "x": 1}]},
            "items.0.x",
            "unknown_field",
        ),
        ({"items": [], "lines": []}, "lines", "unknown_field"),
    ],
)
def test_put_recipe_validation(
    client: TestClient, body: dict[str, Any], key: str, reason: str
) -> None:
    sid, _ = recipe_target(client)
    assert (
        fields_of(client.put(f"/v1/services/{sid}/recipe", json=body, headers=HEADERS))[key]
        == reason
    )


def test_put_recipe_rules_for_duplicates_and_size(client: TestClient) -> None:
    sid, stock = recipe_target(client)
    line = {"item_id": stock, "group": "drugs", "qty": 1}
    assert (
        fields_of(
            client.put(f"/v1/services/{sid}/recipe", json={"items": [line, line]}, headers=HEADERS)
        )["items.1.item_id"]
        == "duplicate_item"
    )
    many = [line] * 31
    assert (
        fields_of(client.put(f"/v1/services/{sid}/recipe", json={"items": many}, headers=HEADERS))[
            "items"
        ]
        == "out_of_range"
    )


def test_put_recipe_accepts_a_valid_body_and_an_empty_techcard(client: TestClient) -> None:
    sid, stock = recipe_target(client)
    body = {
        "minutes": None,
        "doctor_pct": 12.5,
        "items": [{"item_id": stock, "group": "supplies", "qty": 0.125}],
    }
    r = client.put(f"/v1/services/{sid}/recipe", json=body, headers=HEADERS)
    assert r.status_code == 200 and r.json()["has_recipe"] and r.json()["items"][0]["qty"] == 0.125
    assert r.json()["minutes"] is None and r.json()["doctor_pct"] == 12.5
    empty = client.put(f"/v1/services/{sid}/recipe", json={"items": []}, headers=HEADERS)
    assert empty.status_code == 200 and empty.json()["has_recipe"] and empty.json()["items"] == []


def test_put_recipe_of_an_unknown_service_is_404_before_the_body_is_checked(
    client: TestClient,
) -> None:
    r = client.put(f"/v1/services/{UNKNOWN}/recipe", json={"lines": []}, headers=HEADERS)
    assert r.status_code == 404


def test_stock_items_search_and_unit_cost(client: TestClient) -> None:
    body = get(client, "/v1/stock/items", limit=200)
    assert len(body["items"]) == 16 and sum(1 for i in body["items"] if i["unit_cost"] is None) == 1
    first = body["items"][0]["name"]
    assert get(client, "/v1/stock/items", q=first.upper())["items"][0]["name"] == first
    assert (
        fields_of(client.get("/v1/stock/items", params={"limit": 0}, headers=HEADERS))["limit"]
        == "must_be_positive"
    )


# ------------------------------------------------------------------ efficiency
def test_efficiency_identities_of_the_example(client: TestClient) -> None:
    e = get(client, "/v1/efficiency")
    assert (
        e["load_by"] == "rooms"
        and e["status"] == "ok"
        and e["partial_reasons"] == []
        and e["doctors"] == []
    )
    assert e["period"]["month"] == "2026-09" and e["period"]["status"] == "closed"
    assert sum(r["available_hours"]["value"] for r in e["rooms"]) == 690
    assert sum(r["busy_hours"]["value"] for r in e["rooms"]) == 146
    assert sum(r["free_hours"]["value"] for r in e["rooms"]) == 690 - 146
    assert [b["value"] for b in e["load_pct"]["breakdown"]] == [146, 690]
    assert sum(b["value"] for b in e["hour_cost"]["breakdown"]) == e["hour_cost"]["value"]
    assert [p["key"] for p in e["hour_cost_parts"]] == [
        "hours",
        "busy_hours",
        "fixed",
        "obligations",
    ]
    parts = {p["key"]: p["figure"]["value"] for p in e["hour_cost_parts"]}
    assert parts["fixed"] + parts["obligations"] == 31_840_000


@pytest.mark.parametrize(
    "bad,field",
    [
        ({"month": "2026-13"}, "month"),
        ({"month": "август"}, "month"),
        ({"month": "2999-01"}, "month"),
        ({"month": "2026-10", "as_of": "2026-10-05"}, "month"),
        ({"as_of": "2026-02-30"}, "as_of"),
    ],
)
def test_invalid_efficiency_parameters(client: TestClient, bad: dict[str, str], field: str) -> None:
    assert field in fields_of(client.get("/v1/efficiency", params=bad, headers=HEADERS))


def test_efficiency_accepts_the_last_closed_month(client: TestClient) -> None:
    assert get(client, "/v1/efficiency", month="2026-09", as_of="2026-10-01")["month"] == "2026-09"


def test_efficiency_settings_roundtrip_and_validation(client: TestClient) -> None:
    s = get(client, "/v1/efficiency/settings")
    assert s["avg_visit_minutes"] == 30 and len(s["doctors"]) == 3
    doctor = s["doctors"][0]["id"]
    ok = client.put(
        "/v1/efficiency/settings",
        json={"avg_visit_minutes": 20, "doctors": [{"id": doctor, "hours_per_week": 38.5}]},
        headers=HEADERS,
    )
    assert (
        ok.status_code == 200
        and ok.json()["avg_visit_minutes"] == 20
        and ok.json()["doctors"][0]["hours_per_week"] == 38.5
    )
    cleared = client.put(
        "/v1/efficiency/settings",
        json={"avg_visit_minutes": 20, "doctors": [{"id": doctor, "hours_per_week": None}]},
        headers=HEADERS,
    )
    assert cleared.json()["doctors"][0]["hours_per_week"] is None
    for body, key, reason in (
        ({}, "avg_visit_minutes", "required"),
        ({"avg_visit_minutes": 4}, "avg_visit_minutes", "out_of_range"),
        ({"avg_visit_minutes": 241}, "avg_visit_minutes", "out_of_range"),
        ({"avg_visit_minutes": 5.5}, "avg_visit_minutes", "invalid"),
        (
            {"avg_visit_minutes": 30, "doctors": [{"id": doctor, "hours_per_week": 81}]},
            "doctors.0.hours_per_week",
            "out_of_range",
        ),
        (
            {"avg_visit_minutes": 30, "doctors": [{"id": doctor, "hours_per_week": 36.25}]},
            "doctors.0.hours_per_week",
            "too_many_decimals",
        ),
        (
            {"avg_visit_minutes": 30, "doctors": [{"id": doctor, "hours_per_week": 36.3}]},
            "doctors.0.hours_per_week",
            "invalid",
        ),
        ({"avg_visit_minutes": 30, "doctors": [{"id": UNKNOWN}]}, "doctors.0.id", "invalid"),
        ({"avg_visit_minutes": 30, "x": 1}, "x", "unknown_field"),
    ):
        assert (
            fields_of(client.put("/v1/efficiency/settings", json=body, headers=HEADERS))[key]
            == reason
        ), body


def test_parse_month() -> None:
    assert parse_month(None) is None and parse_month("2026-09") == "2026-09"


def test_categories_carry_the_stage_5_flags(client: TestClient) -> None:
    body = {c["name"]: c for c in get(client, "/v1/categories")["items"]}
    assert body["Расходные материалы"]["in_service_recipes"]
    assert not body["Аренда и коммуналка"]["in_service_recipes"]
    assert body["Проценты врачам"]["doctor_percent"] and not body["Налоги"]["doctor_percent"]
