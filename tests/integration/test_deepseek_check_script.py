"""Offline guard/validator tests only. Never evidence of real provider compatibility."""

import asyncio
import copy
import json

import pytest

from componentmatch.agent.graph import AgentWorkflow
from componentmatch.core.config import Settings
from componentmatch.llm.client import DeepSeekTransport, JSONModel, LLMFailure, LLMReply
from componentmatch.services.matching import MatchingService
from componentmatch_contracts.agent import AgentRequest
from scripts import check_deepseek as script
from tests.agent_fakes import DRAFT, FakeTransport


@pytest.fixture
def configured(monkeypatch, engine):
    settings = Settings(
        deepseek_api_key="test-only-placeholder",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-flash",
        database_url=str(engine.url),
    )
    monkeypatch.setattr(script, "Settings", lambda: settings)
    return settings


def test_preflight_with_key_never_constructs_transport(configured, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Preflight must not instantiate a model transport")

    monkeypatch.setattr(script, "LimitedDeepSeekTransport", denied)
    result = asyncio.run(script.check())
    assert result["status"] == "awaiting_approval"
    assert result["transport_attempts"] == 0
    assert result["compatibility_verified"] is False
    assert configured.deepseek_api_key.get_secret_value() not in json.dumps(result)


@pytest.mark.parametrize("paid", [False, True])
def test_missing_key_never_claims_live_success(configured, monkeypatch, paid):
    monkeypatch.setattr(
        script, "Settings", lambda: configured.model_copy(update={"deepseek_api_key": None})
    )
    result = asyncio.run(script.check(allow_paid_api=paid))
    assert result["status"] == ("blocked" if paid else "needs_configuration")
    assert result["transport_attempts"] == 0
    assert result["compatibility_verified"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("deepseek_base_url", "https://unapproved.example/test-only-placeholder"),
        ("deepseek_base_url", "https://api.deepseek.com/?token=test-only-placeholder"),
        ("deepseek_model", "test-only-placeholder"),
    ],
)
def test_configuration_allowlist_hides_rejected_values(configured, monkeypatch, field, value):
    monkeypatch.setattr(script, "Settings", lambda: configured.model_copy(update={field: value}))
    result = asyncio.run(script.check(allow_paid_api=True))
    assert result["error_code"] == "UNAPPROVED_PROVIDER_CONFIGURATION"
    assert "test-only-placeholder" not in json.dumps(result)
    assert result["transport_attempts"] == 0


def test_configuration_exception_never_exposes_input(monkeypatch):
    def broken():
        raise ValueError("sensitive-test-input")

    monkeypatch.setattr(script, "Settings", broken)
    result = asyncio.run(script.check())
    assert result["status"] == "failed"
    assert "sensitive-test-input" not in json.dumps(result)


@pytest.mark.parametrize("name,text,status", script.SCENARIOS)
def test_three_workflow_scenarios_offline_and_mock_rejected_as_live(engine, name, text, status):
    draft = copy.deepcopy(DRAFT)
    if name == "missing":
        draft = {
            "manufacturer": "TI",
            "part_number": "LM358DR",
            "field_evidence": {"manufacturer": "TI", "part_number": "LM358DR"},
        }
    elif name == "no_match":
        draft["max_unit_price"] = {"amount": "1", "unit": "CNY_cent", "quote": "单价不超过1分"}
        draft["field_evidence"]["max_unit_price_cents"] = "单价不超过1分"
    service = MatchingService(engine)
    fake = FakeTransport(draft)
    workflow = AgentWorkflow(service, JSONModel(fake, Settings(llm_max_retries=0)))
    result, http = asyncio.run(workflow.run(AgentRequest(text=text)))
    baseline = None if name == "missing" else service.match(script.expected_requirement(name))
    checks = script.validate_result(name, status, result, http, baseline, fake.model_name)
    assert checks.pop("real_transport") is False
    assert all(checks.values()), checks


def test_template_fallback_is_not_full_live_acceptance(engine):
    service = MatchingService(engine)
    fake = FakeTransport(explain=LLMFailure("LLM_TIMEOUT"))
    workflow = AgentWorkflow(service, JSONModel(fake, Settings(llm_max_retries=0)))
    result, http = asyncio.run(workflow.run(AgentRequest(text=script.NORMAL_TEXT)))
    checks = script.validate_result(
        "normal",
        "success",
        result,
        http,
        service.match(script.expected_requirement("normal")),
        fake.model_name,
    )
    assert checks["explanation_mode"] is False
    assert checks["calls_succeeded"] is False
    assert checks["rankings_scores_evidence_risks"] is True


def test_dispatch_limit_blocks_fifth_request_without_network(configured, monkeypatch):
    calls = []

    async def simulated_dispatch(self, *args):
        calls.append(True)
        return LLMReply("{}")

    monkeypatch.setattr(DeepSeekTransport, "generate", simulated_dispatch)
    transport = script.LimitedDeepSeekTransport(configured)

    async def run():
        for _ in range(4):
            await transport.generate("", "", 1)
        with pytest.raises(LLMFailure, match="LIVE_CALL_LIMIT"):
            await transport.generate("", "", 1)

    asyncio.run(run())
    assert len(calls) == transport.dispatch_attempts == 4


def test_mock_full_runner_stops_after_failed_live_provenance(configured, monkeypatch):
    class ExplicitMock(FakeTransport):
        def __init__(self, *args, **kwargs):
            super().__init__()

        @property
        def dispatch_attempts(self):
            return len(self.calls)

    monkeypatch.setattr(script, "LimitedDeepSeekTransport", ExplicitMock)
    result = asyncio.run(script.check(allow_paid_api=True))
    assert result["status"] == "failed"
    assert result["compatibility_verified"] is False
    assert len(result["scenarios"]) == 1
    assert result["scenarios"][0]["checks"]["real_transport"] is False
