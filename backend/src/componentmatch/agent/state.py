"""Request-local graph state contains DTOs only, never sessions, clients, or credentials."""

from datetime import datetime
from typing import TypedDict

from componentmatch_contracts.agent import (
    AgentRequest,
    AgentResult,
    ConstraintIssue,
    ExtractionEvidence,
    FieldName,
    LLMCallRecord,
    NodeTrace,
    RequirementDraft,
    SupplierExplanation,
)
from componentmatch_contracts.requirement import ProcurementRequirement
from componentmatch_contracts.result import MatchError, MatchResult

from componentmatch.services.matching import FilteredMatch, PreparedMatch


class MatchState(TypedDict, total=False):
    request_id: str
    request: AgentRequest
    deadline: float
    business_time: datetime
    draft: RequirementDraft
    requirement: ProcurementRequirement | None
    extraction_evidence: tuple[ExtractionEvidence, ...]
    applied_defaults: tuple[str, ...]
    clarification_questions: tuple[str, ...]
    clarification_fields: tuple[FieldName, ...]
    unsupported_constraints: tuple[ConstraintIssue, ...]
    prepared: PreparedMatch
    filtered: FilteredMatch
    match_result: MatchResult
    status: str
    error: MatchError
    http_status: int
    explanations: tuple[SupplierExplanation, ...]
    explanation_mode: str
    explanation_fallback_reason: str | None
    llm_calls: list[LLMCallRecord]
    node_trace: list[NodeTrace]
    response: AgentResult
