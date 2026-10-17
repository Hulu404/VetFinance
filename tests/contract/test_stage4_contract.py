"""Stage 4 contract tests: payment calendar and obligations (functions 21, 22, 23, 43), docs/api-contract.md «Планирование».

    GET    /v1/calendar?days=22&as_of=YYYY-MM-DD[&preview=<suggestion id>]
    POST   /v1/calendar/payments       DELETE /v1/calendar/payments/{id}
    PATCH  /v1/counterparties/{id}
    GET    /v1/obligations?as_of=YYYY-MM-DD
    POST   /v1/obligations             PATCH /v1/obligations/{id}            DELETE /v1/obligations/{id}  (= close)
    PATCH  /v1/clinic {safe_balance}   GET /v1/dashboard (advice `cash_gap`)

Shapes are the published ones (contract of 2026-10-17, backend-developer):
calendar = {as_of, data_as_of, window{from,to} (exactly two keys), status, partial_reasons, history_days, start_balance (= days[0].opening),
            safe_balance (+ safe_balance_set), preview|null, summary{income, expense, payments_count, lowest{date, balance, status}},
            alerts[{id, date, date_to, severity, icon, title, text (WITHOUT the suggestion), shortfall, suggestion|null, why}],
            days[{date, weekday, opening, income_forecast, payments[{id, name, category, counterparty, amount, source, balance_after,
            max_deferral_days, moved_from?}], closing, status ok|below_safe|below_zero, note}]}
suggestion = flat {id, payment_id, payment_name, amount, from_date, to_date, delay_days, closes_gap, lowest_after, text}
obligations = {as_of, debt_total, monthly_payment, [monthly_payment_share_pct], amortization_month, pnl_month{month, amount},
               loans[{id, kind, name, lender, principal, remaining, paid_pct, payment, rate_pct, payment_day, next_payment_date,
               last_payment_month, status active|paid|closed, closed_from}], equipment[{id, kind, name, cost, life_years,
               in_service_from, amortization_from, amortization_to, monthly, status, closed_from}]}
DELETE of an obligation closes it from the current month of the clinic (owner's decision 2026-10-16, item 4).

Every test SKIPS while the endpoint answers 404/405/501 without the contract error body (route not implemented yet).
Tests that change data run only with VF_CONTRACT_WRITES=1 (on a test clinic; they restore or delete what they create; closed
obligations stay in the list by design, so use a throw-away test clinic).
VF_STAGE4_STUB=1 marks the tests that cannot pass on a server of the step 1 (stubs that always answer with the set05 example) as xfail.
Run: eval "$(python tests/contract/get_tokens.py)" && pytest tests/contract/test_stage4_contract.py -rs
Local run without Postgres (real API and engine, in-memory data: A is nearly empty, B empty, F is golden set05), see tests/README.md:
  cd backend && VF_LOCAL_PLANNING_TESTS=1 .venv/Scripts/python -m uvicorn tests.planning_server:app --port 8766
  .venv/Scripts/python -m tests.planning_server   # prints export VF_TOKEN_A/B/F; VF_API_URL=http://127.0.0.1:8766
Read-only shape tests run on clinic A and on the golden clinic F (fixtures cal_x, obl_x).
Golden comparison against set05: VF_SEEDED_SET05=1 and VF_TOKEN_F (clinic F seeded from tests/golden/set05).
"""
import json
import os
import re
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from test_stage0_contract import assert_error
from test_stage2_contract import assert_figure_v2, walk_figures

httpx = pytest.importorskip("httpx")

SET05 = Path(__file__).resolve().parents[1] / "golden" / "set05"
EXPECTED = json.loads((SET05 / "expected.json").read_text(encoding="utf-8"))
DATA = json.loads((SET05 / "data.json").read_text(encoding="utf-8"))
SEEDED = os.environ.get("VF_SEEDED_SET05") == "1"
WRITES = os.environ.get("VF_CONTRACT_WRITES") == "1"
STUB = os.environ.get("VF_STAGE4_STUB") == "1"
GOLDEN_AS_OF = EXPECTED["as_of"]
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
SOURCES = {"recurring", "obligation", "manual"}
STATUSES = {"ok", "below_safe", "below_zero"}
REASONS = ["short_history", "obligations_missing", "no_bank"]
UNKNOWN = "00000000-0000-4000-8000-000000000000"
FORBIDDEN = ("ИИ", "нейросет", "катастроф")
NO_GAP_PHRASE = "Перенос одного платежа разрыв не закрывает. Если поставщик согласен подождать, укажите отсрочку у его платежа."
PARTIAL_PHRASE = "уменьшит разрыв, но не закроет его."
FULL_PHRASE = "разрыва не будет."
SAFE_MAX = 10_000_000_000
D = date.fromisoformat
DROP = object()

engine_only = pytest.mark.xfail(STUB, reason="needs the engine (step 2): the step 1 stub always answers with the set05 example", strict=False)


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


def calendar(client, **params):
    r = implemented(client.get("/v1/calendar", params=params), "GET /v1/calendar")
    assert r.status_code == 200, r.text
    return r.json()


def obligations(client, **params):
    r = implemented(client.get("/v1/obligations", params=params), "GET /v1/obligations")
    assert r.status_code == 200, r.text
    return r.json()


def val(fig):
    return fig["value"]


def norm(text):
    """Text with every kind of space turned into a plain one (amounts use non-breaking spaces)."""
    return re.sub(r"[   \s]+", " ", text).strip()


def payments_sum(day):
    return sum(val(p["amount"]) for p in day["payments"])


def move_of(s, days=None):
    """{name, amount, from, to} of the flat suggestion of the contract."""
    return {"name": s["payment_name"], "amount": val(s["amount"]), "from": s["from_date"], "to": s["to_date"]}


def is_red(day):
    return day["status"] != "ok"


def episode_dates(days, start):
    """The run of red days that starts at `start`."""
    out, inside = [], False
    for d in days:
        if d["date"] == start:
            inside = True
        if inside and not is_red(d):
            break
        if inside:
            out.append(d["date"])
    return out


def recompute_with_move(days, move):
    bal, out = val(days[0]["opening"]), []
    for d in days:
        pays = payments_sum(d)
        if d["date"] == move["from"]:
            pays -= move["amount"]
        if d["date"] == move["to"]:
            pays += move["amount"]
        bal += val(d["income_forecast"]) - pays
        out.append((d["date"], bal))
    return out


def workday(iso):
    return D(iso).weekday() < 5


def month_of(iso):
    return iso[:7]


def prev_month(iso_month):
    y, m = map(int, iso_month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def all_rows(obl):
    return obl["loans"] + obl["equipment"]


def _row(obl, item_id):
    return next((x for x in all_rows(obl) if x["id"] == item_id), None)


def pnl_obligations(client, month, as_of):
    r = implemented(client.get("/v1/reports/pnl", params={"month": month, "as_of": as_of}), "GET /v1/reports/pnl")
    assert r.status_code == 200, r.text
    return {x["key"]: x for x in r.json()["rows"]}["obligations"]["amount"]["value"]


def with_overlay(base, overlay):
    body = {**base, **overlay}
    return {k: x for k, x in body.items() if x is not DROP}


@pytest.fixture(scope="module")
def cal_a(client_a):
    return calendar(client_a)


@pytest.fixture(scope="module")
def obl_a(client_a):
    return obligations(client_a)


@pytest.fixture(scope="module", params=["A", "F"])
def cal_x(request, client_a):
    """The calendar of clinic A and of the golden clinic F (as_of of the set): read-only shape tests run on both."""
    if request.param == "A":
        return calendar(client_a)
    return calendar(request.getfixturevalue("client_f"), as_of=GOLDEN_AS_OF)


@pytest.fixture(scope="module", params=["A", "F"])
def obl_x(request, client_a):
    if request.param == "A":
        return obligations(client_a)
    return obligations(request.getfixturevalue("client_f"), as_of=GOLDEN_AS_OF)


@pytest.fixture(scope="module")
def cp_client(request, client_a):
    """The client whose calendar has regular payments with counterparties: clinic F when it is seeded, else A."""
    try:
        return request.getfixturevalue("client_f")
    except pytest.skip.Exception:
        return client_a


@pytest.fixture(scope="module")
def client_f(base_url):
    token = os.environ.get("VF_TOKEN_F")
    if not token or not SEEDED:
        pytest.skip("VF_TOKEN_F and VF_SEEDED_SET05=1 are needed (clinic F seeded from golden set05)")
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60) as c:
        yield c


def need_writes():
    if not WRITES:
        pytest.skip("VF_CONTRACT_WRITES=1 is needed: this test changes data of the test clinic and restores it")


# ------------------------------------------------------------------ 401
ROUTES = [("GET", "/v1/calendar"), ("POST", "/v1/calendar/payments"), ("DELETE", f"/v1/calendar/payments/{UNKNOWN}"),
          ("PATCH", f"/v1/counterparties/{UNKNOWN}"), ("GET", "/v1/obligations"), ("POST", "/v1/obligations"),
          ("PATCH", f"/v1/obligations/{UNKNOWN}"), ("DELETE", f"/v1/obligations/{UNKNOWN}")]


@pytest.mark.parametrize("method,path", ROUTES)
def test_no_token_and_garbage_token_are_401(anon, method, path):
    body = {} if method in ("POST", "PATCH") else None
    r = implemented(anon.request(method, path, json=body), f"{method} {path}")
    assert_error(r, 401, "unauthorized")
    r = anon.request(method, path, headers={"Authorization": "Bearer garbage"}, json=body)
    assert_error(r, 401, "unauthorized")


# ------------------------------------------------------------------ calendar: header
def test_calendar_top_level_shape(cal_x):
    keys = {"as_of", "data_as_of", "window", "status", "partial_reasons", "history_days", "start_balance", "safe_balance",
            "safe_balance_set", "preview", "summary", "alerts", "days"}
    assert keys <= set(cal_x), keys - set(cal_x)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cal_x["as_of"])
    assert cal_x["data_as_of"] is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:\d{2})", cal_x["data_as_of"])
    assert cal_x["status"] in ("empty", "partial", "ok")
    assert type(cal_x["history_days"]) is int and cal_x["history_days"] >= 0
    assert cal_x["preview"] is None
    s = cal_x["summary"]
    assert {"income", "expense", "payments_count", "lowest"} <= set(s)
    assert type(s["payments_count"]) is int and {"date", "balance", "status"} <= set(s["lowest"])
    assert s["lowest"]["status"] in STATUSES
    assert isinstance(cal_x["alerts"], list) and isinstance(cal_x["days"], list)


def test_status_and_partial_reasons_agree(cal_x):
    reasons = cal_x["partial_reasons"]
    assert [r for r in REASONS if r in reasons] == reasons, "known reasons only, in the order short_history, obligations_missing, no_bank"
    if cal_x["status"] == "partial":
        assert reasons
    if cal_x["status"] == "ok":
        assert reasons == []
    if "no_bank" in reasons:
        assert cal_x["history_days"] == 0
    if cal_x["status"] == "empty":
        assert cal_x["data_as_of"] is None or cal_x["history_days"] == 0


def test_window_is_two_keys_22_days_from_as_of_and_start_balance_is_the_first_opening(cal_x):
    days = cal_x["days"]
    start = D(cal_x["as_of"])
    assert [d["date"] for d in days] == [(start + timedelta(days=i)).isoformat() for i in range(22)]
    assert [d["weekday"] for d in days] == [WEEKDAYS[D(d["date"]).weekday()] for d in days]
    assert cal_x["window"] == {"from": days[0]["date"], "to": days[-1]["date"]}
    assert cal_x["start_balance"] == days[0]["opening"], "start_balance is an alias of days[0].opening (same Figure)"


def test_safe_balance_figure_and_flag(cal_x):
    safe = cal_x["safe_balance"]
    assert safe["unit"] == "rub" and safe["source"] == ["manual"]
    assert [b["label"] for b in safe["breakdown"]] == ["Задан в настройках"]
    assert cal_x["safe_balance_set"] is (val(safe) > 0)


def test_every_figure_has_breakdown_source_and_note(cal_x):
    figures = list(walk_figures(cal_x))
    assert len(figures) >= 22 * 3
    for path, fig in figures:
        assert_figure_v2(fig, path)
        assert fig["unit"] == "rub", path


# ------------------------------------------------------------------ calendar: days
def test_day_identity_and_chain(cal_x):
    days = cal_x["days"]
    for i, d in enumerate(days):
        assert val(d["opening"]) + val(d["income_forecast"]) - payments_sum(d) == val(d["closing"]), d["date"]
        if i:
            assert val(d["opening"]) == val(days[i - 1]["closing"]), d["date"]


def test_opening_breakdown_accounts_first_day_evening_of_the_previous_day_after(cal_x):
    days = cal_x["days"]
    assert sum(b["value"] for b in days[0]["opening"]["breakdown"]) == val(days[0]["opening"])
    assert len(days[0]["opening"]["breakdown"]) >= 1
    for prev, d in zip(days, days[1:]):
        bd = d["opening"]["breakdown"]
        assert len(bd) == 1 and bd[0]["label"].startswith("Остаток на вечер") and bd[0]["value"] == val(d["opening"]), d["date"]


def test_closing_tooltip_is_morning_payments_income(cal_x):
    for d in cal_x["days"]:
        bd = d["closing"]["breakdown"]
        assert sum(b["value"] for b in bd) == val(d["closing"]), d["date"]
        assert len(bd) == 2 + len(d["payments"]), f"{d['date']}: «На утро», one row per payment, «Выручка, прогноз»"
        assert bd[0]["label"] == "На утро" and bd[0]["value"] == val(d["opening"])
        assert bd[-1]["label"] == "Выручка, прогноз" and bd[-1]["value"] == val(d["income_forecast"])
        assert [b["value"] for b in bd[1:-1]] == [-val(p["amount"]) for p in d["payments"]], f"{d['date']}: payments with «−», in the order of `payments`"


def test_income_forecast_tooltip(cal_x):
    for d in cal_x["days"]:
        f = d["income_forecast"]
        assert len(f["breakdown"]) == 1 and f["breakdown"][0]["label"].startswith("Среднее поступление"), d["date"]
        assert f["breakdown"][0]["value"] == val(f), d["date"]
        det = f.get("details") or []
        assert len(det) == 2 and det[0]["unit"] == "count" and det[1]["unit"] == "rub", f"{d['date']}: days counted, amount received"
        assert "÷" in f["note"], "note shows the division"


def test_day_status_note_and_red_rule(cal_x):
    """status: below_zero if a balance after a payment or the closing is < 0; else below_safe if closing < safe; else ok."""
    safe = val(cal_x["safe_balance"])
    for d in cal_x["days"]:
        afters = [val(p["balance_after"]) for p in d["payments"]]
        below_zero = min([val(d["closing"])] + afters) < 0
        exp = "below_zero" if below_zero else "below_safe" if val(d["closing"]) < safe else "ok"
        assert d["status"] == exp, d["date"]
        assert isinstance(d["note"], str) and d["note"].strip(), d["date"]
    low = cal_x["summary"]["lowest"]
    assert next(d for d in cal_x["days"] if d["date"] == low["date"])["status"] == low["status"]


def test_payment_order_and_balance_after(cal_x):
    for d in cal_x["days"]:
        keys = [(-val(p["amount"]), p["name"]) for p in d["payments"]]
        assert keys == sorted(keys), f"{d['date']}: payments by amount descending, equal amounts by name"
        running = val(d["opening"])
        for p in d["payments"]:
            running -= val(p["amount"])
            assert val(p["balance_after"]) == running, d["date"]
            bd = p["balance_after"]["breakdown"]
            assert [b["label"] for b in bd][0] == "До платежа" and [b["value"] for b in bd] == [running + val(p["amount"]), -val(p["amount"])]


def test_payment_fields(cal_x):
    ids = []
    for d in cal_x["days"]:
        for p in d["payments"]:
            assert {"id", "name", "category", "counterparty", "amount", "source", "balance_after", "max_deferral_days"} <= set(p)
            assert isinstance(p["id"], str) and p["id"]
            ids.append(p["id"])
            assert isinstance(p["name"], str) and p["name"]
            assert p["source"] in SOURCES and val(p["amount"]) > 0
            assert p["category"] is None or (isinstance(p["category"]["id"], str) and p["category"]["name"])
            assert type(p["max_deferral_days"]) is int and 0 <= p["max_deferral_days"] <= 30
            if p["source"] == "recurring":
                cp = p["counterparty"]
                assert cp and isinstance(cp["id"], str) and cp["id"] and cp["name"], f"{d['date']}: a regular payment always has a counterparty with an id"
            else:
                assert p["counterparty"] is None, f"{d['date']}: counterparty only for regular payments"
            if p["source"] == "obligation":
                assert p["max_deferral_days"] == 0
            assert p.get("moved_from") is None, "moved_from only in an answer with ?preview="
    assert len(ids) == len(set(ids)), "payment ids are unique in the window"


def test_summary_agrees_with_the_days(cal_x):
    days, s = cal_x["days"], cal_x["summary"]
    assert val(s["income"]) == sum(val(d["income_forecast"]) for d in days)
    assert val(s["expense"]) == sum(payments_sum(d) for d in days)
    assert s["payments_count"] == sum(len(d["payments"]) for d in days)
    low = min(days, key=lambda d: (val(d["closing"]), d["date"]))
    assert s["lowest"]["date"] == low["date"] and val(s["lowest"]["balance"]) == val(low["closing"])


def test_summary_weeks_and_sources(cal_x):
    """Breakdown by calendar weeks Mon-Sun clipped by the window; expense details by the three sources."""
    days = cal_x["days"]
    weeks = {}
    for d in days:
        monday = (D(d["date"]) - timedelta(days=D(d["date"]).weekday())).isoformat()
        w = weeks.setdefault(monday, {"income": 0, "expense": 0})
        w["income"] += val(d["income_forecast"])
        w["expense"] += payments_sum(d)
    for key in ("income", "expense"):
        bd = cal_x["summary"][key]["breakdown"]
        assert [b["value"] for b in bd] == [w[key] for _, w in sorted(weeks.items())], key
        assert all(b["label"] for b in bd)
    by_source = {"recurring": 0, "obligation": 0, "manual": 0}
    for d in days:
        for p in d["payments"]:
            by_source[p["source"]] += val(p["amount"])
    details = {x["label"]: x["value"] for x in cal_x["summary"]["expense"].get("details", [])}
    for label, src in (("Регулярные платежи", "recurring"), ("Обязательства", "obligation"), ("Внесено вручную", "manual")):
        assert details.get(label, 0) == by_source[src], label


# ------------------------------------------------------------------ calendar: alerts and suggestions
def test_alerts_are_the_runs_of_red_days(cal_x):
    days = cal_x["days"]
    safe = val(cal_x["safe_balance"])
    starts = [d["date"] for i, d in enumerate(days) if is_red(d) and (i == 0 or not is_red(days[i - 1]))]
    assert [a["date"] for a in cal_x["alerts"]] == starts[:3], "one alert per run of red days, by date, at most 3"
    assert len({a["id"] for a in cal_x["alerts"]}) == len(cal_x["alerts"])
    by_date = {d["date"]: d for d in days}
    for a in cal_x["alerts"]:
        assert {"id", "date", "date_to", "severity", "icon", "title", "text", "shortfall", "suggestion", "why"} <= set(a)
        assert isinstance(a["id"], str) and a["id"] and a["icon"] == "📅"
        run = episode_dates(days, a["date"])
        assert a["date_to"] == run[-1], f"{a['date']}: date_to is the last red day of the run"
        zero = [by_date[x] for x in run if by_date[x]["status"] == "below_zero"]
        if zero:
            worst = min(min([val(d["closing"])] + [val(p["balance_after"]) for p in d["payments"]]) for d in zero)
            assert a["severity"] == "alert" and val(a["shortfall"]) == -worst, a["date"]
            assert [b["label"] for b in a["shortfall"]["breakdown"]][:2] == ["К выплате", "Будет на утро"] or \
                a["shortfall"]["breakdown"][0]["label"].startswith("К выплате"), a["date"]
        else:
            lowest = min(val(by_date[x]["closing"]) for x in run)
            assert a["severity"] == "warning" and val(a["shortfall"]) == safe - lowest, a["date"]
            bd = a["shortfall"]["breakdown"]
            assert [b["value"] for b in bd] == [safe, -lowest] and bd[0]["label"] == "Безопасный запас" and bd[1]["label"].startswith("Остаток на вечер")
        assert a["title"] and len(a["title"]) <= 80 and a["text"] and len(a["text"]) <= 200
        why = a["why"]
        assert why["summary"] and 2 <= len(why["steps"]) <= 5 and why["sources"] and all(len(x) <= 240 for x in why["steps"])
        text = " ".join([a["title"], a["text"], why["summary"]] + why["steps"])
        assert not [w for w in FORBIDDEN if w in text]


def test_alert_text_has_no_suggestion_and_no_gap_phrase(cal_x):
    for a in cal_x["alerts"]:
        if a["suggestion"]:
            assert a["suggestion"]["text"] not in a["text"], "text carries no suggestion: the client appends suggestion.text"
            assert a["suggestion"]["payment_name"] not in a["text"]
        else:
            assert a["text"].endswith(NO_GAP_PHRASE), a["date"]


def test_suggestion_fields_and_texts(cal_x):
    days = cal_x["days"]
    suggestions = [a for a in cal_x["alerts"] if a["suggestion"]]
    if not suggestions:
        pytest.skip("no suggestion in this clinic's calendar today; the golden part checks one on clinic F")
    by_date = {d["date"]: d for d in days}
    for a in suggestions:
        s = a["suggestion"]
        assert {"id", "payment_id", "payment_name", "amount", "from_date", "to_date", "delay_days", "closes_gap", "lowest_after",
                "text"} <= set(s)
        assert "move" not in s, "the suggestion is flat (no nested move)"
        assert isinstance(s["id"], str) and s["id"] and type(s["closes_gap"]) is bool and type(s["delay_days"]) is int
        pay = next((p for p in by_date[s["from_date"]]["payments"] if p["id"] == s["payment_id"]), None)
        assert pay and pay["name"] == s["payment_name"] and val(pay["amount"]) == val(s["amount"]), "payment_id points at the payment on from_date"
        assert s["delay_days"] == (D(s["to_date"]) - D(s["from_date"])).days >= 1
        assert s["delay_days"] <= pay["max_deferral_days"], "never further than the deferral of the payment"
        assert s["to_date"] <= days[-1]["date"] and workday(s["to_date"])
        assert s["lowest_after"]["breakdown"] and s["lowest_after"]["breakdown"][0]["label"].startswith("Остаток на вечер")
        text = s["text"]
        if s["closes_gap"]:
            assert text.startswith("Перенесите платёж") and text.endswith(FULL_PHRASE), text
        else:
            assert text.startswith("Перенос платежа") and text.endswith(PARTIAL_PHRASE), text
        assert s["payment_name"] in text and not [w for w in FORBIDDEN if w in text]


def test_suggestion_really_closes_the_gap_and_lowest_after_is_right(cal_x):
    """Recomputed from the response itself: the move leaves no red day in the run and no new red day elsewhere."""
    days, safe = cal_x["days"], val(cal_x["safe_balance"])
    red = {d["date"] for d in days if is_red(d)}
    suggestions = [a for a in cal_x["alerts"] if a["suggestion"]]
    if not suggestions:
        pytest.skip("no suggestion in this clinic's calendar today; the golden part checks one on clinic F")
    for a in suggestions:
        s = a["suggestion"]
        after = recompute_with_move(days, move_of(s))
        run = set(episode_dates(days, a["date"]))
        closes = all(b >= safe for x, b in after if x in run) and not [x for x, b in after if b < safe and x not in red]
        assert closes is s["closes_gap"], a["date"]
        assert val(s["lowest_after"]) == min(b for _, b in after), a["date"]


@engine_only
def test_preview_of_a_suggestion_returns_the_moved_calendar(client_a, cal_a):
    with_id = [a for a in cal_a["alerts"] if a["suggestion"]]
    if not with_id:
        pytest.skip("no suggestion today; checked on clinic F")
    s = with_id[0]["suggestion"]
    prev = calendar(client_a, as_of=cal_a["as_of"], preview=s["id"])
    expected = dict(recompute_with_move(cal_a["days"], move_of(s)))
    assert {d["date"]: val(d["closing"]) for d in prev["days"]} == expected
    assert prev["preview"] == {"suggestion_id": s["id"], "payment_id": s["payment_id"], "from_date": s["from_date"], "to_date": s["to_date"]}
    moved = [p for d in prev["days"] for p in d["payments"] if p.get("moved_from")]
    assert [(p["id"], p["moved_from"]) for p in moved] == [(s["payment_id"], s["from_date"])]
    assert next(d for d in prev["days"] if d["date"] == s["to_date"])["payments"].count(moved[0]) == 1
    for d in prev["days"]:
        assert val(d["opening"]) + val(d["income_forecast"]) - payments_sum(d) == val(d["closing"])


@engine_only
def test_preview_of_another_as_of_is_invalid(client_a, cal_a):
    with_id = [a for a in cal_a["alerts"] if a["suggestion"]]
    if not with_id:
        pytest.skip("no suggestion today; checked on clinic F")
    later = (D(cal_a["as_of"]) + timedelta(days=30)).isoformat()
    r = implemented(client_a.get("/v1/calendar", params={"as_of": later, "preview": with_id[0]["suggestion"]["id"]}), "GET /v1/calendar")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"] == {"preview": "invalid"}


@pytest.mark.parametrize("bad", [{"as_of": "2026-13-01"}, {"as_of": "вчера"}, {"days": "0"}, {"days": "21"}, {"days": "x"},
                                 {"days": "1000"}, {"preview": "not-a-suggestion"}])
def test_invalid_parameters_are_validation_errors(client_a, bad):
    r = implemented(client_a.get("/v1/calendar", params=bad), "GET /v1/calendar")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"] == {k: "invalid" for k in bad}


def test_days_22_is_accepted_and_equals_the_default(client_a, cal_a):
    assert calendar(client_a, days="22", as_of=cal_a["as_of"]) == calendar(client_a, as_of=cal_a["as_of"])


@engine_only
def test_as_of_is_echoed_and_moves_the_window(client_a):
    d = calendar(client_a, as_of="2026-09-01")
    assert d["as_of"] == "2026-09-01" and d["days"][0]["date"] == "2026-09-01" and d["days"][-1]["date"] == "2026-09-22"
    assert d["window"] == {"from": "2026-09-01", "to": "2026-09-22"}
    assert calendar(client_a, as_of="2026-12-20")["window"]["to"] == "2027-01-10", "the window crosses the month and the year"


@engine_only
def test_as_of_before_any_data_does_not_crash(client_a):
    d = calendar(client_a, as_of="2020-01-01")
    assert len(d["days"]) == 22
    for day in d["days"]:
        assert val(day["opening"]) + val(day["income_forecast"]) - payments_sum(day) == val(day["closing"])


def test_same_request_twice_gives_identical_answers(client_a, cal_a):
    assert calendar(client_a, as_of=cal_a["as_of"]) == calendar(client_a, as_of=cal_a["as_of"])


def test_clinic_id_parameter_does_not_switch_the_clinic(client_a, cal_a):
    assert calendar(client_a, as_of=cal_a["as_of"], clinic_id=UNKNOWN) == calendar(client_a, as_of=cal_a["as_of"])


@engine_only
def test_opening_equals_the_dashboard_balance_of_the_same_as_of(client_a, cal_a):
    dash = implemented(client_a.get("/v1/dashboard", params={"as_of": cal_a["as_of"]}), "GET /v1/dashboard").json()
    assert val(cal_a["days"][0]["opening"]) == dash["balance"]["total"]["value"]


# ------------------------------------------------------------------ settings of the calendar: safe balance, deferral
@pytest.mark.parametrize("body,reason", [({"safe_balance": -1}, "must_be_positive"), ({"safe_balance": SAFE_MAX + 1}, "too_large"),
                                         ({"safe_balance": "150000"}, "invalid"), ({"safe_balance": 1.5}, "invalid")])
def test_patch_clinic_safe_balance_validation(client_a, body, reason):
    r = client_a.patch("/v1/clinic", json=body)
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"] == {"safe_balance": reason}


def first_counterparty(client):
    cal = calendar(client)
    for d in cal["days"]:
        for p in d["payments"]:
            if p["counterparty"]:
                return p["counterparty"], p
    pytest.skip("no regular payment with a counterparty in this clinic's calendar")


DEFERRAL_INVALID = [({}, "required"), ({"max_deferral_days": "5"}, "invalid"), ({"max_deferral_days": 5.5}, "invalid"),
                    ({"max_deferral_days": True}, "invalid"), ({"max_deferral_days": -1}, "out_of_range"),
                    ({"max_deferral_days": 31}, "out_of_range"), ({"max_deferral_days": 10 ** 6}, "out_of_range")]


@pytest.mark.parametrize("body,reason", DEFERRAL_INVALID, ids=[str(b) for b, _ in DEFERRAL_INVALID])
def test_patch_counterparty_validation(cp_client, body, reason):
    cp, _ = first_counterparty(cp_client)
    r = implemented(cp_client.patch(f"/v1/counterparties/{cp['id']}", json=body), "PATCH /v1/counterparties/{id}")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"] == {"max_deferral_days": reason}


def test_patch_unknown_counterparty_is_404(client_a):
    r = implemented(client_a.patch(f"/v1/counterparties/{UNKNOWN}", json={"max_deferral_days": 3}), "PATCH /v1/counterparties/{id}")
    assert_error(r, 404, "not_found")


@engine_only
def test_counterparty_deferral_is_saved_and_shown_in_the_calendar(cp_client):
    need_writes()
    cp, pay = first_counterparty(cp_client)
    old = pay["max_deferral_days"]
    new = 7 if old != 7 else 4
    try:
        r = implemented(cp_client.patch(f"/v1/counterparties/{cp['id']}", json={"max_deferral_days": new}), "PATCH /v1/counterparties/{id}")
        assert r.status_code == 200, r.text
        assert r.json() == {"id": cp["id"], "name": cp["name"], "max_deferral_days": new}
        cal = calendar(cp_client)
        mine = [p for d in cal["days"] for p in d["payments"] if p["counterparty"] and p["counterparty"]["id"] == cp["id"]]
        assert mine and {p["max_deferral_days"] for p in mine} == {new}, "all payments of the counterparty carry the new deferral"
    finally:
        cp_client.patch(f"/v1/counterparties/{cp['id']}", json={"max_deferral_days": old})


def test_foreign_counterparty_is_invisible(client_a, client_b):
    cp_b, _ = first_counterparty(client_b)  # skips while clinic B has no regular payment
    cp_a_ids = {p["counterparty"]["id"] for d in calendar(client_a)["days"] for p in d["payments"] if p["counterparty"]}
    if cp_b["id"] in cp_a_ids:
        pytest.skip("clinics A and B happen to share a counterparty key (same INN); isolation is checked on ids unique to B")
    r = implemented(client_b.get("/v1/calendar"), "GET /v1/calendar")
    assert r.status_code == 200
    assert_error(client_a.patch(f"/v1/counterparties/{cp_b['id']}", json={"max_deferral_days": 3}), 404, "not_found")


# ------------------------------------------------------------------ manual payments
PAY_INVALID = [
    ({"name": DROP}, "name", {"required"}),
    ({"name": ""}, "name", {"required"}),
    ({"name": "я" * 81}, "name", {"too_long"}),
    ({"amount": DROP}, "amount", {"required"}),
    ({"amount": 0}, "amount", {"must_be_positive"}),
    ({"amount": -5}, "amount", {"must_be_positive"}),
    ({"amount": 10 ** 13}, "amount", {"too_large"}),
    ({"amount": "100"}, "amount", {"invalid"}),
    ({"amount": 1.5}, "amount", {"invalid"}),
    ({"date": DROP}, "date", {"required"}),
    ({"date": "2026-13-01"}, "date", {"invalid"}),
    ({"date": "вчера"}, "date", {"invalid"}),
    ({"category_id": "not-a-uuid"}, "category_id", {"invalid"}),
    ({"category_id": UNKNOWN}, "category_id", {"invalid"}),
    ({"max_deferral_days": -1}, "max_deferral_days", {"out_of_range"}),
    ({"max_deferral_days": 31}, "max_deferral_days", {"out_of_range"}),
    ({"max_deferral_days": "3"}, "max_deferral_days", {"invalid"}),
    ({"max_deferral_days": 2.5}, "max_deferral_days", {"invalid"}),
    ({"clinic_id": UNKNOWN}, "clinic_id", {"unknown_field"}),
]


def pay_body(cal, **overlay):
    base = {"name": f"Тестовый платёж {uuid.uuid4().hex[:6]}", "amount": 123_400, "date": cal["days"][10]["date"], "max_deferral_days": 0}
    return with_overlay(base, overlay)


@pytest.mark.parametrize("overlay,field,reasons", PAY_INVALID, ids=[f"{i}-{f}" for i, (_, f, _) in enumerate(PAY_INVALID)])
def test_post_manual_payment_validation(client_a, cal_a, overlay, field, reasons):
    r = implemented(client_a.post("/v1/calendar/payments", json=pay_body(cal_a, **overlay)), "POST /v1/calendar/payments")
    if r.status_code == 201:
        client_a.delete(f"/v1/calendar/payments/{r.json()['id']}")
        if STUB and field == "category_id":
            pytest.xfail("the stub does not know the categories of the clinic (step 2)")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"].get(field) in reasons, r.json()["error"]["details"]


@engine_only
@pytest.mark.parametrize("when", ["before", "after"])
def test_manual_payment_outside_the_window_is_out_of_window(client_a, cal_a, when):
    days = cal_a["days"]
    bad = (D(days[0]["date"]) - timedelta(days=1)) if when == "before" else (D(days[-1]["date"]) + timedelta(days=1))
    r = implemented(client_a.post("/v1/calendar/payments", json=pay_body(cal_a, date=bad.isoformat())), "POST /v1/calendar/payments")
    if r.status_code == 201:
        client_a.delete(f"/v1/calendar/payments/{r.json()['id']}")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"] == {"date": "out_of_window"}


def test_delete_unknown_or_not_manual_payment_is_404(client_a, cal_a):
    assert_error(implemented(client_a.delete(f"/v1/calendar/payments/{UNKNOWN}"), "DELETE /v1/calendar/payments/{id}"), 404, "not_found")
    not_manual = next((p for d in cal_a["days"] for p in d["payments"] if p["source"] != "manual"), None)
    if not_manual:
        assert_error(client_a.delete(f"/v1/calendar/payments/{not_manual['id']}"), 404, "not_found")
        assert calendar(client_a, as_of=cal_a["as_of"]) == cal_a, "a failed delete changes nothing"


@engine_only
def test_manual_payment_lifecycle(client_a, cal_a):
    need_writes()
    day = cal_a["days"][10]["date"]
    body = pay_body(cal_a, max_deferral_days=3)
    r = implemented(client_a.post("/v1/calendar/payments", json=body), "POST /v1/calendar/payments")
    assert r.status_code == 201, r.text
    item = r.json()
    try:
        assert {"id", "date", "name", "category", "amount", "source", "max_deferral_days"} <= set(item)
        assert item["source"] == "manual" and item["date"] == day and item["name"] == body["name"] and item["max_deferral_days"] == 3
        assert_figure_v2(item["amount"], "amount") and val(item["amount"]) == body["amount"]
        after = calendar(client_a, as_of=cal_a["as_of"])
        hits = [(d["date"], p) for d in after["days"] for p in d["payments"] if p["name"] == body["name"]]
        assert [h[0] for h in hits] == [day]
        p = hits[0][1]
        assert p["id"] == item["id"] and p["source"] == "manual" and val(p["amount"]) == body["amount"]
        assert p["counterparty"] is None and p["max_deferral_days"] == 3
        before = {d["date"]: d for d in cal_a["days"]}
        for d in after["days"]:
            if d["date"] >= day:
                assert val(d["closing"]) == val(before[d["date"]]["closing"]) - body["amount"], d["date"]
        assert val(after["summary"]["expense"]) == val(cal_a["summary"]["expense"]) + body["amount"]
    finally:
        assert client_a.delete(f"/v1/calendar/payments/{item['id']}").status_code == 204
    assert calendar(client_a, as_of=cal_a["as_of"]) == cal_a
    assert_error(client_a.delete(f"/v1/calendar/payments/{item['id']}"), 404, "not_found")


@engine_only
def test_manual_payment_is_private_to_its_clinic(client_a, client_b, cal_a):
    need_writes()
    body = pay_body(cal_a)
    r = implemented(client_a.post("/v1/calendar/payments", json=body), "POST /v1/calendar/payments")
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    try:
        assert not [p for d in calendar(client_b)["days"] for p in d["payments"] if p["name"] == body["name"]]
        assert_error(client_b.delete(f"/v1/calendar/payments/{pid}"), 404, "not_found")
    finally:
        assert client_a.delete(f"/v1/calendar/payments/{pid}").status_code == 204


# ------------------------------------------------------------------ safe balance and the dashboard advice (VF_CONTRACT_WRITES=1)
@pytest.fixture
def safe_restore(client_a):
    need_writes()
    r = client_a.get("/v1/clinic")
    assert r.status_code == 200, r.text
    original = r.json()["safe_balance"]
    yield original
    client_a.patch("/v1/clinic", json={"safe_balance": original})


def set_safe(client, value):
    r = client.patch("/v1/clinic", json={"safe_balance": value})
    assert r.status_code == 200, r.text
    return r.json()


@engine_only
def test_safe_balance_zero_means_not_set_and_only_negative_days_are_red(client_a, cal_a, safe_restore):
    set_safe(client_a, 0)
    cal = calendar(client_a, as_of=cal_a["as_of"])
    assert val(cal["safe_balance"]) == 0 and cal["safe_balance_set"] is False
    assert not [d for d in cal["days"] if d["status"] == "below_safe"]


@engine_only
def test_safe_balance_boundary_equal_is_not_red_one_more_is(client_a, cal_a, safe_restore):
    low = cal_a["summary"]["lowest"]
    day = next(d for d in cal_a["days"] if d["date"] == low["date"])
    if val(low["balance"]) <= 0 or day["status"] == "below_zero":
        pytest.skip("the lowest day of this clinic is at or below zero; the boundary is checked on clinic F")
    set_safe(client_a, val(low["balance"]))
    cal = calendar(client_a, as_of=cal_a["as_of"])
    assert next(d for d in cal["days"] if d["date"] == low["date"])["status"] == "ok", "exactly the safe balance is not red"
    set_safe(client_a, val(low["balance"]) + 1)
    cal = calendar(client_a, as_of=cal_a["as_of"])
    assert next(d for d in cal["days"] if d["date"] == low["date"])["status"] == "below_safe"
    assert cal["safe_balance_set"] is True


@engine_only
def test_huge_safe_balance_gives_one_alert_for_the_whole_window_and_a_dashboard_advice(client_a, cal_a, safe_restore):
    set_safe(client_a, SAFE_MAX)
    cal = calendar(client_a, as_of=cal_a["as_of"])
    assert all(is_red(d) for d in cal["days"])
    assert len(cal["alerts"]) == 1 and cal["alerts"][0]["date"] == cal["days"][0]["date"] and cal["alerts"][0]["date_to"] == cal["days"][-1]["date"]
    dash = implemented(client_a.get("/v1/dashboard", params={"as_of": cal["as_of"]}), "GET /v1/dashboard").json()
    gap = [a for a in dash["advice"] if a["id"] == "cash_gap"]
    assert len(gap) == 1, "the advice cash_gap appears with a gap"
    assert_cash_gap_advice(gap[0], cal["alerts"][0])
    assert len(dash["advice"]) <= 5
    set_safe(client_a, 0)
    dash = client_a.get("/v1/dashboard", params={"as_of": cal["as_of"]}).json()
    cal0 = calendar(client_a, as_of=cal["as_of"])
    if not cal0["alerts"]:
        assert not [a for a in dash["advice"] if a["id"] == "cash_gap"], "no gap, no advice"


def assert_cash_gap_advice(advice, alert):
    assert advice["icon"] == "📅" and advice["severity"] == alert["severity"]
    assert advice["title"] == alert["title"] and advice["why"] == alert["why"]
    suffix = (" " + alert["suggestion"]["text"]) if alert["suggestion"] else ""
    assert advice["text"] == alert["text"] + suffix, "advice text = alert text + a space + suggestion text"
    assert advice["link"] == {"path": "/planning/calendar", "date": alert["date"]}


# ------------------------------------------------------------------ obligations shape
def test_obligations_shape(obl_x):
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", obl_x["as_of"])
    for key in ("debt_total", "monthly_payment", "amortization_month"):
        assert_figure_v2(obl_x[key], key)
        assert obl_x[key]["unit"] == "rub"
    if "monthly_payment_share_pct" in obl_x:
        assert obl_x["monthly_payment_share_pct"]["unit"] == "pct"
        assert [b["label"] for b in obl_x["monthly_payment_share_pct"]["breakdown"]][0] == "Платёж в месяц"
    pm = obl_x["pnl_month"]
    assert re.fullmatch(r"\d{4}-\d{2}", pm["month"]) and pm["month"] == month_of(obl_x["as_of"])
    assert_figure_v2(pm["amount"], "pnl_month.amount")
    assert {b["label"] for b in pm["amount"]["breakdown"]} <= {"Проценты по кредиту", "Лизинг (платёж целиком)", "Амортизация оборудования"}
    for x in obl_x["loans"]:
        assert {"id", "kind", "name", "lender", "principal", "remaining", "paid_pct", "payment", "rate_pct", "payment_day",
                "next_payment_date", "last_payment_month", "status", "closed_from"} <= set(x)
        assert x["kind"] in ("loan", "lease") and x["status"] in ("active", "paid", "closed")
        assert x["paid_pct"]["unit"] == "pct" and 0 <= x["paid_pct"]["value"] <= 100
        assert re.fullmatch(r"\d{4}-\d{2}", x["last_payment_month"])
        assert (x["rate_pct"] is None) is (x["kind"] == "lease")
        assert 1 <= x["payment_day"] <= 31
        assert (x["closed_from"] is not None) is (x["status"] == "closed")
        if x["status"] != "active":
            assert val(x["remaining"]) == 0 and val(x["payment"]) == 0
    for x in obl_x["equipment"]:
        assert {"id", "kind", "name", "cost", "life_years", "in_service_from", "amortization_from", "amortization_to", "monthly",
                "status", "closed_from"} <= set(x)
        assert x["kind"] == "equipment" and type(x["life_years"]) is int and x["life_years"] > 0
        assert x["status"] in ("active", "paid", "closed") and (x["closed_from"] is not None) is (x["status"] == "closed")
        assert re.fullmatch(r"\d{4}-\d{2}", x["amortization_from"]) and re.fullmatch(r"\d{4}-\d{2}", x["amortization_to"])
    for path, fig in walk_figures(obl_x):
        assert_figure_v2(fig, path)


def test_paid_pct_breakdown_is_in_roubles(obl_x):
    """Contract: paid_pct.breakdown «Выплачено», «По договору» are amounts in roubles (a percent unit would print them as %)."""
    for x in obl_x["loans"]:
        assert [b["unit"] for b in x["paid_pct"]["breakdown"]] == ["rub", "rub"], x["name"]
        assert [b["label"] for b in x["paid_pct"]["breakdown"]] == ["Выплачено", "По договору"]


def test_obligation_totals_agree_with_the_rows(obl_x):
    assert val(obl_x["debt_total"]) == sum(val(x["remaining"]) for x in obl_x["loans"])
    assert val(obl_x["monthly_payment"]) == sum(val(x["payment"]) for x in obl_x["loans"] if x["status"] == "active")
    assert val(obl_x["amortization_month"]) == sum(val(x["monthly"]) for x in obl_x["equipment"] if x["status"] == "active")
    pm = obl_x["pnl_month"]["amount"]
    assert sum(b["value"] for b in pm["breakdown"]) == val(pm)
    for key in ("loans", "equipment"):
        order = [{"active": 0, "paid": 1, "closed": 2}[x["status"]] for x in obl_x[key]]
        assert order == sorted(order), f"{key}: active, then paid, then closed"


@engine_only
def test_obligations_pnl_month_equals_the_pnl_row(client_a, obl_a):
    assert val(obl_a["pnl_month"]["amount"]) == pnl_obligations(client_a, obl_a["pnl_month"]["month"], obl_a["as_of"])


@pytest.mark.parametrize("bad", [{"as_of": "2026-13-01"}, {"as_of": "вчера"}])
def test_obligations_invalid_as_of(client_a, bad):
    r = implemented(client_a.get("/v1/obligations", params=bad), "GET /v1/obligations")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"] == {"as_of": "invalid"}


# ------------------------------------------------------------------ obligations: validation, isolation (no writes)
VALID = {
    "equipment": {"kind": "equipment", "name": "Тестовая центрифуга (контрактный тест)", "cost": 3_600_000, "life_years": 3,
                  "in_service_from": "2026-09-10"},
    "loan": {"kind": "loan", "name": "Тестовый кредит (контрактный тест)", "lender": "Тест-банк", "principal": 10_000_000,
             "remaining": 10_000_000, "rate_pct": 12.0, "payment": 900_000, "payment_day": 15},
    "lease": {"kind": "lease", "name": "Тестовый лизинг (контрактный тест)", "lender": "Тест-лизинг", "principal": 12_000_000,
              "remaining": 6_000_000, "payment": 500_000, "payment_day": 20},
}
INVALID = [
    ({}, "kind", {"required"}),
    ({"kind": "mortgage", "name": "x"}, "kind", {"invalid"}),
    ({**VALID["equipment"], "name": ""}, "name", {"required"}),
    ({**VALID["equipment"], "name": "я" * 81}, "name", {"too_long"}),
    ({**VALID["loan"], "lender": "я" * 1000}, "lender", {"too_long"}),
    ({k: x for k, x in VALID["equipment"].items() if k != "cost"}, "cost", {"required"}),
    ({**VALID["equipment"], "cost": 0}, "cost", {"must_be_positive"}),
    ({**VALID["equipment"], "cost": -100}, "cost", {"must_be_positive"}),
    ({**VALID["equipment"], "cost": 10 ** 13}, "cost", {"too_large"}),
    ({**VALID["equipment"], "cost": "3600000"}, "cost", {"invalid"}),
    ({**VALID["equipment"], "cost": 1.5}, "cost", {"invalid"}),
    ({**VALID["equipment"], "life_years": 0}, "life_years", {"out_of_range"}),
    ({**VALID["equipment"], "life_years": 31}, "life_years", {"out_of_range"}),
    ({k: x for k, x in VALID["equipment"].items() if k != "life_years"}, "life_years", {"required"}),
    ({**VALID["equipment"], "in_service_from": "2026-13-01"}, "in_service_from", {"invalid"}),
    ({**VALID["equipment"], "in_service_from": "2099-01-01"}, "in_service_from", {"in_future"}),
    ({k: x for k, x in VALID["equipment"].items() if k != "in_service_from"}, "in_service_from", {"required"}),
    ({**VALID["loan"], "payment_day": 0}, "payment_day", {"out_of_range"}),
    ({**VALID["loan"], "payment_day": 32}, "payment_day", {"out_of_range"}),
    ({k: x for k, x in VALID["loan"].items() if k != "payment_day"}, "payment_day", {"required"}),
    ({**VALID["loan"], "payment": -1}, "payment", {"must_be_positive"}),
    ({**VALID["loan"], "rate_pct": -1}, "rate_pct", {"out_of_range"}),
    ({**VALID["loan"], "rate_pct": 101}, "rate_pct", {"out_of_range"}),
    ({**VALID["loan"], "rate_pct": 12.345}, "rate_pct", {"too_many_decimals"}),
    ({k: x for k, x in VALID["loan"].items() if k != "rate_pct"}, "rate_pct", {"required"}),
    ({**VALID["loan"], "remaining": 20_000_000}, "remaining", {"remaining_gt_principal"}),
    ({**VALID["loan"], "payment": 50_000}, "payment", {"payment_below_interest"}),
    ({**VALID["loan"], "payment": 100_000}, "payment", {"payment_below_interest"}),
    ({k: x for k, x in VALID["loan"].items() if k != "principal"}, "principal", {"required"}),
    ({**VALID["lease"], "payment": 0}, "payment", {"must_be_positive"}),
    ({**VALID["equipment"], "clinic_id": UNKNOWN}, "clinic_id", {"unknown_field"}),
    ({**VALID["lease"], "rate_pct": 5}, "rate_pct", {"unknown_field"}),
]


@pytest.mark.parametrize("body,field,reasons", INVALID, ids=[f"{i}-{f}" for i, (_, f, _) in enumerate(INVALID)])
def test_post_obligation_validation(client_a, body, field, reasons):
    r = implemented(client_a.post("/v1/obligations", json=body), "POST /v1/obligations")
    assert_error(r, 422, "validation")
    fields = r.json()["error"]["details"].get("fields", {})
    assert fields.get(field) in reasons, fields


def test_loan_with_zero_remaining_passes_validation_but_payment_below_interest_names_the_interest(client_a):
    """remaining may be 0 (the loan is paid); payment_below_interest carries details.interest = round(remaining x rate / 12) in kopecks."""
    r = implemented(client_a.post("/v1/obligations", json={**VALID["loan"], "payment": 50_000}), "POST /v1/obligations")
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["interest"] == 100_000, "10 000 000 kopecks x 12% / 12"


def test_patch_and_delete_unknown_obligation_is_404(client_a):
    r = implemented(client_a.patch(f"/v1/obligations/{UNKNOWN}", json={"name": "x"}), "PATCH /v1/obligations/{id}")
    assert_error(r, 404, "not_found")
    r = implemented(client_a.delete(f"/v1/obligations/{UNKNOWN}"), "DELETE /v1/obligations/{id}")
    assert_error(r, 404, "not_found")


@engine_only
def test_foreign_obligations_are_invisible_and_not_editable(client_a, client_b, obl_a):
    obl_b = obligations(client_b)
    ids_a = {x["id"] for x in all_rows(obl_a)}
    ids_b = {x["id"] for x in all_rows(obl_b)}
    assert not ids_a & ids_b
    for oid in sorted(ids_b)[:2]:
        assert_error(client_a.patch(f"/v1/obligations/{oid}", json={"name": "чужое"}), 404, "not_found")
        assert_error(client_a.delete(f"/v1/obligations/{oid}"), 404, "not_found")
    assert obligations(client_b) == obl_b


# ------------------------------------------------------------------ obligations: create, see everywhere, CLOSE (VF_CONTRACT_WRITES=1)
@pytest.fixture
def created(client_a):
    need_writes()
    made = []

    def make(kind, **over):
        body = {**VALID[kind], **over, "name": f"{VALID[kind]['name']} {uuid.uuid4().hex[:6]}"}
        r = implemented(client_a.post("/v1/obligations", json=body), "POST /v1/obligations")
        assert r.status_code == 201, r.text
        item = r.json()
        assert item["id"] and item["kind"] == kind and item["name"] == body["name"] and item["status"] == "active"
        made.append(item["id"])
        return item
    yield make
    for oid in made:
        r = client_a.delete(f"/v1/obligations/{oid}")
        assert r.status_code in (204, 404), f"cleanup of {oid} failed: {r.status_code} {r.text}"   # 404: the test closed it already


def today_of(client):
    return D(calendar(client)["as_of"])        # "today" of the clinic, as the API counts it


@engine_only
def test_equipment_appears_in_obligations_and_in_the_pnl_row(client_a, created):
    """In service in the previous month -> amortized from this month: + cost / months in amortization_month and in P&L."""
    as_of = today_of(client_a)
    prev_month_day = (as_of.replace(day=1) - timedelta(days=1)).replace(day=10).isoformat()
    month = as_of.strftime("%Y-%m")
    pnl_before = pnl_obligations(client_a, month, as_of.isoformat())
    obl_before = obligations(client_a)
    item = created("equipment", in_service_from=prev_month_day)
    monthly = 3_600_000 // 36
    obl_after = obligations(client_a)
    row = _row(obl_after, item["id"])
    assert row and val(row["monthly"]) == monthly and val(row["cost"]) == 3_600_000 and row["status"] == "active"
    assert val(obl_after["amortization_month"]) - val(obl_before["amortization_month"]) == monthly
    assert val(obl_after["pnl_month"]["amount"]) - val(obl_before["pnl_month"]["amount"]) == monthly
    assert pnl_obligations(client_a, month, as_of.isoformat()) - pnl_before == monthly


@engine_only
def test_close_keeps_past_accruals_and_drops_the_current_month(client_a, created):
    """DELETE = close from the current month: past months of the P&L keep the accrual, this and later months lose it."""
    as_of = today_of(client_a)
    month = as_of.strftime("%Y-%m")
    last = prev_month(month)
    in_service = (as_of.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=20)    # a month and a half back
    monthly = 3_600_000 // 36
    before_cur, before_last = pnl_obligations(client_a, month, as_of.isoformat()), pnl_obligations(client_a, last, as_of.isoformat())
    obl_before = obligations(client_a)
    item = created("equipment", in_service_from=in_service.isoformat())
    assert pnl_obligations(client_a, month, as_of.isoformat()) == before_cur + monthly
    assert pnl_obligations(client_a, last, as_of.isoformat()) == before_last + monthly

    assert client_a.delete(f"/v1/obligations/{item['id']}").status_code == 204
    assert pnl_obligations(client_a, month, as_of.isoformat()) == before_cur, "this month loses the closed obligation"
    assert pnl_obligations(client_a, last, as_of.isoformat()) == before_last + monthly, "the past month keeps its accrual"
    obl = obligations(client_a)
    row = _row(obl, item["id"])
    assert row and row["status"] == "closed" and row["closed_from"] == month, "the closed object stays in the list"
    assert val(row["monthly"]) == monthly, "monthly stays as a reference"
    assert val(obl["amortization_month"]) == val(obl_before["amortization_month"]) and val(obl["pnl_month"]["amount"]) == val(obl_before["pnl_month"]["amount"])
    assert [x["status"] for x in obl["equipment"]][-1] == "closed", "closed rows go last"
    earlier = obligations(client_a, as_of=(as_of.replace(day=1) - timedelta(days=5)).isoformat())
    assert _row(earlier, item["id"])["status"] == "active", "for an as_of before the closing month the object is active"
    assert_error(client_a.delete(f"/v1/obligations/{item['id']}"), 404, "not_found")
    assert_error(client_a.patch(f"/v1/obligations/{item['id']}", json={"name": "ещё раз"}), 404, "not_found")


@engine_only
def test_closed_loan_leaves_the_calendar_and_the_totals(client_a, created):
    cal = calendar(client_a)
    target = next(D(d["date"]) for d in cal["days"][3:] if D(d["date"]).weekday() < 5)
    obl_before = obligations(client_a)
    item = created("loan", payment_day=target.day)
    assert [p["source"] for d in calendar(client_a, as_of=cal["as_of"])["days"] for p in d["payments"] if p["name"] == item["name"]] == ["obligation"]
    assert val(obligations(client_a)["monthly_payment"]) - val(obl_before["monthly_payment"]) == VALID["loan"]["payment"]
    assert client_a.delete(f"/v1/obligations/{item['id']}").status_code == 204
    after = calendar(client_a, as_of=cal["as_of"])
    assert not [p for d in after["days"] for p in d["payments"] if p["name"] == item["name"]]
    assert after == cal, "closing returns the calendar to what it was"
    obl = obligations(client_a)
    row = _row(obl, item["id"])
    assert row["status"] == "closed" and val(row["remaining"]) == 0 and val(row["payment"]) == 0 and row["closed_from"] == cal["as_of"][:7]
    assert val(obl["debt_total"]) == val(obl_before["debt_total"]) and val(obl["monthly_payment"]) == val(obl_before["monthly_payment"])


@engine_only
def test_patch_changes_the_obligation_and_validates(client_a, created):
    item = created("equipment")
    r = client_a.patch(f"/v1/obligations/{item['id']}", json={"name": "Переименовано (контрактный тест)"})
    assert r.status_code == 200, r.text
    assert _row(obligations(client_a), item["id"])["name"] == "Переименовано (контрактный тест)"
    assert_error(client_a.patch(f"/v1/obligations/{item['id']}", json={"cost": -1}), 422, "validation")
    r = client_a.patch(f"/v1/obligations/{item['id']}", json={"kind": "loan"})
    assert_error(r, 422, "validation")
    assert r.json()["error"]["details"]["fields"] == {"kind": "invalid"}


@engine_only
def test_loan_payment_appears_in_the_calendar_on_its_day(client_a, created):
    cal = calendar(client_a)
    target = next(D(d["date"]) for d in cal["days"][3:] if D(d["date"]).weekday() < 5)
    item = created("loan", payment_day=target.day)
    after = calendar(client_a, as_of=cal["as_of"])
    hits = [(d["date"], p) for d in after["days"] for p in d["payments"] if p["name"] == item["name"]]
    assert [h[0] for h in hits] == [target.isoformat()] and hits[0][1]["source"] == "obligation"
    assert hits[0][1]["counterparty"] is None and hits[0][1]["max_deferral_days"] == 0
    assert val(hits[0][1]["amount"]) == VALID["loan"]["payment"]
    by_date = {d["date"]: d for d in cal["days"]}
    for d in after["days"]:
        if d["date"] >= target.isoformat():
            assert val(d["closing"]) == val(by_date[d["date"]]["closing"]) - VALID["loan"]["payment"], d["date"]


@engine_only
def test_created_obligation_is_invisible_to_clinic_b(client_a, client_b, created):
    item = created("lease")
    obl_b = obligations(client_b)
    assert item["id"] not in {x["id"] for x in all_rows(obl_b)}
    assert not [p for d in calendar(client_b)["days"] for p in d["payments"] if p["name"] == item["name"]]
    assert_error(client_b.patch(f"/v1/obligations/{item['id']}", json={"name": "чужое"}), 404, "not_found")
    assert_error(client_b.delete(f"/v1/obligations/{item['id']}"), 404, "not_found")


# ------------------------------------------------------------------ golden: clinic F seeded from tests/golden/set05
G = EXPECTED["calendar"]["main"]
GH = EXPECTED["calendar"]["high_safe"]
GO = EXPECTED["obligations"]
SERIES_SLOTS = {(s["key"], sl["slot"]): sl for s in G["recurring"] for sl in s["slots"]}
MONTH_NAMES = {"07": "Июль", "08": "Август", "09": "Сентябрь"}


def history_days_of_data():
    bank_ids = {a["id"] for a in DATA["accounts"] if a["type"] == "bank"}
    first = min(D(t["date"]) for t in DATA["transactions"] if t["account_id"] in bank_ids)
    return (D(GOLDEN_AS_OF) - first).days + 1        # from the earliest bank operation to as_of, both days counted


@pytest.fixture(scope="module")
def cal_f(client_f):
    return calendar(client_f, as_of=GOLDEN_AS_OF)


def test_golden_header(cal_f):
    assert cal_f["as_of"] == GOLDEN_AS_OF and cal_f["window"] == {"from": G["window"]["from"], "to": G["window"]["to"]}
    assert val(cal_f["safe_balance"]) == G["safe_balance"] and cal_f["safe_balance_set"] is True
    assert cal_f["status"] == "ok" and cal_f["partial_reasons"] == []
    assert cal_f["history_days"] == history_days_of_data(), "days from the earliest bank operation to as_of inclusive"
    assert cal_f["preview"] is None
    assert cal_f["start_balance"] == cal_f["days"][0]["opening"]


def test_golden_calendar_days(cal_f):
    assert len(cal_f["days"]) == len(G["days"]) == 22
    for got, exp in zip(cal_f["days"], G["days"]):
        assert got["date"] == exp["date"] and got["weekday"] == exp["weekday"]
        assert (val(got["opening"]), val(got["income_forecast"]), val(got["closing"]), got["status"]) == \
            (exp["opening"], exp["income_forecast"], exp["closing"], exp["status"]), exp["date"]
        assert sorted((p["name"], val(p["amount"]), p["source"]) for p in got["payments"]) == \
            sorted((p["name"], p["amount"], p["source"]) for p in exp["payments"]), exp["date"]
        assert [(p["name"], val(p["balance_after"])) for p in got["payments"]] == [(p["name"], p["balance_after"]) for p in exp["payments"]], exp["date"]


def test_golden_opening_breakdown_by_accounts(cal_f):
    op = cal_f["days"][0]["opening"]
    assert val(op) == G["opening"]["value"]
    assert [(b["label"], b["value"]) for b in op["breakdown"]] == [(b["label"], b["value"]) for b in G["opening"]["breakdown"]]


def test_golden_payment_details(cal_f):
    """Counterparty id = INN, deferral from the contract terms, three last amounts of a regular payment by months."""
    for got, exp in zip(cal_f["days"], G["days"]):
        exp_by = {(p["name"], p["amount"]): p for p in exp["payments"]}
        for p in got["payments"]:
            e = exp_by[(p["name"], val(p["amount"]))]
            assert p["max_deferral_days"] == e["max_deferral_days"], (exp["date"], p["name"])
            if p["source"] == "recurring":
                assert p["counterparty"] == {"id": e["series"].split("|")[0], "name": p["name"]}, (exp["date"], p["name"])
                last = SERIES_SLOTS[(e["series"], e["slot"])]["last_amounts"]
                det = p["amount"].get("details", [])
                assert [(x["label"], x["value"]) for x in det] == [(MONTH_NAMES[m], v) for m, v in zip(("07", "08", "09"), last)], (exp["date"], p["name"])
            else:
                assert p["counterparty"] is None
            if p["source"] == "manual":
                assert p["name"] == "Ремонт кондиционера"


def test_golden_deferral_default_is_zero_for_counterparties_without_terms(cal_f):
    terms = {c["name"]: c["max_deferral_days"] for c in DATA["counterparties"]}
    for d in cal_f["days"]:
        for p in d["payments"]:
            if p["source"] == "recurring":
                assert p["max_deferral_days"] == terms.get(p["name"], 0), p["name"]


@engine_only
def test_golden_opening_equals_the_dashboard_balance(client_f, cal_f):
    dash = implemented(client_f.get("/v1/dashboard", params={"as_of": GOLDEN_AS_OF}), "GET /v1/dashboard").json()
    assert val(cal_f["days"][0]["opening"]) == G["opening"]["value"] == dash["balance"]["total"]["value"]


def test_golden_summary_and_alert(cal_f):
    s = cal_f["summary"]
    assert (val(s["income"]), val(s["expense"]), s["payments_count"]) == \
        (G["summary"]["income"], G["summary"]["expense"], G["summary"]["payments_count"])
    assert s["lowest"]["date"] == G["summary"]["lowest"]["date"] and val(s["lowest"]["balance"]) == G["summary"]["lowest"]["balance"]
    assert s["lowest"]["status"] == "below_safe"
    assert [(b["label"], b["value"]) for b in s["income"]["breakdown"]] == [(b["label"], b["value"]) for b in G["summary"]["income_by_week"]]
    assert [(b["label"], b["value"]) for b in s["expense"]["breakdown"]] == [(b["label"], b["value"]) for b in G["summary"]["expense_by_week"]]
    (a,), (e,) = cal_f["alerts"], G["alerts"]
    assert a["date"] == e["date"] and a["date_to"] == e["end_date"] and a["severity"] == e["severity"] and a["icon"] == e["icon"]
    assert val(a["shortfall"]) == e["shortfall"] and norm(a["title"]) == norm(e["title"])
    sg, es = a["suggestion"], e["suggestion"]
    assert (sg["payment_name"], val(sg["amount"]), sg["from_date"], sg["to_date"], sg["delay_days"], sg["closes_gap"]) == \
        (es["name"], es["amount"], es["from"], es["to"], es["shift_days"], True)
    assert norm(sg["text"]) == norm(es["text"])
    assert norm(a["text"] + " " + sg["text"]) == norm(e["text"]), "alert.text + suggestion.text = the full text of the expected alert"
    assert val(sg["lowest_after"]) == min(x["closing"] for x in e["after"])
    assert dict(recompute_with_move(cal_f["days"], move_of(sg))) == {x["date"]: x["closing"] for x in e["after"]}
    pay = next(p for p in next(d for d in cal_f["days"] if d["date"] == es["from"])["payments"] if p["id"] == sg["payment_id"])
    assert pay["name"] == "ООО «Зоовет»" and pay["max_deferral_days"] == 5


@engine_only
def test_golden_preview_closes_the_gap(client_f, cal_f):
    sug = cal_f["alerts"][0]["suggestion"]
    prev = calendar(client_f, as_of=GOLDEN_AS_OF, preview=sug["id"])
    assert [val(d["closing"]) for d in prev["days"]] == [x["closing"] for x in G["alerts"][0]["after"]]
    assert not [d for d in prev["days"] if is_red(d)] and prev["alerts"] == []
    assert prev["preview"]["suggestion_id"] == sug["id"]
    moved = [(d["date"], p["name"], p["moved_from"]) for d in prev["days"] for p in d["payments"] if p.get("moved_from")]
    assert moved == [("2026-10-12", "ООО «Зоовет»", "2026-10-07")]
    assert calendar(client_f, as_of=GOLDEN_AS_OF) == cal_f, "a preview does not change the real calendar"


@engine_only
def test_golden_dashboard_has_the_cash_gap_advice(client_f, cal_f):
    dash = implemented(client_f.get("/v1/dashboard", params={"as_of": GOLDEN_AS_OF}), "GET /v1/dashboard").json()
    gap = [a for a in dash["advice"] if a["id"] == "cash_gap"]
    assert len(gap) == 1, "advice `cash_gap` with the calendar's first alert"
    assert_cash_gap_advice(gap[0], cal_f["alerts"][0])
    assert len(dash["advice"]) <= 5
    assert [a["id"] for a in dash["advice"] if "link" in a] == ["cash_gap"], "`link` only on cash_gap"


@engine_only
def test_golden_high_safe_balance_through_patch_clinic(client_f):
    """Safe balance 250 000 ₽: two alerts; the first has a PARTIAL suggestion (closes_gap = false), the second a full one."""
    need_writes()
    original = client_f.get("/v1/clinic").json()["safe_balance"]
    assert original == G["safe_balance"], "clinic F is seeded with the safe balance of the case `main`"
    try:
        assert client_f.patch("/v1/clinic", json={"safe_balance": GH["safe_balance"]}).status_code == 200
        cal = calendar(client_f, as_of=GOLDEN_AS_OF)
        assert [(val(d["closing"]), d["status"]) for d in cal["days"]] == [(d["closing"], d["status"]) for d in GH["days"]]
        assert [(a["date"], a["date_to"], a["severity"], val(a["shortfall"])) for a in cal["alerts"]] == \
            [(a["date"], a["end_date"], a["severity"], a["shortfall"]) for a in GH["alerts"]]
        for a, e in zip(cal["alerts"], GH["alerts"]):
            sg, es = a["suggestion"], e["suggestion"]
            assert (sg["payment_name"], val(sg["amount"]), sg["from_date"], sg["to_date"], sg["closes_gap"]) == \
                (es["name"], es["amount"], es["from"], es["to"], es["closes_gap"]), e["date"]
            assert norm(sg["text"]) == norm(es["text"]) and val(sg["lowest_after"]) == e["after_lowest"]["closing"]
            assert norm(a["text"] + " " + sg["text"]) == norm(e["text"])
    finally:
        client_f.patch("/v1/clinic", json={"safe_balance": original})
    assert calendar(client_f, as_of=GOLDEN_AS_OF)["alerts"][0]["suggestion"]["closes_gap"] is True


@engine_only
def test_golden_deferral_zero_for_zoovet_removes_its_suggestion_and_restoring_brings_it_back(client_f, cal_f):
    need_writes()
    zoovet = next(p["counterparty"] for d in cal_f["days"] for p in d["payments"] if p["name"] == "ООО «Зоовет»")
    original = cal_f["alerts"][0]["suggestion"]
    try:
        r = client_f.patch(f"/v1/counterparties/{zoovet['id']}", json={"max_deferral_days": 0})
        assert r.status_code == 200 and r.json()["max_deferral_days"] == 0, r.text
        cal = calendar(client_f, as_of=GOLDEN_AS_OF)
        sg = cal["alerts"][0]["suggestion"]
        assert sg is None or sg["payment_name"] != "ООО «Зоовет»"
        assert cal["alerts"][0]["date"] == "2026-10-09", "the gap itself does not depend on the deferral"
        assert [val(d["closing"]) for d in cal["days"]] == [val(d["closing"]) for d in cal_f["days"]]
    finally:
        client_f.patch(f"/v1/counterparties/{zoovet['id']}", json={"max_deferral_days": 5})
    assert calendar(client_f, as_of=GOLDEN_AS_OF)["alerts"][0]["suggestion"] == original


def test_golden_obligations(client_f):
    o = obligations(client_f, as_of=GOLDEN_AS_OF)
    assert o["as_of"] == GOLDEN_AS_OF
    assert (val(o["debt_total"]), val(o["monthly_payment"]), val(o["amortization_month"])) == \
        (GO["debt_total"], GO["monthly_payment"], GO["amortization_month"])
    loans = {x["name"]: x for x in o["loans"]}
    for e in GO["loans"]:
        g = loans[e["name"]]
        assert (g["kind"], val(g["remaining"]), val(g["payment"]), g["paid_pct"]["value"], g["last_payment_month"]) == \
            (e["kind"], e["remaining"], e["payment"], e["paid_pct"], e["until"]), e["name"]
        assert (g["lender"], g["payment_day"], g["next_payment_date"], g["status"], g["closed_from"]) == \
            (e["lender"], e["payment_day"], e["next_payment_date"], "active", None), e["name"]
    eq = {x["name"]: x for x in o["equipment"]}
    assert set(eq) == {e["name"] for e in GO["equipment"]}
    for e in GO["equipment"]:
        g = eq[e["name"]]
        assert (val(g["cost"]), g["life_years"], val(g["monthly"]), g["in_service_from"], g["amortization_from"], g["amortization_to"]) == \
            (e["cost"], e["life_years"], e["monthly"], e["in_service"], e["amortization_from"], e["amortization_to"]), e["name"]
        assert g["status"] == ("paid" if e["this_month"] == 0 else "active"), e["name"]
    assert eq["Автоклав"]["status"] == "paid", "amortization ended in April: «срок вышел»"
    assert [x["name"] for x in o["equipment"]][-1] == "Автоклав", "paid rows go below the active ones"
    pm = o["pnl_month"]
    assert pm["month"] == "2026-10" and val(pm["amount"]) == GO["charges_month"]["total"]
    by_kind = {"loan_interest": 0, "lease": 0, "amortization": 0}
    for c in GO["charges_month"]["items"]:
        by_kind[c["kind"]] += c["amount"]
    labels = {"Проценты по кредиту": "loan_interest", "Лизинг (платёж целиком)": "lease", "Амортизация оборудования": "amortization"}
    assert {b["label"]: b["value"] for b in pm["amount"]["breakdown"]} == {k: by_kind[v] for k, v in labels.items() if by_kind[v]}


@engine_only
def test_golden_obligations_as_of_the_end_of_september_has_the_earlier_remaining(client_f):
    """`remaining` is the debt after the payments dated before as_of: on 2026-10-09 the payment of the 8th is made."""
    before = obligations(client_f, as_of="2026-10-07")
    after = obligations(client_f, as_of="2026-10-09")
    loan_b = next(x for x in before["loans"] if x["kind"] == "loan")
    loan_a = next(x for x in after["loans"] if x["kind"] == "loan")
    assert val(loan_a["remaining"]) < val(loan_b["remaining"])
    assert val(before["debt_total"]) == GO["debt_total"]


@pytest.mark.parametrize("month,as_of", [("2026-10", GOLDEN_AS_OF), ("2026-09", "2026-10-07")])
@engine_only
def test_golden_obligations_land_in_the_pnl_row(client_f, month, as_of):
    r = implemented(client_f.get("/v1/reports/pnl", params={"month": month, "as_of": as_of}), "GET /v1/reports/pnl")
    assert r.status_code == 200, r.text
    row = {x["key"]: x for x in r.json()["rows"]}["obligations"]
    assert row["amount"]["value"] == EXPECTED["pnl_obligations_row"][month]
    assert "warning" not in row


@engine_only
def test_golden_clinic_f_is_invisible_to_clinic_a(client_a, client_f):
    ids_f = {x["id"] for x in all_rows(obligations(client_f))}
    obl_a = obligations(client_a)
    assert not ids_f & {x["id"] for x in all_rows(obl_a)}
    for oid in sorted(ids_f)[:2]:
        assert_error(client_a.patch(f"/v1/obligations/{oid}", json={"name": "чужое"}), 404, "not_found")
        assert_error(client_a.delete(f"/v1/obligations/{oid}"), 404, "not_found")
    cp_f = first_counterparty(client_f)[0]
    assert_error(client_a.patch(f"/v1/counterparties/{cp_f['id']}", json={"max_deferral_days": 1}), 404, "not_found")
