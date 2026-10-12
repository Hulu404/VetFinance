"""GET /v1/dashboard over the in-memory repository loaded with golden set 3 (tests/golden/set03, read only).

The numbers are compared with expected.json, which is computed independently of this code.
"""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.rows import ClinicRow
from engine.dashboard_inputs import NormsInput
from engine.vetmanager import Sale, SaleLine
from tests.conftest import FakeVetmanagerApi, build_app, make_token
from tests.memory_repo import MemoryRepo

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / "set03"
DATA = json.loads((GOLDEN / "data.json").read_text(encoding="utf-8"))
EXPECTED = {
    c["as_of"]: c for c in json.loads((GOLDEN / "expected.json").read_text("utf-8"))["cases"]
}
HEADERS = {"Authorization": f"Bearer {make_token()}"}
FORBIDDEN_WORDS = ("нейросет", "ассистент", "катастроф")


def load_set03() -> MemoryRepo:
    repo = MemoryRepo(ClinicRow("d", DATA["clinic"]["name"], None, None, "Europe/Moscow", 0))
    repo.add_connections()
    n = DATA["norms"]
    repo.norms = NormsInput(
        n["drugs"]["category"], n["drugs"]["max_pct"], n["profit_margin"]["min_pct"]
    )
    for a in DATA["accounts"]:
        repo.add_account(
            id=a["id"],
            name=a["name"],
            kind=a["type"],
            opening_balance=a["opening_balance"],
            opening_date=date.fromisoformat(a["opening_date"]),
        )
    categories = {
        name: repo.add_category(name).id
        for name in sorted({t["category"] for t in DATA["transactions"] if t["category"]})
    }
    for t in DATA["transactions"]:
        repo.add_tx(
            t["account_id"],
            date.fromisoformat(t["date"]),
            t["amount"],
            source=t["source"],
            status=t["status"],
            kind=t["kind"],
            category_id=categories.get(t["category"]),
        )
    for doctor in DATA["doctors"]:
        repo.doctors[doctor["id"]] = (f"doc-{doctor['id']}", doctor["id"], doctor["name"])
    for v in DATA["visits"]:
        repo.visits[v["id"]] = (date.fromisoformat(v["date"]), f"doc-{v['doctor_id']}")
    for s in DATA["sales"]:
        repo.sales[s["id"]] = Sale(
            s["id"],
            date.fromisoformat(s["date"]),
            s["status"],
            s["amount"],
            tuple(SaleLine(line["kind"], line["amount"]) for line in s["lines"]),
        )
    return repo


@pytest.fixture(scope="module")
def client_d() -> Iterator[TestClient]:
    from app.secrets import FernetBox

    app = build_app(load_set03(), FakeVetmanagerApi(), FernetBox(Fernet.generate_key().decode()))
    with TestClient(app) as c:
        yield c


def get(client: TestClient, as_of: str) -> dict[str, Any]:
    r = client.get("/v1/dashboard", params={"as_of": as_of}, headers=HEADERS)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def labels(figure: dict[str, Any]) -> dict[str, int]:
    return {b["label"]: b["value"] for b in figure["breakdown"]}


@pytest.mark.parametrize("as_of", sorted(EXPECTED))
def test_api_numbers_match_the_golden_set(client_d: TestClient, as_of: str) -> None:
    exp, body = EXPECTED[as_of], get(client_d, as_of)
    for key in ("total", "bank", "cash"):
        assert body["balance"][key]["value"] == exp["balance"][key]["value"], key
        assert labels(body["balance"][key]) == exp["balance"][key]["breakdown"]
        assert body["balance"][key]["source"] == exp["balance"][key]["source"]
    assert body["balance_trend"] == exp["balance_trend"]
    assert body["balance"]["runway_days"]["value"] == exp["runway_days"]["value"]
    month, exp_month = body["month"], exp["month"]
    for key in ("revenue", "expenses", "profit"):
        assert month[key]["value"] == exp_month[key]["value"], key
        assert labels(month[key]) == exp_month[key]["breakdown"], key
    assert month["profit_margin_pct"]["value"] == exp_month["profit_margin_pct"]["value"]
    assert month["avg_check"]["value"] == exp_month["avg_check"]["value"]
    assert month["visits"]["value"] == exp_month["visits"]["value"]
    assert [(a["id"], a["severity"]) for a in body["advice"]] == [
        (a["id"], a["severity"]) for a in exp["advice"]
    ]


def test_api_json_types_and_optional_keys(client_d: TestClient) -> None:
    body = get(client_d, "2026-09-09")
    assert type(body["balance"]["total"]["value"]) is int
    pct = body["balance"]["week_change_pct"]
    assert type(pct["value"]) is float and pct["value"] == 12.2 and pct["delta"] is True
    assert body["balance"]["week_change"]["delta"] is True
    assert all(b["delta"] is True for b in body["balance"]["week_change"]["breakdown"])
    assert "delta" not in body["balance"]["total"] and "details" not in body["balance"]["total"]
    assert [d["label"] for d in body["month"]["revenue"]["details"]] == ["Средний чек", "Приёмов"]
    assert body["balance_trend_info"]["source"] and body["balance_trend_info"]["note"]
    young = get(client_d, "2026-08-04")
    assert young["balance"]["week_change"] is None and "week_change" in young["balance"]
    assert young["balance"]["week_change_pct"] is None and young["advice"] == []


def test_api_advice_has_why_and_no_forbidden_words(client_d: TestClient) -> None:
    body = get(client_d, "2026-09-20")
    assert [a["severity"] for a in body["advice"]] == ["alert", "warning", "warning"]
    for advice in body["advice"]:
        assert advice["why"]["summary"] and advice["why"]["steps"] and advice["why"]["sources"]
        text = json.dumps(advice, ensure_ascii=False).lower()
        assert not any(word in text for word in FORBIDDEN_WORDS)
        for doctor in DATA["doctors"]:
            assert doctor["name"] not in text  # doctor names never go into advice texts


def test_api_as_of_outside_the_data_and_bad_values(client_d: TestClient) -> None:
    body = get(client_d, "2000-01-01")
    assert body["month"]["revenue"]["value"] == 0 and body["advice"] == []
    assert body["balance_trend"] == []
    for bad in ("garbage", "2026-13-40", ""):
        r = client_d.get("/v1/dashboard", params={"as_of": bad}, headers=HEADERS)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation", bad


def test_api_same_request_twice_is_identical(client_d: TestClient) -> None:
    assert get(client_d, "2026-09-09") == get(client_d, "2026-09-09")


def test_api_requires_authentication(client_d: TestClient) -> None:
    r = client_d.get("/v1/dashboard")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
