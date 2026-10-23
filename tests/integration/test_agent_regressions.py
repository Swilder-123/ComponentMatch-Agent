"""HTTP and graph regression checks; no provider network or paid calls."""

import asyncio
import copy
import threading
import time
from datetime import UTC, datetime

import pytest
from componentmatch.agent.graph import AgentWorkflow
from componentmatch.api.agent_routes import get_agent_workflow
from componentmatch.api.main import app
from componentmatch.api.routes import get_matching_service
from componentmatch.core.config import Settings
from componentmatch.llm.client import JSONModel, LLMFailure
from componentmatch_contracts.agent import AgentRequest
from fastapi.testclient import TestClient

from tests.agent_fakes import DRAFT, TEXT, FakeTransport


def graph(service, fake=None, budget=10):
    return AgentWorkflow(
        service,
        JSONModel(
            fake or FakeTransport(), Settings(llm_max_retries=0, agent_timeout_seconds=budget)
        ),
    )


@pytest.mark.parametrize(
    "case",
    [
        "negative_quantity",
        "negative_unit",
        "negative_total",
        "conflicting_signs",
        "authorization",
        "date_conflict",
        "missing_total",
        "missing_cert",
        "missing_manufacturer",
    ],
)
def test_invalid_or_omitted_constraints_never_reach_matching(service, monkeypatch, case):
    data, text = copy.deepcopy(DRAFT), TEXT
    if case == "negative_quantity":
        text = text.replace("1000片", "-1000片")
        data["field_evidence"]["quantity"] = "-1000片"
    elif case in {"negative_unit", "negative_total", "conflicting_signs"}:
        field = "total_budget" if case == "negative_total" else "max_unit_price"
        evidence_field = "total_budget_cents" if field == "total_budget" else "max_unit_price_cents"
        number = "1200" if field == "total_budget" else "1.2"
        sign = "+-" if case == "conflicting_signs" else "-"
        quote = data[field]["quote"].replace(number, sign + number)
        text = text.replace(data[field]["quote"], quote)
        data[field]["quote"] = data["field_evidence"][evidence_field] = quote
    elif case == "authorization":
        text += "要求原厂授权。"
    elif case == "date_conflict":
        text += "必须2026年10月22日之前到货。"
    else:
        data[
            {
                "missing_total": "total_budget",
                "missing_cert": "required_certifications",
                "missing_manufacturer": "manufacturer",
            }[case]
        ] = None
    reached = []

    def forbidden(*args, **kwargs):
        reached.append(True)
        raise AssertionError("Invalid input reached database")

    monkeypatch.setattr(service, "prepare", forbidden)
    result, _ = asyncio.run(graph(service, FakeTransport(data)).run(AgentRequest(text=text)))
    assert not reached and not result.recommendations
    assert result.status in {"needs_clarification", "error"}


@pytest.mark.parametrize("mode", ["success", "clarification", "no_match", "error", "fallback"])
def test_http_outcomes_and_structured_ranking_are_preserved(service, build_requirement, mode):
    fake = FakeTransport()
    request = {"text": TEXT}
    if mode == "clarification":
        fake = FakeTransport(
            {"part_number": "LM358DR", "field_evidence": {"part_number": "LM358DR"}}
        )
        request = {"text": "采购LM358DR"}
    elif mode == "no_match":
        request["confirmed_fields"] = {"max_unit_price_cents": 1}
    elif mode == "error":
        fake = FakeTransport(parse_error=LLMFailure("LLM_AUTH_ERROR"))
    elif mode == "fallback":
        fake = FakeTransport(explain=TimeoutError())
    workflow = graph(service, fake)
    app.dependency_overrides[get_agent_workflow] = lambda: workflow
    app.dependency_overrides[get_matching_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/agent/matches", json=request)
            body = response.json()
            expected = {"clarification": "needs_clarification", "fallback": "success"}.get(
                mode, mode
            )
            assert response.status_code == (503 if mode == "error" else 200)
            assert body["status"] == expected and body["request_id"]
            assert all(c["source"] == "mock" for c in body["llm_calls"])
            if expected == "success":
                structured = client.post(
                    "/api/v1/matches", json={"requirement": body["requirement"]}
                )
                assert structured.status_code == 200
                assert body["recommendations"] == structured.json()["recommendations"]
                assert body["explanation_mode"] == ("template" if mode == "fallback" else "llm")
            else:
                assert not body["recommendations"]
    finally:
        app.dependency_overrides.clear()


def test_date_only_request_runs_full_graph_and_uses_test_business_date(service):
    data = copy.deepcopy(DRAFT)
    data["delivery_mode"] = data["max_delivery_days"] = None
    data["field_evidence"].pop("delivery_mode")
    data["field_evidence"].pop("max_delivery_days")
    request = AgentRequest(text=TEXT.replace("7天内到货", "不晚于2026年10月28日到货"))
    result, status = asyncio.run(graph(service, FakeTransport(data)).run(request))
    assert status == 200 and result.status == "success"
    assert result.requirement.max_delivery_days == 7
    assert result.recommendations == service.match(result.requirement).recommendations


def test_crossing_shanghai_midnight_requires_reconfirmation(service, monkeypatch):
    class Clock:
        def __init__(self):
            self.calls = 0

        def now(self):
            self.calls += 1
            return (
                datetime(2026, 10, 21, 15, 59, 59, tzinfo=UTC)
                if self.calls == 1
                else datetime(2026, 10, 21, 16, 0, tzinfo=UTC)
            )

    monkeypatch.setattr(service, "clock", Clock())
    data = copy.deepcopy(DRAFT)
    data["delivery_mode"] = data["max_delivery_days"] = None
    data["field_evidence"].pop("delivery_mode")
    data["field_evidence"].pop("max_delivery_days")
    request = AgentRequest(text=TEXT.replace("7天内到货", "2026年10月28日到货"))
    result, status = asyncio.run(graph(service, FakeTransport(data)).run(request))
    assert status == 200 and result.status == "needs_clarification"
    assert "score_and_rank" not in [t.node for t in result.node_trace]


def test_database_timeout_returns_before_worker_is_released(service, monkeypatch):
    release, finished = threading.Event(), threading.Event()
    original = service.prepare

    def blocked(*args, **kwargs):
        try:
            release.wait(3)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(service, "prepare", blocked)

    async def run():
        task = asyncio.create_task(graph(service, budget=0.2).run(AgentRequest(text=TEXT)))
        try:
            result, status = await asyncio.wait_for(asyncio.shield(task), 1)
            assert not release.is_set() and not finished.is_set()
            assert status == 504 and result.error.code == "AGENT_TIMEOUT"
            assert not result.recommendations
            assert "filter_candidates" not in [t.node for t in result.node_trace]
        finally:
            release.set()
            await task
            assert await asyncio.to_thread(finished.wait, 3)

    asyncio.run(run())


def test_synchronous_scoring_overrun_discards_late_result(service, monkeypatch):
    original = service.score_and_rank

    def slow(*args, **kwargs):
        time.sleep(0.25)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "score_and_rank", slow)
    result, status = asyncio.run(graph(service, budget=0.2).run(AgentRequest(text=TEXT)))
    assert status == 504 and result.error.code == "AGENT_TIMEOUT"
    assert not result.recommendations
    assert "explain_results" not in [t.node for t in result.node_trace]
