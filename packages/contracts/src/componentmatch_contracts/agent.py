"""Separate natural-language contracts; the phase-2 API remains unchanged."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator

from componentmatch_contracts.requirement import MoneyLimit, ProcurementRequirement, Profile
from componentmatch_contracts.result import (
    Contract,
    ExclusionSummary,
    MatchError,
    MatchMetadata,
    MatchResult,
    Recommendation,
    RejectedOffer,
)

FieldName = Literal[
    "manufacturer",
    "part_number",
    "quantity",
    "delivery_mode",
    "max_delivery_days",
    "max_unit_price_cents",
    "total_budget_cents",
    "currency",
    "required_certifications",
    "preference_profile",
]


class ConfirmedFields(Contract):
    manufacturer: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    part_number: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    quantity: Annotated[StrictInt, Field(gt=0, le=1_000_000_000)] | None = None
    delivery_mode: Literal["unspecified", "within_days", "unconstrained"] | None = None
    max_delivery_days: Annotated[StrictInt, Field(ge=0, le=3650)] | None = None
    max_unit_price_cents: MoneyLimit | None = None
    total_budget_cents: MoneyLimit | None = None
    currency: Literal["CNY"] | None = None
    required_certifications: tuple[Literal["ISO9001"], ...] | None = None
    preference_profile: Profile | None = None


class AgentRequest(Contract):
    text: StrictStr = Field(min_length=1, max_length=2000)
    confirmed_fields: ConfirmedFields = Field(default_factory=ConfirmedFields)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("采购需求不能为空")
        return value


class MoneyMention(Contract):
    amount: StrictStr = Field(pattern=r"^\d{1,19}(?:\.\d{1,8})?$")
    unit: Literal["CNY_yuan", "CNY_cent"]
    quote: StrictStr = Field(min_length=1, max_length=2000)


class ConstraintIssue(Contract):
    field: FieldName | None = None
    quote: StrictStr = Field(min_length=1, max_length=2000)
    message: StrictStr = Field(min_length=1, max_length=300)


class RequirementDraft(Contract):
    manufacturer: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    part_number: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    quantity: Annotated[StrictInt, Field(gt=0, le=1_000_000_000)] | None = None
    delivery_mode: Literal["within_days", "unconstrained"] | None = None
    max_delivery_days: Annotated[StrictInt, Field(ge=0, le=3650)] | None = None
    max_unit_price: MoneyMention | None = None
    total_budget: MoneyMention | None = None
    currency: StrictStr | None = None
    required_certifications: tuple[StrictStr, ...] | None = None
    preference_profile: Profile | None = None
    field_evidence: dict[FieldName, StrictStr] = Field(default_factory=dict)
    ambiguous_constraints: tuple[ConstraintIssue, ...] = ()
    unhandled_constraints: tuple[ConstraintIssue, ...] = ()


class ExtractionEvidence(Contract):
    field: FieldName
    source: Literal["text", "confirmed_fields"]
    quote: str


class LLMCallRecord(Contract):
    phase: Literal["parse", "explain"]
    attempt: int
    source: Literal["deepseek", "mock"]
    model_name: str
    outcome: Literal["success", "error"]
    error_code: str | None = None
    duration_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None


class ExplanationReason(Contract):
    metric: Literal["price", "delivery", "quality", "on_time", "response"]
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class ExplanationChoice(Contract):
    supplier_id: StrictInt
    reasons: tuple[ExplanationReason, ...] = Field(min_length=1, max_length=5)
    risk_codes: tuple[str, ...]


class ExplanationPlan(Contract):
    suppliers: tuple[ExplanationChoice, ...] = Field(min_length=1, max_length=3)


class SupplierExplanation(Contract):
    supplier_id: int
    rank: int
    reasons: tuple[str, ...]
    risk_messages: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    data_label: Literal["DEMO"] = "DEMO"


class NodeTrace(Contract):
    node: str
    duration_ms: float
    status: str


class AgentMetadata(MatchMetadata):
    explanation_mode: Literal["llm", "template", "none"] = "none"
    model_name: str | None = None


class AgentResult(Contract):
    request_id: str
    input_mode: Literal["natural_language"] = "natural_language"
    status: Literal["success", "needs_clarification", "no_match", "error"]
    requirement: ProcurementRequirement | None = None
    draft: RequirementDraft | None = None
    extraction_evidence: tuple[ExtractionEvidence, ...] = ()
    applied_defaults: tuple[str, ...] = ()
    clarification_questions: tuple[str, ...] = ()
    clarification_fields: tuple[FieldName, ...] = ()
    unsupported_constraints: tuple[ConstraintIssue, ...] = ()
    recommendations: tuple[Recommendation, ...] = Field(default=(), max_length=3)
    rejected_offers: tuple[RejectedOffer, ...] = ()
    exclusion_summary: ExclusionSummary = Field(default_factory=ExclusionSummary)
    metadata: AgentMetadata | None = None
    explanations: tuple[SupplierExplanation, ...] = ()
    explanation_mode: Literal["llm", "template", "none"] = "none"
    explanation_fallback_reason: str | None = None
    llm_calls: tuple[LLMCallRecord, ...] = ()
    node_trace: tuple[NodeTrace, ...] = ()
    warnings: tuple[str, ...] = MatchResult.model_fields["warnings"].default
    error: MatchError | None = None
    data_label: Literal["DEMO"] = "DEMO"

    @model_validator(mode="after")
    def check_outcome(self):
        if (self.status == "success") != bool(self.recommendations):
            raise ValueError("Success must contain recommendations; other outcomes must not")
        if (self.status == "error") != (self.error is not None):
            raise ValueError("Error must agree with status")
        if self.status == "needs_clarification" and not self.clarification_questions:
            raise ValueError("Clarification requires questions")
        if self.status == "success":
            if self.requirement is None or self.metadata is None:
                raise ValueError("Successful matching requires requirement and provenance")
            # Reuse all phase-2 consistency checks; do not create a parallel scoring contract.
            matching_metadata = MatchMetadata.model_validate(
                self.metadata.model_dump()
                | {
                    "explanation_mode": "none",
                    "model_name": None,
                }
            )
            MatchResult(
                request_id=self.request_id,
                status="success",
                requirement=self.requirement,
                recommendations=self.recommendations,
                metadata=matching_metadata,
            )
            if self.metadata.explanation_mode != self.explanation_mode:
                raise ValueError("Explanation mode and metadata must agree")
            if [(e.supplier_id, e.rank) for e in self.explanations] != [
                (r.supplier_id, r.rank) for r in self.recommendations
            ]:
                raise ValueError("Explanations must preserve the exact recommendation order")
            if self.explanation_mode == "llm" and not any(
                c.phase == "explain" and c.outcome == "success" for c in self.llm_calls
            ):
                raise ValueError("LLM explanation requires a recorded successful model call")
        return self
