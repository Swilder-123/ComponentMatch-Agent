import copy

import pytest
from componentmatch.llm.client import LLMFailure
from componentmatch.llm.parser import (
    money_cents,
    normalize_draft,
    number_value,
    validate_draft_sources,
)
from componentmatch_contracts.agent import AgentRequest, MoneyMention, RequirementDraft
from pydantic import ValidationError

from tests.agent_fakes import DRAFT, TEXT


def test_normal_extraction_retains_original_sources_and_contract():
    draft = RequirementDraft.model_validate(DRAFT)
    validate_draft_sources(draft, TEXT)
    req, questions, unsupported, evidence, defaults = normalize_draft(
        draft, AgentRequest(text=TEXT)
    )
    assert req.quantity == 1000 and req.max_unit_price_cents == 120
    assert req.total_budget_cents == 120000 and req.preference_profile == "quality"
    assert not questions and not unsupported
    assert any(e.field == "max_unit_price_cents" and e.quote == "单价不超过1.2元" for e in evidence)
    assert "currency=CNY" in defaults


@pytest.mark.parametrize(
    "amount,unit,quote,expected",
    [
        ("1.2", "CNY_yuan", "单价1.2元", 120),
        ("120", "CNY_cent", "单价120分", 120),
        ("0.01", "CNY_yuan", "单价0.01元", 1),
        ("1", "CNY_yuan", "总预算1万元", 1000000),
        ("0", "CNY_cent", "单价0分", 0),
    ],
)
def test_exact_money_conversion(amount, unit, quote, expected):
    assert money_cents(MoneyMention(amount=amount, unit=unit, quote=quote)) == expected


@pytest.mark.parametrize(
    "amount,unit,quote",
    [
        ("0.001", "CNY_yuan", "单价0.001元"),
        ("120", "CNY_yuan", "单价1.2元"),
        ("1.2", "CNY_cent", "单价1.2元"),
        ("100", "CNY_yuan", "预算100"),
    ],
)
def test_unit_or_precision_discrepancy_requires_confirmation(amount, unit, quote):
    with pytest.raises(ValueError):
        money_cents(MoneyMention(amount=amount, unit=unit, quote=quote))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1k片", 1000),
        ("1.5k片", 1500),
        ("一千片", 1000),
        ("两万片", 20000),
        ("7天", 7),
        ("1,000片", 1000),
    ],
)
def test_supported_quantity_tokens(text, expected):
    assert number_value(text) == expected


def test_missing_fields_not_invented_and_explicit_confirmation_has_provenance():
    draft = RequirementDraft(part_number="LM358DR", field_evidence={"part_number": "LM358DR"})
    request = AgentRequest(text="LM358DR")
    req, questions, *_ = normalize_draft(draft, request)
    assert req is None and len(questions) == 2
    confirmed = AgentRequest(
        text="LM358DR", confirmed_fields={"quantity": 1000, "delivery_mode": "unconstrained"}
    )
    req, questions, _, evidence, _ = normalize_draft(draft, confirmed)
    assert not questions and req.quantity == 1000 and req.manufacturer is None
    assert any(e.field == "quantity" and e.source == "confirmed_fields" for e in evidence)


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": True},
        {"quantity": "1000"},
        {"quantity": -1},
        {"invented_field": "ignored"},
        {"manufacturer": 3},
    ],
)
def test_draft_schema_is_strict(changes):
    with pytest.raises(ValidationError):
        RequirementDraft.model_validate(DRAFT | changes)


def test_fabricated_source_and_guessed_manufacturer_rejected():
    draft = copy.deepcopy(DRAFT)
    draft["field_evidence"]["quantity"] = "99999片"
    with pytest.raises(LLMFailure, match="EVIDENCE"):
        validate_draft_sources(RequirementDraft.model_validate(draft), TEXT)
    draft = RequirementDraft(manufacturer="TI", field_evidence={"manufacturer": "LM358DR"})
    with pytest.raises(LLMFailure):
        validate_draft_sources(draft, "LM358DR")


def test_ambiguous_budget_is_not_silently_dropped():
    draft = RequirementDraft.model_validate(DRAFT)
    data = draft.model_dump()
    data["max_unit_price"] = {"amount": "100", "unit": "CNY_yuan", "quote": "预算100元"}
    data["field_evidence"]["max_unit_price_cents"] = "预算100元"
    req, questions, *_ = normalize_draft(
        RequirementDraft.model_validate(data), AgentRequest(text=TEXT)
    )
    assert req is None and questions


def test_unsupported_hard_constraint_is_blocked_even_if_model_omits_issue():
    _, _, unsupported, *_ = normalize_draft(
        RequirementDraft.model_validate(DRAFT), AgentRequest(text=TEXT + "必须原厂授权")
    )
    assert unsupported


def test_multiple_part_numbers_cannot_be_resolved_by_guess():
    req, questions, *_ = normalize_draft(
        RequirementDraft.model_validate(DRAFT), AgentRequest(text=TEXT + "或者NE555DR")
    )
    assert req is None and questions


@pytest.mark.parametrize(
    "profile,quote", [("cost", "价格优先"), ("delivery", "交期优先"), ("quality", "质量优先")]
)
def test_named_profiles_require_explicit_text_evidence(profile, quote):
    draft = RequirementDraft(
        preference_profile=profile, field_evidence={"preference_profile": quote}
    )
    validate_draft_sources(draft, quote)


def test_field_scoped_ambiguity_can_be_explicitly_confirmed():
    draft = RequirementDraft.model_validate(
        DRAFT
        | {
            "quantity": None,
            "ambiguous_constraints": [
                {"field": "quantity", "quote": "一批", "message": "数量不清"}
            ],
        }
    )
    request = AgentRequest(text=TEXT + "一批", confirmed_fields={"quantity": 1000})
    req, questions, *_ = normalize_draft(draft, request)
    assert req.quantity == 1000 and not questions
