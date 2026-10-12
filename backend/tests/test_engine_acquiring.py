from datetime import date

from engine.acquiring import (
    MATCHED,
    MISMATCH,
    NO_STATEMENT,
    WAITING,
    AcquiringParams,
    BankCredit,
    CardPayment,
    add_business_days,
    business_days_between,
    reconcile_acquiring,
)
from engine.acquiring_report import build_report, rate_text

PARAMS = AcquiringParams()
TODAY = date(2026, 9, 30)


def card(day: int, amount: int) -> CardPayment:
    return CardPayment(date(2026, 9, day), amount)


def credit(i: str, day: int, amount: int) -> BankCredit:
    return BankCredit(i, date(2026, 9, day), amount)


def run(cards: list[CardPayment], credits: list[BankCredit], as_of: date = TODAY):  # type: ignore[no-untyped-def]
    return reconcile_acquiring(cards, credits, PARAMS, as_of=as_of, bank_covered_to=as_of)


def test_business_day_helpers_skip_weekends() -> None:
    friday = date(2026, 9, 4)
    assert add_business_days(friday, 1) == date(2026, 9, 7)
    assert add_business_days(friday, 3) == date(2026, 9, 9)
    assert business_days_between(friday, date(2026, 9, 7)) == 1
    assert business_days_between(date(2026, 9, 7), date(2026, 9, 7)) == 0


def test_commission_is_rounded_half_up_per_day() -> None:
    result = run([card(2, 10_050)], [credit("c", 3, 9_859)])  # 10050 * 1.9% = 190.95 -> 191
    assert result[0].expected_commission == 191 and result[0].expected_credit == 9_859
    assert result[0].status == MATCHED and result[0].diff == 0


def test_tolerance_is_inclusive_and_overpayment_is_a_mismatch_too() -> None:
    base = 100_000 - 1_900
    assert run([card(2, 100_000)], [credit("c", 3, base + 100)])[0].status == MATCHED
    over = run([card(2, 100_000)], [credit("c", 3, base + 101)])[0]
    assert over.status == MISMATCH and over.diff == 101


def test_credit_far_from_expected_is_not_taken_as_underpayment() -> None:
    result = run([card(2, 100_000)], [credit("c", 3, 50_000)], as_of=date(2026, 9, 30))
    assert (
        result[0].status == MISMATCH and result[0].credit_id is None and result[0].diff == -98_100
    )


def test_one_credit_closes_a_group_only_of_adjacent_days() -> None:
    cards = [card(3, 100_000), card(4, 100_000), card(7, 100_000)]  # Thu, Fri, Mon
    group = run(cards, [credit("c", 7, 2 * 98_100)])
    assert [r.group_days for r in group[:2]] == [(date(2026, 9, 3), date(2026, 9, 4))] * 2
    assert group[2].status in (WAITING, NO_STATEMENT, MISMATCH) and group[2].credit_id is None
    # Friday and Monday are not neighbours: one credit for both is not accepted
    apart = run([card(4, 100_000), card(7, 100_000)], [credit("c", 8, 2 * 98_100)])
    assert apart[0].credit_id is None


def test_a_credit_is_used_once() -> None:
    cards = [card(1, 100_000), card(2, 100_000)]
    result = run(cards, [credit("c", 3, 98_100)])
    assert [r.credit_id for r in result] == ["c", None]


def test_deadline_is_counted_in_business_days() -> None:
    result = run([card(4, 100_000)], [], as_of=date(2026, 9, 9))  # Friday + 3 business days = Wed
    assert result[0].status == WAITING and result[0].expected_by == date(2026, 9, 9)
    after = reconcile_acquiring(
        [card(4, 100_000)], [], PARAMS, as_of=date(2026, 9, 10), bank_covered_to=date(2026, 9, 9)
    )
    assert after[0].status == MISMATCH and after[0].credit_amount == 0
    unknown = reconcile_acquiring(
        [card(4, 100_000)], [], PARAMS, as_of=date(2026, 9, 10), bank_covered_to=None
    )
    assert unknown[0].status == NO_STATEMENT and unknown[0].diff is None


def test_refunds_and_empty_days_are_ignored() -> None:
    assert run([card(2, 0), card(3, -500)], []) == []
    assert run([], [credit("c", 3, 100)]) == []


def test_report_groups_days_and_sums_to_the_totals() -> None:
    cards = [
        card(4, 1_350_000),
        card(5, 550_000),
        card(6, 300_000),
        card(14, 1_800_000),
        card(30, 900_000),
    ]
    credits = [credit("g", 7, 2_158_200), credit("m", 15, 1_755_000)]
    results = run(cards, credits)
    report = build_report(results, "2026-09", 190, {})
    assert [(r.date_from.day, r.date_to.day, r.status) for r in report.rows] == [
        (30, 30, WAITING),
        (14, 14, MISMATCH),
        (4, 6, MATCHED),
    ]
    group = report.rows[2]
    assert [m.day.day for m in group.members] == [4, 5, 6]
    assert group.card_payments.value == 2_200_000
    assert group.card_payments.value - group.commission.value == group.expected.value
    assert group.credited is not None and group.credited.value == 2_158_200
    summary = report.summary
    assert summary.card_payments.value == sum(r.card_payments.value for r in report.rows)
    assert summary.waiting.value == 882_900
    assert summary.discrepancy.value == -10_800
    for figure in (
        summary.card_payments,
        summary.commission,
        summary.credited,
        summary.discrepancy,
    ):
        assert sum(i.value for i in figure.breakdown) == figure.value
    assert build_report(results, "2026-10", 190, {}).rows == ()
    empty = build_report([], "2026-09", 190, {})
    assert empty.summary.card_payments.value == 0 and empty.summary.card_payments.breakdown


def test_rate_text() -> None:
    assert rate_text(190) == "1,9%" and rate_text(200) == "2%" and rate_text(225) == "2,25%"
