from decimal import Decimal

import pytest
from pydantic import ValidationError

from componentmatch.scoring.weights import METRICS, PROFILES, validate_weights, weights_for
from componentmatch_contracts.requirement import MatchRequest, ProcurementRequirement


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", 0),
        ("quantity", -1),
        ("quantity", True),
        ("quantity", "1000"),
        ("quantity", 1.5),
        ("part_number", " "),
        ("manufacturer", " "),
        ("max_unit_price_cents", -1),
        ("max_unit_price_cents", 0.5),
        ("total_budget_cents", True),
        ("total_budget_cents", float("nan")),
        ("total_budget_cents", float("inf")),
        ("currency", "USD"),
        ("required_certifications", ["UNKNOWN"]),
        ("preference_profile", "model_decides"),
        ("budget_scope", "unit"),
        ("allow_substitutes", True),
    ],
)
def test_invalid_or_unsupported_input(build_requirement, field, value):
    with pytest.raises(ValidationError):
        build_requirement(**{field: value})


@pytest.mark.parametrize(
    "mode,days", [("within_days", None), ("unconstrained", 7), ("unspecified", 7)]
)
def test_delivery_cross_field_validation(build_requirement, mode, days):
    with pytest.raises(ValidationError):
        build_requirement(delivery_mode=mode, max_delivery_days=days)


def test_both_budget_limits_have_distinct_units_and_can_coexist(build_requirement):
    requirement = build_requirement(max_unit_price_cents=100, total_budget_cents=90_000)
    assert requirement.max_unit_price_cents == 100
    assert requirement.total_budget_cents == 90_000
    assert ProcurementRequirement.model_validate_json(requirement.model_dump_json()) == requirement


def test_no_natural_language_or_undeclared_hard_constraints(build_requirement):
    with pytest.raises(ValidationError):
        MatchRequest(input_mode="natural_language", requirement=build_requirement())
    with pytest.raises(ValidationError):
        build_requirement(required_authorization=True)
    with pytest.raises(ValidationError):
        build_requirement(required_certifications=("ISO9001", "ISO9001"))


def test_default_weights_match_phase_two_decision():
    assert weights_for("balanced") == dict(
        zip(METRICS, map(Decimal, ("0.20", "0.25", "0.30", "0.20", "0.05")), strict=True)
    )
    for profile in PROFILES:
        assert sum(weights_for(profile).values()) == 1


@pytest.mark.parametrize(
    "bad",
    [
        {},
        dict.fromkeys(METRICS, Decimal("0.1")),
        dict.fromkeys(METRICS, Decimal("NaN")),
        dict.fromkeys(METRICS, Decimal("Infinity")),
        dict.fromkeys(METRICS, Decimal("-0.2")),
        dict.fromkeys(METRICS, 0.2),
    ],
)
def test_invalid_weights_rejected(bad):
    with pytest.raises(ValueError):
        validate_weights(bad)


@pytest.mark.parametrize(
    "change",
    [
        {"goods_total_cents": 1},
        {"available_quantity": 1},
        {"total_score": 0},
        {"rank": 4},
        {"data_label": "REAL"},
    ],
)
def test_result_contract_rejects_tampered_numbers(service, build_requirement, change):
    from componentmatch_contracts.result import Recommendation

    row = service.match(build_requirement()).recommendations[0]
    with pytest.raises(ValidationError):
        Recommendation.model_validate(row.model_dump() | change)


def test_result_contract_rejects_invented_contribution_and_evidence(service, build_requirement):
    from componentmatch_contracts.result import Recommendation

    row = service.match(build_requirement()).recommendations[0]
    fields = row.model_dump()
    fields["dimensions"][0]["contribution"] = Decimal(99)
    with pytest.raises(ValidationError):
        Recommendation.model_validate(fields)
    fields = row.model_dump()
    fields["dimensions"][0]["evidence_ids"] = ("offers:999999",)
    with pytest.raises(ValidationError):
        Recommendation.model_validate(fields)
