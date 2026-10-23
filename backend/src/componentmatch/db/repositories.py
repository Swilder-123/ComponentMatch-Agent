"""Exact catalog lookup; fetch all offers before any business exclusions."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from componentmatch.core.identity import manufacturer_key, part_key
from componentmatch.models import (
    Component,
    DemoMetadata,
    Offer,
    PerformanceRecord,
    SupplierCertification,
)
from componentmatch.schemas.snapshot import (
    Candidate,
    CertificationData,
    ComponentData,
    OfferData,
    PerformanceData,
    SupplierData,
)

SCHEMA_VERSION = "schema-v1"
DATASET_VERSION = "DEMO-v2"


class DataInvalidError(ValueError):
    pass


def metadata(session: Session) -> DemoMetadata:
    row = session.get(DemoMetadata, 1)
    if row is None or not row.is_mock or row.schema_version != SCHEMA_VERSION:
        raise DataInvalidError("DEMO metadata missing or schema version invalid; run seed script")
    if not row.dataset_version.startswith("DEMO-") or "DEMO" not in row.description:
        raise DataInvalidError("Dataset provenance must explicitly identify DEMO data")
    return row


def find_components(session: Session, part: str, manufacturer: str | None) -> list[ComponentData]:
    query = select(Component).where(Component.part_number_key == part_key(part))
    if manufacturer is not None:
        query = query.where(Component.manufacturer_key == manufacturer_key(manufacturer))
    result = [
        ComponentData.model_validate(row) for row in session.scalars(query.order_by(Component.id))
    ]
    for row in result:
        if (
            part_key(row.part_number) != row.part_number_key
            or manufacturer_key(row.manufacturer) != row.manufacturer_key
            or row.reference_currency != "CNY"
        ):
            raise DataInvalidError("Catalog identity or currency is inconsistent")
    return result


def candidates(session: Session, component: ComponentData) -> tuple[Candidate, ...]:
    offers = list(
        session.scalars(
            select(Offer)
            .where(Offer.component_id == component.id)
            .options(joinedload(Offer.supplier))
            .order_by(Offer.id)
        )
    )
    if not offers:
        return ()
    supplier_ids = {offer.supplier_id for offer in offers}
    certs = list(
        session.scalars(
            select(SupplierCertification)
            .where(SupplierCertification.supplier_id.in_(supplier_ids))
            .order_by(SupplierCertification.id)
        )
    )
    history = list(
        session.scalars(
            select(PerformanceRecord)
            .where(
                PerformanceRecord.supplier_id.in_(supplier_ids),
                PerformanceRecord.component_id == component.id,
            )
            .order_by(PerformanceRecord.id)
        )
    )
    result = tuple(
        Candidate(
            component=component,
            supplier=SupplierData.model_validate(offer.supplier),
            offer=OfferData.model_validate(offer),
            certifications=tuple(
                CertificationData.model_validate(c)
                for c in certs
                if c.supplier_id == offer.supplier_id
            ),
            history=tuple(
                PerformanceData.model_validate(h)
                for h in history
                if h.supplier_id == offer.supplier_id
            ),
        )
        for offer in offers
    )
    for candidate in result:
        records = (
            candidate.component,
            candidate.supplier,
            candidate.offer,
            *candidate.certifications,
            *candidate.history,
        )
        if any(not r.is_mock for r in records):
            raise DataInvalidError("Mixed DEMO and non-DEMO records are prohibited")
        if candidate.component.reference_currency != "CNY" or candidate.offer.currency != "CNY":
            raise DataInvalidError("Unsupported currency in DEMO catalog")
    return result
