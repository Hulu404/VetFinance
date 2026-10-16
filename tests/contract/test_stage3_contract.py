"""Stage 3 contract tests: reports (functions 14, 15, 17, 18, 20) of docs/api-contract.md, "Отчёты".

    GET /v1/reports/pnl?month=YYYY-MM&view=clinic|direction
    GET /v1/reports/norm?month=YYYY-MM
    GET /v1/reports/stock[?as_of=YYYY-MM-DD]
    GET /v1/reports/{pnl|norm|stock}/export?format=xlsx|pdf&month=

Shapes follow the published "Отчёты" section of docs/api-contract.md (stage 3, step 1) and the owner's decisions of 2026-10-14:
pnl = {month, view, as_of, data_as_of, period{month,status,from,to,first_month}, status, partial_reasons[], headline?,
       rows[{key,label,kind,amount,share_pct?,children?,warning?}], unclassified: Figure, unclassified_count: int};
       view=direction adds directions[{direction,label,revenue,revenue_share_pct,direct_costs,margin,margin_pct}] and common_variable;
norm = {..same header.., items[{key,label,kind,memo,status?,tone?,norm?,actual_pct,deviation_pp?,deviation_rub?}]}; an open month has no
       status/tone/deviation_* keys; unit `pp` is checked on deviation_pp and on its breakdown rows;
stock = {stock_value, frozen, frozen_positions, idle_buckets[], expiring_60d, expiring[], expired_on_hand, expired_items[], written_off_month,
       written_off_norm, written_off_items[], turnover_days (90 days), norm_turnover_days}; GET /stock/idle pages the frozen positions.

Every test SKIPS while the endpoint answers 404 without the contract error body (route not implemented yet).
Run: eval "$(python tests/contract/get_tokens.py)" && pytest tests/contract/test_stage3_contract.py -rs
Golden comparison against set04: VF_SEEDED_SET04=1 and VF_TOKEN_E (clinic E seeded from tests/golden/set04).
Exports downloaded by the e2e run (tests/e2e/reports.spec.ts) are checked when VF_E2E_DOWNLOADS points at their folder.
"""
import json
import os
import re
from pathlib import Path

import pytest

import export_support as ex
from test_stage0_contract import ERROR_CODES, assert_error
from test_stage2_contract import assert_figure_v2
from test_stage2_contract import walk_figures

httpx = pytest.importorskip("httpx")

SET04 = Path(__file__).resolve().parents[1] / "golden" / "set04"
EXPECTED = json.loads((SET04 / "expected.json").read_text(encoding="utf-8"))
SEEDED = os.environ.get("VF_SEEDED_SET04") == "1"
MONTHS = ["2026-07", "2026-08", "2026-09"]
ROW_KEYS = ["revenue", "variable", "marginal_profit", "fixed", "taxes", "obligations", "net_profit"]
ROW_KINDS = ["revenue", "expense", "subtotal", "expense", "expense", "expense", "total"]
STATUSES = {"ok", "above", "below", "no_norm"}
TONES = {"good", "warn", "bad", "neutral"}
PERIOD_STATUSES = {"closed", "open"}
REPORT_STATUSES = {"ok", "partial", "empty"}
PARTIAL_REASONS = {"no_vetmanager", "bank_gap", "short_period", "no_obligations", "no_benchmark"}
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORTS = [("pnl", "month"), ("norm", "month"), ("stock", None)]


# ------------------------------------------------------------------ helpers
def get_report(client, path, **params):
    r = client.get(path, params=params)
    if r.status_code in (404, 405, 501) and "error" not in _json(r):
        pytest.skip(f"{path} is not implemented yet (HTTP {r.status_code} without a contract error body)")
    return r


def _json(r):
    try:
        body = r.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def ok(client, path, **params):
    r = get_report(client, path, **params)
    assert r.status_code == 200, r.text
    return r.json()


def pnl(client, month="2026-09", view="clinic"):
    return ok(client, "/v1/reports/pnl", month=month, view=view)


def labels(fig):
    return {b["label"]: b["value"] for b in fig["breakdown"]}


def by_key(rows):
    return {r["key"]: r for r in rows}


@pytest.fixture(scope="module")
def client_e(base_url):
    token = os.environ.get("VF_TOKEN_E")
    if not token or not SEEDED:
        pytest.skip("VF_TOKEN_E and VF_SEEDED_SET04=1 are needed (clinic seeded from golden set04)")
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60) as c:
        yield c


# ------------------------------------------------------------------ P&L shape
def assert_meta(d, month=None):
    """period / status / partial_reasons of design/screens/pnl.md and norm.md."""
    p = d["period"]
    assert re.fullmatch(r"\d{4}-\d{2}", p["month"]) and (month is None or p["month"] == month)
    assert d["month"] == p["month"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["as_of"]) and "data_as_of" in d
    assert p["status"] in PERIOD_STATUSES
    assert p["from"] == p["month"] + "-01"
    if p["status"] == "closed":  # as_of is not earlier than the last day of the month
        assert p["to"] is None
    else:
        assert p["to"] == d["as_of"] and p["to"][:7] == p["month"]
    assert p["first_month"] is None or re.fullmatch(r"\d{4}-\d{2}", p["first_month"])
    assert "headline" in d or d["status"] == "empty"
    assert d["status"] in REPORT_STATUSES
    assert isinstance(d["partial_reasons"], list) and set(d["partial_reasons"]) <= PARTIAL_REASONS
    assert (d["status"] == "partial") == bool(d["partial_reasons"])


def test_pnl_rows_are_in_contract_order_and_carry_the_obligations_line(client_a):
    d = pnl(client_a)
    assert d["view"] == "clinic"
    assert_meta(d, "2026-09")
    assert [r["key"] for r in d["rows"]] == ROW_KEYS
    assert [r["kind"] for r in d["rows"]] == ROW_KINDS
    assert d["rows"][5]["label"] == "Обязательства и амортизация"
    for r in d["rows"]:
        assert isinstance(r["label"], str) and r["label"]


def test_pnl_obligations_warning_matches_partial_reasons_and_unclassified_is_a_figure(client_a):
    d = pnl(client_a)
    ob = by_key(d["rows"])["obligations"]
    assert ("no_obligations" in d["partial_reasons"]) == (ob.get("warning") == "no_obligations")
    assert all("warning" not in r for r in d["rows"] if r["key"] != "obligations")
    assert_figure_v2(d["unclassified"], "unclassified")
    assert d["unclassified"]["unit"] == "rub" and type(d["unclassified_count"]) is int
    assert (d["unclassified_count"] == 0) == (d["unclassified"]["value"] == 0)


def test_pnl_identity_holds_in_the_response_itself(client_a):
    rows = {r["key"]: r["amount"]["value"] for r in pnl(client_a)["rows"]}
    assert rows["revenue"] - rows["variable"] - rows["fixed"] - rows["taxes"] - rows["obligations"] == rows["net_profit"]
    assert rows["marginal_profit"] == rows["revenue"] - rows["variable"]


def test_pnl_fixed_costs_children(client_a):
    fixed = by_key(pnl(client_a)["rows"])["fixed"]
    kids = fixed.get("children")
    assert kids, "rows[fixed].children is required by the contract"
    assert all("children" not in r for r in pnl(client_a)["rows"] if r["key"] != "fixed"), "children only on `fixed`"
    assert [c["key"] for c in kids] == ["fixed_payroll", "fixed_other"]
    assert sum(c["amount"]["value"] for c in kids) == fixed["amount"]["value"]
    for c in kids:
        assert c["kind"] == "child"
        assert_figure_v2(c["amount"], c["key"])


def test_pnl_every_figure_has_breakdown_source_and_note(client_a):
    d = pnl(client_a)
    found = list(walk_figures(d))
    assert len(found) >= 7
    for path, fig in found:
        assert_figure_v2(fig, path)
    for r in d["rows"]:
        if r["key"] not in ("marginal_profit", "net_profit"):
            assert sum(b["value"] for b in r["amount"]["breakdown"]) == r["amount"]["value"]


def test_pnl_share_is_percent_of_revenue_or_absent_without_revenue(client_a):
    d = pnl(client_a)
    revenue = by_key(d["rows"])["revenue"]["amount"]["value"]
    for r in d["rows"]:
        if revenue == 0:
            assert r.get("share_pct") is None
            continue
        assert r["share_pct"]["unit"] == "pct"
        expected = round(r["amount"]["value"] * 1000 / revenue) / 10
        assert abs(float(r["share_pct"]["value"]) - expected) <= 0.1 + 1e-9, r["key"]
    if revenue:
        assert float(by_key(d["rows"])["revenue"]["share_pct"]["value"]) == 100.0
        assert [b["label"] for b in by_key(d["rows"])["variable"]["share_pct"]["breakdown"]] == ["Сумма строки", "Выручка"]


def test_pnl_month_without_data_is_zeros_and_status_empty(client_a):
    d = pnl(client_a, month="2000-01")
    assert all(r["amount"]["value"] == 0 for r in d["rows"])
    assert all(r.get("share_pct") is None for r in d["rows"])
    assert d["status"] == "empty"


def test_pnl_direction_view(client_a):
    d = ok(client_a, "/v1/reports/pnl", month="2026-09", view="direction")
    assert d["view"] == "direction"
    assert [x["direction"] for x in d["directions"]] == ["services", "goods"]
    for x in d["directions"]:
        for k in ("revenue", "direct_costs", "margin"):
            assert_figure_v2(x[k], f"{x['direction']}.{k}")
        assert x["revenue"]["value"] - x["direct_costs"]["value"] == x["margin"]["value"]
        assert "profit" not in x, "the field is `margin` (decision of 2026-10-14)"
        assert isinstance(x["label"], str) and x["label"]
        for k in ("revenue_share_pct", "margin_pct"):
            assert_figure_v2(x[k], f"{x['direction']}.{k}")
            assert x[k]["unit"] == "pct"
    assert_figure_v2(d["common_variable"], "common_variable")
    rows = by_key(pnl(client_a)["rows"])
    s, g = d["directions"]
    assert s["revenue"]["value"] + g["revenue"]["value"] == rows["revenue"]["amount"]["value"]
    assert s["direct_costs"]["value"] + g["direct_costs"]["value"] + d["common_variable"]["value"] == rows["variable"]["amount"]["value"]
    assert s["margin"]["value"] + g["margin"]["value"] - d["common_variable"]["value"] == rows["marginal_profit"]["amount"]["value"]
    if "rows" in d:
        assert d["rows"] == pnl(client_a)["rows"]


@pytest.mark.parametrize("bad", ["garbage", "2026-13", "2026-9", "26-09", "2026-09-01", ""])
def test_pnl_invalid_month_is_a_validation_error(client_a, bad):
    r = get_report(client_a, "/v1/reports/pnl", month=bad)
    assert_error(r, 422, "validation")
    assert "month" in r.json()["error"]["details"].get("fields", {})


@pytest.mark.parametrize("bad", ["", "all", "CLINIC"])
def test_pnl_invalid_view_is_a_validation_error(client_a, bad):
    r = get_report(client_a, "/v1/reports/pnl", month="2026-09", view=bad)
    assert_error(r, 422, "validation")
    assert "view" in r.json()["error"]["details"].get("fields", {})


def test_pnl_without_month_uses_the_current_one_or_asks_for_it(client_a):
    r = get_report(client_a, "/v1/reports/pnl")
    assert r.status_code in (200, 422), r.text
    if r.status_code == 200:
        assert re.fullmatch(r"\d{4}-\d{2}", r.json()["month"])
    else:
        assert_error(r, 422, "validation")


# ------------------------------------------------------------------ norm shape
NORM_KEYS = ["payroll", "drugs", "rent", "lab", "writeoff", "acquiring", "marketing", "other", "net_profit"]
NORM_SOURCES = {"industry", "clinic"}
OPEN_FORBIDDEN = ("status", "tone", "deviation_pp", "deviation_rub")


def norm(client, month="2026-09", **params):
    return ok(client, "/v1/reports/norm", month=month, **params)


def test_norm_items_shape(client_a):
    d = norm(client_a)
    assert_meta(d, "2026-09")
    assert d["period"]["status"] == "closed", "2026-09 is closed at the default as_of; the open month is tested separately"
    assert isinstance(d["items"], list)
    keys = [i["key"] for i in d["items"]]
    assert len(keys) == len(set(keys))
    if d["status"] != "empty":
        assert [k for k in keys if k in NORM_KEYS] == [k for k in NORM_KEYS if k in keys], "items are in benchmarks.sort order"
        assert keys[-2:] == ["other", "net_profit"]
    for i in d["items"]:
        assert isinstance(i["label"], str) and i["label"]
        assert i["kind"] in ("expense", "other", "profit") and type(i["memo"]) is bool
        assert i["status"] in STATUSES and i["tone"] in TONES
        assert_figure_v2(i["actual_pct"], f"{i['key']}.actual_pct")
        assert i["actual_pct"]["unit"] == "pct"
        if i["status"] == "no_norm":
            assert i["tone"] == "neutral"
            assert not any(k in i for k in ("norm", "deviation_pp", "deviation_rub")), "no_norm rows carry no norm and no deviations"
            continue
        n = i["norm"]
        assert set(n) >= {"min_pct", "max_pct", "source"} and n["source"] in NORM_SOURCES
        assert n["min_pct"] is not None or n["max_pct"] is not None
        if n["min_pct"] is not None and n["max_pct"] is not None:
            assert 0 <= n["min_pct"] <= n["max_pct"]
        assert isinstance(n.get("note"), str) and n["note"], "norm.note describes the norm"
        assert all(b["unit"] == "rub" for b in n.get("breakdown", [])), "norm.breakdown: bounds in roubles"
        assert_figure_v2(i["deviation_pp"], f"{i['key']}.deviation_pp")
        assert i["deviation_pp"]["unit"] == "pp" and i["deviation_pp"].get("delta") is True, "deviation_pp is Figure(pp, delta)"
        assert_figure_v2(i["deviation_rub"], f"{i['key']}.deviation_rub")
        assert i["deviation_rub"]["unit"] == "rub" and i["deviation_rub"].get("delta") is True


def test_norm_pp_unit_is_checked_in_the_figure_and_in_its_breakdown_rows(client_a):
    rated = [i for i in norm(client_a)["items"] if i["status"] in ("above", "below", "ok")]
    if not rated:
        pytest.skip("no rated item in 2026-09")
    for i in rated:
        fig = i["deviation_pp"]
        assert fig["unit"] == "pp", i["key"]
        assert all(b["unit"] in ("pct", "pp") for b in fig["breakdown"]), f"{i['key']}: pp breakdown rows are pct or pp"
        if i["status"] != "ok":  # "Ваша доля", "Граница нормы" (pct) and "Отклонение" (pp, delta)
            assert [b["unit"] for b in fig["breakdown"]] == ["pct", "pct", "pp"], i["key"]
            assert fig["breakdown"][2].get("delta") is True and fig["breakdown"][2]["value"] == fig["value"], i["key"]


def test_norm_status_and_signs_agree(client_a):
    for i in norm(client_a)["items"]:
        if i["status"] == "no_norm":
            continue
        rub, pp = i["deviation_rub"]["value"], float(i["deviation_pp"]["value"])
        if i["status"] == "ok":
            assert rub == 0 and pp == 0, i["key"]
            assert i["deviation_rub"]["breakdown"] == [] and i["deviation_rub"]["details"], "ok: empty breakdown, headroom in details"
        elif i["status"] == "above":
            assert rub > 0 and pp >= 0, i["key"]
        else:
            assert rub < 0 and pp <= 0, i["key"]
        if i["status"] != "ok":
            bound = i["norm"]["max_pct"] if i["status"] == "above" else i["norm"]["min_pct"]
            assert abs(float(i["actual_pct"]["value"]) - float(bound) - pp) <= 0.1 + 1e-9, f"{i['key']}: shown share - shown bound != shown deviation"
            assert sum(b["value"] for b in i["deviation_rub"]["breakdown"]) == rub, f"{i['key']}: deviation_rub breakdown must add up"


def test_norm_tone_follows_status(client_a):
    for i in norm(client_a)["items"]:
        if i["status"] == "no_norm":
            continue
        profit = i["key"] == "net_profit"
        expected = {"ok": "good", "above": "good" if profit else "bad", "below": "bad" if profit else "warn"}[i["status"]]
        assert i["tone"] == expected, (i["key"], i["status"])


def test_norm_memo_row_is_the_writeoff_and_outside_the_hundred_percent(client_a):
    d = norm(client_a)
    if d["status"] == "empty":
        pytest.skip("no data for 2026-09")
    assert [i["key"] for i in d["items"] if i["memo"]] == ["writeoff"], "only the expiry write-off is a memo row"


def test_norm_accounts_for_the_whole_revenue(client_a):
    """groups + 'other' + net profit = revenue (the memo row 'writeoff' is outside); from the response itself."""
    d = norm(client_a)
    revenue = by_key(pnl(client_a)["rows"])["revenue"]["amount"]["value"]
    if d["status"] == "empty" or not d["items"]:
        pytest.skip("no revenue for this clinic in 2026-09")
    total = sum(sum(b["value"] for b in i["actual_pct"]["breakdown"]) for i in d["items"] if not i["memo"])
    assert total == revenue


def test_norm_net_profit_agrees_with_the_pnl(client_a):
    items = by_key(norm(client_a)["items"])
    if "net_profit" not in items:
        pytest.skip("no net_profit item")
    rows = by_key(pnl(client_a)["rows"])
    assert float(items["net_profit"]["actual_pct"]["value"]) == float(rows["net_profit"]["share_pct"]["value"])


def test_norm_every_figure_has_breakdown_source_and_note(client_a):
    for path, fig in walk_figures(norm(client_a)):
        assert_figure_v2(fig, path)


def test_norm_invalid_month(client_a):
    assert_error(get_report(client_a, "/v1/reports/norm", month="09.2026"), 422, "validation")


# ------------------------------------------------------------------ the running month (period.status = open)
OPEN_AS_OF = "2026-09-15"


def open_report(client, path, **params):
    d = ok(client, path, month="2026-09", as_of=OPEN_AS_OF, **params)
    assert d["period"]["status"] == "open", f"as_of={OPEN_AS_OF} must open 2026-09, got period.status={d['period']['status']} (as_of ignored?)"
    return d


def test_norm_in_a_running_month_has_no_ratings(client_a):
    """Shares are shown, norm bounds stay, but the keys status/tone/deviation_* are ABSENT (owner decision 2026-10-14)."""
    d = open_report(client_a, "/v1/reports/norm")
    assert_meta(d, "2026-09")
    assert d["period"]["to"] == OPEN_AS_OF and d["as_of"] == OPEN_AS_OF
    if d["status"] == "empty":
        pytest.skip("clinic has no data in the first half of 2026-09")
    assert "Сравним с нормой, когда месяц закончится" in d["headline"]
    for i in d["items"]:
        for k in OPEN_FORBIDDEN:
            assert k not in i, f"{i['key']}: key `{k}` must be absent in a running month"
        assert_figure_v2(i["actual_pct"], f"{i['key']}.actual_pct")
        if "norm" in i:
            assert i["norm"]["source"] in NORM_SOURCES


def test_pnl_in_a_running_month_to_equals_as_of_and_identity_holds(client_a):
    d = open_report(client_a, "/v1/reports/pnl", view="clinic")
    assert_meta(d, "2026-09")
    assert d["period"]["to"] == OPEN_AS_OF and d["as_of"] == OPEN_AS_OF
    rows = {r["key"]: r["amount"]["value"] for r in d["rows"]}
    assert rows["revenue"] - rows["variable"] - rows["fixed"] - rows["taxes"] - rows["obligations"] == rows["net_profit"]
    for key in ("taxes", "obligations"):
        assert by_key(d["rows"])[key]["amount"]["note"], key


def test_report_month_after_the_as_of_month_is_in_future(client_a):
    r = get_report(client_a, "/v1/reports/pnl", month="2026-10", as_of=OPEN_AS_OF)
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"]["month"] == "in_future"


# ------------------------------------------------------------------ stock shape
STOCK_REASONS = {"missing_expiry", "short_history", "stale_stock", "no_vetmanager", "bank_gap"}
BUCKETS = ["60_89", "90_179", "180_plus"]
DATE_RE = r"\d{4}-\d{2}-\d{2}"


def stock(client, **params):
    return ok(client, "/v1/reports/stock", **params)


def test_stock_has_the_contract_fields(client_a):
    d = stock(client_a)
    for key in ("stock_value", "frozen", "frozen_positions", "expiring_60d", "expired_on_hand", "written_off_month", "written_off_norm",
                "turnover_days"):
        assert_figure_v2(d[key], key)
    assert d["frozen_positions"]["unit"] == "count"
    assert d["turnover_days"]["unit"] == "days"
    assert d["norm_turnover_days"] == 45 and type(d["norm_turnover_days"]) is int
    for key in ("expiring", "expired_items", "written_off_items", "idle_buckets"):
        assert isinstance(d[key], list), key
    assert d["status"] in REPORT_STATUSES and set(d["partial_reasons"]) <= STOCK_REASONS
    assert re.fullmatch(r"\d{4}-\d{2}", d["month"]) and re.fullmatch(DATE_RE, d["as_of"])
    assert "frozen_items" not in d, "the position list is paged through /stock/idle"


def test_stock_turnover_uses_the_90_day_window(client_a):
    fig = stock(client_a)["turnover_days"]
    if fig["value"] == 0 and not fig["breakdown"]:
        pytest.skip("no stock data")
    names = [b["label"] for b in fig["breakdown"]]
    assert names[:3] == ["Запас на складе", "Расход за 90 дней", "Окно расчёта"], names
    assert fig["breakdown"][2]["value"] == 90 and fig["breakdown"][2]["unit"] == "days"
    held, spent = fig["breakdown"][0]["value"], fig["breakdown"][1]["value"]
    if spent:  # nearest day, half up, integer arithmetic
        assert fig["value"] == (held * 90 * 2 + spent) // (2 * spent)
    assert any(x["label"] == "Норма" for x in fig.get("details", []))


def test_stock_expiring_rows(client_a):
    d = stock(client_a)
    rows = d["expiring"]
    for r in rows:
        assert set(r) >= {"item", "expires_on", "days_left", "qty", "amount"}
        assert re.fullmatch(DATE_RE, r["expires_on"])
        assert 0 <= r["days_left"] <= 60 and type(r["qty"]) is int, "expired batches are never in expiring[]"
        assert_figure_v2(r["amount"], f"expiring.{r['item']}")
    assert [(r["expires_on"], r["item"]) for r in rows] == sorted((r["expires_on"], r["item"]) for r in rows)
    assert sum(r["amount"]["value"] for r in rows) == d["expiring_60d"]["value"]


def test_stock_expired_on_hand_is_separate_from_expiring(client_a):
    d = stock(client_a)
    expired = d["expired_items"]
    assert all(r["days_left"] < 0 for r in expired)
    assert sum(r["amount"]["value"] for r in expired) == d["expired_on_hand"]["value"]
    assert (d["expired_on_hand"]["value"] == 0) == (not expired)
    if expired:
        assert d["expired_on_hand"]["details"], "details: how long the oldest batch has been expired"


def test_stock_frozen_breakdown_has_three_buckets_and_sums(client_a):
    d = stock(client_a)
    fig = d["frozen"]
    if fig["value"]:
        assert len(fig["breakdown"]) == 3
    assert sum(b["value"] for b in fig["breakdown"]) == fig["value"]
    if d["idle_buckets"]:
        assert [b["key"] for b in d["idle_buckets"]] == BUCKETS
    assert sum(b["amount"]["value"] for b in d["idle_buckets"]) == fig["value"]
    assert sum(b["positions"]["value"] for b in d["idle_buckets"]) == d["frozen_positions"]["value"]
    for b in d["idle_buckets"]:
        assert isinstance(b["label"], str) and b["label"] and b["positions"]["unit"] == "count"
        assert_figure_v2(b["amount"], b["key"])
        assert_figure_v2(b["positions"], b["key"] + ".positions")


def test_stock_written_off(client_a):
    d = stock(client_a)
    items = d["written_off_items"]
    for r in items:
        assert set(r) >= {"item", "date", "qty", "reason", "amount"} and r["reason"] in ("expired", "damaged", "other")
        assert_figure_v2(r["amount"], f"written_off.{r['item']}")
    assert [r["amount"]["value"] for r in items] == sorted((r["amount"]["value"] for r in items), reverse=True)
    assert sum(r["amount"]["value"] for r in items) == d["written_off_month"]["value"]


def test_stock_writeoff_agrees_with_the_norm_memo_row(client_a):
    """The Norm row counts only reason `expired`; `written_off_month` has all reasons, so the match is on the expired part."""
    s_ = stock(client_a, month="2026-09", as_of="2026-09-30")
    n_ = norm(client_a, month="2026-09", as_of="2026-09-30")
    row = by_key(n_["items"]).get("writeoff")
    if row is None or s_["status"] == "empty":
        pytest.skip("no write-off row / no stock data")
    assert row["memo"] is True
    memo_amount = sum(b["value"] for b in row["actual_pct"]["breakdown"])
    expired = sum(r["amount"]["value"] for r in s_["written_off_items"] if r["reason"] == "expired")
    assert memo_amount == expired, "Norm memo row = Stock write-offs with reason expired"
    assert memo_amount <= s_["written_off_month"]["value"]
    assert s_["written_off_norm"]["value"] == row["norm"]["breakdown"][-1]["value"], "written_off_norm = upper bound of the `writeoff` norm row"


def test_stock_invalid_as_of(client_a):
    assert_error(get_report(client_a, "/v1/reports/stock", as_of="nope"), 422, "validation")


# ------------------------------------------------------------------ GET /stock/idle
def idle(client, **params):
    return ok(client, "/v1/reports/stock/idle", **params)


def test_stock_idle_page_shape(client_a):
    d = idle(client_a, bucket="all", limit=3)
    assert set(d) >= {"items", "next_cursor", "total"}
    assert_figure_v2(d["total"], "total")
    assert d["total"]["unit"] == "count"
    assert len(d["items"]) <= 3
    for r in d["items"]:
        assert set(r) >= {"item", "last_movement_on", "idle_days", "bucket", "qty", "amount"}
        assert r["bucket"] in BUCKETS and r["idle_days"] >= 60
        assert_figure_v2(r["amount"], f"idle.{r['item']}")
    assert [(-r["amount"]["value"], r["item"]) for r in d["items"]] == sorted((-r["amount"]["value"], r["item"]) for r in d["items"])
    assert (d["next_cursor"] is None) == (len(d["items"]) >= d["total"]["value"] or len(d["items"]) < 3)


def test_stock_idle_cursor_walks_all_positions_without_repeats(client_a):
    seen, cursor, total = [], None, None
    for _ in range(30):
        params = {"bucket": "all", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        d = idle(client_a, **params)
        total = d["total"]["value"]
        seen += [r["item"] for r in d["items"]]
        cursor = d["next_cursor"]
        if not cursor:
            break
    assert cursor is None, "paging must end"
    assert len(seen) == len(set(seen)) == total


@pytest.mark.parametrize("bucket", BUCKETS)
def test_stock_idle_bucket_filter(client_a, bucket):
    d = idle(client_a, bucket=bucket, limit=50)
    assert all(r["bucket"] == bucket for r in d["items"])
    assert d["total"]["value"] == len(d["items"])


@pytest.mark.parametrize("params", [{"bucket": "30_59"}, {"bucket": ""}, {"limit": 0}, {"limit": 51}, {"limit": "x"}, {"cursor": "!!not-a-cursor!!"}])
def test_stock_idle_invalid_params_are_validation_errors(client_a, params):
    assert_error(get_report(client_a, "/v1/reports/stock/idle", **params), 422, "validation")


# ------------------------------------------------------------------ cross-cutting: money, determinism, auth, isolation
@pytest.mark.parametrize("path,params", [("/v1/reports/pnl", {"month": "2026-09"}), ("/v1/reports/norm", {"month": "2026-09"}),
                                         ("/v1/reports/stock", {})])
def test_money_is_never_a_string_or_float_and_response_is_deterministic(client_a, path, params):
    first = ok(client_a, path, **params)

    def scan(node, where):
        if isinstance(node, dict):
            for k, v in node.items():
                scan(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan(v, f"{where}[{i}]")
        elif isinstance(node, str) and where.endswith(".value"):
            pytest.fail(f"{where}: value is a string {node!r}")
    scan(first, path)
    assert ok(client_a, path, **params) == first, "the same request twice must give identical numbers"


@pytest.mark.parametrize("path", ["/v1/reports/pnl", "/v1/reports/norm", "/v1/reports/stock", "/v1/reports/pnl/export"])
def test_no_token_is_401(anon, path):
    r = anon.get(path, params={"month": "2026-09", "format": "xlsx"})
    if r.status_code == 404 and "error" not in _json(r):
        pytest.skip(f"{path} is not implemented yet")
    assert_error(r, 401, "unauthorized")


def test_clinic_id_parameter_is_ignored(client_a):
    base = pnl(client_a)
    other = ok(client_a, "/v1/reports/pnl", month="2026-09", view="clinic", clinic_id="00000000-0000-0000-0000-000000000000")
    assert base == other


def test_two_clinics_get_different_reports_and_never_each_others_labels(client_a, client_b):
    a, b = pnl(client_a), pnl(client_b)
    ra, rb = by_key(a["rows"]), by_key(b["rows"])
    if ra["revenue"]["amount"]["value"] == 0 and rb["revenue"]["amount"]["value"] == 0:
        pytest.skip("both test clinics have no revenue in 2026-09: nothing to compare")
    assert a != b
    own_a = {x["name"] for x in _items(client_a.get("/v1/accounts").json())}
    own_b = {x["name"] for x in _items(client_b.get("/v1/accounts").json())}
    for r in b["rows"]:  # labels of a report are articles and fixed words, never the other clinic's accounts or counterparties
        assert not (set(labels(r["amount"])) & (own_a - own_b))


def _items(body):
    return body["items"] if isinstance(body, dict) and "items" in body else body


def test_error_codes_stay_inside_the_contract(client_a):
    r = get_report(client_a, "/v1/reports/pnl", month="nope")
    assert r.json()["error"]["code"] in ERROR_CODES


# ------------------------------------------------------------------ export (function 20)
def export(client, name, fmt, **params):
    r = get_report(client, f"/v1/reports/{name}/export", format=fmt, **params)
    assert r.status_code == 200, r.text[:300]
    return r


def params_for(name, month):
    return {"month": month} if name != "stock" else {}


@pytest.mark.parametrize("name,_", EXPORTS)
def test_export_headers_for_xlsx_and_pdf(client_a, name, _):
    x = export(client_a, name, "xlsx", **params_for(name, "2026-09"))
    assert x.headers["content-type"].split(";")[0] == XLSX_TYPE
    assert "attachment" in x.headers.get("content-disposition", "") and ".xlsx" in x.headers["content-disposition"]
    assert x.content[:2] == b"PK", "xlsx is a zip container"
    p = export(client_a, name, "pdf", **params_for(name, "2026-09"))
    assert p.headers["content-type"].split(";")[0] == "application/pdf"
    assert ".pdf" in p.headers.get("content-disposition", "") and p.content[:5] == b"%PDF-"


@pytest.mark.parametrize("bad", ["", "csv", "XLSX", "doc"])
def test_export_unknown_format_is_a_validation_error(client_a, bad):
    r = get_report(client_a, "/v1/reports/pnl/export", format=bad, month="2026-09")
    assert_error(r, 422, "validation")
    assert "format" in r.json()["error"]["details"].get("fields", {})


def test_export_unknown_report_is_not_found(client_a):
    r = client_a.get("/v1/reports/nothing/export", params={"format": "xlsx", "month": "2026-09"})
    if r.status_code == 404 and "error" not in _json(r):
        pytest.skip("export route is not implemented yet")
    assert_error(r, 404, "not_found")


def test_export_invalid_month_is_a_validation_error(client_a):
    assert_error(get_report(client_a, "/v1/reports/pnl/export", format="xlsx", month="2026-13"), 422, "validation")


def check_pnl_xlsx(wb, d):
    rows = list(ex.sheet_rows(wb))
    for r in d["rows"] + [c for row in d["rows"] for c in row.get("children") or []]:
        row = ex.find_row(rows, r["label"])
        assert row is not None, f"xlsx: row '{r['label']}' not found"
        assert ex.row_has_money(row, r["amount"]["value"]), f"xlsx: {r['label']} amount differs from the screen ({r['amount']['value']} kop)"
        if r.get("share_pct"):
            assert ex.row_has_pct(row, r["share_pct"]["value"]), f"xlsx: {r['label']} share differs"


def check_norm_xlsx(wb, d):
    rows = list(ex.sheet_rows(wb))
    for i in d["items"]:
        row = ex.find_row(rows, i["label"])
        assert row is not None, f"xlsx: row '{i['label']}' not found"
        assert ex.row_has_pct(row, i["actual_pct"]["value"]), f"xlsx: {i['label']} actual share differs"
        if i.get("deviation_rub"):
            assert ex.row_has_money(row, i["deviation_rub"]["value"]) or i["deviation_rub"]["value"] == 0, f"xlsx: {i['label']} deviation differs"
            assert ex.row_has_pct(row, i["deviation_pp"]["value"]) or float(i["deviation_pp"]["value"]) == 0, f"xlsx: {i['label']} pp differs"


def check_stock_xlsx(wb, d):
    for key in ("frozen", "expiring_60d", "written_off_month"):
        if d[key]["value"]:
            assert ex.workbook_has_money(wb, d[key]["value"]), f"xlsx: {key} total {d[key]['value']} kop not found"
    assert any(abs(float(c) - d["turnover_days"]["value"]) < 0.5 for c in ex.all_numbers(wb)), "xlsx: turnover days not found"
    texts = ex.text_cells(wb)
    for r in d["expiring"]:
        assert any(r["item"] in t for t in texts), f"xlsx: expiring item {r['item']} not found"
        assert ex.workbook_has_money(wb, r["amount"]["value"])


def check_pdf(text, name, d):
    if name == "pnl":
        for r in d["rows"] + [c for row in d["rows"] for c in row.get("children") or []]:
            assert ex.pdf_has_label(text, r["label"]), f"pdf: '{r['label']}' missing"
            assert ex.pdf_has_amount(text, r["amount"]["value"]), f"pdf: {r['label']} amount {r['amount']['value']} kop missing"
    elif name == "norm":
        for i in d["items"]:
            assert ex.pdf_has_label(text, i["label"]), f"pdf: '{i['label']}' missing"
            assert ex.pdf_has_pct(text, i["actual_pct"]["value"]), f"pdf: {i['label']} share missing"
            if i.get("deviation_rub") and i["deviation_rub"]["value"]:
                assert ex.pdf_has_amount(text, i["deviation_rub"]["value"]), f"pdf: {i['label']} deviation missing"
    else:
        for key in ("frozen", "expiring_60d", "written_off_month"):
            if d[key]["value"]:
                assert ex.pdf_has_amount(text, d[key]["value"]), f"pdf: {key} missing"
        for r in d["expiring"]:
            assert ex.pdf_has_label(text, r["item"]) and ex.pdf_has_amount(text, r["amount"]["value"])


XLSX_CHECKS = {"pnl": check_pnl_xlsx, "norm": check_norm_xlsx, "stock": check_stock_xlsx}


@pytest.mark.parametrize("name,_", EXPORTS)
def test_xlsx_numbers_equal_the_screen_json(client_a, name, _):
    params = params_for(name, "2026-09")
    d = ok(client_a, f"/v1/reports/{name}", **params)
    wb = ex.load_xlsx(export(client_a, name, "xlsx", **params).content)
    XLSX_CHECKS[name](wb, d)


@pytest.mark.parametrize("name,_", EXPORTS)
def test_pdf_text_contains_the_screen_numbers(client_a, name, _):
    params = params_for(name, "2026-09")
    d = ok(client_a, f"/v1/reports/{name}", **params)
    check_pdf(ex.pdf_text(export(client_a, name, "pdf", **params).content), name, d)


def test_export_does_not_leak_the_other_clinic(client_a, client_b):
    pa = ex.load_xlsx(export(client_a, "pnl", "xlsx", month="2026-09").content)
    pb = ex.load_xlsx(export(client_b, "pnl", "xlsx", month="2026-09").content)
    ra, rb = by_key(pnl(client_a)["rows"]), by_key(pnl(client_b)["rows"])
    if ra["net_profit"]["amount"]["value"] != rb["net_profit"]["amount"]["value"]:
        assert not ex.workbook_has_money(pa, rb["net_profit"]["amount"]["value"])
        assert not ex.workbook_has_money(pb, ra["net_profit"]["amount"]["value"])


# ------------------------------------------------------------------ exports saved by the e2e run
DOWNLOADS = os.environ.get("VF_E2E_DOWNLOADS")


@pytest.mark.skipif(not DOWNLOADS, reason="VF_E2E_DOWNLOADS (folder with files saved by tests/e2e/reports.spec.ts) is not set")
def test_files_downloaded_by_e2e_equal_the_api(client_a, client_e):
    """File names written by the e2e: <report>-<month>.xlsx / .pdf, clinic from VF_E2E_DOWNLOADS_CLINIC (default A)."""
    golden = os.environ.get("VF_E2E_DOWNLOADS_CLINIC") == "E"
    client = client_e if golden else client_a
    # the e2e opens the stock of the golden clinic at STOCK_AS_OF (reports.spec.ts), not at today
    stock_params = {"as_of": "2026-09-30"} if golden else {}
    folder = Path(DOWNLOADS)
    files = sorted(folder.glob("*.xlsx")) + sorted(folder.glob("*.pdf"))
    assert files, f"no exports found in {folder}"
    for f in files:
        m = re.fullmatch(r"(pnl|norm|stock)-(\d{4}-\d{2}|current)\.(xlsx|pdf)", f.name)
        assert m, f"unexpected file name {f.name}"
        name, month, fmt = m.groups()
        params = stock_params if name == "stock" else {} if month == "current" else {"month": month}
        d = ok(client, f"/v1/reports/{name}", **params)
        if fmt == "xlsx":
            XLSX_CHECKS[name](ex.load_xlsx(f.read_bytes()), d)
        else:
            check_pdf(ex.pdf_text(f.read_bytes()), name, d)


# ------------------------------------------------------------------ golden clinic (seeded from set04)
@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
@pytest.mark.parametrize("month", MONTHS)
def test_pnl_matches_golden_set04(client_e, month):
    d = pnl(client_e, month)
    exp = {r["key"]: r for r in EXPECTED["pnl"][month]["rows"]}
    assert [r["key"] for r in d["rows"]] == ROW_KEYS
    for r in d["rows"]:
        e = exp[r["key"]]
        assert r["amount"]["value"] == e["amount"]["value"], (month, r["key"])
        assert list(labels(r["amount"]).items()) == list(e["amount"]["breakdown"].items()), (month, r["key"])
        assert r["amount"]["source"] == e["amount"]["source"], (month, r["key"])
        assert float(r["share_pct"]["value"]) == e["share_pct"]["value"], (month, r["key"])
    assert d["unclassified_count"] == EXPECTED["pnl"][month]["unclassified"]["count"]
    assert d["unclassified"]["value"] == EXPECTED["pnl"][month]["unclassified"]["amount"]
    assert d["status"] == EXPECTED["pnl"][month]["status"] and d["partial_reasons"] == EXPECTED["pnl"][month]["partial_reasons"]
    assert d["period"]["first_month"] == "2026-07"


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
@pytest.mark.parametrize("month", MONTHS)
def test_direction_view_matches_golden_set04(client_e, month):
    d = ok(client_e, "/v1/reports/pnl", month=month, view="direction")
    exp = EXPECTED["direction"][month]
    got = {i["direction"]: i for i in d["directions"]}
    for e in exp["directions"]:
        g = got[e["direction"]]
        assert g["revenue"]["value"] == e["revenue"]["value"]
        assert g["direct_costs"]["value"] == e["direct_costs"]
        assert g["margin"]["value"] == e["margin"]
        assert float(g["margin_pct"]["value"]) == e["margin_pct"]
    assert d["common_variable"]["value"] == exp["common_variable"]["value"]
    assert labels(d["common_variable"]) == exp["common_variable"]["breakdown"]


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
@pytest.mark.parametrize("month", MONTHS)
def test_norm_matches_golden_set04(client_e, month):
    d = ok(client_e, "/v1/reports/norm", month=month)
    exp = EXPECTED["norm"][month]["items"]
    assert [i["key"] for i in d["items"]] == [e["key"] for e in exp]
    for g, e in zip(d["items"], exp):
        assert g["status"] == e["status"], (month, g["key"])
        assert g["tone"] == e["tone"], (month, g["key"])
        assert float(g["actual_pct"]["value"]) == e["actual_pct"], (month, g["key"])
        assert list(labels(g["actual_pct"]).items()) == list(e["amount_breakdown"].items()), (month, g["key"])
        if e["status"] == "no_norm":
            continue
        assert g["deviation_rub"]["value"] == e["deviation_rub"], (month, g["key"])
        assert float(g["deviation_pp"]["value"]) == e["deviation_pp"], (month, g["key"])
        assert (g["norm"]["source"] == "clinic") == (e["norm"]["source"] == "clinic"), (month, g["key"])


OPEN_CASES = EXPECTED["open_cases"]
OPEN_IDS = [c["key"] for c in OPEN_CASES]


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
@pytest.mark.parametrize("case", OPEN_CASES, ids=OPEN_IDS)
def test_running_month_pnl_matches_golden_set04(client_e, case):
    d = ok(client_e, "/v1/reports/pnl", month=case["month"], view="clinic", as_of=case["as_of"])
    exp = {r["key"]: r for r in EXPECTED["pnl"][case["key"]]["rows"]}
    for r in d["rows"]:
        assert r["amount"]["value"] == exp[r["key"]]["amount"]["value"], r["key"]
        assert float(r["share_pct"]["value"]) == exp[r["key"]]["share_pct"]["value"], r["key"]
    assert d["period"]["status"] == "open" and d["period"]["to"] == case["as_of"] and d["as_of"] == case["as_of"]
    assert d["status"] == EXPECTED["pnl"][case["key"]]["status"] and d["partial_reasons"] == EXPECTED["pnl"][case["key"]]["partial_reasons"]


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
@pytest.mark.parametrize("case", OPEN_CASES, ids=OPEN_IDS)
def test_running_month_norm_matches_golden_set04(client_e, case):
    d = ok(client_e, "/v1/reports/norm", month=case["month"], as_of=case["as_of"])
    exp = EXPECTED["norm"][case["key"]]
    assert d["period"]["status"] == "open" and d["partial_reasons"] == exp["partial_reasons"]
    assert d["headline"].replace(chr(0xA0), " ") == exp["headline_open"]
    assert [i["key"] for i in d["items"]] == [e["key"] for e in exp["items"]]
    for g, e in zip(d["items"], exp["items"]):
        assert not any(k in g for k in OPEN_FORBIDDEN), g["key"]
        assert float(g["actual_pct"]["value"]) == e["actual_pct"], g["key"]
        assert list(labels(g["actual_pct"]).items()) == list(e["amount_breakdown"].items()), g["key"]
        if e["norm"]:
            assert (g["norm"]["min_pct"], g["norm"]["max_pct"]) == (e["norm"]["min_pct"], e["norm"]["max_pct"]), g["key"]


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
def test_stock_matches_golden_set04(client_e):
    exp = EXPECTED["stock"]
    d = stock(client_e, as_of=exp["as_of"])
    assert d["status"] == "ok" or d["status"] == "partial"
    assert d["stock_value"]["value"] == exp["stock_value"]["value"]
    assert d["frozen"]["value"] == exp["frozen"]["value"] and labels(d["frozen"]) == exp["frozen"]["breakdown"]
    assert d["expiring_60d"]["value"] == exp["expiring_60d"]["value"]
    assert [(r["item"], r["expires_on"], r["days_left"], r["qty"], r["amount"]["value"]) for r in d["expiring"]] == \
        [(r["item"], r["expires_on"], r["days_left"], r["qty"], r["amount"]) for r in exp["expiring_60d"]["rows"]]
    assert d["expired_on_hand"]["value"] == exp["expired_on_hand"]["value"] == 55_500
    assert [(r["item"], r["expires_on"], r["days_left"], r["qty"], r["amount"]["value"]) for r in d["expired_items"]] == \
        [(r["item"], r["expires_on"], r["days_left"], r["qty"], r["amount"]) for r in exp["expired_on_hand"]["rows"]]
    assert d["written_off_month"]["value"] == exp["written_off_month"]["value"]
    assert d["turnover_days"]["value"] == exp["turnover_days"]["value"]
    assert [b["value"] for b in d["turnover_days"]["breakdown"][:3]] == exp["turnover_days"]["breakdown_values"]
    assert d["month"] == "2026-09"


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
def test_stock_idle_buckets_positions_writeoffs_and_norm_match_golden_set04(client_e):
    exp = EXPECTED["stock"]
    d = stock(client_e, as_of=exp["as_of"])
    assert [(b["key"], b["amount"]["value"], b["positions"]["value"]) for b in d["idle_buckets"]] == \
        [(b["key"], b["amount"], b["positions"]) for b in exp["idle_buckets"]]
    assert d["frozen_positions"]["value"] == exp["frozen_positions"]["value"]
    assert [b["value"] for b in d["frozen_positions"]["breakdown"]] == exp["frozen_positions"]["breakdown_values"]
    assert [(i["item"], i["date"], i["qty"], i["reason"], i["amount"]["value"]) for i in d["written_off_items"]] == \
        [(i["item"], i["date"], i["qty"], i["reason"], i["amount"]) for i in exp["written_off_items"]]
    wn = exp["written_off_norm"]
    assert d["written_off_norm"]["value"] == wn["value"]
    norm_row = by_key(ok(client_e, "/v1/reports/norm", month=wn["month"], as_of=exp["as_of"])["items"])["writeoff"]
    assert norm_row["memo"] is True and norm_row["deviation_rub"]["value"] == wn["over_norm"]
    assert sum(b["value"] for b in norm_row["actual_pct"]["breakdown"]) == wn["expired"]
    assert norm_row["norm"]["breakdown"][-1]["value"] == wn["value"]


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
@pytest.mark.parametrize("case", EXPECTED["stock"]["idle_pages"], ids=lambda c: f"{c['bucket']}-limit{c['limit']}")
def test_stock_idle_pages_match_golden_set04(client_e, case):
    cursor, got_pages = None, []
    for _ in range(len(case["pages"]) + 1):
        params = {"bucket": case["bucket"], "limit": case["limit"], "as_of": EXPECTED["stock"]["as_of"]}
        if cursor:
            params["cursor"] = cursor
        d = idle(client_e, **params)
        assert d["total"]["value"] == case["total"]
        got_pages.append(([(i["item"], i["last_movement_on"], i["idle_days"], i["bucket"], i["qty"], i["amount"]["value"]) for i in d["items"]],
                          d["next_cursor"] is not None))
        cursor = d["next_cursor"]
        if cursor is None:
            break
    assert got_pages == [([(i["item"], i["last_movement_on"], i["idle_days"], i["bucket"], i["qty"], i["amount"]) for i in pg["items"]],
                          pg["has_next"]) for pg in case["pages"]]


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
@pytest.mark.parametrize("name,_", EXPORTS)
def test_golden_exports_equal_the_screen(client_e, name, _):
    params = params_for(name, "2026-09")
    if name == "stock":
        params = {"as_of": EXPECTED["stock"]["as_of"]}
    d = ok(client_e, f"/v1/reports/{name}", **params)
    XLSX_CHECKS[name](ex.load_xlsx(export(client_e, name, "xlsx", **params).content), d)
    check_pdf(ex.pdf_text(export(client_e, name, "pdf", **params).content), name, d)


@pytest.mark.skipif(not SEEDED, reason="VF_SEEDED_SET04=1 not set")
def test_golden_clinic_is_invisible_to_clinic_a(client_a, client_e):
    net_e = by_key(pnl(client_e, "2026-09")["rows"])["net_profit"]["amount"]["value"]
    assert net_e == EXPECTED["pnl"]["2026-09"]["net_profit"]
    assert by_key(pnl(client_a, "2026-09")["rows"])["net_profit"]["amount"]["value"] != net_e
