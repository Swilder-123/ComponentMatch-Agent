"""Actual business time by default; injected fixed clocks are reserved for tests."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

BUSINESS_ZONE = ZoneInfo("Asia/Shanghai")


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(UTC)


def business_date(value: datetime) -> date:
    return utc(value).astimezone(BUSINESS_ZONE).date()


def month_offset(start: date, offset: int) -> date:
    index = start.year * 12 + start.month - 1 + offset
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


@dataclass(frozen=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return utc(self.value)
