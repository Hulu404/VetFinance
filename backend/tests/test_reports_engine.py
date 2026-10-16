"""Edge cases of the report engines (P&L, norm, stock) on small synthetic data.

The golden set (tests/golden/set04) covers the numbers of a realistic clinic; here are the boundaries and
the texts that a golden set cannot show: losses, a month without revenue, borders of the norm to the kopeck,
a norm without a benchmark, stock without movement data.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from engine.acquiring import CardPayment
from engine.balance import TransactionInput
from engine.dashboard_inputs import SaleInput, SaleLineInput
from engine.norm import NormItem, NormResult, compute_norm
from engine.pnl import PnlResult, compute_direction_view, compute_pnl
from engine.report_facts import last_closed_month
from engine.reports_inputs import (
    BenchmarkInput,
    CategoryInput,
    ConsumptionInput,
    ObligationChargeInput,
    StockBatchInput,
    StockItemInput,
    WriteoffInput,
)
from engine.stock import compute_stock

MONTH = date(2026, 8, 1)
COVERED = date(2026, 8, 31)
NBSP = " "

CATEGORIES = [
    CategoryInput("Аренда", "fixed", norm_key="rent"),
    CategoryInput("Препараты", "variable", norm_key="drugs", direction="goods"),
    CategoryInput("Налоги", "tax"),
    CategoryInput("Кредит", "obligation"),
    CategoryInput("Оборудование", "capex"),
    CategoryInput("Вывод", "owner_draw"),
]
BENCHMARKS = [
    BenchmarkInput(
        "rent", "Аренда и коммуналка", "expense", Decimal("5.0"), Decimal("10.0"), "t", 1
    ),
    BenchmarkInput(
        "drugs", "Препараты и расходники", "expense", Decimal("20.0"), Decimal("25.0"), "t", 2
    ),
    BenchmarkInput(
        "net_profit", "Чистая прибыль", "profit", Decimal("12.0"), Decimal("20.0"), "t", 3
    ),
]


def sale(day: int, amount: int, kind: str = "service", status: str = "exec") -> SaleInput:
    return SaleInput(date(2026, 8, day), status, (SaleLineInput(kind, amount),))


def out(
    day: int, amount: int, category: str | None, status: str = "ok", kind: str = "out"
) -> TransactionInput:
    return TransactionInput("acc", date(2026, 8, day), -amount, status, "bank", kind, category)


def pnl(
    txs: list[TransactionInput],
    sales: list[SaleInput],
    charges: Sequence[ObligationChargeInput] = (),
    cards: Sequence[CardPayment] = (),
) -> PnlResult:
    return compute_pnl(
        CATEGORIES, txs, sales, list(cards), list(charges), MONTH, 190, COVERED, None, BENCHMARKS
    )


def norm(
    txs: list[TransactionInput],
    sales: list[SaleInput],
    categories: Sequence[CategoryInput] = CATEGORIES,
    benchmarks: Sequence[BenchmarkInput] = BENCHMARKS,
    writeoffs: Sequence[WriteoffInput] = (),
) -> NormResult:
    return compute_norm(
        categories, txs, sales, [], [], writeoffs, benchmarks, MONTH, 190, COVERED, None
    )


def amounts(result: PnlResult) -> dict[str, int]:
    return {r.key: int(r.amount.value) for r in result.rows}


# ------------------------------------------------------------------ P&L
def test_loss_month_is_a_loss_with_signed_shares_and_the_owner_text() -> None:
    result = pnl([out(5, 150_000, "Аренда")], [sale(3, 100_000)])
    rows = {r.key: r for r in result.rows}
    assert amounts(result)["net_profit"] == -50_000
    assert rows["net_profit"].label == "Чистый убыток"
    share = rows["net_profit"].share_pct
    assert share is not None and share.value == Decimal("-50.0")
    assert result.headline == f"В августе расходы были больше выручки на 500{NBSP}₽."


def test_month_without_revenue_has_amounts_but_no_shares() -> None:
    result = pnl([out(5, 63_200_000, "Аренда")], [])
    assert result.status == "partial" and result.partial_reasons[0] == "no_vetmanager"
    assert all(r.share_pct is None for r in result.rows)
    assert result.headline == f"В августе выручки нет, расходы 632{NBSP}000{NBSP}₽."


def test_only_costs_of_the_period_enter_the_lines() -> None:
    txs = [
        out(2, 1000, "Аренда"),
        out(3, 5000, "Кредит"),
        out(4, 7000, "Оборудование"),
        out(5, 9000, "Вывод"),
        out(6, 400, "Налоги"),
        out(7, 800, "Аренда", kind="transfer"),
        out(8, 300, "Аренда", status="duplicate"),
        out(9, 10, "Незнакомая статья"),
        out(10, 20, None, status="check"),
    ]
    result = pnl(txs, [sale(3, 10_000), sale(4, 99, status="save")])
    got = amounts(result)
    assert got["revenue"] == 10_000, "drafts are not revenue"
    assert got["fixed"] == 1000 + 10 + 20, (
        "an unknown article and an operation without one are fixed"
    )
    assert got["taxes"] == 400 and got["variable"] == 0
    assert result.unclassified.value == 20 and result.unclassified_count == 1
    assert got["net_profit"] == 10_000 - 1030 - 400 - got["obligations"]
    fixed = next(r for r in result.rows if r.key == "fixed")
    assert fixed.children is not None
    other = fixed.children[1].amount
    assert {i.label: i.value for i in other.breakdown} == {
        "Аренда": 1000,
        "Незнакомая статья": 10,
        "Без статьи": 20,
    }


def test_commission_is_rounded_per_day_not_per_month() -> None:
    # 1.9% of 1 rub = 1.9 kop -> 2 kop a day; ten days 20 kop, while 1.9% of the month (19 kop) would be 19
    cards = [CardPayment(date(2026, 8, d), 100) for d in range(1, 11)]
    result = pnl([], [sale(1, 1_000)], cards=cards)
    assert next(r for r in result.rows if r.key == "variable").amount.value == 20


def test_obligation_charges_are_the_whole_month_and_empty_means_a_warning() -> None:
    charges = [
        ObligationChargeInput("2026-08", "a", "Кредит: проценты", "loan_interest", 700),
        ObligationChargeInput("2026-07", "a", "Кредит: проценты", "loan_interest", 900),
    ]
    with_charges = pnl([], [sale(1, 5_000)], charges)
    assert amounts(with_charges)["obligations"] == 700
    assert [r.warning for r in with_charges.rows if r.key == "obligations"] == [None]
    none = pnl([], [sale(1, 5_000)])
    assert [r.warning for r in none.rows if r.key == "obligations"] == ["no_obligations"]
    assert none.partial_reasons == ("no_obligations",)


def test_running_month_cuts_at_as_of_and_says_taxes_are_only_the_paid_ones() -> None:
    running = compute_pnl(
        CATEGORIES,
        [out(20, 100, "Налоги")],
        [sale(3, 1_000), sale(25, 5_000)],
        [],
        [],
        MONTH,
        190,
        COVERED,
        date(2026, 8, 15),
    )
    assert running.period.status == "open" and running.period.to == date(2026, 8, 15)
    assert amounts(running)["revenue"] == 1_000 and amounts(running)["taxes"] == 0
    assert running.headline is not None
    assert running.headline.startswith("К 15 августа клиника заработала")
    assert "норм" not in running.headline
    taxes = next(r for r in running.rows if r.key == "taxes")
    assert "уже уплаченные к 15 августа" in taxes.amount.note


def test_direction_view_bridges_and_articles_without_direction_are_common() -> None:
    cats = [
        *CATEGORIES,
        CategoryInput("Лаборатории", "variable", direction="services"),
        CategoryInput("Прочее", "variable"),
    ]
    txs = [out(2, 300, "Препараты"), out(3, 200, "Лаборатории"), out(4, 50, "Прочее")]
    result = compute_direction_view(
        cats,
        txs,
        [sale(1, 1_000), sale(1, 600, "good")],
        [CardPayment(date(2026, 8, 1), 100_000)],
        [],
        MONTH,
        190,
        COVERED,
        None,
    )
    services, goods = result.directions or ()
    common = result.common_variable
    assert common is not None
    assert int(common.value) == 50 + 1_900  # the article without a direction + the commission
    direct = int(services.direct_costs.value) + int(goods.direct_costs.value)
    assert direct + int(common.value) == amounts(result)["variable"]
    margins = int(services.margin.value) + int(goods.margin.value)
    assert margins - int(common.value) == amounts(result)["marginal_profit"]
    revenue = int(services.revenue.value) + int(goods.revenue.value)
    assert revenue == amounts(result)["revenue"]


def test_direction_without_revenue_has_zero_shares_and_a_note() -> None:
    result = compute_direction_view(
        CATEGORIES, [], [sale(1, 1_000)], [], [], MONTH, 190, COVERED, None
    )
    _, goods = result.directions or ()
    assert goods.revenue.value == 0 and goods.margin_pct.value == 0 and goods.margin_pct.note


def test_last_closed_month() -> None:
    assert last_closed_month(date(2026, 9, 30)) == date(2026, 9, 1)
    assert last_closed_month(date(2026, 9, 29)) == date(2026, 8, 1)
    assert last_closed_month(date(2026, 1, 15)) == date(2025, 12, 1)
    assert last_closed_month(date(2026, 2, 28)) == date(2026, 2, 1)


# ------------------------------------------------------------------ norm
def rated(result: NormResult) -> dict[str, NormItem]:
    return {i.key: i for i in result.items if isinstance(i, NormItem)}


def test_norm_border_is_inclusive_and_one_kopeck_over_is_above() -> None:
    sales = [sale(1, 1_000_000)]
    at_border = rated(norm([out(2, 100_000, "Аренда")], sales))["rent"]
    over = rated(norm([out(2, 100_001, "Аренда")], sales))["rent"]
    under = rated(norm([out(2, 49_999, "Аренда")], sales))["rent"]
    assert (at_border.status, at_border.tone) == ("ok", "good")
    assert (over.status, over.tone) == ("above", "bad")
    assert (under.status, under.tone) == ("below", "warn")
    assert over.deviation_rub is not None and over.deviation_rub.value == 1
    assert under.deviation_rub is not None and under.deviation_rub.value == 49_999 - 50_000


def test_norm_deviation_in_points_comes_from_unrounded_values() -> None:
    rent = rated(norm([out(2, 101_450, "Аренда")], [sale(1, 1_000_000)]))["rent"]
    assert rent.actual_pct.value == Decimal("10.1")  # 10.145 shown with one decimal
    assert rent.deviation_pp is not None and rent.deviation_pp.value == Decimal("0.1")
    assert rent.deviation_rub is not None and rent.deviation_rub.value == 1_450


def test_norm_profit_is_good_above_the_border_and_bad_below() -> None:
    sales = [sale(1, 1_000_000)]
    good = rated(norm([], sales))["net_profit"]  # 100% of the revenue is above the upper border
    bad = rated(norm([out(2, 950_000, "Аренда")], sales))["net_profit"]
    assert (good.status, good.tone) == ("above", "good")
    assert (bad.status, bad.tone) == ("below", "bad")


def test_norm_everything_in_range_says_so() -> None:
    result = norm([out(2, 70_000, "Аренда"), out(3, 220_000, "Препараты")], [sale(1, 1_000_000)])
    assert result.headline is not None
    assert result.headline.startswith("Все статьи в пределах нормы.")


def test_norm_several_articles_above_are_counted_and_summed() -> None:
    result = norm([out(2, 200_000, "Аренда"), out(3, 300_000, "Препараты")], [sale(1, 1_000_000)])
    assert result.headline is not None
    assert result.headline.startswith("Две статьи выше нормы: аренда и коммуналка (+")
    # rent 200 000 - 100 000 = 100 000 kop over, drugs 300 000 - 250 000 = 50 000: together 1 500 rub
    assert f"Вместе это 1{NBSP}500{NBSP}₽." in result.headline


def test_norm_only_below_is_not_always_bad() -> None:
    result = norm([out(2, 10_000, "Аренда"), out(3, 220_000, "Препараты")], [sale(1, 1_000_000)])
    assert result.headline is not None
    assert result.headline.startswith("Ниже нормы одна статья: аренда и коммуналка (−")
    assert "Это не всегда плохо" in result.headline


def test_norm_without_a_benchmark_of_a_key_moves_the_articles_to_other() -> None:
    benchmarks = [b for b in BENCHMARKS if b.key != "drugs"]
    result = norm([out(3, 220_000, "Препараты")], [sale(1, 1_000_000)], benchmarks=benchmarks)
    assert [i.key for i in result.items] == ["rent", "other", "net_profit"]
    total = sum(
        sum(int(b.value) for b in i.actual_pct.breakdown) for i in result.items if not i.memo
    )
    assert total == 1_000_000, "groups + other + profit stay equal to the revenue"


def test_norm_partial_own_norm_beats_the_industry_one() -> None:
    cats = [CategoryInput("Аренда", "fixed", norm_key="rent", norm_min_pct=Decimal("12.0"))]
    result = norm([out(2, 100_000, "Аренда")], [sale(1, 1_000_000)], categories=cats)
    rent = rated(result)["rent"]
    assert rent.norm is not None and rent.norm.source == "clinic"
    assert rent.norm.min_pct == Decimal("12.0") and rent.norm.max_pct is None
    assert rent.status == "below"
    assert [b.label for b in rent.norm.breakdown] == ["Нижняя граница, 12,0%"]


def test_norm_writeoff_is_a_memo_row_and_counts_only_expired_in_the_month() -> None:
    writeoffs = [
        WriteoffInput(date(2026, 8, 3), "a", 1, 20_000, "expired"),
        WriteoffInput(date(2026, 8, 4), "b", 1, 5_000, "damaged"),
        WriteoffInput(date(2026, 7, 31), "c", 1, 9_000, "expired"),
    ]
    benchmarks = [
        *BENCHMARKS,
        BenchmarkInput(
            "writeoff", "Списание по сроку", "expense", Decimal("0.0"), Decimal("0.8"), "t", 0
        ),
    ]
    result = norm([], [sale(1, 1_000_000)], benchmarks=benchmarks, writeoffs=writeoffs)
    row = rated(result)["writeoff"]
    assert row.memo and sum(int(b.value) for b in row.actual_pct.breakdown) == 20_000
    assert row.status == "above"
    assert row.deviation_rub is not None and row.deviation_rub.value == 20_000 - 8_000
    assert [i.key for i in result.items][0] == "writeoff"


# ------------------------------------------------------------------ stock
AS_OF = date(2026, 9, 30)


def test_stock_idle_borders_and_the_empty_state() -> None:
    items = [
        StockItemInput("a", "a59", date(2026, 8, 2)),
        StockItemInput("b", "b60", date(2026, 8, 1)),
        StockItemInput("c", "c89", date(2026, 7, 3)),
        StockItemInput("d", "d90", date(2026, 7, 2)),
        StockItemInput("e", "e179", date(2026, 4, 4)),
        StockItemInput("f", "f180", date(2026, 4, 3)),
        StockItemInput("g", "g-unknown", None),
    ]
    batches = [StockBatchInput(i.id, 1, 100, None) for i in items]
    result = compute_stock(items, batches, [], [], AS_OF)
    assert [(i.item, i.bucket) for i in result.frozen_items] == [
        ("b60", "60_89"),
        ("c89", "60_89"),
        ("d90", "90_179"),
        ("e179", "90_179"),
        ("f180", "180_plus"),
    ]
    assert result.status == "ok" and result.headline is not None
    empty = compute_stock([], [], [], [], AS_OF)
    assert empty.status == "empty" and empty.headline is None and empty.turnover_days.value == 0


def test_stock_turnover_without_consumption_is_zero_with_an_explaining_note() -> None:
    items = [StockItemInput("a", "a", AS_OF)]
    batches = [StockBatchInput("a", 2, 500, None)]
    result = compute_stock(items, batches, [], [], AS_OF)
    assert result.turnover_days.value == 0
    assert "оборачиваемость не посчитать" in result.turnover_days.note
    spent = [ConsumptionInput(date(2026, 9, 1), 300), ConsumptionInput(date(2026, 7, 1), 99_999)]
    # the second row is outside the 90 days window ending on 30 September
    # stock 1 000 kop x 90 days / 300 kop spent = 300 days
    assert compute_stock(items, batches, [], spent, AS_OF).turnover_days.value == 300


def test_stock_write_off_norm_needs_the_revenue_and_the_benchmark() -> None:
    bench = [
        BenchmarkInput(
            "writeoff", "Списание по сроку", "expense", Decimal("0.0"), Decimal("0.8"), "t", 5
        )
    ]
    writeoffs = [WriteoffInput(date(2026, 9, 3), "a", 1, 20_000, "expired")]
    items = [StockItemInput("a", "a", AS_OF)]
    full = compute_stock(items, [], writeoffs, [], AS_OF, month_revenue=1_000_000, benchmarks=bench)
    assert full.written_off_norm.value == 8_000
    assert [d.label for d in full.written_off_norm.details] == ["Списано по сроку", "Сверх нормы"]
    no_revenue = compute_stock(items, [], writeoffs, [], AS_OF, benchmarks=bench)
    assert no_revenue.written_off_norm.value == 0
    no_bench = compute_stock(items, [], writeoffs, [], AS_OF, month_revenue=1_000_000)
    assert no_bench.written_off_norm.value == 0


def test_stock_month_of_the_write_offs_is_cut_at_as_of() -> None:
    writeoffs = [
        WriteoffInput(date(2026, 8, 20), "a", 1, 100, "expired"),
        WriteoffInput(date(2026, 9, 10), "a", 1, 200, "other"),
        WriteoffInput(date(2026, 9, 20), "a", 1, 400, "other"),
    ]
    items = [StockItemInput("a", "a", AS_OF)]
    default = compute_stock(items, [], writeoffs, [], date(2026, 9, 15))
    assert default.written_off_month.value == 200 and default.month == "2026-09"
    august = compute_stock(items, [], writeoffs, [], date(2026, 9, 15), month=date(2026, 8, 1))
    assert august.written_off_month.value == 100 and august.month == "2026-08"
