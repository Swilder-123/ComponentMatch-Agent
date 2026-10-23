"""Immutable, detached data for pure constraints and scoring functions."""

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    id: int
    is_mock: bool
    source_label: str = Field(pattern=r"^DEMO:")
    updated_at: AwareDatetime


class ComponentData(Record):
    manufacturer: str
    manufacturer_key: str
    part_number: str
    part_number_key: str
    reference_unit_price_cents: int | None
    reference_currency: str
    reference_observed_at: AwareDatetime | None


class SupplierData(Record):
    name: str
    status: str


class OfferData(Record):
    supplier_id: int
    component_id: int
    unit_price_cents: int | None
    currency: str
    available_quantity: int | None
    min_order_quantity: int
    order_multiple: int
    lead_time_days: int | None
    observed_at: AwareDatetime
    valid_until: AwareDatetime
    status: str


class CertificationData(Record):
    supplier_id: int
    certification_code: str
    valid_from: date
    expires_on: date
    verification_status: str
    verified_at: AwareDatetime | None


class PerformanceData(Record):
    supplier_id: int
    component_id: int
    period_start: date
    period_end: date
    quality_evaluated_orders: int
    inspected_units: int
    accepted_units: int
    orders_due: int
    orders_on_time: int
    response_minutes_total: int
    response_samples: int


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    component: ComponentData
    supplier: SupplierData
    offer: OfferData
    certifications: tuple[CertificationData, ...]
    history: tuple[PerformanceData, ...]
