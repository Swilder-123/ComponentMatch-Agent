"""SQLite-compatible UTC type and DEMO provenance shared by business tables."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from componentmatch.core.clock import utc


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else utc(value).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class DemoProvenance:
    is_mock: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True), CheckConstraint("is_mock = 1"), default=True
    )
    source_label: Mapped[str] = mapped_column(
        String, CheckConstraint("source_label LIKE 'DEMO:%'"), default="DEMO:seed-v2"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
