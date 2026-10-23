"""Auditable result contracts. All amounts are cents; scores retain six decimals."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from componentmatch_contracts.requirement import ProcurementRequirement

Metric = Literal["price", "delivery", "quality", "on_time", "response"]
Score = Annotated[Decimal, Field(ge=0, le=100, allow_inf_nan=False)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(Contract):
    evidence_id: str
    table: str
    record_id: int
    source_label: str = Field(pattern=r"^DEMO:")
    observed_at: AwareDatetime
    fields: dict[str, str | int | bool | None]
    data_label: Literal["DEMO"] = "DEMO"


class Risk(Contract):
    code: str
    message: str
    evidence_ids: tuple[str, ...] = ()


class ExclusionReason(Contract):
    code: str
    message: str
    field: str
    actual: str | int | None = None
    expected: str | int | None = None


class RejectedOffer(Contract):
    supplier_id: int
    supplier_name: str
    offer_id: int
    reasons: tuple[ExclusionReason, ...] = Field(min_length=1)


class DimensionScore(Contract):
    metric: Metric
    raw_value: Decimal | None = Field(allow_inf_nan=False)
    raw_unit: str
    score: Score
    weight: Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]
    contribution: Score
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_contribution(self) -> Self:
        with localcontext() as context:
            context.prec = 40
            expected = (self.score * self.weight).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
        if self.contribution != expected:
            raise ValueError("Contribution must equal rounded score times weight")
        return self


class Recommendation(Contract):
    rank: int = Field(ge=1, le=3)
    supplier_id: int
    supplier_name: str
    offer_id: int
    component_id: int
    manufacturer: str
    part_number: str
    quantity: int = Field(gt=0)
    available_quantity: int = Field(ge=0)
    unit_price_cents: int = Field(gt=0)
    goods_total_cents: int = Field(gt=0)
    currency: Literal["CNY"] = "CNY"
    lead_time_days: int = Field(ge=0)
    total_score: Score
    dimensions: tuple[DimensionScore, ...]
    evidence: tuple[Evidence, ...]
    risks: tuple[Risk, ...]
    data_label: Literal["DEMO"] = "DEMO"

    @model_validator(mode="after")
    def validate_calculation(self) -> Self:
        if self.available_quantity < self.quantity:
            raise ValueError("Stock must cover the exact order quantity")
        if self.goods_total_cents != self.unit_price_cents * self.quantity:
            raise ValueError("Goods total does not match exact order quantity")
        if {d.metric for d in self.dimensions} != {
            "price",
            "delivery",
            "quality",
            "on_time",
            "response",
        } or len(self.dimensions) != 5:
            raise ValueError("Exactly five distinct scoring dimensions required")
        if sum(d.weight for d in self.dimensions) != 1:
            raise ValueError("Weights must sum to one")
        if sum(d.contribution for d in self.dimensions) != self.total_score:
            raise ValueError("Contributions do not match total score")
        ids = {e.evidence_id for e in self.evidence}
        if len(ids) != len(self.evidence):
            raise ValueError("Duplicate evidence id")
        refs = {ref for d in self.dimensions for ref in d.evidence_ids}
        refs.update(ref for risk in self.risks for ref in risk.evidence_ids)
        if not refs <= ids:
            raise ValueError("Evidence reference does not exist")
        return self


class ExclusionSummary(Contract):
    retrieved_offers: int = Field(default=0, ge=0)
    eligible_offers: int = Field(default=0, ge=0)
    eligible_suppliers: int = Field(default=0, ge=0)
    reason_counts: dict[str, int] = Field(default_factory=dict)
    note: str = "按报价记录计数；一条报价可有多个排除原因，各原因之和可大于排除报价数"


class MatchMetadata(Contract):
    data_label: Literal["DEMO"] = "DEMO"
    is_mock: Literal[True] = True
    dataset_version: str
    schema_version: str
    dataset_snapshot_time: AwareDatetime
    business_time: AwareDatetime
    business_date: date
    business_timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    executed_at: AwareDatetime
    clock_mode: Literal["business", "test"]
    rule_version: str
    weights: dict[Metric, Decimal]
    explanation_mode: Literal["none"] = "none"
    model_name: None = None


class MatchError(Contract):
    code: str
    message: str


class MatchResult(Contract):
    request_id: str
    status: Literal["success", "needs_clarification", "no_match", "error"]
    input_mode: Literal["structured"] = "structured"
    requirement: ProcurementRequirement
    clarification_questions: tuple[str, ...] = ()
    recommendations: tuple[Recommendation, ...] = Field(default=(), max_length=3)
    rejected_offers: tuple[RejectedOffer, ...] = ()
    exclusion_summary: ExclusionSummary = Field(default_factory=ExclusionSummary)
    warnings: tuple[str, ...] = (
        "DEMO：所有数据均为虚构，不代表云汉芯城或任何真实企业的库存、报价、资质和评价",
    )
    error: MatchError | None = None
    metadata: MatchMetadata | None = None

    @model_validator(mode="after")
    def check_result(self) -> Self:
        if (self.status == "success") != bool(self.recommendations):
            raise ValueError("Only success contains recommendations, and success must be nonempty")
        if len({r.supplier_id for r in self.recommendations}) != len(self.recommendations):
            raise ValueError("Suppliers must be distinct")
        if [r.rank for r in self.recommendations] != list(range(1, len(self.recommendations) + 1)):
            raise ValueError("Ranks must be consecutive")
        if self.status == "error" and self.error is None:
            raise ValueError("Error detail required")
        if self.status != "error" and self.error is not None:
            raise ValueError("Non-error result cannot carry an error")
        if self.status in {"success", "no_match"} and self.metadata is None:
            raise ValueError("Completed matching requires provenance metadata")
        if self.status == "needs_clarification" and not self.clarification_questions:
            raise ValueError("Clarification questions required")
        return self
