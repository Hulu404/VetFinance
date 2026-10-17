"""Golden tests of the stage 4 engines (payment calendar, regular payments, obligations), set05.

Expected numbers come from set05/expected.json, computed independently by tools/compute_expected_set05.py, never from the engine.
Interfaces under test: see set05_support.py and docs/handoff.md ("tester -> backend-developer (этап 4)"). Tests of
engine.calendar / engine.obligations skip while the modules do not exist. Two bridges run already now on the engines of
stages 0 and 3: the opening balance equals engine.balance, and the charges of a month land in the P&L row "obligations".
"""
from datetime import date, timedelta

import pytest

from set05_support import (AS_OF, CASES, DATA, EXPECTED, accounts, build, calendar_inputs, call, categories, contains_amount,
                           engine_function, expected_payment_tuples, month_arg, obligations, payment_tuples, plain,
                           profile_amounts, recompute_with_move, recurring_tuples, red, reversed_inputs, run_calendar,
                           suggested_move, transactions, v)

CAL = EXPECTED["calendar"]
MAIN = CAL["main"]
OBL = EXPECTED["obligations"]
DAY_IDS = [d["date"] for d in MAIN["days"]]
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
SOURCES = {"recurring", "obligation", "manual"}
FORBIDDEN = ("ИИ", "нейросет", "катастроф", "долг")


# ================================================================== calendar (functions 21, 43)
@pytest.fixture(scope="module")
def cal_fn():
    return engine_function("engine.calendar", "compute_calendar")


@pytest.fixture(scope="module")
def cal(cal_fn):
    inputs = calendar_inputs()
    return {key: run_calendar(cal_fn, key, inputs) for key in CASES}


def days_by_date(result):
    return {d["date"]: d for d in result["days"]}


def test_22_consecutive_days_from_as_of_with_weekdays(cal):
    days = cal["main"]["days"]
    assert len(days) == 22
    assert [d["date"] for d in days] == [(AS_OF + timedelta(days=i)).isoformat() for i in range(22)]
    assert [d["weekday"] for d in days] == [WEEKDAYS[date.fromisoformat(d["date"]).weekday()] for d in days]


def test_opening_of_the_first_day_is_the_balance_on_the_morning_of_as_of(cal):
    first = cal["main"]["days"][0]
    assert v(first["opening"]) == MAIN["opening"]["value"]
    if isinstance(first["opening"], dict) and first["opening"].get("breakdown"):
        got = {b["label"]: b["value"] for b in first["opening"]["breakdown"]}
        assert got == {b["label"]: b["value"] for b in MAIN["opening"]["breakdown"]}


@pytest.mark.parametrize("day", DAY_IDS)
def test_every_day_opening_income_closing_to_the_kopeck(cal, day):
    got, exp = days_by_date(cal["main"])[day], days_by_date(MAIN)[day]
    assert (v(got["opening"]), v(got["income_forecast"]), v(got["closing"])) == \
        (exp["opening"], exp["income_forecast"], exp["closing"])
    assert red(got) is exp["below_safe"]


@pytest.mark.parametrize("day", DAY_IDS)
def test_every_day_payments_with_source(cal, day):
    got, exp = days_by_date(cal["main"])[day], days_by_date(MAIN)[day]
    assert payment_tuples(got) == expected_payment_tuples(exp)
    for p in got["payments"]:
        assert p["source"] in SOURCES and type(v(p["amount"])) is int and v(p["amount"]) > 0


@pytest.mark.parametrize("case", list(CASES))
def test_identity_and_chain_on_the_engine_own_numbers(cal, case):
    days = cal[case]["days"]
    for i, d in enumerate(days):
        assert v(d["opening"]) + v(d["income_forecast"]) - sum(v(p["amount"]) for p in d["payments"]) == v(d["closing"]), d["date"]
        if i:
            assert v(d["opening"]) == v(days[i - 1]["closing"]), d["date"]


@pytest.mark.parametrize("case", list(CASES))
def test_below_safe_iff_closing_is_less_than_the_safe_balance(cal, case):
    safe = CASES[case]["safe_balance"]
    assert v(cal[case]["safe_balance"]) == safe
    for d in cal[case]["days"]:
        assert red(d) is (v(d["closing"]) < safe), d["date"]
    assert [d["date"] for d in cal[case]["days"] if red(d)] == [d["date"] for d in CAL[case]["days"] if d["below_safe"]]


@pytest.mark.parametrize("case", list(CASES))
def test_day_status_and_balance_after_each_payment(cal, case):
    """Rules 14 and 16 (designer's definitions): payments first by amount, income at the end; status ok|below_safe|below_zero."""
    for got, exp in zip(cal[case]["days"], CAL[case]["days"]):
        if "status" in got:
            assert got["status"] == exp["status"], exp["date"]
        pays = got["payments"]
        if pays and "balance_after" in pays[0]:
            assert [(p["name"], v(p["balance_after"])) for p in pays] == \
                [(p["name"], p["balance_after"]) for p in exp["payments"]], exp["date"]
        elif pays:
            pytest.skip("payments[].balance_after is not returned yet (function 21: balance after each payment)")


def test_closing_breakdown_is_morning_plus_income_minus_payments(cal):
    for d in cal["main"]["days"]:
        if not isinstance(d["closing"], dict):
            pytest.skip("closing is a plain number; the contract wants a Figure with a breakdown")
        bd = d["closing"]["breakdown"]
        assert sum(b["value"] for b in bd) == v(d["closing"]), d["date"]
        assert len(bd) == 2 + len(d["payments"]), d["date"]


def test_summary(cal):
    s, e = cal["main"]["summary"], MAIN["summary"]
    assert v(s["income"]) == e["income"] and v(s["expense"]) == e["expense"]
    assert s["payments_count"] == e["payments_count"]
    assert s["lowest"]["date"] == e["lowest"]["date"] and v(s["lowest"]["balance"]) == e["lowest"]["balance"]
    if isinstance(s["income"], dict):
        assert [(b["label"], b["value"]) for b in s["income"]["breakdown"]] == [(b["label"], b["value"]) for b in e["income_by_week"]]
        assert [(b["label"], b["value"]) for b in s["expense"]["breakdown"]] == [(b["label"], b["value"]) for b in e["expense_by_week"]]


@pytest.mark.parametrize("case", list(CASES))
def test_alerts_date_shortfall_and_suggestion(cal, case):
    got, exp = cal[case]["alerts"], CAL[case]["alerts"]
    assert [a["date"] for a in got] == [a["date"] for a in exp]
    for g, e in zip(got, exp):
        assert v(g["shortfall"]) == e["shortfall"], e["date"]
        if e["suggestion"] is None:
            assert g.get("suggestion") is None, e["date"]
            continue
        s, es = g["suggestion"], e["suggestion"]
        move = suggested_move(s, cal[case]["days"])
        assert (move["name"], move["amount"], move["from"], move["to"]) == (es["name"], es["amount"], es["from"], es["to"])
        assert s["closes_gap"] is es["closes_gap"], e["date"]
        if "severity" in g:
            assert g["severity"] == e["severity"], e["date"]
        end = g.get("date_to", g.get("end_date"))
        if end is not None:
            assert end == e["end_date"], e["date"]
        # extra fields of the flat suggestion (contract 2026-10-17), checked when the engine returns them
        if "delay_days" in s:
            assert s["delay_days"] == es["shift_days"], e["date"]
        if "lowest_after" in s:
            assert v(s["lowest_after"]) == min(x["closing"] for x in e["after"]), e["date"]
        if "payment_id" in s:
            day = next(d for d in cal[case]["days"] if d["date"] == es["from"])
            assert [p["name"] for p in day["payments"] if p.get("id") == s["payment_id"]] == [es["name"]], e["date"]


@pytest.mark.parametrize("case", list(CASES))
def test_the_suggested_move_really_closes_the_gap(cal, case):
    """Recomputed from the engine's own days: after the move no day of the gap is below the safe balance and no new red day."""
    safe = CASES[case]["safe_balance"]
    days = cal[case]["days"]
    red_before = {d["date"] for d in days if red(d)}
    for a, e in zip(cal[case]["alerts"], CAL[case]["alerts"]):
        if not a.get("suggestion"):
            continue
        s = a["suggestion"]
        after = recompute_with_move(days, suggested_move(s, days))
        assert [x["closing"] for x in after] == [x["closing"] for x in e["after"]], e["date"]
        gap = set(e["days_below"])
        closes = all(x["closing"] >= safe for x in after if x["date"] in gap) and \
            not [x for x in after if x["closing"] < safe and x["date"] not in red_before]
        assert closes is s["closes_gap"], e["date"]


def test_preview_with_the_move_has_no_red_days(cal_fn, cal):
    """If the engine can apply a move (`moves`), the calendar after it has no red day and no alert."""
    import inspect
    if "moves" not in inspect.signature(cal_fn).parameters:
        pytest.skip("compute_calendar has no `moves` parameter yet (preview of a suggestion); proposed in docs/handoff.md")
    s = MAIN["alerts"][0]["suggestion"]
    pay = next(p for d in cal["main"]["days"] if d["date"] == s["from"] for p in d["payments"] if p["name"] == s["name"])
    move = build("PaymentMoveInput", name=s["name"], source=s["source"], from_date=date.fromisoformat(s["from"]),
                 to_date=date.fromisoformat(s["to"]), payment_id=pay.get("id"))
    after = run_calendar(cal_fn, "main", moves=[move])
    assert [v(d["closing"]) for d in after["days"]] == [x["closing"] for x in MAIN["alerts"][0]["after"]]
    assert not [d for d in after["days"] if red(d)] and after["alerts"] == []
    moved = [(d["date"], p["name"], p.get("moved_from")) for d in after["days"] for p in d["payments"] if p.get("moved_from")]
    assert moved in ([], [(s["to"], s["name"], s["from"])]), "if the engine marks the moved payment it is the one of the suggestion"


def test_alert_texts_name_the_numbers_and_avoid_forbidden_words(cal):
    a, e = cal["main"]["alerts"][0], MAIN["alerts"][0]
    assert contains_amount(a["title"], e["shortfall"]), a["title"]
    assert contains_amount(a["text"], e["lowest"]), a["text"]
    s = a["suggestion"]["text"]
    assert "Зоовет" in s and contains_amount(s, e["suggestion"]["amount"]) and "12 октября" in s, s
    why = a.get("why") or {}
    assert why.get("summary") and 2 <= len(why.get("steps", [])) <= 5 and why.get("sources"), "why: summary, 2-5 steps, sources"
    text = " ".join([a["title"], a["text"], s, why.get("summary", "")] + list(why.get("steps", [])))
    for word in FORBIDDEN:
        assert word not in text, word


def test_same_input_twice_and_in_reverse_order_gives_the_same_calendar(cal_fn, cal):
    inputs = calendar_inputs()
    assert run_calendar(cal_fn, "main", inputs) == cal["main"]
    assert run_calendar(cal_fn, "main", reversed_inputs(inputs)) == cal["main"]


# ================================================================== regular payments and income (function 22)
@pytest.fixture(scope="module")
def recurring():
    fn = engine_function("engine.calendar", "detect_recurring")
    return plain(call(fn, transactions=transactions(), categories=categories(), as_of=AS_OF,
                      counterparties=[]))


def test_regular_payments_found_in_the_bank_history(recurring):
    exp = {(s["name"], s["category"], slot["day"], slot["amount"]) for s in MAIN["recurring"] for slot in s["slots"]}
    assert recurring_tuples(recurring) == exp


def test_one_off_payments_and_obligations_are_not_regular(recurring):
    names = {s.get("name") or s.get("counterparty_name") for s in recurring}
    for r in MAIN["not_recurring"]:
        assert r["name"] not in names, r
    cats = {s.get("category") for s in recurring}
    assert not cats & {"Платежи по кредитам и лизингу", "Покупка оборудования", "Вывод средств владельца"}


def test_income_profile_by_weekday():
    fn = engine_function("engine.calendar", "income_profile")
    got = profile_amounts(plain(call(fn, transactions=transactions(), categories=categories(), as_of=AS_OF)))
    assert got == [r["average"] for r in MAIN["income_profile"]["by_weekday"]]


def test_calendar_payments_come_from_three_sources(cal):
    sources = {p["source"] for d in cal["main"]["days"] for p in d["payments"]}
    assert sources == SOURCES
    loan_days = [d["date"] for d in cal["main"]["days"] for p in d["payments"] if p["name"] == "Кредит на аппарат УЗИ"]
    assert loan_days == ["2026-10-08"], "the loan comes once, from the obligation, not again from the bank history"


# ================================================================== obligations (function 23)
@pytest.fixture(scope="module")
def charges_fn():
    return engine_function("engine.obligations", "compute_obligation_charges")


@pytest.mark.parametrize("month", DATA["charge_months"])
def test_charges_of_every_month(charges_fn, month):
    got = plain(call(charges_fn, obligations=obligations(), month=month_arg(month)))
    exp = EXPECTED["charges_by_month"][month]
    assert sorted((c["obligation_id"], c["kind"], c["amount"]) for c in got) == \
        sorted((c["obligation_id"], c["kind"], c["amount"]) for c in exp["items"])
    assert all(str(c["month"])[:7] == month for c in got)


def test_autoclave_ended_in_april_and_centrifuge_starts_in_october(charges_fn):
    def ids(month):
        return {c["obligation_id"] for c in plain(call(charges_fn, obligations=obligations(), month=month_arg(month)))
                if c["kind"] == "amortization"}
    assert "S5-eq-autoclave" in ids("2026-04") and "S5-eq-autoclave" not in ids("2026-05")
    assert "S5-eq-centr" not in ids("2026-09") and "S5-eq-centr" in ids("2026-10")


@pytest.fixture(scope="module")
def summary():
    fn = engine_function("engine.obligations", "compute_obligations")
    return plain(call(fn, obligations=obligations(), as_of=AS_OF))


def test_obligations_summary(summary):
    for key in ("debt_total", "monthly_payment", "amortization_month"):
        assert v(summary[key]) == OBL[key], key
    if "charges_month" in summary:
        assert v(summary["charges_month"]) == OBL["charges_month"]["total"]


def test_loans_and_leases(summary):
    got = {x["name"]: x for x in summary["loans"]}
    for e in OBL["loans"]:
        g = got[e["name"]]
        assert (v(g["remaining"]), v(g["payment"]), float(v(g["paid_pct"])), g["until"][:7]) == \
            (e["remaining"], e["payment"], e["paid_pct"], e["until"]), e["name"]
        assert g.get("lender") == e["lender"]


def test_equipment(summary):
    got = {x["name"]: x for x in summary["equipment"]}
    for e in OBL["equipment"]:
        g = got[e["name"]]
        assert (v(g["cost"]), g["life_years"], v(g["monthly"])) == (e["cost"], e["life_years"], e["monthly"]), e["name"]


def test_charges_from_the_engine_land_in_the_pnl_row(charges_fn):
    pnl = engine_function("engine.pnl", "compute_pnl")
    for month, as_of in (("2026-09", None), ("2026-10", AS_OF)):
        charges = call(charges_fn, obligations=obligations(), month=month_arg(month))
        res = plain(call(pnl, categories=categories(), transactions=transactions(with_counterparty=False), sales=[],
                         card_payments=[], charges=list(charges), month=month_arg(month), acquiring_rate_bp=0, as_of=as_of))
        row = {r["key"]: r for r in res["rows"]}["obligations"]
        assert row["amount"]["value"] == EXPECTED["pnl_obligations_row"][month], month


# ================================================================== bridges that run now (stages 0 and 3)
def _charge_inputs(month):
    return [build("ObligationChargeInput", month=month, obligation_id=c["obligation_id"], name=c["name"], kind=c["kind"],
                  amount=c["amount"]) for c in EXPECTED["charges_by_month"][month]["items"]]


@pytest.mark.parametrize("month,as_of", [("2026-09", None), ("2026-10", "2026-10-07")])
def test_expected_charges_are_the_pnl_obligations_row_and_bank_loan_payments_are_not(month, as_of):
    """The stage 3 P&L engine takes the whole month of charges, also in a running month; the bank payments of the loan
    and the lease (article of type obligation), the centrifuge (capex) and the owner draw are not in any row."""
    pnl = engine_function("engine.pnl", "compute_pnl")
    res = plain(call(pnl, categories=categories(), transactions=transactions(with_counterparty=False), sales=[], card_payments=[],
                     charges=_charge_inputs(month), month=month_arg(month), acquiring_rate_bp=0,
                     as_of=date.fromisoformat(as_of) if as_of else None))
    rows = {r["key"]: r for r in res["rows"]}
    assert rows["obligations"]["amount"]["value"] == EXPECTED["pnl_obligations_row"][month]
    labels = {b["label"] for r in res["rows"] for b in r["amount"]["breakdown"]}
    assert not labels & {"Платежи по кредитам и лизингу", "Покупка оборудования", "Вывод средств владельца"}


def test_opening_equals_the_balance_engine_on_the_eve_of_as_of():
    fn = engine_function("engine.balance", "compute_balance")
    res = plain(call(fn, accounts=accounts(), transactions=transactions(with_counterparty=False),
                     as_of=AS_OF - timedelta(days=1)))
    assert res["total"]["value"] == MAIN["opening"]["value"] == EXPECTED["dashboard_balance_at_as_of"]
