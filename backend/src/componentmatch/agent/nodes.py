"""Thin graph nodes delegate all lookup, hard filtering, and scoring to MatchingService."""

import asyncio
import logging
import time

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from componentmatch.agent.clarification import clarification_fields
from componentmatch.db.repositories import DataInvalidError
from componentmatch.llm.client import LLMFailure
from componentmatch.llm.explainer import (
    EXPLAIN_SYSTEM,
    allowed_reasons,
    explanation_payload,
    render_explanations,
    validate_plan,
)
from componentmatch.llm.parser import PARSE_SYSTEM, normalize_draft, validate_draft_sources
from componentmatch_contracts.agent import (
    AgentMetadata,
    AgentResult,
    ExplanationPlan,
    NodeTrace,
    RequirementDraft,
)
from componentmatch_contracts.result import MatchError

logger = logging.getLogger("componentmatch.agent")


class Nodes:
    def __init__(self, matching, model):
        self.matching, self.model = matching, model

    def guarded(self, name):
        async def run(state):
            started = time.monotonic()
            exception_type = "none"
            try:
                bounded = name not in {"explain_results", "handle_error", "finalize_response"}
                if bounded and started >= state["deadline"]:
                    raise LLMFailure("AGENT_TIMEOUT", http_status=504)
                update = await getattr(self, name)(state)
                # Synchronous validation/scoring cannot be preempted; discard late outcomes.
                if bounded and time.monotonic() >= state["deadline"]:
                    raise LLMFailure("AGENT_TIMEOUT", http_status=504)
            except LLMFailure as exc:
                exception_type = type(exc).__name__
                update = {
                    "status": "error",
                    "error": MatchError(
                        code=exc.code,
                        message="模型或请求处理失败，请检查配置或稍后重试；可使用结构化接口",
                    ),
                    "http_status": exc.http_status,
                }
            except (DataInvalidError, ValidationError) as exc:
                exception_type = type(exc).__name__
                update = {
                    "status": "error",
                    "error": MatchError(code="DATA_INVALID", message="数据或结果契约无效"),
                    "http_status": 500,
                }
            except SQLAlchemyError as exc:
                exception_type = type(exc).__name__
                update = {
                    "status": "error",
                    "error": MatchError(
                        code="DATABASE_ERROR", message="数据库不可用，请检查初始化与连接配置"
                    ),
                    "http_status": 500,
                }
            except Exception as exc:
                exception_type = type(exc).__name__
                update = {
                    "status": "error",
                    "error": MatchError(code="INTERNAL_ERROR", message="工作流内部错误"),
                    "http_status": 500,
                }
            trace = NodeTrace(
                node=name,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
                status=update.get("status", state.get("status", "running")),
            )
            traces = [*state["node_trace"], trace]
            update["node_trace"] = traces
            error = update.get("error") or state.get("error")
            prepared = update.get("prepared") or state.get("prepared")
            log = logger.warning if error else logger.info
            log(
                "agent_node request_id=%s node=%s duration_ms=%.3f status=%s "
                "error_code=%s exception_type=%s candidates=%s fallback=%s",
                state["request_id"],
                name,
                trace.duration_ms,
                trace.status,
                error.code if error else "none",
                exception_type,
                len(prepared.snapshot) if prepared else 0,
                update.get("explanation_fallback_reason", "none"),
            )
            if "response" in update:
                update["response"] = update["response"].model_copy(
                    update={"node_trace": tuple(traces)}
                )
            return update

        return run

    async def parse_request(self, state):
        request = state["request"]
        draft = await self.model.complete(
            RequirementDraft,
            phase="parse",
            system=PARSE_SYSTEM,
            payload={
                "text": request.text,
                "confirmed_fields": request.confirmed_fields.model_dump(exclude_unset=True),
                "business_time": state["business_time"].isoformat(),
                "business_timezone": "Asia/Shanghai",
                "schema": RequirementDraft.model_json_schema(),
            },
            deadline=state["deadline"],
            calls=state["llm_calls"],
            validate=lambda d: validate_draft_sources(d, request.text),
        )
        return {"draft": draft}

    async def validate_request(self, state):
        requirement, questions, unsupported, evidence, defaults = normalize_draft(
            state["draft"], state["request"], now=state["business_time"]
        )
        output = {
            "requirement": requirement,
            "clarification_questions": questions,
            "unsupported_constraints": unsupported,
            "extraction_evidence": evidence,
            "applied_defaults": defaults,
            "clarification_fields": clarification_fields(questions),
        }
        if unsupported:
            output.update(
                status="error",
                http_status=422,
                error=MatchError(
                    code="UNSUPPORTED_CONSTRAINT", message="存在本版无法验证的硬条件，未执行匹配"
                ),
            )
        elif questions:
            output["status"] = "needs_clarification"
        return output

    async def retrieve_candidates(self, state):
        try:
            async with asyncio.timeout(max(0, state["deadline"] - time.monotonic())):
                prepared = await asyncio.to_thread(
                    self.matching.prepare, state["requirement"], request_id=state["request_id"]
                )
        except TimeoutError:
            # Cancellation ends the await, not the underlying read-only worker/thread.
            raise LLMFailure("AGENT_TIMEOUT", http_status=504) from None
        output = {"prepared": prepared}
        current, questions, *_ = normalize_draft(state["draft"], state["request"], now=prepared.now)
        if current != state["requirement"]:
            return {
                **output,
                "status": "needs_clarification",
                "clarification_questions": questions
                or ("业务日期或截止时刻已变化，请重新确认交期",),
            }
        if prepared.early_result is not None:
            output.update(
                match_result=prepared.early_result,
                status=prepared.early_result.status,
                clarification_questions=prepared.early_result.clarification_questions,
                clarification_fields=("manufacturer",)
                if prepared.early_result.status == "needs_clarification"
                else (),
            )
        elif not prepared.snapshot:
            output["status"] = "no_match"
        return output

    async def filter_candidates(self, state):
        filtered = self.matching.filter_candidates(state["prepared"])
        return {"filtered": filtered, **({"status": "no_match"} if not filtered.eligible else {})}

    async def score_and_rank(self, state):
        result = self.matching.score_and_rank(state["filtered"])
        return {"match_result": result, "status": result.status}

    async def request_clarification(self, state):
        return {"status": "needs_clarification"}

    async def build_no_match(self, state):
        result = self.matching.build_no_match(state.get("filtered") or state["prepared"])
        return {"match_result": result, "status": "no_match"}

    async def explain_results(self, state):
        result = state["match_result"]
        if any(not allowed_reasons(row) for row in result.recommendations):
            return {
                "explanations": render_explanations(result),
                "explanation_mode": "template",
                "explanation_fallback_reason": "EXPLANATION_NO_SUPPORTED_REASONS",
            }
        try:
            plan = await self.model.complete(
                ExplanationPlan,
                phase="explain",
                system=EXPLAIN_SYSTEM,
                payload={
                    **explanation_payload(result),
                    "schema": ExplanationPlan.model_json_schema(),
                },
                deadline=state["deadline"],
                calls=state["llm_calls"],
                validate=lambda p: validate_plan(p, result),
            )
            explanations = render_explanations(result, plan)
            return {"explanations": explanations, "explanation_mode": "llm"}
        except Exception as exc:
            reason = exc.code if isinstance(exc, LLMFailure) else "EXPLANATION_FAILED"
            return {
                "explanations": render_explanations(result),
                "explanation_mode": "template",
                "explanation_fallback_reason": reason,
            }

    async def handle_error(self, state):
        return {"status": "error"}

    async def finalize_response(self, state):
        result = state.get("match_result")
        output = dict(
            request_id=state["request_id"],
            status=state["status"],
            requirement=state.get("requirement"),
            draft=state.get("draft"),
            extraction_evidence=state.get("extraction_evidence", ()),
            applied_defaults=state.get("applied_defaults", ()),
            clarification_questions=state.get("clarification_questions", ()),
            clarification_fields=state.get("clarification_fields", ()),
            unsupported_constraints=state.get("unsupported_constraints", ()),
            error=state.get("error"),
            llm_calls=tuple(state["llm_calls"]),
            explanations=state.get("explanations", ()),
            explanation_mode=state.get("explanation_mode", "none"),
            explanation_fallback_reason=state.get("explanation_fallback_reason"),
        )
        if result is not None:
            metadata = (
                AgentMetadata(
                    **(
                        result.metadata.model_dump()
                        | {
                            "explanation_mode": state.get("explanation_mode", "none"),
                            "model_name": self.model.transport.model_name,
                        }
                    )
                )
                if result.metadata is not None
                else None
            )
            output.update(
                metadata=metadata,
                exclusion_summary=result.exclusion_summary,
                rejected_offers=result.rejected_offers,
                warnings=result.warnings,
            )
            if state["status"] == "success":
                output["recommendations"] = result.recommendations
        return {"response": AgentResult(**output)}
