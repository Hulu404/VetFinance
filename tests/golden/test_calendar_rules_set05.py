"""Golden tests of set05 for rules that the first draft of the set left open (stage 4, engine level).

Covers the three rules that backend-developer asked to confirm (docs/handoff.md, 2026-10-17, item 7) and the closing of an
obligation (owner's decision of 2026-10-16, item 4: "закрыть вместо удалить"):

  * the forecast of the day `as_of` is reduced by the income already in the statement (not below zero);
  * a regular payment already paid on `as_of` is not forecast again (README rule 11);
  * `history_days` and the threshold of `short_history`; a short history divides an average by the days that exist;
  * DELETE of an obligation = close from a month: past accruals stay, this month and later ones go.

Every expected number is derived from expected.json / data.json by arithmetic written in the test, never from the engine.
Interfaces: set05_support.py. Tests skip while the engine modules or input fields are missing.
"""
from datetime import date, timedelta

import pytest

from set05_support import (AS_OF, DATA, EXPECTED, build, calendar_inputs, call, categories, div_round, engine_function, month_arg,
                           obligations, plain, run_calendar, transactions, v)

CAL = EXPECTED["calendar"]
MAIN = CAL["main"]
OBL = EXPECTED["obligations"]


@pytest.fixture(scope="module")
def cal_fn():
    return engine_function("engine.calendar", "compute_calendar")


@pytest.fixture(scope="module")
def base(cal_fn):
    return run_calendar(cal_fn, "main")


def tx_row(**kw):
    row = {"id": "X-1", "account_id": "S5-bank", "date": str(AS_OF), "amount": 0, "kind": "in", "status": "ok", "source": "bank",
           "category": "Выручка эквайринг", "counterparty_inn": "7707083893", "counterparty_name": "Сбербанк (эквайринг)",
           "description": "тест: операция дня as_of"}
    return {**row, **kw}


def closings(result):
    return {d["date"]: v(d["closing"]) for d in result["days"]}


# ================================================================== the day as_of itself
@pytest.mark.parametrize("received", [1_000_000, 4_287_345, 6_000_000])
def test_income_already_in_the_statement_on_as_of_replaces_the_forecast_of_that_day(cal_fn, base, received):
    """The money is in the opening balance, so the closing of every day grows only by what exceeds the forecast:
    closing' = closing + max(0, received - forecast); the forecast of the day is forecast - received, not below zero."""
    forecast = v(base["days"][0]["income_forecast"])
    assert forecast == 4_287_345, "the Wednesday average of set05 (README: 42 873,45 ₽)"
    res = run_calendar(cal_fn, "main", calendar_inputs(extra_tx=[tx_row(amount=received)]))
    first = res["days"][0]
    assert v(first["opening"]) == v(base["days"][0]["opening"]) + received, "operations of as_of are in the balance of the morning"
    assert v(first["income_forecast"]) == max(0, forecast - received)
    extra = max(0, received - forecast)
    assert closings(res) == {d: c + extra for d, c in closings(base).items()}
    assert [v(d["income_forecast"]) for d in res["days"][1:]] == [v(d["income_forecast"]) for d in base["days"][1:]], \
        "the operation of as_of is outside the 12 weeks of the profile"


def test_regular_payment_already_paid_on_as_of_is_not_forecast_again(cal_fn, base):
    """«Зоовет» paid its first slot of October on 7 October (README rule 11): the bank has it, the window must not repeat it,
    so every closing is the same as without the operation; the second slot (21 October) stays."""
    paid = tx_row(id="X-2", kind="out", amount=-10_850_000, category="Препараты и расходники", counterparty_inn="5003012345",
                  counterparty_name="ООО «Зоовет»", description="тест: платёж дня as_of")
    res = run_calendar(cal_fn, "main", calendar_inputs(extra_tx=[paid]))
    assert v(res["days"][0]["opening"]) == v(base["days"][0]["opening"]) - 10_850_000
    assert closings(res) == closings(base)
    names = {d["date"]: [p["name"] for p in d["payments"]] for d in res["days"]}
    assert "ООО «Зоовет»" not in names["2026-10-07"] and "ООО «Зоовет»" in names["2026-10-21"]


# ================================================================== history_days, short_history
SINCE = date(2026, 8, 10)           # a Monday with a bank operation: 59 days of history up to 7 October inclusive


def test_short_history_divides_by_the_days_that_exist(cal_fn):
    """History from 10 August: the average of a weekday = income of those days / their number in 10 Aug - 6 Oct (not 12)."""
    types = {c["name"]: c["type"] for c in DATA["categories"]}
    end = AS_OF - timedelta(days=1)
    days = [SINCE + timedelta(days=i) for i in range((end - SINCE).days + 1)]
    counts = [sum(1 for d in days if d.weekday() == w) for w in range(7)]
    assert counts == [9, 9, 8, 8, 8, 8, 8]
    sums = [0] * 7
    for t in DATA["transactions"]:
        d = date.fromisoformat(t["date"])
        if SINCE <= d <= end and t["kind"] == "in" and t["status"] != "duplicate" and types.get(t["category"]) == "income":
            sums[d.weekday()] += t["amount"]
    expected = [div_round(sums[w], counts[w]) for w in range(7)]
    assert expected != [r["average"] for r in MAIN["income_profile"]["by_weekday"]], "the shorter history changes the averages"

    res = run_calendar(cal_fn, "main", calendar_inputs(since=SINCE))
    assert [v(d["income_forecast"]) for d in res["days"]] == [expected[date.fromisoformat(d["date"]).weekday()] for d in res["days"]]
    assert v(res["days"][0]["opening"]) == MAIN["opening"]["value"], "the accounts open on 10 August with the balance they had"
    if "history_days" in res:
        assert res["history_days"] == (AS_OF - SINCE).days + 1 == 59
    if "partial_reasons" in res:
        assert "short_history" in res["partial_reasons"] and res["status"] == "partial"


@pytest.mark.parametrize("since,days,short", [(date(2026, 7, 1), 99, False), (date(2026, 7, 15), 85, True)])
def test_short_history_is_also_fewer_than_three_full_months_before_the_month_of_as_of(cal_fn, since, days, short):
    """Contract: short_history = history shorter than three full months before the month of as_of OR shorter than 84 days.
    From 1 July the months July, August, September are complete (99 days); from 15 July only two are (85 days: the day count
    alone would say «enough», but no regular payment can be found without three full months)."""
    assert any(t["date"] == str(since) and t["source"] == "bank" for t in DATA["transactions"]), "the set has a bank operation that day"
    res = run_calendar(cal_fn, "main", calendar_inputs(since=since))
    if "partial_reasons" not in res:
        pytest.skip("the engine result has no partial_reasons")
    assert res["history_days"] == (AS_OF - since).days + 1 == days
    assert ("short_history" in res["partial_reasons"]) is short, res["partial_reasons"]


def test_full_history_has_no_partial_reason(base):
    if "partial_reasons" not in base:
        pytest.skip("the engine result has no partial_reasons")
    assert base["partial_reasons"] == [] and base["status"] == "ok"
    first_bank_day = date.fromisoformat(DATA["history"]["from"])
    assert base["history_days"] == (AS_OF - first_bank_day).days + 1 == 190, "from the earliest bank operation to as_of, both counted"


# ================================================================== closing an obligation
CLOSE_FROM = "2026-10"
CLOSED = {"S5-loan": ("loan", "Кредит на аппарат УЗИ"), "S5-eq-centr": ("equipment", "Центрифуга")}


@pytest.fixture(scope="module")
def charges_fn():
    return engine_function("engine.obligations", "compute_obligation_charges")


@pytest.mark.parametrize("oid", list(CLOSED))
def test_closing_from_october_keeps_the_past_and_drops_october_on(charges_fn, oid):
    closed = {oid: CLOSE_FROM}
    for month in DATA["charge_months"]:
        got = plain(call(charges_fn, obligations=obligations(closed), month=month_arg(month)))
        items = EXPECTED["charges_by_month"][month]["items"]
        exp = items if month < CLOSE_FROM else [c for c in items if c["obligation_id"] != oid]
        assert sorted((c["obligation_id"], c["kind"], c["amount"]) for c in got) == \
            sorted((c["obligation_id"], c["kind"], c["amount"]) for c in exp), month


@pytest.mark.parametrize("oid", list(CLOSED))
def test_closed_obligation_in_the_summary(oid):
    fn = engine_function("engine.obligations", "compute_obligations")
    res = plain(call(fn, obligations=obligations({oid: CLOSE_FROM}), as_of=AS_OF))
    kind, name = CLOSED[oid]
    row = {x["name"]: x for x in res["loans"] + res["equipment"]}[name]
    assert row["status"] == "closed" and str(row["closed_from"])[:7] == CLOSE_FROM
    loan = next((x for x in OBL["loans"] if x["name"] == name), None)
    equipment = next((x for x in OBL["equipment"] if x["name"] == name), None)
    if kind == "loan":
        assert v(row["remaining"]) == 0 and v(row["payment"]) == 0
        assert v(res["debt_total"]) == OBL["debt_total"] - loan["remaining"]
        assert v(res["monthly_payment"]) == OBL["monthly_payment"] - loan["payment"]
        assert v(res["amortization_month"]) == OBL["amortization_month"]
    else:
        assert v(row["monthly"]) == equipment["monthly"], "monthly stays as a reference"
        assert v(res["amortization_month"]) == OBL["amortization_month"] - equipment["monthly"]
        assert v(res["debt_total"]) == OBL["debt_total"]
    month_charges = res.get("pnl_month") or res.get("charges_month")
    if month_charges is not None:
        amount = v(month_charges["amount"]) if isinstance(month_charges, dict) and "amount" in month_charges else v(month_charges)
        gone = next(c["amount"] for c in OBL["charges_month"]["items"] if c["obligation_id"] == oid)
        assert amount == OBL["charges_month"]["total"] - gone


def test_the_same_obligation_is_active_for_an_earlier_as_of():
    fn = engine_function("engine.obligations", "compute_obligations")
    res = plain(call(fn, obligations=obligations({"S5-loan": CLOSE_FROM}), as_of=date(2026, 9, 15)))
    row = next(x for x in res["loans"] if x["name"] == "Кредит на аппарат УЗИ")
    assert row["status"] == "active" and v(row["remaining"]) > 0 and v(row["payment"]) == 5_273_500


def test_closed_loan_leaves_the_calendar_and_the_balance_of_the_following_days_rises(cal_fn, base):
    res = run_calendar(cal_fn, "main", calendar_inputs(closed={"S5-loan": CLOSE_FROM}))
    assert not [p for d in res["days"] for p in d["payments"] if p["name"] == "Кредит на аппарат УЗИ"]
    assert closings(res) == {d: c + (5_273_500 if d >= "2026-10-08" else 0) for d, c in closings(base).items()}


def test_closed_obligation_charges_leave_the_pnl_row_of_the_running_month_only(charges_fn):
    pnl = engine_function("engine.pnl", "compute_pnl")
    interest = next(c["amount"] for c in OBL["charges_month"]["items"] if c["obligation_id"] == "S5-loan")
    for month, as_of in (("2026-09", None), ("2026-10", AS_OF)):
        charges = call(charges_fn, obligations=obligations({"S5-loan": CLOSE_FROM}), month=month_arg(month))
        res = plain(call(pnl, categories=categories(), transactions=transactions(with_counterparty=False), sales=[],
                         card_payments=[], charges=list(charges), month=month_arg(month), acquiring_rate_bp=0, as_of=as_of))
        row = {r["key"]: r for r in res["rows"]}["obligations"]
        assert row["amount"]["value"] == EXPECTED["pnl_obligations_row"][month] - (interest if month >= CLOSE_FROM else 0), month
