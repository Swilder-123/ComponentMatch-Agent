from datetime import timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from componentmatch.db.seed import EXPECTED_COUNTS, dataset_counts, seed_demo
from componentmatch.models import DemoMetadata, Offer


def test_exactly_six_tables_counts_and_foreign_keys(engine):
    assert set(inspect(engine).get_table_names()) == set(EXPECTED_COUNTS)
    with Session(engine) as session:
        assert dataset_counts(session) == EXPECTED_COUNTS
        assert session.scalar(text("PRAGMA foreign_keys")) == 1


def test_seed_repeats_without_duplicates_or_refresh(engine, now):
    result = seed_demo(engine, test_business_time=now + timedelta(days=3))
    assert result["action"] == "unchanged" and result["counts"] == EXPECTED_COUNTS
    with Session(engine) as session:
        assert session.get(DemoMetadata, 1).business_time == now
        assert session.get(Offer, 1).observed_at == now - timedelta(days=1)


def test_seed_rejects_version_mismatch_without_overwrite(engine):
    with Session(engine) as session, session.begin():
        session.get(DemoMetadata, 1).dataset_version = "DEMO-another-version"
    with pytest.raises(ValueError, match="version differs"):
        seed_demo(engine)
    with Session(engine) as session:
        assert session.get(DemoMetadata, 1).dataset_version == "DEMO-another-version"


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE offers SET available_quantity=-1 WHERE id=1",
        "UPDATE offers SET supplier_id=9999 WHERE id=1",
        "UPDATE offers SET is_mock=0 WHERE id=1",
        "UPDATE offers SET source_label='real-data' WHERE id=1",
        "UPDATE offers SET currency='USD' WHERE id=1",
        "UPDATE offers SET offer_code=(SELECT offer_code FROM offers WHERE id=2) WHERE id=13",
        "UPDATE performance_records SET accepted_units=inspected_units+1 WHERE id=1",
        "UPDATE performance_records SET period_start='2026-04-02' WHERE id=1",
        "UPDATE supplier_certifications SET verified_at=NULL WHERE id=1",
        "DELETE FROM suppliers WHERE id=1",
    ],
)
def test_database_constraints_enforced(engine, sql):
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(sql))
        connection.commit()


def test_utc_round_trip_and_naive_timestamp_rejected(engine, now):
    with Session(engine) as session:
        assert session.get(Offer, 1).observed_at.tzinfo is not None
    with Session(engine) as session, pytest.raises(StatementError):
        session.get(Offer, 1).observed_at = now.replace(tzinfo=None)
        session.flush()
