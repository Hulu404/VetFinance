"""Stage 5 contract tests: price list, service cost, techcard, efficiency (functions 11, 12, 33, 34), docs/api-contract.md
«Прайс услуг» and «Аналитика» (`/v1/efficiency`), field names of design/screens/price.md and efficiency.md.

    GET /v1/services?sort=margin|profit&order=asc|desc&filter=all|loss|no_recipe&q=&limit=&cursor=[&as_of=YYYY-MM-DD]
    GET /v1/services/{id}/cost[?as_of=]            GET|PUT /v1/services/{id}/recipe
    GET /v1/efficiency?month=YYYY-MM[&as_of=]      GET|PUT /v1/efficiency/settings

Shapes: the DRAFT of docs/api-contract.md (stubs of stage 5) plus the "запрос" fields of the designer specs; everything beyond the
contract is marked PROPOSAL and is checked only when the server returns it (otherwise the test skips with the reason):
  list         = {counts{all, loss, no_recipe}, headline, items[{id, name, group, price, visits_month, margin_pct|null,
                  monthly_profit|null, status ok|no_recipe|partial}], next_cursor}
  cost         = {service{id, name, group}, price, net_profit|null, net_margin_pct|null, parts[7 x {key, label, amount|null,
                  share_pct|null}] in the order doctor_pay, drugs, anesthesia, supplies, acquiring, fixed, taxes, monthly_profit|null,
                  status, missing[recipe|minutes|hours|item_no_cost], basis_month}
  efficiency   = {period, headline, status ok|partial, partial_reasons, visits, load_pct|null, load_by rooms|doctors, avg_check,
                  rooms[{id, name, load_pct}], doctors[{id, name, load_pct|null}], hour_cost|null, hour_cost_parts[{key, label, figure}],
                  hour_margin|null}
Rules (set06/README.md): parts + net_profit = price to the kopeck; shares + net_margin_pct = 100,0 exactly; no techcard -> no profit;
the two lines of the hour cost add up to it; every Figure has breakdown, source and note; clinic B never sees clinic G.

Every test SKIPS while the endpoint answers 404/405/501 without the contract error body (route not implemented yet).
Run: eval "$(python tests/contract/get_tokens.py)" && pytest tests/contract/test_stage5_contract.py -rs
Golden comparison against set06: VF_SEEDED_SET06=1 and VF_TOKEN_G (clinic G seeded from tests/golden/set06, as_of 2026-10-01).
Tests that change data (techcard, hours) run only with VF_CONTRACT_WRITES=1 on a test clinic.
VF_STAGE5_STUB=1 marks as xfail the tests that cannot pass on a server of step 1 (stubs that always answer with an example).
"""
import json
import os
from pathlib import Path

import pytest

from test_stage0_contract import assert_error
from test_stage2_contract import assert_figure_v2, walk_figures

httpx = pytest.importorskip("httpx")

SET06 = Path(__file__).resolve().parents[1] / "golden" / "set06"
EXPECTED = json.loads((SET06 / "expected.json").read_text(encoding="utf-8"))
SEEDED = os.environ.get("VF_SEEDED_SET06") == "1"
WRITES = os.environ.get("VF_CONTRACT_WRITES") == "1"
STUB = os.environ.get("VF_STAGE5_STUB") == "1"
GOLDEN_AS_OF, GOLDEN_MONTH = EXPECTED["as_of"], EXPECTED["month"]
MAIN = EXPECTED["cases"]["main"]
PART_KEYS = ["doctor_pay", "drugs", "anesthesia", "supplies", "acquiring", "fixed", "taxes"]
STATUSES = {"ok", "no_recipe", "partial"}
MISSING = ["recipe", "hour_cost", "item_no_cost", "no_expenses"]
LOAD_BY = {"rooms", "doctors"}
UNKNOWN = "00000000-0000-4000-8000-000000000000"
engine_only = pytest.mark.xfail(STUB, reason="needs the engine: the step 1 stub always answers with the example", strict=False)

ROUTES = [("GET", "/v1/services"), ("POST", "/v1/services"), ("PATCH", f"/v1/services/{UNKNOWN}"), ("DELETE", f"/v1/services/{UNKNOWN}"), ("GET", f"/v1/services/{UNKNOWN}/cost"), ("GET", f"/v1/services/{UNKNOWN}/recipe"),
          ("PUT", f"/v1/services/{UNKNOWN}/recipe"), ("GET", "/v1/efficiency"), ("GET", "/v1/efficiency/settings"),
          ("PUT", "/v1/efficiency/settings")]


# ------------------------------------------------------------------ helpers
def _json(r):
    try:
        body = r.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def implemented(r, what):
    if r.status_code in (404, 405, 501) and "error" not in _json(r):
        pytest.skip(f"{what} is not implemented yet (HTTP {r.status_code} without a contract error body)")
    return r


def val(fig):
    return fig["value"]


def listing(client, **params):
    r = implemented(client.get("/v1/services", params={"sort": "margin", **params}), "GET /v1/services")
    assert r.status_code == 200, r.text
    body = r.json()
    return body if isinstance(body, dict) else {"items": body}


def services(client, **params):
    return listing(client, **params)["items"]


def cost(client, service_id, **params):
    r = implemented(client.get(f"/v1/services/{service_id}/cost", params=params), "GET /v1/services/{id}/cost")
    assert r.status_code == 200, r.text
    return r.json()


def efficiency(client, **params):
    r = implemented(client.get("/v1/efficiency", params=params), "GET /v1/efficiency")
    assert r.status_code == 200, r.text
    return r.json()


def proposed(body, key):
    if key not in body:
        pytest.skip(f"field {key!r} is only a proposal (docs/handoff.md, tester -> backend-developer, этап 5) and is not returned yet")
    return body[key]


def parts_by_key(card):
    return {p["key"]: p for p in card["parts"]}


def figures_ok(node):
    found = list(walk_figures(node))
    for path, fig in found:
        assert_figure_v2(fig, path)
    return found


@pytest.fixture(scope="module")
def client_g(base_url):
    token = os.environ.get("VF_TOKEN_G")
    if not token or not SEEDED:
        pytest.skip("VF_TOKEN_G and VF_SEEDED_SET06=1 are needed (clinic G seeded from golden set06)")
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60) as c:
        yield c


@pytest.fixture(scope="module")
def list_a(client_a):
    return services(client_a)


@pytest.fixture(scope="module", params=["A", "G"])
def list_x(request, client_a):
    """The price list of clinic A and of the golden clinic G: read-only shape tests run on both."""
    if request.param == "A":
        return services(client_a)
    return services(request.getfixturevalue("client_g"), as_of=GOLDEN_AS_OF)


@pytest.fixture(scope="module", params=["A", "G"])
def eff_x(request, client_a):
    if request.param == "A":
        return efficiency(client_a)
    return efficiency(request.getfixturevalue("client_g"), as_of=GOLDEN_AS_OF, month=GOLDEN_MONTH)


@pytest.fixture(scope="module", params=["A", "G"])
def cards_x(request, client_a):
    """Cost cards of the first four services of clinic A and of the golden clinic G (all would be slow on a remote server)."""
    if request.param == "A":
        client, params = client_a, {}
    else:
        client, params = request.getfixturevalue("client_g"), {"as_of": GOLDEN_AS_OF}
    return [cost(client, s["id"], **params) for s in services(client, **params)[:4]]


# ------------------------------------------------------------------ 401 and parameters
@pytest.mark.parametrize("method,path", ROUTES)
def test_no_token_and_garbage_token_are_401(anon, method, path):
    body = {} if method in ("PUT", "POST", "PATCH") else None
    r = implemented(anon.request(method, path, json=body), f"{method} {path}")
    assert_error(r, 401, "unauthorized")
    r = anon.request(method, path, headers={"Authorization": "Bearer garbage"}, json=body)
    assert_error(r, 401, "unauthorized")


@pytest.mark.parametrize("bad", [{"as_of": "2026-13-01"}, {"as_of": "вчера"}, {"sort": "price;drop"}, {"sort": "-"}, {"order": "up"},
                                 {"filter": "всё"}, {"limit": "0"}, {"limit": "x"}])
def test_invalid_list_parameters_are_validation_errors(client_a, bad):
    r = implemented(client_a.get("/v1/services", params={"sort": "margin", **bad}), "GET /v1/services")
    assert_error(r, 422, "validation")
    assert set(r.json()["error"]["details"]["fields"]) & set(bad)


@pytest.mark.parametrize("bad", [{"month": "2026-13"}, {"month": "август"}, {"month": "2999-01"}, {"as_of": "2026-02-30"}])
def test_invalid_efficiency_parameters_are_validation_errors(client_a, bad):
    """A month later than the last closed one is a validation error too (designer, efficiency.md)."""
    r = implemented(client_a.get("/v1/efficiency", params=bad), "GET /v1/efficiency")
    assert_error(r, 422, "validation")


def test_month_after_the_last_closed_one_is_in_future(client_a):
    r = implemented(client_a.get("/v1/efficiency", params={"month": "2999-01"}), "GET /v1/efficiency")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"]["month"] == "in_future"


def test_limit_above_the_maximum_is_too_large(client_a):
    r = implemented(client_a.get("/v1/services", params={"limit": "201"}), "GET /v1/services")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"]["limit"] == "too_large"


def test_unknown_service_is_404(client_a):
    assert_error(implemented(client_a.get(f"/v1/services/{UNKNOWN}/cost"), "GET /v1/services/{id}/cost"), 404, "not_found")
    assert_error(client_a.get("/v1/services/нет-такой/cost"), 404, "not_found")
    assert_error(implemented(client_a.get(f"/v1/services/{UNKNOWN}/recipe"), "GET /v1/services/{id}/recipe"), 404, "not_found")


def test_clinic_id_parameter_does_not_switch_the_clinic(client_a, list_a):
    assert services(client_a, clinic_id=UNKNOWN) == list_a


def test_same_request_twice_gives_identical_answers(client_a, list_a):
    assert services(client_a) == list_a
    assert efficiency(client_a) == efficiency(client_a)


# ------------------------------------------------------------------ price list
def test_list_envelope_counts_and_item_shape(list_x, request):
    for s in list_x:
        assert {"id", "name", "price", "visits_month", "margin_pct", "status"} <= set(s), s
        assert isinstance(s["id"], str) and s["id"] and isinstance(s["name"], str) and s["name"]
        assert s["status"] in STATUSES
        assert s["price"]["unit"] == "rub" and s["visits_month"]["unit"] == "count"
        assert s["margin_pct"] is None or s["margin_pct"]["unit"] == "pct"
        assert (s["margin_pct"] is None) == (s["status"] == "no_recipe"), "no techcard means no margin, nothing else does"
        for key in ("price", "visits_month", "margin_pct", "monthly_profit"):
            if s.get(key) is not None:
                assert_figure_v2(s[key], f"{s['id']}.{key}")
    assert len({s["id"] for s in list_x}) == len(list_x)


def test_list_envelope_headline_basis_month_and_unit_label(list_x, client_a):
    body = listing(client_a)
    for key in ("headline", "basis_month", "counts"):
        proposed(body, key)
    assert isinstance(body["headline"], str) and len(body["basis_month"]) == 7
    assert all(isinstance(s["unit_label"], str) for s in body["items"] if "unit_label" in s)


def test_counts_agree_with_the_filters(client_a):
    body = listing(client_a)
    counts = proposed(body, "counts")
    assert counts["all"] == len(listing(client_a, limit=200)["items"])
    for key, flt in (("loss", "loss"), ("no_recipe", "no_recipe")):
        assert counts[key] == len(listing(client_a, filter=flt, limit=200)["items"]), key


def test_default_order_is_the_worst_margin_first_and_services_without_margin_go_last(list_x):
    rated = [s for s in list_x if s["margin_pct"] is not None]
    assert list_x[:len(rated)] == rated, "services without margin must be at the end"
    margins = [val(s["margin_pct"]) for s in rated]
    assert margins == sorted(margins)


def test_order_desc_reverses_the_rated_part_and_keeps_nulls_last(client_a):
    asc, desc = services(client_a, order="asc"), services(client_a, order="desc")
    assert sorted(s["id"] for s in asc) == sorted(s["id"] for s in desc)
    rated = [s for s in desc if s["margin_pct"] is not None]
    assert [val(s["margin_pct"]) for s in rated] == sorted((val(s["margin_pct"]) for s in rated), reverse=True)
    assert all(s["margin_pct"] is None for s in desc[len(rated):])


def test_filters_return_what_they_say(client_a):
    assert all(s["margin_pct"] is not None and val(s["margin_pct"]) < 0 for s in services(client_a, filter="loss"))
    assert all(s["status"] == "no_recipe" for s in services(client_a, filter="no_recipe"))


def test_pagination_has_no_gaps_or_repeats(client_a):
    whole = services(client_a, limit=200)
    if len(whole) < 3:
        pytest.skip("fewer than 3 services in clinic A")
    first = listing(client_a, limit=2)
    assert len(first["items"]) == 2 and first.get("next_cursor")
    second = listing(client_a, limit=2, cursor=first["next_cursor"])
    assert [s["id"] for s in first["items"] + second["items"]] == [s["id"] for s in whole][:2 + len(second["items"])]


# ------------------------------------------------------------------ cost card
def test_card_shape_parts_order_and_figures(cards_x):
    if not cards_x:
        pytest.skip("no services in this clinic")
    for c in cards_x:
        assert {"price", "net_profit", "net_margin_pct", "parts", "monthly_profit", "status", "missing"} <= set(c)
        assert [p["key"] for p in c["parts"]] == PART_KEYS
        assert c["status"] in STATUSES and [m for m in MISSING if m in c["missing"]] == c["missing"]
        assert c["price"]["unit"] == "rub"
        for p in c["parts"]:
            assert isinstance(p["label"], str) and p["label"]
            assert p["amount"] is None or (p["amount"]["unit"] == "rub" and p["share_pct"]["unit"] == "pct")
        figures_ok(c)


def test_status_and_missing_agree(cards_x):
    for c in cards_x:
        assert (c["status"] == "no_recipe") == ("recipe" in c["missing"])
        assert (c["status"] == "ok") == (c["missing"] == [])
        parts = parts_by_key(c)
        if c["status"] == "no_recipe":
            assert all(parts[k]["amount"] is None for k in ("drugs", "anesthesia", "supplies"))
            assert c["net_profit"] is None and c["net_margin_pct"] is None and c["monthly_profit"] is None
        else:
            assert c["net_profit"] is not None and c["net_margin_pct"] is not None
        if "hour_cost" in c["missing"]:
            assert parts["fixed"]["amount"] is None


def test_parts_and_profit_add_up_to_the_price_to_the_kopeck(cards_x):
    for c in cards_x:
        if c["net_profit"] is None:
            continue
        assert sum(val(p["amount"]) for p in c["parts"] if p["amount"] is not None) + val(c["net_profit"]) == val(c["price"])


def test_shares_add_up_to_exactly_100(cards_x):
    for c in cards_x:
        if c["net_profit"] is None:
            continue
        total = sum(val(p["share_pct"]) for p in c["parts"] if p["share_pct"] is not None) + val(c["net_margin_pct"])
        assert round(total * 10) == 1000, c["service"] if "service" in c else total
        price = val(c["price"])
        for p in c["parts"]:
            if p["amount"] is not None:
                assert abs(val(p["share_pct"]) - val(p["amount"]) * 100 / price) < 0.1 + 1e-9, p["key"]


def test_monthly_profit_is_profit_times_visits_and_margin_matches_the_list(client_a, list_a):
    rated = [s for s in list_a if s["margin_pct"] is not None]
    if not rated:
        pytest.skip("clinic A has no service with a techcard")
    s = rated[0]
    c = cost(client_a, s["id"])
    assert val(c["net_margin_pct"]) == val(s["margin_pct"]) and val(c["price"]) == val(s["price"])
    assert val(c["monthly_profit"]) == val(c["net_profit"]) * val(s["visits_month"])


def test_card_of_a_loss_making_service_has_negative_numbers_that_still_add_up(client_a, list_a):
    losing = [s for s in list_a if s["margin_pct"] is not None and val(s["margin_pct"]) < 0]
    if not losing:
        pytest.skip("no loss-making service in clinic A")
    c = cost(client_a, losing[0]["id"])
    assert val(c["net_profit"]) < 0 and val(c["net_margin_pct"]) < 0
    assert sum(val(p["amount"]) for p in c["parts"] if p["amount"] is not None) + val(c["net_profit"]) == val(c["price"])


def test_basis_month_is_a_closed_month(cards_x):
    for c in cards_x:
        month = proposed(c, "basis_month")
        assert len(month) == 7 and month[4] == "-"


# ------------------------------------------------------------------ efficiency
def test_efficiency_shape_and_figures(eff_x):
    assert {"visits", "load_pct", "avg_check", "rooms", "hour_cost", "hour_cost_parts"} <= set(eff_x)
    assert eff_x["visits"]["unit"] == "count"
    assert eff_x["avg_check"] is None or eff_x["avg_check"]["unit"] == "rub"
    assert eff_x["load_pct"] is None or eff_x["load_pct"]["unit"] == "pct"
    assert eff_x["hour_cost"] is None or eff_x["hour_cost"]["unit"] == "rub"
    assert isinstance(eff_x["rooms"], list) and isinstance(eff_x["hour_cost_parts"], list)
    for r in eff_x["rooms"]:
        assert isinstance(r["name"], str) and r["load_pct"]["unit"] == "pct"
    figures_ok(eff_x)


def test_hour_cost_lines_add_up_to_the_hour_cost(eff_x):
    if eff_x["hour_cost"] is None:
        pytest.skip("hour cost is not computed for this clinic (no hours)")
    bd = eff_x["hour_cost"]["breakdown"]
    assert len(bd) == 2 and sum(b["value"] for b in bd) == val(eff_x["hour_cost"])


def test_hour_cost_parts_table(eff_x):
    if eff_x["hour_cost"] is None:
        assert eff_x["hour_cost_parts"] == [] or all(p.get("figure") is None for p in eff_x["hour_cost_parts"])
        return
    parts = {p["key"]: p for p in eff_x["hour_cost_parts"] if "key" in p}
    if not parts:
        pytest.skip("hour_cost_parts items have no `key` yet (PROPOSAL {key, label, figure})")
    assert set(parts) == {"hours", "busy_hours", "fixed", "obligations"}


def test_load_by_status_and_empty_rooms(eff_x):
    load_by = proposed(eff_x, "load_by")
    assert load_by in LOAD_BY
    if not eff_x["rooms"]:
        assert load_by == "doctors"      # api-contract.md: without room schedules `rooms` is empty and load_by is "doctors"
    status = proposed(eff_x, "status")
    assert status in ("ok", "partial", "empty")
    if status != "empty":
        assert (status == "ok") == (eff_x.get("partial_reasons", []) == [])
    assert set(eff_x.get("partial_reasons", [])) <= {"no_doctor_hours", "no_expenses"}
    if eff_x["load_pct"] is None and status == "partial":
        assert "no_doctor_hours" in eff_x["partial_reasons"]


def test_load_is_a_percent_number_with_one_decimal(eff_x):
    if eff_x["load_pct"] is None:
        pytest.skip("load is not computed for this clinic")
    assert 0 <= val(eff_x["load_pct"]) and round(val(eff_x["load_pct"]), 1) == val(eff_x["load_pct"])


def test_empty_clinic_does_not_crash(client_b):
    e = efficiency(client_b)
    assert val(e["visits"]) == 0 and e["rooms"] == [] and e["load_pct"] is None
    assert e["avg_check"] is None or val(e["avg_check"]) == 0
    body = listing(client_b)
    assert body["items"] == [] and body.get("counts", {"all": 0, "loss": 0, "no_recipe": 0}) == {"all": 0, "loss": 0, "no_recipe": 0}


# ------------------------------------------------------------------ techcard and hours (settings): validation and isolation
@pytest.fixture(scope="module")
def recipe_target(client_a, list_a):
    if not list_a:
        pytest.skip("clinic A has no services to change a techcard of")
    return list_a[0]["id"]


@pytest.mark.parametrize("body,field,reason", [
    ({"minutes": 0, "items": []}, "minutes", "out_of_range"), ({"minutes": 1441, "items": []}, "minutes", "out_of_range"),
    ({"minutes": 12.5, "items": []}, "minutes", "invalid"), ({"minutes": 10, "doctor_pct": 101, "items": []}, "doctor_pct", "out_of_range"),
    ({"minutes": 10, "doctor_pct": 10.123, "items": []}, "doctor_pct", "too_many_decimals"),
    ({"minutes": 10, "items": [{"item_id": UNKNOWN, "group": "drugs", "qty": 1}]}, "items", "unknown_item"),
    ({"minutes": 10, "items": [{"item_id": UNKNOWN, "group": "drugs", "qty": 0}]}, "items", "must_be_positive"),
    ({"minutes": 10, "items": [{"item_id": UNKNOWN, "group": "drugs", "qty": 1.2345}]}, "items", "too_many_decimals"),
    ({"minutes": 10, "items": [{"item_id": UNKNOWN, "group": "sweets", "qty": 1}]}, "items", "invalid"),
])
def test_put_recipe_validation(client_a, recipe_target, body, field, reason):
    """Field names of design/screens/price.md: minutes, doctor_pct (percent, null = clinic average), items[{item_id, group, qty}]."""
    r = implemented(client_a.put(f"/v1/services/{recipe_target}/recipe", json=body), "PUT /v1/services/{id}/recipe")
    assert_error(r, 422, "validation")
    fields = r.json()["error"]["details"]["fields"]
    assert any(k == field or k.startswith(field) for k in fields), fields


@pytest.mark.parametrize("body,field", [({"avg_visit_minutes": 4}, "avg_visit_minutes"), ({"avg_visit_minutes": 241}, "avg_visit_minutes"),
                                        ({"doctors": [{"id": UNKNOWN, "hours_per_week": 81}]}, "doctors")])
def test_put_efficiency_settings_validation(client_a, body, field):
    r = implemented(client_a.put("/v1/efficiency/settings", json=body), "PUT /v1/efficiency/settings")
    assert r.status_code in (404, 422)
    if r.status_code == 422:
        assert any(k.startswith(field) for k in r.json()["error"]["details"]["fields"])


def test_recipe_of_a_foreign_service_is_404(client_b, client_g):
    s = services(client_g, as_of=GOLDEN_AS_OF)[0]
    assert_error(implemented(client_b.get(f"/v1/services/{s['id']}/recipe"), "GET /v1/services/{id}/recipe"), 404, "not_found")
    assert_error(client_b.put(f"/v1/services/{s['id']}/recipe", json={"minutes": 10, "lines": []}), 404, "not_found")


# ------------------------------------------------------------------ isolation between clinics
def test_clinic_b_sees_nothing_of_clinic_g(client_b, client_g):
    names_g = {s["name"] for s in services(client_g, as_of=GOLDEN_AS_OF)}
    assert names_g, "clinic G must have services"
    assert not names_g & {s["name"] for s in services(client_b, as_of=GOLDEN_AS_OF)}


def test_service_of_clinic_g_is_404_for_clinic_b(client_b, client_g):
    s = services(client_g, as_of=GOLDEN_AS_OF)[0]
    assert_error(client_b.get(f"/v1/services/{s['id']}/cost", params={"as_of": GOLDEN_AS_OF}), 404, "not_found")


def test_service_of_clinic_a_is_404_for_clinic_b(client_a, client_b, list_a):
    if not list_a:
        pytest.skip("clinic A has no services")
    assert_error(client_b.get(f"/v1/services/{list_a[0]['id']}/cost"), 404, "not_found")


def test_efficiency_of_clinic_b_does_not_include_clinic_g(client_b, client_g):
    assert val(efficiency(client_g, as_of=GOLDEN_AS_OF, month=GOLDEN_MONTH)["visits"]) == MAIN["efficiency"]["visits"]
    assert val(efficiency(client_b, as_of=GOLDEN_AS_OF, month=GOLDEN_MONTH)["visits"]) == 0


# ------------------------------------------------------------------ golden comparison with set06 (clinic G)
@pytest.fixture(scope="module")
def golden_body(client_g):
    return listing(client_g, as_of=GOLDEN_AS_OF)


@pytest.fixture(scope="module")
def golden_cards(client_g, golden_body):
    return {s["name"]: cost(client_g, s["id"], as_of=GOLDEN_AS_OF) for s in golden_body["items"]}


@engine_only
def test_golden_list_order_counts_prices_visits_and_margins(golden_body):
    exp = MAIN["services"]
    assert [s["name"] for s in golden_body["items"]] == [s["name"] for s in exp]
    if "counts" in golden_body:
        assert {k: golden_body["counts"][k] for k in ("all", "loss", "no_recipe")} == MAIN["counts"]
    for got, want in zip(golden_body["items"], exp):
        assert (val(got["price"]), val(got["visits_month"]), got["status"]) == (want["price"], want["visits_month"], want["status"])
        assert (None if got["margin_pct"] is None else val(got["margin_pct"])) == want["net_margin_pct"], want["name"]


@engine_only
@pytest.mark.parametrize("want", MAIN["services"], ids=[s["id"] for s in MAIN["services"]])
def test_golden_card_parts_to_the_kopeck(golden_cards, want):
    c = golden_cards[want["name"]]
    parts = parts_by_key(c)
    assert {k: (None if parts[k]["amount"] is None else val(parts[k]["amount"])) for k in PART_KEYS} == \
        {k: want["parts"][k] for k in PART_KEYS}
    assert c["status"] == want["status"] and c["missing"] == want["missing"]
    for key in ("net_profit", "net_margin_pct", "monthly_profit"):
        assert (None if c[key] is None else val(c[key])) == want[key], key
    if want["shares"] is not None:
        assert {k: val(parts[k]["share_pct"]) for k in PART_KEYS if parts[k]["amount"] is not None} == want["shares"]


NO_STATEMENT_AS_OF = "2026-09-15"      # the basis month is August: the golden seed has bank operations for September only


def test_month_without_a_statement_gives_no_profit_to_any_service(client_g):
    """Owner's decision 14: no statement for the basis month -> no price calculation: profit, margin, shares and hour cost are null."""
    body = listing(client_g, as_of=NO_STATEMENT_AS_OF)
    assert body["items"], "services are still listed (prices come from sales)"
    for s in body["items"]:
        assert s["margin_pct"] is None and s["monthly_profit"] is None, s["name"]
        assert s["status"] in ("partial", "no_recipe")
    assert body.get("counts", {}).get("loss", 0) == 0
    card = cost(client_g, next(s["id"] for s in body["items"] if s["status"] == "partial"), as_of=NO_STATEMENT_AS_OF)
    assert "no_expenses" in card["missing"] and [m for m in MISSING if m in card["missing"]] == card["missing"]
    assert card["net_profit"] is None and card["net_margin_pct"] is None and card["monthly_profit"] is None
    by_key = parts_by_key(card)
    for key in ("acquiring", "taxes", "fixed"):
        assert by_key[key]["amount"] is None and by_key[key]["share_pct"] is None, key      # their sources are the empty P&L
    assert all((p["amount"] is None) == (p["share_pct"] is None) for p in card["parts"])      # a known part keeps its simple share of the price
    figures_ok(card)
    eff = efficiency(client_g, as_of=NO_STATEMENT_AS_OF)
    assert eff["hour_cost"] is None and "no_expenses" in eff["partial_reasons"]


@engine_only
def test_golden_efficiency(client_g):
    e, exp = efficiency(client_g, as_of=GOLDEN_AS_OF, month=GOLDEN_MONTH), MAIN["efficiency"]
    assert (val(e["visits"]), val(e["avg_check"]), val(e["load_pct"]), val(e["hour_cost"])) == \
        (exp["visits"], exp["avg_check"], exp["load_pct"], exp["hour_cost"])
    assert [b["value"] for b in e["hour_cost"]["breakdown"]] == [exp["hour_cost_lines"]["fixed"], exp["hour_cost_lines"]["obligations"]]
    assert e.get("load_by", "rooms") == "rooms" and len(e["rooms"]) == 3
    by_name = {r["name"]: r for r in e["rooms"]}
    for want in exp["rooms"]:
        assert val(by_name[want["name"]]["load_pct"]) == want["load_pct"]
    if "hour_margin" in e:
        assert val(e["hour_margin"]) == exp["hour_margin"]


def test_every_figure_of_the_golden_clinic_has_breakdown_source_and_note(golden_body, golden_cards, client_g):
    figures_ok(golden_body)
    for card in golden_cards.values():
        figures_ok(card)
    figures_ok(efficiency(client_g, as_of=GOLDEN_AS_OF, month=GOLDEN_MONTH))


# ------------------------------------------------------------------ manual services (owner's decision 2026-10-18, item 1)
# POST /v1/services {name <=120, group <=80 optional, price kopecks}; PATCH/DELETE /v1/services/{id} only for source = manual
# (a service from Vetmanager answers 403 forbidden). Names follow design/screens/price.md; amounts are kopecks.
def need_writes():
    if not WRITES:
        pytest.skip("VF_CONTRACT_WRITES=1 is needed: this test creates and deletes a service of the test clinic")


@pytest.mark.parametrize("body,field,reason", [
    ({"price": 100_000}, "name", "required"), ({"name": "", "price": 100_000}, "name", "required"),
    ({"name": "я" * 121, "price": 100_000}, "name", "too_long"), ({"name": "Тест", "group": "г" * 81, "price": 100_000}, "group", "too_long"),
    ({"name": "Тест"}, "price", "required"), ({"name": "Тест", "price": 0}, "price", "must_be_positive"),
    ({"name": "Тест", "price": -5}, "price", "must_be_positive"), ({"name": "Тест", "price": 10.5}, "price", "invalid"),
    ({"name": "Тест", "price": 10 ** 13}, "price", "too_large"), ({"name": "Тест", "price": 1, "x": 1}, "x", "unknown_field"),
])
def test_post_service_validation(client_a, body, field, reason):
    r = implemented(client_a.post("/v1/services", json=body), "POST /v1/services")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"].get(field) == reason


def test_manual_service_lifecycle_and_duplicate_name(client_a):
    need_writes()
    name = "Тестовая услуга контракта 5"
    r = implemented(client_a.post("/v1/services", json={"name": name, "group": "Тест", "price": 123_450}), "POST /v1/services")
    assert r.status_code == 201, r.text
    try:
        created = r.json()
        sid = created["id"]
        row = next(s for s in services(client_a, limit=200) if s["id"] == sid)
        assert row["name"] == name and val(row["price"]) == 123_450 and val(row["visits_month"]) == 0
        assert row["status"] == "no_recipe" and row["margin_pct"] is None
        assert proposed(row, "source") == "manual"
        card = cost(client_a, sid)
        assert val(card["price"]) == 123_450 and card["status"] == "no_recipe"
        assert_error(client_a.post("/v1/services", json={"name": name.upper(), "price": 1}), 422, "validation")      # duplicate_name
        p = client_a.patch(f"/v1/services/{sid}", json={"price": 150_000, "name": name + " 2"})
        assert p.status_code in (200, 204), p.text
        assert val(next(s for s in services(client_a, limit=200) if s["id"] == sid)["price"]) == 150_000
        assert_error(client_a.patch(f"/v1/services/{sid}", json={"price": 0}), 422, "validation")
    finally:
        assert client_a.delete(f"/v1/services/{sid}").status_code in (204, 404)
    assert sid not in [s["id"] for s in services(client_a, limit=200)]
    assert_error(client_a.delete(f"/v1/services/{sid}"), 404, "not_found")


def test_service_from_vetmanager_cannot_be_edited_or_deleted(client_g):
    s = next(x for x in services(client_g, as_of=GOLDEN_AS_OF) if x.get("source", "vetmanager") == "vetmanager")
    assert_error(implemented(client_g.delete(f"/v1/services/{s['id']}"), "DELETE /v1/services/{id}"), 403, "forbidden")
    assert_error(client_g.patch(f"/v1/services/{s['id']}", json={"price": 1}), 403, "forbidden")


def test_manual_service_of_another_clinic_is_404(client_b):
    assert_error(implemented(client_b.delete(f"/v1/services/{UNKNOWN}"), "DELETE /v1/services/{id}"), 404, "not_found")
    assert_error(client_b.patch(f"/v1/services/{UNKNOWN}", json={"price": 1}), 404, "not_found")


@engine_only
def test_golden_manual_service_without_sales_keeps_its_entered_price(client_g):
    """Set06: M1 «Консультация ортопеда» (entered 2 500 rub, no sales); the manual «Чистка ушей» is absorbed by the sales of S7."""
    by_name = {s["name"]: s for s in services(client_g, as_of=GOLDEN_AS_OF)}
    m1 = by_name["Консультация ортопеда"]
    assert (val(m1["price"]), val(m1["visits_month"])) == (250_000, 0) and proposed(m1, "source") == "manual"
    assert by_name["Чистка ушей"].get("source", "vetmanager") == "vetmanager" and val(by_name["Чистка ушей"]["price"]) == 60_000
    assert len([n for n in by_name if n.lower().replace("  ", " ").strip() == "чистка ушей"]) == 1
