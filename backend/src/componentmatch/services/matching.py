"""Structured requirement -> SQLite snapshot -> hard rules -> deterministic Top 3."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from componentmatch_contracts.requirement import ProcurementRequirement
from componentmatch_contracts.result import (
    ExclusionSummary,
    MatchError,
    MatchMetadata,
    MatchResult,
    RejectedOffer,
)
from pydantic import ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from componentmatch.core.clock import FixedClock, business_date
from componentmatch.db import repositories
from componentmatch.schemas.snapshot import Candidate
from componentmatch.scoring.constraints import hard_failures
from componentmatch.scoring.engine import ranking_key, score_candidate
from componentmatch.scoring.weights import RULE_VERSION, weights_for


@dataclass(frozen=True)
class PreparedMatch:
    requirement: ProcurementRequirement
    request_id: str
    now: datetime
    metadata: MatchMetadata | None
    has_component: bool
    snapshot: tuple[Candidate, ...] = ()
    early_result: MatchResult | None = None


@dataclass(frozen=True)
class FilteredMatch:
    prepared: PreparedMatch
    eligible: tuple[Candidate, ...]
    rejected: tuple[RejectedOffer, ...]


class MatchingService:
    def __init__(
        self,
        engine: Engine,
        *,
        mode: Literal["business", "test"] = "business",
        clock: FixedClock | None = None,
    ):
        if mode not in {"business", "test"} or (mode == "test") != (clock is not None):
            raise ValueError("Only explicit test mode accepts and requires a FixedClock")
        self.engine, self.mode, self.clock = engine, mode, clock

    def prepare(
        self, requirement: ProcurementRequirement, *, request_id: str | None = None
    ) -> PreparedMatch:
        if not isinstance(requirement, ProcurementRequirement):
            raise TypeError("Validate input with ProcurementRequirement first")
        executed_at = datetime.now(UTC)
        now = self.clock.now() if self.clock is not None else executed_at
        request_id = request_id or str(uuid4())
        weights = weights_for(requirement.preference_profile)
        base = dict(request_id=request_id, requirement=requirement)
        if requirement.delivery_mode == "unspecified":
            early = MatchResult(
                **base,
                status="needs_clarification",
                clarification_questions=("请提供到货自然日上限，或明确交期不限（unconstrained）",),
            )
            return PreparedMatch(requirement, request_id, now, None, False, early_result=early)
        with Session(self.engine) as session, session.begin():
            info = repositories.metadata(session)
            meta = MatchMetadata(
                dataset_version=info.dataset_version,
                schema_version=info.schema_version,
                dataset_snapshot_time=info.business_time,
                business_time=now,
                business_date=business_date(now),
                executed_at=executed_at,
                clock_mode=self.mode,
                rule_version=RULE_VERSION,
                weights=weights,
            )
            components = repositories.find_components(
                session, requirement.part_number, requirement.manufacturer
            )
            if any(not c.is_mock for c in components):
                raise repositories.DataInvalidError("Catalog contains non-DEMO records")
            if len(components) > 1:
                early = MatchResult(
                    **base,
                    status="needs_clarification",
                    metadata=meta,
                    clarification_questions=("同名完整料号存在多个制造商，请明确制造商",),
                )
                return PreparedMatch(requirement, request_id, now, meta, True, early_result=early)
            snapshot = repositories.candidates(session, components[0]) if components else ()
        return PreparedMatch(requirement, request_id, now, meta, bool(components), snapshot)

    def filter_candidates(self, prepared: PreparedMatch) -> FilteredMatch:
        rejected, eligible = [], []
        for candidate in prepared.snapshot:
            failures = hard_failures(candidate, prepared.requirement, prepared.now)
            if failures:
                rejected.append(
                    RejectedOffer(
                        supplier_id=candidate.supplier.id,
                        supplier_name=candidate.supplier.name,
                        offer_id=candidate.offer.id,
                        reasons=failures,
                    )
                )
            else:
                eligible.append(candidate)
        return FilteredMatch(prepared, tuple(eligible), tuple(rejected))

    def score_and_rank(self, filtered: FilteredMatch) -> MatchResult:
        prepared = filtered.prepared
        weights = weights_for(prepared.requirement.preference_profile)
        scored = sorted(
            (
                score_candidate(c, prepared.requirement, prepared.now, weights)
                for c in filtered.eligible
            ),
            key=ranking_key,
        )
        return self._finish(filtered, scored)

    def build_no_match(self, value: PreparedMatch | FilteredMatch) -> MatchResult:
        filtered = value if isinstance(value, FilteredMatch) else FilteredMatch(value, (), ())
        if filtered.eligible or (isinstance(value, PreparedMatch) and value.snapshot):
            raise ValueError("No-match branch cannot discard unfiltered/eligible offers")
        return self._finish(filtered, ())

    def _finish(self, filtered, scored) -> MatchResult:
        prepared = filtered.prepared
        best = {}
        for row in scored:
            best.setdefault(row.supplier_id, row)
        top = tuple(
            row.model_copy(update={"rank": i})
            for i, row in enumerate(list(best.values())[:3], start=1)
        )
        counts = Counter(
            code for row in filtered.rejected for code in {r.code for r in row.reasons}
        )
        summary = ExclusionSummary(
            retrieved_offers=len(prepared.snapshot),
            eligible_offers=len(filtered.eligible),
            eligible_suppliers=len(best),
            reason_counts=dict(sorted(counts.items())),
        )
        warnings = list(MatchResult.model_fields["warnings"].default)
        if not prepared.has_component:
            warnings.append("CATALOG_NOT_FOUND：目录无精确制造商/完整型号，不推荐相似替代")
        elif not prepared.snapshot:
            warnings.append("NO_OFFERS：该精确型号没有供货记录")
        elif not top:
            warnings.append("NO_ELIGIBLE_OFFERS：全部报价未通过硬约束，条件未放宽")
        result = MatchResult(
            request_id=prepared.request_id,
            requirement=prepared.requirement,
            status="success" if top else "no_match",
            recommendations=top,
            rejected_offers=filtered.rejected,
            exclusion_summary=summary,
            metadata=prepared.metadata,
            warnings=tuple(warnings),
        )
        return MatchResult.model_validate(result.model_dump())

    def match(self, requirement: ProcurementRequirement) -> MatchResult:
        if not isinstance(requirement, ProcurementRequirement):
            raise TypeError("Validate input with ProcurementRequirement first")
        base = dict(request_id=str(uuid4()), requirement=requirement)
        try:
            prepared = self.prepare(requirement, request_id=base["request_id"])
            if prepared.early_result is not None:
                return prepared.early_result
            return self.score_and_rank(self.filter_candidates(prepared))
        except (repositories.DataInvalidError, ValidationError) as exc:
            return MatchResult(
                **base,
                status="error",
                error=MatchError(
                    code="DATA_INVALID", message=f"DEMO 数据或结果契约无效（{type(exc).__name__}）"
                ),
            )
        except SQLAlchemyError:
            return MatchResult(
                **base,
                status="error",
                error=MatchError(
                    code="DATABASE_ERROR", message="数据库读取失败，请检查路径并显式执行初始化脚本"
                ),
            )
