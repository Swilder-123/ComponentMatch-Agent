"""The six agreed SQLite tables; amounts are integer CNY cents."""

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from componentmatch.models.base import Base, DemoProvenance, UTCDateTime


class Component(DemoProvenance, Base):
    __tablename__ = "components"
    __table_args__ = (
        UniqueConstraint("manufacturer_key", "part_number_key"),
        CheckConstraint("reference_unit_price_cents IS NULL OR reference_unit_price_cents > 0"),
        CheckConstraint("reference_currency = 'CNY'"),
        CheckConstraint("(reference_unit_price_cents IS NULL) = (reference_observed_at IS NULL)"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer: Mapped[str] = mapped_column(String)
    manufacturer_key: Mapped[str] = mapped_column(String)
    part_number: Mapped[str] = mapped_column(String)
    part_number_key: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)
    package: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    reference_unit_price_cents: Mapped[int | None]
    reference_currency: Mapped[str] = mapped_column(String, default="CNY")
    reference_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    offers: Mapped[list["Offer"]] = relationship(back_populates="component")
    performance_records: Mapped[list["PerformanceRecord"]] = relationship(
        back_populates="component"
    )


class Supplier(DemoProvenance, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')"),
        CheckConstraint(
            "supplier_type IN ('manufacturer', 'authorized_distributor', 'independent_distributor')"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    supplier_type: Mapped[str] = mapped_column(String, default="independent_distributor")
    region: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    offers: Mapped[list["Offer"]] = relationship(back_populates="supplier")
    certifications: Mapped[list["SupplierCertification"]] = relationship(back_populates="supplier")
    performance_records: Mapped[list["PerformanceRecord"]] = relationship(back_populates="supplier")


class SupplierCertification(DemoProvenance, Base):
    __tablename__ = "supplier_certifications"
    __table_args__ = (
        UniqueConstraint("supplier_id", "certification_code", "certificate_number"),
        Index("ix_cert_supplier_code", "supplier_id", "certification_code"),
        CheckConstraint("expires_on >= valid_from"),
        CheckConstraint("verification_status IN ('verified', 'unverified', 'revoked')"),
        CheckConstraint("verification_status != 'verified' OR verified_at IS NOT NULL"),
        CheckConstraint("certificate_number LIKE 'MOCK-%'"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
    certification_code: Mapped[str] = mapped_column(String)
    certificate_number: Mapped[str] = mapped_column(String)
    valid_from: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date] = mapped_column(Date)
    verification_status: Mapped[str] = mapped_column(String)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    supplier: Mapped[Supplier] = relationship(back_populates="certifications")


class Offer(DemoProvenance, Base):
    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("supplier_id", "offer_code"),
        Index("ix_offer_component_status", "component_id", "status"),
        Index("ix_offer_supplier_component", "supplier_id", "component_id"),
        CheckConstraint("unit_price_cents IS NULL OR unit_price_cents > 0"),
        CheckConstraint("currency = 'CNY'"),
        CheckConstraint("available_quantity IS NULL OR available_quantity >= 0"),
        CheckConstraint("min_order_quantity > 0 AND order_multiple > 0"),
        CheckConstraint("lead_time_days IS NULL OR lead_time_days >= 0"),
        CheckConstraint("valid_until >= observed_at"),
        CheckConstraint("status IN ('active', 'withdrawn')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="RESTRICT"))
    offer_code: Mapped[str] = mapped_column(String)
    unit_price_cents: Mapped[int | None]
    currency: Mapped[str] = mapped_column(String, default="CNY")
    available_quantity: Mapped[int | None]
    min_order_quantity: Mapped[int]
    order_multiple: Mapped[int]
    lead_time_days: Mapped[int | None]
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    valid_until: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String, default="active")
    supplier: Mapped[Supplier] = relationship(back_populates="offers")
    component: Mapped[Component] = relationship(back_populates="offers")


class PerformanceRecord(DemoProvenance, Base):
    __tablename__ = "performance_records"
    __table_args__ = (
        UniqueConstraint("supplier_id", "component_id", "period_start", "period_end"),
        CheckConstraint("period_end > period_start"),
        CheckConstraint(
            "strftime('%d', period_start) = '01' AND date(period_start, '+1 month') = period_end"
        ),
        CheckConstraint("quality_evaluated_orders >= 0 AND inspected_units >= 0"),
        CheckConstraint("accepted_units >= 0 AND accepted_units <= inspected_units"),
        CheckConstraint("quality_evaluated_orders > 0 OR inspected_units = 0"),
        CheckConstraint("inspected_units = 0 OR quality_evaluated_orders > 0"),
        CheckConstraint("orders_due >= 0 AND orders_on_time >= 0 AND orders_on_time <= orders_due"),
        CheckConstraint("response_minutes_total >= 0 AND response_samples >= 0"),
        CheckConstraint("response_samples > 0 OR response_minutes_total = 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="RESTRICT"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    quality_evaluated_orders: Mapped[int]
    inspected_units: Mapped[int]
    accepted_units: Mapped[int]
    orders_due: Mapped[int]
    orders_on_time: Mapped[int]
    response_minutes_total: Mapped[int]
    response_samples: Mapped[int]
    supplier: Mapped[Supplier] = relationship(back_populates="performance_records")
    component: Mapped[Component] = relationship(back_populates="performance_records")


class DemoMetadata(Base):
    __tablename__ = "demo_metadata"
    __table_args__ = (CheckConstraint("id = 1 AND is_mock = 1"),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    schema_version: Mapped[str] = mapped_column(String)
    dataset_version: Mapped[str] = mapped_column(String)
    is_mock: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=True)
    business_time: Mapped[datetime] = mapped_column(UTCDateTime())
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    description: Mapped[str] = mapped_column(String)
