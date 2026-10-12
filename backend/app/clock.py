"""The current moment, as a dependency so tests can fix it."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def get_now() -> datetime:
    return datetime.now(UTC)


def clinic_today(now: datetime, timezone: str) -> date:
    """ "Today" in the clinic's time zone."""
    return now.astimezone(ZoneInfo(timezone)).date()
