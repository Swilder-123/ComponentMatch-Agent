import asyncio
import copy
import logging

import pytest
from componentmatch.agent.graph import AgentWorkflow
from componentmatch.api.agent_routes import get_agent_workflow
from componentmatch.api.main import app
from componentmatch.core.config import Settings
from componentmatch.llm.client import JSONModel, LLMFailure
from componentmatch_contracts.agent import AgentRequest, AgentResult
from fastapi.testclient import TestClient
from sqlalchemy import event

from tests.agent_fakes import DRAFT, TEXT, FakeTransport, valid_plan


def execute(service, *, draft=None, text=TEXT, confirmed=None, fake=None):
    fake = fake or FakeTransport(draft)
    settings = Settings(llm_max_retries=0)
    workflow = AgentWorkflow(service, JSONModel(fake, settings))
    result, status = asyncio.run(
        workflow.run(AgentRequest(text=text, confirmed_fields=confirmed or {}))
    )
    return result, status, fake, workflow


def test_compiled_graph_success_reuses_existing_results_and_stages_once(
    service, monkeypatch, engine, caplog
):
    stages, queries = [], []
    for method in ("prepare", "filter_candidates", "score_and_rank"):
        original = getattr(service, method)

        def spy(*args, _name=method, _original=original, **kwargs):
            stages.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(service, method, spy)

    def record_sql(*args):
        queries.append(args[2])

    event.listen(engine, "before_cursor_execute", record_sql)
    caplog.set_level(logging.INFO, logger="componentmatch.agent")
    result, status, fake, workflow = execute(service)
    event.remove(engine, "before_cursor_execute", record_sql)
    assert status == 200 and result.status == "success"
    assert stages == ["prepare", "filter_candidates", "score_and_rank"]
    assert len([sql for sql in queries if sql.startswith("SELECT")]) == 5
    assert fake.calls == ["parse", "explain"]
    assert result.explanation_mode == "llm"
    assert result.metadata.explanation_mode == "llm"
    assert result.metadata.model_name == "test-only-fake"
    assert all(call.source == "mock" for call in result.llm_calls)
    assert result.recommendations == service.match(result.requirement).recommendations
    assert [t.node for t in result.node_trace] == [
        "parse_request",
        "validate_request",
        "retrieve_candidates",
        "filter_candidates",
        "score_and_rank",
        "explain_results",
        "finalize_response",
    ]
    assert {"request_clarification", "build_no_match", "handle_error"} <= set(workflow.graph.nodes)
    assert TEXT not in caplog.text and "LM358DR" not in caplog.text
    assert result.request_id in caplog.text
    assert AgentResult.model_validate_json(result.model_dump_json()) == result


def test_missing_fields_and_user_clarification(service):
    draft = {"part_number": "LM358DR", "field_evidence": {"part_number": "LM358DR"}}
    result, _, fake, _ = execute(service, draft=draft, text="采购LM358DR")
    assert result.status == "needs_clarification" and fake.calls == ["parse"]
    assert result.requirement is None and not result.recommendations
    clarified, _, _, _ = execute(
        service,
        draft=draft,
        text="采购LM358DR",
        confirmed={
            "quantity": 1000,
            "delivery_mode": "within_days",
            "max_delivery_days": 7,
            "manufacturer": "TI",
            "required_certifications": ["ISO9001"],
        },
    )
    assert clarified.status == "success"
    assert clarified.request_id != result.request_id
    assert any(e.source == "confirmed_fields" for e in clarified.extraction_evidence)


def test_catalog_manufacturer_ambiguity(service):
    draft = {
        "part_number": "DEMO-CROSS-01",
        "quantity": 1000,
        "delivery_mode": "unconstrained",
        "field_evidence": {
            "part_number": "DEMO-CROSS-01",
            "quantity": "1000片",
            "delivery_mode": "交期不限",
        },
    }
    result, _, fake, _ = execute(service, draft=draft, text="DEMO-CROSS-01 1000片 交期不限")
    assert result.status == "needs_clarification"
    assert fake.calls == ["parse"]
    assert [t.node for t in result.node_trace][-2:] == [
        "request_clarification",
        "finalize_response",
    ]


def test_unsupported_hard_condition_never_queries(service, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Unsupported condition must not reach matching")

    monkeypatch.setattr(service, "prepare", denied)
    result, status, fake, _ = execute(service, text=TEXT + "必须原厂授权")
    assert result.status == "error" and status == 422
    assert result.error.code == "UNSUPPORTED_CONSTRAINT" and result.unsupported_constraints
    assert fake.calls == ["parse"]


def test_no_match_after_filtering_preserves_exclusion_reasons(service):
    result, status, fake, _ = execute(service, confirmed={"max_unit_price_cents": 1})
    assert status == 200 and result.status == "no_match"
    assert result.exclusion_summary.reason_counts["UNIT_PRICE_OVER_LIMIT"] == 13
    assert result.recommendations == () and fake.calls == ["parse"]
    assert "build_no_match" in [t.node for t in result.node_trace]
    assert "score_and_rank" not in [t.node for t in result.node_trace]


def test_no_exact_catalog_match_branches_before_filtering(service):
    result, _, fake, _ = execute(service, confirmed={"part_number": "LM358DRX"})
    assert result.status == "no_match" and result.exclusion_summary.retrieved_offers == 0
    assert "filter_candidates" not in [t.node for t in result.node_trace]
    assert fake.calls == ["parse"]


@pytest.mark.parametrize(
    "error",
    [
        LLMFailure("LLM_TIMEOUT"),
        LLMFailure("LLM_RATE_LIMIT"),
        LLMFailure("LLM_AUTH_ERROR"),
        LLMFailure("CONFIG_MISSING"),
    ],
)
def test_parse_failure_is_error_with_request_id_and_no_fake_results(service, error):
    result, status, _, _ = execute(service, fake=FakeTransport(parse_error=error))
    assert status == 503 and result.status == "error" and result.request_id
    assert result.error.code == error.code
    assert not result.recommendations and result.explanation_mode == "none"
    assert result.llm_calls[0].outcome == "error"


def test_explanation_failure_keeps_deterministic_result(service):
    result, status, _, _ = execute(
        service, fake=FakeTransport(explain=TimeoutError("private body"))
    )
    assert status == 200 and result.status == "success"
    assert (
        result.explanation_mode == "template"
        and result.explanation_fallback_reason == "LLM_TIMEOUT"
    )
    assert result.recommendations == service.match(result.requirement).recommendations
    assert all(e.risk_messages for e in result.explanations)


@pytest.mark.parametrize(
    "mutation", ["supplier", "rank", "score", "quote", "reference", "risk", "order"]
)
def test_model_cannot_change_facts_or_hide_risks(service, mutation):
    def malicious(payload):
        plan = valid_plan(payload)
        first = plan["suppliers"][0]
        if mutation == "supplier":
            first["supplier_id"] = 9999
        elif mutation in {"rank", "score", "quote"}:
            first[mutation] = 0
        elif mutation == "reference":
            first["reasons"][0]["evidence_ids"] = ["offers:999999"]
        elif mutation == "risk":
            first["risk_codes"] = []
        elif mutation == "order":
            plan["suppliers"].reverse()
        return plan

    result, status, _, _ = execute(service, fake=FakeTransport(explain=malicious))
    assert status == 200 and result.status == "success" and result.explanation_mode == "template"
    assert result.recommendations == service.match(result.requirement).recommendations
    assert result.recommendations[0].supplier_id == 2


def test_schema_error_from_model_does_not_reach_service(service):
    draft = copy.deepcopy(DRAFT)
    draft["quantity"] = "1000"
    result, status, _, _ = execute(service, draft=draft)
    assert status == 503 and result.error.code == "LLM_SCHEMA_INVALID"


def test_database_failure_is_error_not_no_match(service, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def broken(*args, **kwargs):
        raise OperationalError("sensitive SQL", {}, Exception("private"))

    monkeypatch.setattr(service, "prepare", broken)
    result, status, _, _ = execute(service)
    assert status == 500 and result.error.code == "DATABASE_ERROR"
    assert "sensitive" not in result.model_dump_json()


def test_agent_http_api_and_original_endpoint_are_separate(service):
    workflow = AgentWorkflow(service, JSONModel(FakeTransport(), Settings(llm_max_retries=0)))
    app.dependency_overrides[get_agent_workflow] = lambda: workflow
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/agent/matches", json={"text": TEXT})
            assert response.status_code == 200 and response.json()["status"] == "success"
            assert response.json()["llm_calls"][0]["source"] == "mock"
            assert client.post("/api/v1/agent/matches", json={"text": " "}).status_code == 422
            assert (
                client.post(
                    "/api/v1/agent/matches", json={"text": TEXT, "api_key": "x"}
                ).status_code
                == 422
            )
            assert "/api/v1/matches" in client.get("/openapi.json").json()["paths"]
    finally:
        app.dependency_overrides.clear()
