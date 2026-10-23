"""Regression inputs for polarity and delivery comparison direction."""

from datetime import UTC, datetime

import pytest
from componentmatch.llm.parser import normalize_draft, validate_draft_sources
from componentmatch_contracts.agent import AgentRequest, RequirementDraft


def draft():
    return RequirementDraft(
        manufacturer="TI",
        part_number="LM358DR",
        quantity=1000,
        delivery_mode="within_days",
        max_delivery_days=7,
        field_evidence={
            "manufacturer": "TI",
            "part_number": "LM358DR",
            "quantity": "1000片",
            "delivery_mode": "7天",
            "max_delivery_days": "7天",
        },
    )


def normalize(text, data=None):
    data = data or draft()
    validate_draft_sources(data, text)
    return normalize_draft(data, AgentRequest(text=text), now=datetime(2026, 10, 21, 4, tzinfo=UTC))


@pytest.mark.parametrize(
    "delivery",
    [
        "7天后到货",
        "至少7天到货",
        "不得早于7天到货",
        "7天以后到货",
        "交期超过7天",
        "7天前到货",
        "7天之前到货",
        "7天以前到货",
        "7天以外到货",
    ],
)
def test_lower_and_strict_bounds_cannot_pass_as_inclusive_upper_bound(delivery):
    requirement, questions, *_ = normalize("TI LM358DR 1000片 " + delivery)
    assert requirement is None and questions


@pytest.mark.parametrize(
    "delivery",
    [
        "7天内到货",
        "交期不超过7天",
        "不晚于7天到货",
        "不得超过7天到货",
        "最多7天到货",
        "7天以内到货",
    ],
)
def test_supported_upper_bounds_remain_accepted(delivery):
    requirement, questions, unsupported, *_ = normalize("TI LM358DR 1000片 " + delivery)
    assert requirement.max_delivery_days == 7
    assert not questions and not unsupported


@pytest.mark.parametrize(
    "waiver",
    [
        "不要求原厂授权",
        "无需原厂授权",
        "不需要提供原厂授权",
        "原厂授权不作要求",
        "不强制要求ISO14001",
        "RoHS可选",
        "不要求ISO9001",
        "ISO9001证书不限",
    ],
)
def test_explicit_waiver_is_not_promoted_to_a_hard_requirement(waiver):
    requirement, questions, unsupported, *_ = normalize("TI LM358DR 1000片 7天内到货，" + waiver)
    assert requirement is not None and not questions and not unsupported
    assert not requirement.required_certifications


@pytest.mark.parametrize(
    "text",
    ["不要求ISO9001，但必须原厂授权", "不要求原厂授权，但必须原厂授权", "不要求原厂授权，必须RoHS"],
)
def test_waiver_never_cancels_a_later_required_unsupported_condition(text):
    requirement, _, unsupported, *_ = normalize("TI LM358DR 1000片 7天内到货，" + text)
    assert requirement is None and unsupported


def test_complete_waiver_in_model_unhandled_issue_is_not_blocked():
    values = draft().model_dump()
    values["unhandled_constraints"] = [{"quote": "不要求原厂授权", "message": "授权条件"}]
    requirement, _, unsupported, *_ = normalize(
        "TI LM358DR 1000片 7天内到货，不要求原厂授权", RequirementDraft.model_validate(values)
    )
    assert requirement is not None and not unsupported


@pytest.mark.parametrize("prefix", ["不得早于", "不早于", "晚于", "最早"])
def test_date_lower_bounds_are_not_deadlines(prefix):
    data = draft().model_dump()
    data.update(delivery_mode=None, max_delivery_days=None)
    data["field_evidence"] = {
        k: v
        for k, v in data["field_evidence"].items()
        if k not in {"delivery_mode", "max_delivery_days"}
    }
    requirement, questions, *_ = normalize(
        "TI LM358DR 1000片 " + prefix + "2026-10-28到货", RequirementDraft.model_validate(data)
    )
    assert requirement is None and questions
