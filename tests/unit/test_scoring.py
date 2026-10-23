from datetime import timedelta
from decimal import Decimal, localcontext

import pytest

from componentmatch.core.clock import business_date, month_offset
from componentmatch.scoring.engine import score_candidate
from componentmatch.scoring.weights import weights_for


def dimensions(result):
    return {d.metric: d for d in result.dimensions}


def risks(result):
    return {r.code for r in result.risks}


def score(candidate, req, now):
    return score_candidate(candidate, req, now, weights_for(req.preference_profile))


def test_independent_hand_calculation(candidate, build_requirement, now):
    # P=50,D=80,Q=80,O=80,R=100; 10+20+24+16+5=75 with new default weights.
    offer = candidate.offer.model_copy(update={"unit_price_cents": 100, "lead_time_days": 6})
    history = tuple(
        h.model_copy(
            update={"accepted_units": 990, "orders_on_time": 96, "response_minutes_total": 600}
        )
        for h in candidate.history
    )
    result = score(
        candidate.model_copy(update={"offer": offer, "history": history}), build_requirement(), now
    )
    assert {m: d.score for m, d in dimensions(result).items()} == {
        "price": 50,
        "delivery": 80,
        "quality": 80,
        "on_time": 80,
        "response": 100,
    }
    assert result.total_score == Decimal("75.000000")


def test_no_history_is_not_perfect_and_weights_are_not_redistributed(
    candidate, build_requirement, now
):
    result = score(candidate.model_copy(update={"history": ()}), build_requirement(), now)
    ds = dimensions(result)
    assert all(
        ds[m].score == 0 and ds[m].raw_value is None for m in ("quality", "on_time", "response")
    )
    assert result.total_score == Decimal("28.500000")  # 0.2*30 + 0.25*90
    assert "HISTORY_MISSING" in risks(result)


def test_small_sample_caps_all_history_dimensions(candidate, build_requirement, now):
    row = candidate.history[-1].model_copy(
        update={
            "quality_evaluated_orders": 1,
            "inspected_units": 100,
            "accepted_units": 100,
            "orders_due": 1,
            "orders_on_time": 1,
            "response_samples": 1,
            "response_minutes_total": 60,
        }
    )
    result = score(candidate.model_copy(update={"history": (row,)}), build_requirement(), now)
    assert all(dimensions(result)[m].score == 50 for m in ("quality", "on_time", "response"))
    assert {"QUALITY_SAMPLE_SMALL", "DELIVERY_SAMPLE_SMALL", "RESPONSE_SAMPLE_SMALL"} <= risks(
        result
    )


def test_ratios_are_weighted_by_real_denominators(candidate, build_requirement, now):
    rows = tuple(
        h.model_copy(update={"inspected_units": n, "accepted_units": a})
        for h, n, a in zip(candidate.history[-2:], (500, 1500), (490, 1500), strict=True)
    )
    result = score(candidate.model_copy(update={"history": rows}), build_requirement(), now)
    assert dimensions(result)["quality"].raw_value == Decimal("0.995")
    assert dimensions(result)["quality"].score == 90


def test_stale_history_does_not_score_as_current(candidate, build_requirement, now):
    start = month_offset(business_date(now).replace(day=1), -4)
    row = candidate.history[0].model_copy(
        update={"period_start": start, "period_end": month_offset(start, 1)}
    )
    result = score(candidate.model_copy(update={"history": (row,)}), build_requirement(), now)
    assert "HISTORY_STALE" in risks(result)
    assert dimensions(result)["quality"].score == 0


def test_invalid_history_row_ignored_and_reported(candidate, build_requirement, now):
    bad = candidate.history[-1].model_copy(update={"accepted_units": 999999})
    result = score(
        candidate.model_copy(update={"history": (*candidate.history[:-1], bad)}),
        build_requirement(),
        now,
    )
    assert "HISTORY_ROW_INVALID" in risks(result)
    assert len([e for e in result.evidence if e.table == "performance_records"]) == 5
    assert dimensions(result)["quality"].score == 100


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_old_reference_gets_zero_price_score(candidate, build_requirement, now, missing):
    component = candidate.component.model_copy(
        update={
            "reference_unit_price_cents": None if missing else 100,
            "reference_observed_at": None if missing else now - timedelta(days=31),
        }
    )
    result = score(candidate.model_copy(update={"component": component}), build_requirement(), now)
    assert dimensions(result)["price"].score == 0
    assert "PRICE_REFERENCE_UNAVAILABLE" in risks(result)


def test_price_and_delivery_improvements_are_monotone(candidate, build_requirement, now):
    baseline = score(candidate, build_requirement(), now)
    for values in ({"unit_price_cents": 110}, {"lead_time_days": 2}):
        improved = candidate.model_copy(update={"offer": candidate.offer.model_copy(update=values)})
        assert score(improved, build_requirement(), now).total_score >= baseline.total_score


def test_decimal_context_does_not_change_result(candidate, build_requirement, now):
    first = score(candidate, build_requirement(), now)
    with localcontext() as context:
        context.prec = 12
        second = score(candidate, build_requirement(), now)
    assert second == first


def test_evidence_references_and_contribution_total(candidate, build_requirement, now):
    result = score(candidate, build_requirement(), now)
    assert sum(d.contribution for d in result.dimensions) == result.total_score
    ids = {e.evidence_id for e in result.evidence}
    assert {r for d in result.dimensions for r in d.evidence_ids} <= ids
    assert all(
        e.data_label == "DEMO" and e.source_label.startswith("DEMO:") for e in result.evidence
    )
