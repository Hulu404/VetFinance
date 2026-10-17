"""Boundary of `short_history`: history_days counts the day of as_of, the income profile needs 84 days before it."""

from datetime import date, timedelta

import pytest

from engine.calendar import PROFILE_DAYS, _short_history

AS_OF = date(2026, 10, 31)


@pytest.mark.parametrize(("history_days", "short"), [(83, True), (84, True), (85, False)])
def test_day_threshold(history_days: int, short: bool) -> None:
    # first day of a month three months back, so only the day count can make the history short
    first = date(2026, 7, 1)
    assert _short_history(first, history_days, AS_OF) is short


def test_threshold_matches_the_profile_window() -> None:
    first = AS_OF - timedelta(
        days=PROFILE_DAYS
    )  # the profile sees exactly 84 days: 84 days before as_of
    assert (AS_OF - first).days + 1 == PROFILE_DAYS + 1
    assert _short_history(date(2026, 7, 1), PROFILE_DAYS + 1, AS_OF) is False
