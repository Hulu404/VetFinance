"""Stage 2 contract tests: the full GET /v1/dashboard (docs/api-contract.md, "Рабочий стол").

Every Figure must carry a breakdown and a source (rule 4 of CLAUDE.md); money is int kopecks; percents are numbers with
one decimal; "advice" items carry a "Почему?" block.

Run:  eval "$(python tests/contract/get_tokens.py)" && pytest tests/contract/test_stage2_contract.py -rs
While the backend still answers with the stage 0 shape (no "month"), the shape tests skip with a reason, not fail.
Optional golden comparison: VF_SEEDED_SET03=1 and VF_TOKEN_D (clinic D seeded from tests/golden/set03, see
docs/handoff.md); then the numbers of 2026-09-09 are compared with set03/expected.json.
"""
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from test_stage0_contract import ERROR_CODES, SOURCES, UNITS, assert_error

httpx = pytest.importorskip("httpx")

SET03 = Path(__file__).resolve().parents[1] / "golden" / "set03"
EXPECTED = json.loads((SET03 / "expected.json").read_text(encoding="utf-8"))
SEEDED = os.environ.get("VF_SEEDED_SET03") == "1"
SOURCE_ORDER = ["bank", "vetmanager", "bot", "manual", "calc"]
SEVERITIES = {"alert", "warning", "good"}
BALANCE_REQUIRED = ["total", "bank", "cash", "week_change", "runway_days"]
MONTH_FIGURES = ["revenue", "expenses", "profit", "profit_margin_pct"]


# ------------------------------------------------------------------ helpers
def is_figure(node):
    return isinstance(node, dict) and {"value", "unit", "breakdown"} <= set(node)


def walk_figures(node, path=""):
    if is_figure(node):
        yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_figures(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_figures(v, f"{path}[{i}]")


def assert_figure_v2(fig, where):
    """Figure of the contract: int value for rub/count/days, number with one decimal for pct; breakdown, source, note."""
    assert isinstance(fig, dict), where
    assert fig.get("unit") in UNITS, f"{where}.unit"
    value = fig.get("value")
    if fig["unit"] == "pct":
        assert type(value) in (int, float), f"{where}.value must be a JSON number for pct, got {value!r}"
        assert round(value, 1) == value, f"{where}.value must have at most one decimal"
    else:
        assert type(value) is int, f"{where}.value must be int, got {value!r}"
    bd = fig.get("breakdown")
    assert isinstance(bd, list), f"{where}.breakdown"
    assert bd or (fig["unit"] == "rub" and value == 0), f"{where}.breakdown is empty (allowed only for a zero amount)"
    for i, b in enumerate(bd):
        assert isinstance(b.get("label"), str) and b["label"], f"{where}.breakdown[{i}].label"
        assert b.get("unit") in UNITS, f"{where}.breakdown[{i}].unit"
        if b["unit"] == "pct":
            assert type(b.get("value")) in (int, float)
        else:
            assert type(b.get("value")) is int, f"{where}.breakdown[{i}].value must be int"
    src = fig.get("source")
    assert isinstance(src, list) and src and set(src) <= SOURCES, f"{where}.source must be a non-empty list of known sources"
    assert src == sorted(set(src), key=SOURCE_ORDER.index), f"{where}.source: duplicates or wrong order"
    assert isinstance(fig.get("note"), str) and fig["note"].strip(), f"{where}.note must be a non-empty string"
    if fig["unit"] == "rub" and all(b["unit"] == "rub" for b in bd) and bd:
        assert sum(b["value"] for b in bd) == value, f"{where}: breakdown does not add up to value"
    if fig["unit"] == "count" and bd and all(b["unit"] == "count" for b in bd):
        assert sum(b["value"] for b in bd) == value, f"{where}: breakdown does not add up to value"


def dashboard(client, **params):
    r = client.get("/v1/dashboard", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def full(client, **params):
    d = dashboard(client, **params)
    if "month" not in d or "advice" not in d:
        pytest.skip("GET /v1/dashboard still has the stage 0 shape (no month/advice); stage 2 is not implemented yet")
    return d


@pytest.fixture(scope="module")
def dash_a(client_a):
    return full(client_a)


@pytest.fixture(scope="module")
def client_d(base_url):
    token = os.environ.get("VF_TOKEN_D")
    if not token or not SEEDED:
        pytest.skip("VF_TOKEN_D and VF_SEEDED_SET03=1 are needed (clinic seeded from golden set03)")
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60) as c:
        yield c


# ------------------------------------------------------------------ shape
def test_top_level_keys(dash_a):
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", dash_a["as_of"])
    assert {"as_of", "data_as_of", "balance", "month", "balance_trend", "advice"} <= set(dash_a)
    assert dash_a["data_as_of"] is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+(Z|[+-]\d{2}:\d{2})", dash_a["data_as_of"])


def test_balance_block_has_all_figures(dash_a):
    b = dash_a["balance"]
    assert set(BALANCE_REQUIRED) <= set(b), f"missing: {set(BALANCE_REQUIRED) - set(b)}"
    for key in BALANCE_REQUIRED:
        assert_figure_v2(b[key], f"balance.{key}")
    assert b["runway_days"]["unit"] == "days"
    assert b["total"]["value"] == b["bank"]["value"] + b["cash"]["value"], "total must be bank + cash"


def test_month_block(dash_a):
    m = dash_a["month"]
    for key in MONTH_FIGURES:
        if key == "profit_margin_pct" and m["revenue"]["value"] == 0:
            assert key not in m, "margin is undefined without revenue: the field is omitted (contract)"
            continue
        assert_figure_v2(m[key], f"month.{key}")
    if "profit_margin_pct" in m:
        assert m["profit_margin_pct"]["unit"] == "pct"
    assert type(m["days_passed"]) is int and type(m["days_total"]) is int
    assert 1 <= m["days_passed"] <= m["days_total"] <= 31
    assert m["days_passed"] == int(dash_a["as_of"][-2:]), "days_passed is the day of as_of (inclusive)"
    assert m["profit"]["value"] == m["revenue"]["value"] - m["expenses"]["value"]
    assert [b["label"] for b in m["revenue"]["breakdown"]] == ["Услуги", "Товары"]
    for key in ("visits", "avg_check"):  # proposed additions (function 2); validated when present
        if key in m:
            assert_figure_v2(m[key], f"month.{key}")


def test_balance_trend(dash_a):
    trend = dash_a["balance_trend"]
    assert isinstance(trend, list) and 1 <= len(trend) <= 14
    days = [date.fromisoformat(p["date"]) for p in trend]
    assert days[-1] == date.fromisoformat(dash_a["as_of"])
    assert all(b - a == timedelta(days=1) for a, b in zip(days, days[1:])), "one point per day, ascending"
    assert all(type(p["value"]) is int for p in trend)
    assert trend[-1]["value"] == dash_a["balance"]["total"]["value"]


def test_advice_items(dash_a):
    ids = [a["id"] for a in dash_a["advice"]]
    assert len(ids) == len(set(ids)), "advice ids must be unique"
    rank = {"alert": 0, "warning": 1, "good": 2}
    assert [rank[a["severity"]] for a in dash_a["advice"]] == sorted(rank[a["severity"]] for a in dash_a["advice"]), \
        "order: alert, warning, good"
    for a in dash_a["advice"]:
        assert a["severity"] in SEVERITIES
        for k in ("id", "icon", "title", "text"):
            assert isinstance(a[k], str) and a[k].strip(), f"advice[{a['id']}].{k}"
        why = a["why"]
        assert isinstance(why["summary"], str) and why["summary"].strip()
        assert isinstance(why["steps"], list) and why["steps"] and all(isinstance(s, str) and s.strip() for s in why["steps"])
        assert isinstance(why["sources"], list) and why["sources"] and all(isinstance(s, str) and s.strip() for s in why["sources"])


def test_every_figure_in_the_response_has_breakdown_source_and_note(dash_a):
    found = list(walk_figures(dash_a))
    assert len(found) >= 10
    for path, fig in found:
        assert_figure_v2(fig, path)


def test_money_is_never_a_string_or_float(dash_a):
    def scan(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                scan(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan(v, f"{path}[{i}]")
        elif isinstance(node, str) and path.endswith(".value"):
            pytest.fail(f"{path}: value is a string {node!r} (Decimal serialised as string?)")
    scan(dash_a, "dashboard")


# ------------------------------------------------------------------ as_of parameter and determinism
def test_as_of_is_echoed_and_changes_the_period(client_a):
    first = full(client_a, as_of="2026-09-09")
    other = dashboard(client_a, as_of="2026-08-31")
    assert first["as_of"] == "2026-09-09" and other["as_of"] == "2026-08-31"
    if "month" in other:
        assert other["month"]["days_total"] == 31


@pytest.mark.parametrize("bad", ["garbage", "2026-13-40", "09-09-2026", ""])
def test_invalid_as_of_is_a_validation_error(client_a, bad):
    r = client_a.get("/v1/dashboard", params={"as_of": bad})
    assert_error(r, 422, "validation")


def test_same_request_twice_gives_identical_numbers(client_a):
    a, b = full(client_a, as_of="2026-09-09"), full(client_a, as_of="2026-09-09")
    assert a == b


def test_as_of_before_any_data_does_not_crash(client_a):
    r = client_a.get("/v1/dashboard", params={"as_of": "2000-01-01"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["balance"]["total"]["value"] is not None
    if "month" in d:
        assert d["month"]["revenue"]["value"] == 0 and d["advice"] == []


# ------------------------------------------------------------------ isolation between clinics
def test_clinics_get_different_dashboards_and_own_labels_only(client_a, client_b):
    da, db = full(client_a, as_of="2026-09-09"), full(client_b, as_of="2026-09-09")
    own = {}
    for name, cl in (("a", client_a), ("b", client_b)):
        own[name] = {x["name"] for x in (lambda b: b["items"] if isinstance(b, dict) else b)(cl.get("/v1/accounts").json())}
    assert {x["label"] for x in da["balance"]["total"]["breakdown"]} <= own["a"]
    assert {x["label"] for x in db["balance"]["total"]["breakdown"]} <= own["b"]
    assert da["balance"]["total"]["value"] != db["balance"]["total"]["value"]


def test_clinic_id_parameter_is_ignored(client_a):
    base = full(client_a, as_of="2026-09-09")
    other = full(client_a, as_of="2026-09-09", clinic_id="00000000-0000-0000-0000-000000000000")
    assert base == other


def test_no_token_and_foreign_token(anon):
    assert_error(anon.get("/v1/dashboard"), 401, "unauthorized")
    assert_error(anon.get("/v1/dashboard", headers={"Authorization": "Bearer x.y.z"}), 401, "unauthorized")


def test_error_codes_stay_inside_the_contract(client_a):
    r = client_a.get("/v1/dashboard", params={"as_of": "nope"})
    assert r.json()["error"]["code"] in ERROR_CODES


# ------------------------------------------------------------------ golden (seeded clinic)
@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET03=1 not set")
@pytest.mark.parametrize("as_of", [c["as_of"] for c in EXPECTED["cases"]])
def test_dashboard_matches_golden_set03(client_d, as_of):
    exp = next(c for c in EXPECTED["cases"] if c["as_of"] == as_of)
    d = full(client_d, as_of=as_of)
    for key in ("total", "bank", "cash"):
        assert d["balance"][key]["value"] == exp["balance"][key]["value"], key
        assert {b["label"]: b["value"] for b in d["balance"][key]["breakdown"]} == exp["balance"][key]["breakdown"], key
        assert d["balance"][key]["source"] == exp["balance"][key]["source"], key
    if exp["week_change"]:
        assert d["balance"]["week_change"]["value"] == exp["week_change"]["value"]
    else:
        assert d["balance"].get("week_change") is None
    assert d["balance"]["runway_days"]["value"] == exp["runway_days"]["value"]
    assert d["balance_trend"] == exp["balance_trend"]
    m, em = d["month"], exp["month"]
    for key in ("revenue", "expenses", "profit"):
        assert m[key]["value"] == em[key]["value"], key
        assert {b["label"]: b["value"] for b in m[key]["breakdown"]} == em[key]["breakdown"], key
        assert m[key]["source"] == em[key]["source"], key
    assert float(m["profit_margin_pct"]["value"]) == em["profit_margin_pct"]["value"]
    assert (m["days_passed"], m["days_total"]) == (em["days_passed"], em["days_total"])
    assert [(a["id"], a["severity"]) for a in d["advice"]] == [(a["id"], a["severity"]) for a in exp["advice"]]


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET03=1 not set")
def test_golden_clinic_is_invisible_to_clinic_a(client_a, client_d):
    ids_a = {x["id"] for x in (lambda b: b["items"] if isinstance(b, dict) else b)(client_a.get("/v1/accounts").json())}
    ids_d = {x["id"] for x in (lambda b: b["items"] if isinstance(b, dict) else b)(client_d.get("/v1/accounts").json())}
    assert ids_a and ids_d and not (ids_a & ids_d)
    total_d = full(client_d, as_of="2026-09-09")["balance"]["total"]["value"]
    assert total_d != full(client_a, as_of="2026-09-09")["balance"]["total"]["value"]
