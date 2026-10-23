"""Regression cases from phase3 audit; every provider response is an explicit fake."""

import copy
from datetime import UTC, datetime

import pytest
from componentmatch.llm.client import LLMFailure
from componentmatch.llm.parser import (
    money_cents,
    normalize_draft,
    number_value,
    validate_draft_sources,
)
from componentmatch_contracts.agent import AgentRequest, MoneyMention, RequirementDraft

from tests.agent_fakes import DRAFT, TEXT


@pytest.mark.parametrize(
    "token,expected",
    [
        ("-1000片", -1000),
        ("−1000片", -1000),
        ("－1000片", -1000),
        ("负一千片", -1000),
        ("-1.5k片", -1500),
        ("+1000片", 1000),
        ("＋1000片", 1000),
        ("正一千片", 1000),
        ("- 1,000片", -1000),
        ("–1000片", -1000),
        ("—1000片", -1000),
        ("﹣1000片", -1000),
    ],
)
def test_original_numeric_sign_is_preserved(token, expected):
    assert number_value(token) == expected


@pytest.mark.parametrize("token", ["+-1000片", "-+1000片", "--1000片", "正负1000片", "±1000片"])
def test_conflicting_signs_are_not_simplified(token):
    with pytest.raises(ValueError):
        number_value(token)


@pytest.mark.parametrize("scope", ["单价", "总预算"])
@pytest.mark.parametrize("sign", ["-", "−", "－", "负", "+-", "--"])
def test_money_cannot_drop_negative_or_conflicting_sign(scope, sign):
    with pytest.raises(ValueError):
        money_cents(MoneyMention(amount="1.2", unit="CNY_yuan", quote=f"{scope}{sign}1.2元"))


def test_signed_source_cannot_be_accepted_as_unsigned_model_quantity():
    draft = RequirementDraft(quantity=1000, field_evidence={"quantity": "-1000片"})
    with pytest.raises(LLMFailure, match="LLM_EVIDENCE_INVALID"):
        validate_draft_sources(draft, "采购-1000片")


def normalize(data, text=TEXT, confirmed=None, now=None):
    return normalize_draft(
        RequirementDraft.model_validate(data),
        AgentRequest(text=text, confirmed_fields=confirmed or {}),
        now=now or datetime(2026, 10, 21, 4, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "field",
    [
        "manufacturer",
        "part_number",
        "quantity",
        "max_unit_price",
        "total_budget",
        "required_certifications",
        "max_delivery_days",
    ],
)
def test_supported_explicit_condition_cannot_be_omitted(field):
    data = copy.deepcopy(DRAFT)
    data[field] = None
    result, questions, *_ = normalize(data)
    assert result is None and questions


@pytest.mark.parametrize(
    "suffix",
    [
        "要求原厂授权",
        "只接受原厂授权",
        "需要授权代理",
        "必须有ISO14001",
        "必须符合AEC-Q100",
        "要求RoHS",
        "要求车规",
        "要求温度范围-40到85度",
    ],
)
def test_unsupported_conditions_cannot_be_hidden_by_iso9001(suffix):
    result, _, unsupported, *_ = normalize(DRAFT, TEXT + suffix)
    assert result is None and unsupported


@pytest.mark.parametrize(
    "replacement", ["-1000片", "+-1000片", "−1000片", "0片", "±1000片", "数量-1000"]
)
def test_raw_quantity_scan_catches_cropped_source(replacement):
    data = copy.deepcopy(DRAFT)
    # A model can quote an unsigned substring, so validation must inspect the full request too.
    result, questions, *_ = normalize(data, TEXT.replace("1000片", replacement))
    assert result is None and questions


@pytest.mark.parametrize(
    "original,replacement",
    [
        ("单价不超过1.2元", "单价不超过-1.2元"),
        ("总预算不超过1200元", "总预算不超过-1200元"),
        ("总预算不超过1200元", "总预算不超过+-1200元"),
        ("单价不超过1.2元", "单价不低于1.2元"),
        ("1000片", "1000片或2000片"),
        ("7天内到货", "7天内到货，另要求3天内到货"),
    ],
)
def test_numeric_changes_and_conflicts_never_pass(original, replacement):
    result, questions, *_ = normalize(DRAFT, TEXT.replace(original, replacement))
    assert result is None and questions


def date_draft():
    return {
        "manufacturer": "TI",
        "part_number": "LM358DR",
        "quantity": 1000,
        "field_evidence": {"manufacturer": "TI", "part_number": "LM358DR", "quantity": "1000片"},
    }


@pytest.mark.parametrize(
    "date_text,days",
    [
        ("不晚于2026年10月28日到货", 7),
        ("2026-10-28之前到货", 6),
        ("2026/10/21当天到货", 0),
        ("2026-10-28T12:00:00+08:00到货", 7),
        ("2026-10-28T04:00:00Z到货", 7),
        ("2026-10-27T23:00:00-05:00到货", 7),
        ("2026-10-28T03:59:00Z到货", 6),
    ],
)
def test_explicit_date_omitted_by_model_is_converted(date_text, days):
    result, questions, unsupported, evidence, _ = normalize(
        date_draft(), "TI LM358DR 1000片 " + date_text
    )
    assert result.max_delivery_days == days and result.delivery_mode == "within_days"
    assert not questions and not unsupported
    assert any(e.field == "max_delivery_days" and "2026" in e.quote for e in evidence)


@pytest.mark.parametrize(
    "date_text",
    [
        "2026-10-20到货",
        "2026-10-21之前到货",
        "2026-02-30到货",
        "2026-10-28到货或2026-10-29到货",
        "10月28日到货",
        "明天到货",
        "2026-10-28T12:00:00到货",
        "2026-10-21T03:59:00Z到货",
        "2026-10-28 UTC到货",
        "2026-10-28+00:00到货",
    ],
)
def test_invalid_ambiguous_or_past_dates_require_clarification(date_text):
    result, questions, *_ = normalize(date_draft(), "TI LM358DR 1000片 " + date_text)
    assert result is None and questions


def test_date_conversion_uses_shanghai_not_utc_calendar_date():
    now = datetime(2026, 10, 20, 23, tzinfo=UTC)  # Shanghai Oct 21, 07:00
    result, *_ = normalize(date_draft(), "TI LM358DR 1000片 2026-10-21当天到货", now=now)
    assert result.max_delivery_days == 0


@pytest.mark.parametrize(
    "suffix",
    [
        "必须2026年10月22日之前到货",
        "交期不限",
        "2026-10-29到货",
    ],
)
def test_date_duration_or_unlimited_conflicts_are_not_silently_resolved(suffix):
    result, questions, *_ = normalize(DRAFT, TEXT + suffix)
    assert result is None and questions


def test_consistent_date_and_duration_are_accepted():
    result, questions, *_ = normalize(DRAFT, TEXT + "不晚于2026年10月28日到货")
    assert result.max_delivery_days == 7 and not questions


def test_explicit_user_confirmation_can_resolve_model_omission():
    data = copy.deepcopy(DRAFT)
    data["total_budget"] = None
    result, questions, _, evidence, _ = normalize(data, confirmed={"total_budget_cents": 120000})
    assert result.total_budget_cents == 120000 and not questions
    assert any(e.field == "total_budget_cents" and e.source == "confirmed_fields" for e in evidence)


@pytest.mark.parametrize("suffix", ["要求七个工作日到货", "要求温度85度", "需要ISO 14001"])
def test_other_known_unsupported_forms_are_blocked(suffix):
    result, _, unsupported, *_ = normalize(DRAFT, TEXT + suffix)
    assert result is None and unsupported


def test_postfix_unit_price_omission_is_detected():
    data = copy.deepcopy(DRAFT)
    data["max_unit_price"] = None
    result, questions, *_ = normalize(data, TEXT.replace("单价不超过1.2元", "1.2元/片"))
    assert result is None and questions


def test_model_cannot_use_quantity_number_as_delivery_evidence():
    draft = RequirementDraft(max_delivery_days=7, field_evidence={"max_delivery_days": "7片"})
    with pytest.raises(LLMFailure):
        validate_draft_sources(draft, "采购7片，交期尚不确定")


@pytest.mark.parametrize("date_text", ["2026-10-28之后到货", "2026-10-28下午三点到货"])
def test_unrepresentable_date_semantics_are_not_silently_reinterpreted(date_text):
    result, questions, *_ = normalize(date_draft(), "TI LM358DR 1000片 " + date_text)
    assert result is None and questions


def test_strict_price_comparison_requires_confirmation():
    result, questions, *_ = normalize(DRAFT, TEXT.replace("单价不超过1.2元", "单价<1.2元"))
    assert result is None and questions


@pytest.mark.parametrize("date_text", ["2026-10-28TXX到货", "2026-10-28T12:00:00+05:99到货"])
def test_malformed_timestamp_is_not_truncated_to_a_valid_date(date_text):
    result, questions, *_ = normalize(date_draft(), "TI LM358DR 1000片 " + date_text)
    assert result is None and questions


def test_timezone_token_inside_part_name_is_not_a_timezone_constraint():
    data = copy.deepcopy(DRAFT)
    data["part_number"] = data["field_evidence"]["part_number"] = "TEST123"
    result, questions, *_ = normalize(data, TEXT.replace("LM358DR", "TEST123"))
    assert result.part_number == "TEST123" and not questions


def test_iso9001_followed_by_chinese_word_remains_supported():
    result, questions, unsupported, *_ = normalize(DRAFT, TEXT.replace("ISO9001", "ISO9001认证"))
    assert result is not None and not questions and not unsupported
