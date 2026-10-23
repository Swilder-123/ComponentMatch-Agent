"""Explicit, transactional DEMO dataset. Repeated seeding never refreshes old stock."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from componentmatch.core.clock import business_date, month_offset, utc
from componentmatch.core.identity import manufacturer_key, part_key
from componentmatch.db.repositories import DATASET_VERSION, SCHEMA_VERSION
from componentmatch.models import (
    Base,
    Component,
    DemoMetadata,
    Offer,
    PerformanceRecord,
    Supplier,
    SupplierCertification,
)

TABLE_MODELS = (Component, Supplier, Offer, SupplierCertification, PerformanceRecord, DemoMetadata)
EXPECTED_COUNTS = {
    "components": 6,
    "suppliers": 12,
    "offers": 18,
    "supplier_certifications": 11,
    "performance_records": 66,
    "demo_metadata": 1,
}


def dataset_counts(session: Session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in TABLE_MODELS
    }


def seed_demo(engine: Engine, *, test_business_time: datetime | None = None) -> dict:
    """Only tests pass test_business_time. CLI generation always uses actual time."""
    anchor = utc(test_business_time) if test_business_time is not None else datetime.now(UTC)
    existing_tables = inspect(engine).get_table_names()
    if existing_tables and set(existing_tables) != set(Base.metadata.tables):
        raise ValueError("Existing database schema differs; choose a new dedicated DEMO file")
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        info = session.get(DemoMetadata, 1)
        if info is not None:
            if info.schema_version != SCHEMA_VERSION or info.dataset_version != DATASET_VERSION:
                raise ValueError("Existing dataset version differs; no data overwritten")
            counts = dataset_counts(session)
            if counts != EXPECTED_COUNTS or not info.is_mock or "DEMO" not in info.description:
                raise ValueError("Existing dataset is incomplete or altered; no data overwritten")
            return {
                "data_label": "DEMO",
                "action": "unchanged",
                "counts": counts,
                "dataset_version": info.dataset_version,
                "snapshot_time": info.business_time.isoformat(),
            }
        if any(dataset_counts(session).values()):
            raise ValueError("Nonempty database without metadata; no data overwritten")
        common = {
            "is_mock": True,
            "source_label": f"DEMO:{DATASET_VERSION}",
            "created_at": anchor,
            "updated_at": anchor,
        }
        components = [
            (1, "Texas Instruments", "LM358DR", "SOIC-8", 100),
            (2, "Texas Instruments", "LM358P", "DIP-8", 100),
            (3, "Texas Instruments", "NE555DR", "SOIC-8", 200),
            (4, "DEMO Maker A", "DEMO-CROSS-01", "DEMO-PKG", 100),
            (5, "DEMO Maker B", "DEMO-CROSS-01", "DEMO-PKG", 100),
            (6, "STMicroelectronics", "STM32F103C8T6", "LQFP-48", 1000),
        ]
        for cid, maker, part, package, reference in components:
            session.add(
                Component(
                    id=cid,
                    manufacturer=maker,
                    manufacturer_key=manufacturer_key(maker),
                    part_number=part,
                    part_number_key=part_key(part),
                    category="IC",
                    package=package,
                    description="DEMO：型号标签仅用于精确查询，全部供货与绩效均为虚构",
                    reference_unit_price_cents=reference,
                    reference_currency="CNY",
                    reference_observed_at=anchor - timedelta(days=1),
                    **common,
                )
            )
        for sid in range(1, 13):
            session.add(
                Supplier(
                    id=sid,
                    name=f"DEMO 模拟供应商 {sid:02d}",
                    supplier_type="independent_distributor",
                    region="DEMO",
                    status="suspended" if sid == 12 else "active",
                    **common,
                )
            )
        session.flush()
        day = business_date(anchor)
        for sid in range(1, 13):
            if sid == 9:
                continue
            session.add(
                SupplierCertification(
                    id=sid,
                    supplier_id=sid,
                    certification_code="ISO9001",
                    certificate_number=f"MOCK-DEMO-ISO9001-{sid:02d}",
                    valid_from=day - timedelta(days=365),
                    expires_on=day + timedelta(days=-1 if sid == 8 else 365),
                    verification_status="unverified" if sid == 7 else "verified",
                    verified_at=None if sid == 7 else anchor - timedelta(days=20),
                    **common,
                )
            )
        for sid in range(1, 13):
            fields = dict(
                id=sid,
                supplier_id=sid,
                component_id=1,
                offer_code=f"DEMO-LM358-{sid}",
                unit_price_cents={1: 50, 2: 120, 3: 100}.get(sid, 80),
                currency="CNY",
                available_quantity=5000,
                min_order_quantity=100,
                order_multiple=100,
                lead_time_days={1: 6, 2: 3, 3: 2}.get(sid, 5),
                observed_at=anchor - timedelta(days=1),
                valid_until=anchor + timedelta(days=7),
                status="active",
            )
            if sid == 4:
                fields["available_quantity"] = 900
            elif sid == 5:
                fields["min_order_quantity"] = 2000
            elif sid == 6:
                fields["order_multiple"] = 300
            elif sid == 10:
                fields["observed_at"] = anchor - timedelta(days=10)
            elif sid == 11:
                fields["observed_at"] = anchor - timedelta(days=2)
                fields["valid_until"] = anchor - timedelta(days=1)
            session.add(Offer(**fields, **common))
        for oid, sid, cid, price, lead in (
            (13, 2, 1, 125, 4),  # Same supplier: independently eligible, never a second Top-3 slot.
            (14, 1, 2, 100, 4),
            (15, 2, 3, 200, 4),
            (16, 1, 4, 100, 4),
            (17, 2, 5, 100, 4),
            (18, 3, 6, 1000, 4),
        ):
            session.add(
                Offer(
                    id=oid,
                    supplier_id=sid,
                    component_id=cid,
                    offer_code=f"DEMO-EXTRA-{oid}",
                    unit_price_cents=price,
                    available_quantity=5000,
                    min_order_quantity=100,
                    order_multiple=100,
                    lead_time_days=lead,
                    observed_at=anchor - timedelta(days=1),
                    valid_until=anchor + timedelta(days=7),
                    currency="CNY",
                    status="active",
                    **common,
                )
            )
        month = day.replace(day=1)
        for sid in range(1, 12):
            for index in range(6):
                period = month_offset(month, index - 6)
                session.add(
                    PerformanceRecord(
                        id=(sid - 1) * 6 + index + 1,
                        supplier_id=sid,
                        component_id=1,
                        period_start=period,
                        period_end=month_offset(period, 1),
                        quality_evaluated_orders=10,
                        inspected_units=1000,
                        accepted_units={1: 960, 2: 1000, 3: 990}.get(sid, 980),
                        orders_due=100,
                        orders_on_time={1: 90, 2: 100, 3: 98}.get(sid, 95),
                        response_samples=10,
                        response_minutes_total={1: 2400, 2: 600, 3: 1200}.get(sid, 1800),
                        **common,
                    )
                )
        session.add(
            DemoMetadata(
                id=1,
                schema_version=SCHEMA_VERSION,
                dataset_version=DATASET_VERSION,
                is_mock=True,
                business_time=anchor,
                generated_at=datetime.now(UTC),
                description="DEMO：纯虚构数据，不代表云汉芯城或任何真实企业的库存、报价、资质或供应商评价",
            )
        )
        session.flush()
        counts = dataset_counts(session)
        if counts != EXPECTED_COUNTS:
            raise ValueError("DEMO seed count mismatch; transaction rolled back")
        return {
            "data_label": "DEMO",
            "action": "created",
            "counts": counts,
            "dataset_version": DATASET_VERSION,
            "snapshot_time": anchor.isoformat(),
        }
