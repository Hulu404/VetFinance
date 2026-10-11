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
