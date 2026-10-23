"""Compiled single-agent StateGraph, bounded and stateless across requests."""

import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from componentmatch.agent.nodes import Nodes
from componentmatch.agent.state import MatchState
from componentmatch_contracts.agent import AgentResult
from componentmatch_contracts.result import MatchError

logger = logging.getLogger("componentmatch.agent")


def route(state, onward):
    return {
        "error": "handle_error",
        "needs_clarification": "request_clarification",
        "no_match": "build_no_match",
    }.get(state.get("status"), onward)


def build_graph(matching, model):
    nodes = Nodes(matching, model)
    graph = StateGraph(MatchState)
    names = (
        "parse_request",
        "validate_request",
        "retrieve_candidates",
        "filter_candidates",
        "score_and_rank",
        "explain_results",
        "request_clarification",
        "build_no_match",
        "handle_error",
        "finalize_response",
    )
    for name in names:
        graph.add_node(name, nodes.guarded(name))
    graph.add_edge(START, "parse_request")
    for name, onward, choices in (
        ("parse_request", "validate_request", ("handle_error", "validate_request")),
        (
            "validate_request",
            "retrieve_candidates",
            ("handle_error", "request_clarification", "retrieve_candidates"),
        ),
        (
            "retrieve_candidates",
            "filter_candidates",
            ("handle_error", "request_clarification", "build_no_match", "filter_candidates"),
        ),
        (
            "filter_candidates",
            "score_and_rank",
            ("handle_error", "build_no_match", "score_and_rank"),
        ),
        ("score_and_rank", "explain_results", ("handle_error", "explain_results")),
    ):
        graph.add_conditional_edges(
            name,
            lambda s, next_node=onward: route(s, next_node),
            {choice: choice for choice in choices},
        )
    for name in ("explain_results", "request_clarification", "build_no_match", "handle_error"):
        graph.add_edge(name, "finalize_response")
    graph.add_edge("finalize_response", END)
    return graph.compile()


class AgentWorkflow:
    def __init__(self, matching, model):
        self.model = model
        self.matching = matching
        self.graph = build_graph(matching, model)

    async def run(self, request):
        request_id = str(uuid4())
        state = {
            "request_id": request_id,
            "request": request,
            "status": "running",
            "deadline": time.monotonic() + self.model.settings.agent_timeout_seconds,
            "business_time": (
                self.matching.clock.now() if self.matching.clock else datetime.now(UTC)
            ),
            "llm_calls": [],
            "node_trace": [],
        }
        try:
            with tracing_context(enabled=False):
                result = await self.graph.ainvoke(
                    state, config={"recursion_limit": 20, "callbacks": []}
                )
            if "response" in result:
                return AgentResult.model_validate(result["response"].model_dump()), result.get(
                    "http_status", 200
                )
        except Exception as exc:
            logger.error(
                "agent_workflow request_id=%s error_code=WORKFLOW_ERROR exception_type=%s",
                request_id,
                type(exc).__name__,
            )
        # Never expose raw graph state, prompts or exceptions at the API boundary.
        return AgentResult(
            request_id=request_id,
            status="error",
            error=MatchError(code="WORKFLOW_ERROR", message="工作流无法完成，请检查服务配置"),
        ), 500
