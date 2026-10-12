"""When connected data counts as stale. The client never computes a threshold, it only shows the flag."""

from datetime import date, datetime, timedelta

VETMANAGER_STALE_AFTER = timedelta(hours=36)  # a nightly sync may miss one night
BANK_STALE_AFTER_DAYS = 7  # statements are uploaded by hand


def vetmanager_is_stale(connected: bool, last_success_at: datetime | None, now: datetime) -> bool:
    """Connected, has loaded before, and the last success is older than the threshold."""
    if not connected or last_success_at is None:
        return False
    return now - last_success_at > VETMANAGER_STALE_AFTER


def bank_is_stale(last_statement_to: date | None, today: date) -> bool:
    """A statement was loaded before and it ends more than a week ago."""
    if last_statement_to is None:
        return False
    return (today - last_statement_to).days > BANK_STALE_AFTER_DAYS
