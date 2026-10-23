"""Resource lifecycle, safe diagnostics, and zero-call explanation fallback."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from componentmatch.agent.graph import AgentWorkflow
from componentmatch.api.main import app
from componentmatch.api.routes import get_matching_service
from componentmatch.core.config import Settings
from componentmatch.llm.client import DeepSeekTransport, JSONModel
from componentmatch.models import Offer, PerformanceRecord
from componentmatch_contracts.agent import AgentRequest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from tests.agent_fakes import TEXT, FakeTransport


def test_no_valid_positive_reason_skips_provider_and_preserves_ranking(service, engine):
    with Session(engine) as session, session.begin():
        session.execute(update(Offer).values(unit_price_cents=150, lead_time_days=30))
        session.execute(delete(PerformanceRecord))
    text = "TI LM358DR 1000片 交期不限"
    fake = FakeTransport(
        {
            "manufacturer": "TI",
            "part_number": "LM358DR",
            "quantity": 1000,
            "delivery_mode": "unconstrained",
            "field_evidence": {
                "manufacturer": "TI",
                "part_number": "LM358DR",
                "quantity": "1000片",
                "delivery_mode": "交期不限",
            },
        }
    )
    workflow = AgentWorkflow(service, JSONModel(fake, Settings(llm_max_retries=0)))
    result, status = asyncio.run(workflow.run(AgentRequest(text=text)))
    assert status == 200 and result.status == "success"
    assert result.recommendations == service.match(result.requirement).recommendations
    assert all(row.total_score == 0 for row in result.recommendations)
    assert fake.calls == ["parse"]
    assert result.explanation_mode == "template"
    assert result.explanation_fallback_reason == "EXPLANATION_NO_SUPPORTED_REASONS"


def test_application_reuses_graph_then_closes_transport(service, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    closed = AsyncMock()
    monkeypatch.setattr(DeepSeekTransport, "aclose", closed)
    app.dependency_overrides[get_matching_service] = lambda: service
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/agent/matches", json={"text": TEXT})
            workflow = app.state.agent_workflow
            second = client.post("/api/v1/agent/matches", json={"text": TEXT})
            assert first.status_code == second.status_code == 503
            assert app.state.agent_workflow is workflow
        closed.assert_awaited_once()
        assert app.state.agent_workflow is None
    finally:
        app.dependency_overrides.clear()


def test_transport_closes_owned_clients_once():
    transport = DeepSeekTransport(Settings())
    sync_close, async_close = Mock(), AsyncMock()
    transport._client = SimpleNamespace(
        root_client=SimpleNamespace(close=sync_close),
        root_async_client=SimpleNamespace(close=async_close),
    )

    async def close_twice():
        await transport.aclose()
        await transport.aclose()

    asyncio.run(close_twice())
    sync_close.assert_called_once()
    async_close.assert_awaited_once()


def test_node_diagnostics_identify_failure_without_exception_body(service, monkeypatch, caplog):
    monkeypatch.setattr(service, "prepare", Mock(side_effect=RuntimeError("private-secret-body")))
    workflow = AgentWorkflow(service, JSONModel(FakeTransport(), Settings(llm_max_retries=0)))
    with caplog.at_level(logging.WARNING, logger="componentmatch.agent"):
        result, status = asyncio.run(workflow.run(AgentRequest(text=TEXT)))
    assert status == 500 and result.error.code == "INTERNAL_ERROR"
    assert result.request_id in caplog.text
    assert (
        "exception_type=RuntimeError" in caplog.text and "node=retrieve_candidates" in caplog.text
    )
    assert "private-secret-body" not in caplog.text and TEXT not in caplog.text


def test_framework_failure_is_logged_without_raw_state(service, monkeypatch, caplog):
    workflow = AgentWorkflow(service, JSONModel(FakeTransport(), Settings()))
    monkeypatch.setattr(
        workflow.graph, "ainvoke", AsyncMock(side_effect=ValueError("private-state"))
    )
    with caplog.at_level(logging.ERROR, logger="componentmatch.agent"):
        result, status = asyncio.run(workflow.run(AgentRequest(text=TEXT)))
    assert status == 500 and result.error.code == "WORKFLOW_ERROR"
    assert result.request_id in caplog.text and "exception_type=ValueError" in caplog.text
    assert "private-state" not in caplog.text


def test_shared_compiled_graph_keeps_concurrent_request_state_separate(service):
    workflow = AgentWorkflow(service, JSONModel(FakeTransport(), Settings(llm_max_retries=0)))

    async def run_both():
        return await asyncio.gather(
            workflow.run(AgentRequest(text=TEXT)),
            workflow.run(AgentRequest(text=TEXT, confirmed_fields={"max_unit_price_cents": 1})),
        )

    (success, code1), (empty, code2) = asyncio.run(run_both())
    assert code1 == code2 == 200
    assert success.status == "success" and empty.status == "no_match"
    assert success.request_id != empty.request_id
    assert len(success.llm_calls) == 2 and len(empty.llm_calls) == 1
    assert success.requirement.max_unit_price_cents == 120
    assert empty.requirement.max_unit_price_cents == 1
