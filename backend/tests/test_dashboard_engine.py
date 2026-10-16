"""Edge cases of the dashboard engine (stage 2). The golden numbers live in tests/golden/test_dashboard_set03.py."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from engine.dashboard import (
    AccountInput,
    NormsInput,
    SaleInput,
    SaleLineInput,
    TransactionInput,
    VisitInput,
    compute_dashboard,
    history_start,
)
from engine.money import floor_div, format_pct
from engine.ru import format_days_range

NORMS = NormsInput("Препараты", 25, 12)
OPENING = date(2026, 8, 1)
BANK = AccountInput("b", "Расчётный счёт", "bank", 100_000_000, OPENING)
CASH = AccountInput("c", "Касса", "cash", 0, OPENING)


def tx(day: date, amount: int, *, account: str = "b", **kw: object) -> TransactionInput:
    fields: dict[str, object] = {
        "status": "ok",
        "source": "bank",
        "kind": "out" if amount < 0 else "in",
        "category": None,
    }
    fields.update(kw)
    return TransactionInput(account, day, amount, **fields)  # type: ignore[arg-type]


def sale(day: date, services: int, goods: int = 0, status: str = "exec") -> SaleInput:
    return SaleInput(
        day, status, (SaleLineInput("service", services), SaleLineInput("good", goods))
    )


def run(txs: list[TransactionInput], sales: list[SaleInput], as_of: date, accounts=(BANK, CASH)):  # type: ignore[no-untyped-def]
    return compute_dashboard(list(accounts), txs, sales, [], NORMS, as_of)


def test_no_accounts_gives_zeros_and_no_advice() -> None:
    result = compute_dashboard([], [], [], [], NORMS, date(2026, 9, 9))
    assert result.balance.total.value == 0 and result.balance.total.breakdown == ()
    assert result.balance.total.source == ("manual",)
    assert result.balance_trend == () and result.advice == ()
    assert result.balance.runway_days is None and result.balance.week_change is None
    assert result.month.revenue.value == 0 and result.month.profit_margin_pct is None


def test_as_of_before_the_first_day_is_calm() -> None:
    result = run([tx(date(2026, 8, 5), -100)], [], date(2000, 1, 1))
    assert result.balance_trend == () and result.advice == ()
    assert result.month.expenses.value == 0 and result.month.avg_check is None


def test_runway_has_no_value_without_expenses_and_is_zero_for_empty_accounts() -> None:
    as_of = OPENING + timedelta(days=10)
    assert run([tx(OPENING, 5_000)], [], as_of).balance.runway_days is None
    poor = [tx(OPENING + timedelta(days=2), -100_000_000)]
    runway = run(poor, [], as_of).balance.runway_days
    assert runway is not None and runway.value == 0 and runway.unit == "days"


def test_runway_rounds_down_and_window_is_shorter_for_short_history() -> None:
    as_of = OPENING + timedelta(days=3)  # 4 days of history
    runway = run([tx(OPENING, -10_000_000)], [], as_of).balance.runway_days
    assert runway is not None
    balance, burn, daily, window = (b.value for b in runway.breakdown)
    assert (balance, burn, window, daily) == (90_000_000, 10_000_000, 4, 2_500_000)
    assert runway.value == 90_000_000 * 4 // 10_000_000 == 36


def test_transfers_and_duplicates_are_not_expenses() -> None:
    day = OPENING + timedelta(days=5)
    txs = [
        tx(day, -1_000, kind="transfer"),
        tx(day, 1_000, kind="transfer", account="c"),
        tx(day, -7_000, status="duplicate"),
        tx(day, -3_000, category="Аренда"),
    ]
    result = run(txs, [], day)
    assert result.month.expenses.value == 3_000
    assert [(b.label, b.value) for b in result.month.expenses.breakdown] == [("Аренда", 3_000)]
    assert result.balance.total.value == 100_000_000 - 3_000 - 1_000 + 1_000


def test_drafts_are_not_revenue_and_no_invoices_means_no_average_check() -> None:
    day = OPENING + timedelta(days=5)
    only_draft = run([], [sale(day, 500_000, status="save")], day)
    assert only_draft.month.revenue.value == 0 and only_draft.month.avg_check is None
    assert [b.label for b in only_draft.month.revenue.breakdown] == ["Услуги", "Товары"]
    assert only_draft.month.revenue.source == ("manual",)
    closed = run([], [sale(day, 500_000, 100_000), sale(day, 300_001)], day)
    assert closed.month.revenue.value == 900_001
    assert closed.month.avg_check is not None and closed.month.avg_check.value == 450_001  # half up
    assert [d.label for d in closed.month.revenue.details] == ["Средний чек", "Приёмов"]


def test_visits_use_doctor_names_and_unknown_doctor_label() -> None:
    day = OPENING + timedelta(days=5)
    visits = [VisitInput(day, "Иванов И."), VisitInput(day, "Иванов И."), VisitInput(day, "")]
    result = compute_dashboard([BANK], [], [], visits, NORMS, day)
    assert [(b.label, b.value) for b in result.month.visits.breakdown] == [
        ("Иванов И.", 2),
        ("Без врача", 1),
    ]
    empty = compute_dashboard([BANK], [], [], [], NORMS, day)
    assert empty.month.visits.value == 0 and empty.month.visits.breakdown[0].label == "Нет приёмов"


def test_week_change_is_absent_in_the_first_week_and_pct_needs_a_positive_base() -> None:
    first = run([], [], OPENING + timedelta(days=6))
    assert first.balance.week_change is None and first.balance.week_change_pct is None
    broke = AccountInput("z", "Долг", "bank", -5_000, OPENING)
    result = compute_dashboard(
        [broke],
        [tx(OPENING + timedelta(days=8), 2_000, account="z")],
        [],
        [],
        NORMS,
        OPENING + timedelta(days=9),
    )
    assert result.balance.week_change is not None and result.balance.week_change.value == 2_000
    assert result.balance.week_change_pct is None  # the balance a week ago was not positive


def test_week_change_breakdown_adds_up_and_is_marked_as_a_change() -> None:
    as_of = OPENING + timedelta(days=20)
    result = run([tx(as_of, -250), tx(as_of - timedelta(days=1), 1_000, account="c")], [], as_of)
    week = result.balance.week_change
    assert week is not None and week.delta is True
    assert sum(b.value for b in week.breakdown) == week.value == 750
    assert all(b.delta for b in week.breakdown)
    pct = result.balance.week_change_pct
    assert pct is not None and pct.unit == "pct" and pct.delta is True


def test_trend_has_up_to_fourteen_points_ending_at_the_total() -> None:
    long_ago = OPENING + timedelta(days=40)
    result = run([tx(long_ago, -1_000)], [], long_ago)
    assert len(result.balance_trend) == 14
    assert result.balance_trend[-1].value == result.balance.total.value
    assert result.balance_trend[-1].date == long_ago
    assert [p.date for p in result.balance_trend] == sorted(p.date for p in result.balance_trend)


def _history(extra: list[TransactionInput], as_of: date) -> list[TransactionInput]:
    return [tx(as_of - timedelta(days=d), -1_000_000) for d in range(0, 5)] + extra


def test_advice_waits_for_a_week_of_history_and_a_week_of_the_month() -> None:
    sales = [sale(date(2026, 8, 2), 10_000_000)]
    early = run([tx(date(2026, 8, 3), -50_000_000)], sales, OPENING + timedelta(days=5))
    assert early.advice == ()
    # September 3rd: plenty of history, but the month rules wait for the 7th
    third = run([tx(date(2026, 9, 2), -90_000_000)], sales, date(2026, 9, 3))
    assert [a.id for a in third.advice] == ["cash_runway"]


def test_advice_status_says_why_the_list_is_empty() -> None:
    sales = [sale(date(2026, 8, 2), 10_000_000)]
    assert (
        compute_dashboard([], [], [], [], NORMS, date(2026, 9, 9)).advice_status
        == "not_enough_data"
    )
    assert run([], [], date(2000, 1, 1)).advice_status == "not_enough_data"
    assert run([], sales, OPENING + timedelta(days=5)).advice_status == "not_enough_data"  # 6 days
    seventh = run([], sales, OPENING + timedelta(days=6))  # 7 days of history: rules run
    assert seventh.advice_status == "ready"
    calm = run([], [], date(2026, 9, 3))  # enough history, nothing out of the norm
    assert calm.advice == () and calm.advice_status == "ready"


def test_advice_text_limits_and_forbidden_words() -> None:
    as_of = date(2026, 9, 20)
    txs = [
        tx(date(2026, 9, 3), -40_000_000, category="Препараты"),
        tx(date(2026, 9, 5), -45_000_000),
    ]
    sales = [sale(date(2026, 8, 5), 100_000_000), sale(date(2026, 9, 5), 60_000_000)]
    result = run(txs, sales, as_of)
    ids = [a.id for a in result.advice]
    assert {"cash_runway", "drug_share", "revenue_drop"} <= set(ids)
    assert len(result.advice) <= 5
    for advice in result.advice:
        assert len(advice.title) <= 80 and len(advice.text) <= 200, advice.id
        assert 2 <= len(advice.why.steps) <= 5 and all(len(s) <= 240 for s in advice.why.steps)
        text = " ".join([advice.title, advice.text, advice.why.summary, *advice.why.steps]).lower()
        assert "ии" not in text.split() and "нейросет" not in text and "бот" not in text


def test_drug_share_boundary_is_exclusive() -> None:
    as_of = date(2026, 9, 20)
    sales = [sale(date(2026, 9, 5), 100_000_000)]
    at_norm = run([tx(date(2026, 9, 3), -25_000_000, category="Препараты")], sales, as_of)
    over = run([tx(date(2026, 9, 3), -25_000_001, category="Препараты")], sales, as_of)
    assert "drug_share" not in [a.id for a in at_norm.advice]
    assert "drug_share" in [a.id for a in over.advice]


def test_revenue_drop_boundary_and_missing_previous_month() -> None:
    as_of = date(2026, 9, 20)
    prior = sale(date(2026, 8, 10), 100_000_000)
    exactly_85 = run([], [prior, sale(date(2026, 9, 5), 85_000_000)], as_of)
    below = run([], [prior, sale(date(2026, 9, 5), 84_999_999)], as_of)
    assert "revenue_drop" not in [a.id for a in exactly_85.advice]
    assert "revenue_drop" in [a.id for a in below.advice]
    young = AccountInput("b", "Расчётный счёт", "bank", 0, date(2026, 8, 15))
    no_previous = compute_dashboard(
        [young], [], [prior, sale(date(2026, 9, 5), 1)], [], NORMS, as_of
    )
    assert "revenue_drop" not in [a.id for a in no_previous.advice]


def test_margin_ok_is_good_and_comes_last() -> None:
    as_of = date(2026, 9, 20)
    result = run([tx(date(2026, 9, 5), -1_000_000)], [sale(date(2026, 9, 5), 90_000_000)], as_of)
    assert [(a.id, a.severity) for a in result.advice][-1] == ("margin_ok", "good")


def test_profit_and_margin_advice_say_the_profit_is_by_money() -> None:
    """Owner decision 2026-10-14: the dashboard profit is cash based and is named so everywhere."""
    as_of = date(2026, 9, 20)
    result = run([tx(date(2026, 9, 5), -1_000_000)], [sale(date(2026, 9, 5), 90_000_000)], as_of)
    note = result.month.profit.note
    assert note.startswith("Прибыль по деньгам:")
    assert "все деньги расходов" in note
    assert "Налоги, амортизация и комиссия эквайринга здесь не начислены" in note
    assert "«Чистой прибыли» отчёта" in note
    advice = next(a for a in result.advice if a.id == "margin_ok")
    texts = [advice.text, advice.why.summary, *advice.why.steps]
    assert advice.text.startswith("Прибыль по деньгам за ")
    assert all("Прибыль по деньгам" in t for t in (advice.text, advice.why.summary))
    assert any("Прибыль по деньгам, выручка минус расходы" in t for t in texts)
    assert len(advice.text) <= 200 and len(advice.title) <= 80


def test_inputs_are_not_mutated_and_order_does_not_matter() -> None:
    as_of = date(2026, 9, 12)
    txs = [tx(date(2026, 9, d), -d * 1_000, category="Аренда") for d in range(1, 12)]
    sales = [sale(date(2026, 9, d), d * 10_000) for d in range(1, 12)]
    accounts = [BANK, CASH]
    straight = compute_dashboard(accounts, txs, sales, [], NORMS, as_of)
    reverse = compute_dashboard(accounts[::-1], txs[::-1], sales[::-1], [], NORMS, as_of)
    assert straight == reverse
    assert txs[0] == tx(date(2026, 9, 1), -1_000, category="Аренда") and len(txs) == 11
    assert replace(straight.month, days_passed=1) != straight.month  # results are frozen values


def test_history_start_is_the_first_day_of_the_previous_month() -> None:
    assert history_start(date(2026, 9, 9)) == date(2026, 8, 1)
    assert history_start(date(2026, 1, 31)) == date(2025, 12, 1)


def test_floor_div_and_text_helpers() -> None:
    assert floor_div(17_6, 10) == 17
    with pytest.raises(ValueError):
        floor_div(1, 0)
    assert format_pct(__import__("decimal").Decimal("-30.6")) == "−30,6"
    assert format_days_range(date(2026, 9, 1), date(2026, 9, 9)) == "1–9 сентября"
    assert format_days_range(date(2026, 8, 30), date(2026, 9, 2)) == "30 августа – 2 сентября"
