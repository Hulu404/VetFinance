from decimal import Decimal

import pytest

from engine.money import div_round, pct_one_decimal, rub_to_kopecks


@pytest.mark.parametrize(
    ("n", "d", "expected"),
    [(1, 2, 1), (-1, 2, -1), (1, 3, 0), (2, 3, 1), (-2, 3, -1), (5, -2, -3), (0, 7, 0), (7, 7, 1)],
)
def test_div_round_half_away_from_zero(n: int, d: int, expected: int) -> None:
    assert div_round(n, d) == expected


def test_div_round_zero_denominator() -> None:
    with pytest.raises(ZeroDivisionError):
        div_round(1, 0)


def test_rub_to_kopecks() -> None:
    assert rub_to_kopecks("1234.56") == 123456
    assert rub_to_kopecks("0.005") == 1
    assert rub_to_kopecks(10) == 1000


def test_pct_one_decimal() -> None:
    assert pct_one_decimal(15, 100) == Decimal("15.0")
    assert pct_one_decimal(1, 3) == Decimal("33.3")
    assert pct_one_decimal(2, 3) == Decimal("66.7")
    with pytest.raises(ZeroDivisionError):
        pct_one_decimal(1, 0)


def test_pct_to_tenths_is_exact_for_norms_with_one_decimal() -> None:
    from engine.money import pct_to_tenths

    assert pct_to_tenths(Decimal("22.0")) == 220
    assert pct_to_tenths(Decimal("0.8")) == 8
    assert pct_to_tenths(Decimal("0.75")) == 8  # half up


def test_bound_amount_is_not_rounded_to_hundreds() -> None:
    from engine.money import bound_amount

    assert bound_amount(124_000_000, 8) == 992_000  # 0.8% of 1 240 000 rub = 9 920 rub
    assert bound_amount(10, 5) == 0  # 0.05 kopeck
    assert bound_amount(30, 5) == 0  # 0.15 kopeck rounds to 0


def test_deviation_pp_uses_unrounded_values() -> None:
    from engine.money import deviation_pp

    # 11 141 040 of 109 815 610 against the bound 10.0%: 10.145...% - 10% = 0.1 pp
    assert deviation_pp(11_141_040, 100, 109_815_610) == Decimal("0.1")
    # below the bound: 12 854 493 against 12.0% -> -0.3 pp
    assert deviation_pp(12_854_493, 120, 109_815_610) == Decimal("-0.3")
    assert deviation_pp(0, 0, 1000) == Decimal("0.0")


def test_turnover_rounds_to_the_nearest_day_half_up() -> None:
    from engine.money import turnover_days

    assert turnover_days(740_000, 900_000) == 74  # 74.0
    assert turnover_days(1, 2, window=1) == 1  # 0.5 -> 1
    assert turnover_days(1, 3, window=1) == 0
    with pytest.raises(ZeroDivisionError):
        turnover_days(1, 0)
