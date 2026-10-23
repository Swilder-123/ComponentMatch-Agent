from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from componentmatch.core.clock import FixedClock
from componentmatch.models import (
    Component,
    DemoMetadata,
    Offer,
    PerformanceRecord,
    SupplierCertification,
)
from componentmatch.services.matching import MatchingService
from componentmatch_contracts.result import MatchResult
from sqlalchemy import delete
from sqlalchemy.orm import Session


def supplier_ids(result):
    return [r.supplier_id for r in result.recommendations]


def test_normal_request_returns_three_unique_suppliers(service, build_requirement):
    result = service.match(build_requirement())
    assert result.status == "success"
    assert supplier_ids(result) == [2, 3, 1]
    assert [r.total_score for r in result.recommendations] == [
        Decimal("83.500000"),
        Decimal("80.226950"),
        Decimal("60.680851"),
    ]
    assert [r.rank for r in result.recommendations] == [1, 2, 3]
    assert result.exclusion_summary.retrieved_offers == 13
    assert result.exclusion_summary.eligible_offers == 4
    assert result.exclusion_summary.eligible_suppliers == 3
    assert result.metadata.data_label == "DEMO"
    assert result.metadata.model_name is None
    assert result.metadata.explanation_mode == "none"
    assert MatchResult.model_validate_json(result.model_dump_json()) == result


def test_preference_changes_are_verifiable(service, build_requirement):
    cost = service.match(build_requirement(preference_profile="cost"))
    quality = service.match(build_requirement(preference_profile="quality"))
    assert supplier_ids(cost) == [1, 3, 2]
    assert supplier_ids(quality) == [2, 3, 1]
    assert cost.recommendations[0].unit_price_cents == 50
    q = next(d for d in quality.recommendations[0].dimensions if d.metric == "quality")
    assert q.score == 100
    assert cost.metadata.weights != quality.metadata.weights


def test_strict_budget_returns_no_match_with_real_reasons(service, build_requirement):
    result = service.match(build_requirement(max_unit_price_cents=1))
    assert result.status == "no_match" and result.recommendations == ()
    assert result.exclusion_summary.reason_counts["UNIT_PRICE_OVER_LIMIT"] == 13
    assert len(result.rejected_offers) == 13
    assert "INSUFFICIENT_STOCK" in result.exclusion_summary.reason_counts


def test_unit_limit_and_total_budget_checked_independently(service, build_requirement):
    result = service.match(build_requirement(max_unit_price_cents=120, total_budget_cents=50_000))
    assert supplier_ids(result) == [1]
    rejected = next(r for r in result.rejected_offers if r.offer_id == 2)
    assert {r.code for r in rejected.reasons} == {"TOTAL_BUDGET_EXCEEDED"}
    assert result.recommendations[0].goods_total_cents == 50_000
    unit = service.match(build_requirement(max_unit_price_cents=50))
    assert supplier_ids(unit) == [1]


def test_seeded_exclusions_are_distinguishable(service, build_requirement):
    result = service.match(build_requirement())
    codes = {r.offer_id: {reason.code for reason in r.reasons} for r in result.rejected_offers}
    assert codes[4] == {"INSUFFICIENT_STOCK"}
    assert codes[5] == {"MOQ_NOT_MET"}
    assert codes[6] == {"ORDER_MULTIPLE_MISMATCH"}
    assert "CERT_UNVERIFIED" in codes[7] and "CERT_EXPIRED" not in codes[7]
    assert codes[8] == {"CERT_EXPIRED"}
    assert codes[9] == {"CERT_MISSING"}
    assert codes[10] == {"OFFER_STALE"}
    assert codes[11] == {"OFFER_EXPIRED"}
    assert codes[12] == {"SUPPLIER_INACTIVE"}


@pytest.mark.parametrize(
    "part,maker", [("LM358", "TI"), ("LM358DRX", "TI"), ("LM358DR", "Unknown Maker")]
)
def test_never_recommends_similar_or_wrong_manufacturer(service, build_requirement, part, maker):
    result = service.match(build_requirement(part_number=part, manufacturer=maker))
    assert result.status == "no_match"
    assert result.exclusion_summary.retrieved_offers == 0
    assert "CATALOG_NOT_FOUND" in result.warnings[-1]


def test_suffix_changes_catalog_identity_without_substitution(service, build_requirement):
    result = service.match(build_requirement(part_number="LM358P"))
    assert result.status == "success"
    assert len(result.recommendations) == 1
    assert result.recommendations[0].component_id == 2
    assert "HISTORY_MISSING" in {r.code for r in result.recommendations[0].risks}


def test_catalog_alias_normalization_and_ambiguity(service, build_requirement):
    assert supplier_ids(service.match(build_requirement(part_number=" lm358dr "))) == [2, 3, 1]
    result = service.match(build_requirement(part_number="DEMO-CROSS-01", manufacturer=None))
    assert result.status == "needs_clarification" and not result.recommendations
    resolved = service.match(
        build_requirement(part_number="DEMO-CROSS-01", manufacturer="DEMO Maker A")
    )
    assert supplier_ids(resolved) == [1]


def test_missing_delivery_is_clarification_without_guessing(service, build_requirement):
    result = service.match(build_requirement(delivery_mode="unspecified", max_delivery_days=None))
    assert result.status == "needs_clarification" and result.clarification_questions


def test_same_supplier_multiple_quotes_do_not_fill_multiple_slots(service, build_requirement):
    result = service.match(build_requirement())
    assert len(supplier_ids(result)) == len(set(supplier_ids(result))) == 3
    assert next(r.offer_id for r in result.recommendations if r.supplier_id == 2) == 2


def test_total_score_tie_break_is_stable_by_supplier_then_offer_id(
    engine, service, build_requirement
):
    with Session(engine) as session, session.begin():
        for sid in (1, 3):
            row = session.get(Offer, sid)
            row.unit_price_cents = 120
            row.lead_time_days = 3
            for history in row.supplier.performance_records:
                history.accepted_units = 1000
                history.orders_on_time = 100
                history.response_minutes_total = 600
        extra = session.get(Offer, 13)
        extra.unit_price_cents = 120
        extra.lead_time_days = 3
    first = service.match(build_requirement())
    second = service.match(build_requirement())
    assert supplier_ids(first) == supplier_ids(second) == [1, 2, 3]
    assert {r.total_score for r in first.recommendations} == {Decimal("83.500000")}
    assert next(r.offer_id for r in first.recommendations if r.supplier_id == 2) == 2
    assert first.recommendations == second.recommendations


def test_removing_irrelevant_bad_candidate_does_not_change_scores(
    engine, service, build_requirement
):
    before = service.match(build_requirement())
    with Session(engine) as session, session.begin():
        session.execute(delete(Offer).where(Offer.id == 4))
    after = service.match(build_requirement())
    assert before.recommendations == after.recommendations


def test_missing_history_remains_eligible_but_loses_history_scores(
    engine, service, build_requirement
):
    with Session(engine) as session, session.begin():
        session.execute(delete(PerformanceRecord).where(PerformanceRecord.supplier_id == 2))
    result = service.match(build_requirement())
    row = next(r for r in result.recommendations if r.supplier_id == 2)
    assert "HISTORY_MISSING" in {risk.code for risk in row.risks}
    assert row.total_score == Decimal("28.500000")


def test_actual_business_clock_never_uses_metadata_fixed_date(engine, build_requirement):
    with Session(engine) as session, session.begin():
        session.get(DemoMetadata, 1).business_time = datetime(2000, 1, 1, tzinfo=UTC)
    before = datetime.now(UTC)
    result = MatchingService(engine).match(build_requirement())
    after = datetime.now(UTC)
    assert result.metadata.clock_mode == "business"
    assert before <= result.metadata.business_time <= after
    assert result.metadata.dataset_snapshot_time.year == 2000


def test_fixed_clock_is_explicit_and_china_business_date(engine, build_requirement):
    with pytest.raises(ValueError):
        MatchingService(engine, clock=FixedClock(datetime.now(UTC)))
    with pytest.raises(ValueError):
        MatchingService(engine, mode="test")
    next_day = datetime(2026, 10, 21, 16, tzinfo=UTC)
    result = MatchingService(engine, mode="test", clock=FixedClock(next_day)).match(
        build_requirement()
    )
    assert str(result.metadata.business_date) == "2026-10-22"


def test_missing_metadata_is_error_not_no_match(engine, service, build_requirement):
    with Session(engine) as session, session.begin():
        session.execute(delete(DemoMetadata))
    result = service.match(build_requirement())
    assert result.status == "error" and result.error.code == "DATA_INVALID"
    assert not result.recommendations


def test_catalog_with_no_offers_is_distinct_from_missing_part(engine, service, build_requirement):
    with Session(engine) as session, session.begin():
        session.execute(delete(Offer).where(Offer.component_id == 6))
    result = service.match(
        build_requirement(part_number="STM32F103C8T6", manufacturer="STMicroelectronics")
    )
    assert result.status == "no_match" and "NO_OFFERS" in result.warnings[-1]


def test_missing_offer_fields_fail_closed(engine, service, build_requirement):
    with Session(engine) as session, session.begin():
        session.get(Offer, 1).available_quantity = None
    result = service.match(build_requirement())
    assert supplier_ids(result) == [2, 3]
    assert {r.code for r in next(o for o in result.rejected_offers if o.offer_id == 1).reasons} == {
        "OFFER_DATA_MISSING"
    }


def test_reference_change_only_changes_price_dimension(engine, service, build_requirement):
    with Session(engine) as session, session.begin():
        component = session.get(Component, 1)
        component.reference_unit_price_cents = None
        component.reference_observed_at = None
    result = service.match(build_requirement())
    assert all(
        next(d.score for d in r.dimensions if d.metric == "price") == 0
        for r in result.recommendations
    )


def test_repeated_certificate_reason_counts_once_per_offer(engine, service, build_requirement, now):
    from componentmatch.core.clock import business_date

    with Session(engine) as session, session.begin():
        session.add(
            SupplierCertification(
                id=99,
                supplier_id=7,
                certification_code="ISO9001",
                certificate_number="MOCK-DEMO-99",
                valid_from=business_date(now) - timedelta(days=1),
                expires_on=business_date(now) + timedelta(days=1),
                verification_status="unverified",
                verified_at=None,
                source_label="DEMO:test",
                created_at=now,
                updated_at=now,
            )
        )
    result = service.match(build_requirement())
    bad = next(r for r in result.rejected_offers if r.offer_id == 7)
    assert len([reason for reason in bad.reasons if reason.code == "CERT_UNVERIFIED"]) == 2
    assert result.exclusion_summary.reason_counts["CERT_UNVERIFIED"] == 1


def test_corrupt_normalized_identity_is_data_error(engine, service, build_requirement):
    with Session(engine) as session, session.begin():
        session.get(Component, 1).part_number = "LM358P"
    result = service.match(build_requirement())
    assert result.status == "error" and result.error.code == "DATA_INVALID"
