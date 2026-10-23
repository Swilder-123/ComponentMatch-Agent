"""Offline preflight by default; real workflow checks require --allow-paid-api."""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy.engine import make_url

from componentmatch.agent.graph import AgentWorkflow
from componentmatch.core.config import Settings
from componentmatch.db.session import make_engine
from componentmatch.llm.client import DeepSeekTransport, JSONModel, LLMFailure
from componentmatch.services.matching import MatchingService
from componentmatch_contracts.agent import AgentRequest, AgentResult
from componentmatch_contracts.requirement import ProcurementRequirement

NORMAL_TEXT = (
    "采购TI的LM358DR，1000片，7天内到货，单价不超过1.2元，"
    "总预算不超过1200元，必须ISO9001，质量优先。"
)
SCENARIOS = (
    ("normal", NORMAL_TEXT, "success"),
    ("missing", "采购TI的LM358DR", "needs_clarification"),
    ("no_match", NORMAL_TEXT.replace("1.2元", "1分"), "no_match"),
)
OFFICIAL_URLS = {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
MODELS = {"deepseek-flash", "deepseek-v4-pro"}


class LimitedDeepSeekTransport(DeepSeekTransport):
    """Limit real dispatches even if an unexpected branch requests an explanation."""

    dispatch_attempts = 0

    async def generate(self, system, payload, timeout):
        if self.dispatch_attempts >= 4:
            raise LLMFailure("LIVE_CALL_LIMIT")
        self.dispatch_attempts += 1
        return await super().generate(system, payload, timeout)


def expected_requirement(name):
    return ProcurementRequirement(
        manufacturer="TI",
        part_number="LM358DR",
        quantity=1000,
        delivery_mode="within_days",
        max_delivery_days=7,
        max_unit_price_cents=1 if name == "no_match" else 120,
        total_budget_cents=120000,
        required_certifications=("ISO9001",),
        preference_profile="quality",
    )


def validate_result(name, expected_status, result, http_status, baseline, model_name):
    """Return only check names/booleans; never serialize model text or exception bodies."""
    result = AgentResult.model_validate(result.model_dump())
    checks = {
        "schema": True,
        "request_id": bool(UUID(result.request_id)),
        "http_status": http_status == 200,
        "status": result.status == expected_status,
        "demo_label": result.data_label == "DEMO",
        "real_transport": bool(result.llm_calls)
        and all(c.source == "deepseek" and c.model_name == model_name for c in result.llm_calls),
        "calls_succeeded": all(c.outcome == "success" for c in result.llm_calls),
        "no_retries": all(c.attempt == 1 for c in result.llm_calls),
        "call_phases": [c.phase for c in result.llm_calls]
        == (["parse", "explain"] if name == "normal" else ["parse"]),
        "source_quotes": bool(result.extraction_evidence)
        and all(
            e.source == "text" and e.quote in dict((n, t) for n, t, _ in SCENARIOS)[name]
            for e in result.extraction_evidence
        ),
    }
    if name == "missing":
        checks.update(
            missing_fields_preserved=result.requirement is None
            and result.draft is not None
            and result.draft.quantity is None
            and result.draft.max_delivery_days is None,
            clarification=bool(result.clarification_questions),
            no_recommendations=not result.recommendations and not result.explanations,
            explanation_mode=result.explanation_mode == "none",
        )
    else:
        checks.update(
            requirement=result.requirement == expected_requirement(name),
            rankings_scores_evidence_risks=result.recommendations == baseline.recommendations,
            exclusions=result.rejected_offers == baseline.rejected_offers
            and result.exclusion_summary == baseline.exclusion_summary,
            warnings=result.warnings == baseline.warnings,
            same_business_date=result.metadata is not None
            and result.metadata.business_date == baseline.metadata.business_date,
            provenance=result.metadata is not None
            and result.metadata.clock_mode == "business"
            and result.metadata.weights == baseline.metadata.weights
            and result.metadata.rule_version == baseline.metadata.rule_version
            and result.metadata.dataset_snapshot_time == baseline.metadata.dataset_snapshot_time,
            explanation_mode=result.explanation_mode == ("llm" if name == "normal" else "none"),
        )
        checks["explanation_evidence_and_risks"] = all(
            set(explanation.evidence_ids) <= {e.evidence_id for e in row.evidence}
            and explanation.risk_messages == tuple(r.message for r in row.risks)
            for explanation, row in zip(result.explanations, result.recommendations, strict=True)
        )
    return checks


async def check(*, allow_paid_api=False):
    # Malformed settings must never produce a traceback containing input values.
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "mode": "live" if allow_paid_api else "preflight",
        "status": "blocked",
        "compatibility_verified": False,
        "transport_attempts": 0,
        "billed_amount": None,
        "billing_note": "Attempts/token usage do not establish billed requests or monetary charges",
    }
    engine = None
    try:
        settings = Settings().model_copy(update={"llm_max_retries": 0})
        key = settings.deepseek_api_key.get_secret_value() if settings.deepseek_api_key else ""
        configured = bool(key.strip()) and key.strip().lower() not in {
            "your-api-key",
            "your_deepseek_api_key",
            "<your_api_key>",
        }
        official = settings.deepseek_base_url.rstrip("/") in OFFICIAL_URLS
        known_model = settings.deepseek_model in MODELS
        report["configuration"] = {
            "key_present": configured,
            "official_endpoint": official,
            "model": settings.deepseek_model if known_model else "UNAPPROVED_MODEL",
            "base_url": settings.deepseek_base_url.rstrip("/") if official else "UNAPPROVED_URL",
            "max_retries": 0,
            "max_transport_attempts": 4,
            "llm_timeout_seconds": settings.llm_timeout_seconds,
            "agent_timeout_seconds": settings.agent_timeout_seconds,
            "max_tokens": settings.llm_max_tokens,
        }
        if not official or not known_model:
            report["error_code"] = "UNAPPROVED_PROVIDER_CONFIGURATION"
            return report
        url = make_url(settings.database_url)
        if url.drivername != "sqlite" or not url.database or not Path(url.database).is_file():
            report["error_code"] = "LOCAL_SQLITE_DATABASE_REQUIRED"
            return report
        engine = make_engine(settings.database_url)
        service = MatchingService(engine)
        baselines = {
            name: service.match(expected_requirement(name)) for name in ("normal", "no_match")
        }
        report["database_checks"] = {
            name: baseline.status == ("success" if name == "normal" else "no_match")
            and baseline.metadata is not None
            and baseline.metadata.clock_mode == "business"
            for name, baseline in baselines.items()
        }
        report["database_checks"]["normal_top3"] = len(baselines["normal"].recommendations) == 3
        report["database_checks"]["no_match_retrieved_offers"] = (
            baselines["no_match"].exclusion_summary.retrieved_offers > 0
        )
        if not all(report["database_checks"].values()):
            report["error_code"] = "DEMO_SCENARIO_PREFLIGHT_FAILED"
            return report
        report["local_checks_passed"] = True
        if not allow_paid_api:
            report["status"] = "awaiting_approval" if configured else "needs_configuration"
            return report
        if not configured:
            report["error_code"] = "CONFIG_MISSING"
            return report
        report["scenarios"] = []
        # Official HTTPS only, no environment proxies or redirects, and no fake runtime transport.
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
            with httpx.Client(trust_env=False, follow_redirects=False) as sync_http:
                transport = LimitedDeepSeekTransport(
                    settings, http_client=sync_http, http_async_client=http
                )
                workflow = AgentWorkflow(service, JSONModel(transport, settings))
                for name, text, status in SCENARIOS:
                    started = time.monotonic()
                    result, http_status = await workflow.run(AgentRequest(text=text))
                    report["transport_attempts"] = transport.dispatch_attempts
                    try:
                        checks = validate_result(
                            name,
                            status,
                            result,
                            http_status,
                            baselines.get(name),
                            settings.deepseek_model,
                        )
                    except Exception:
                        checks = {"response_validation": False}
                    row = {
                        "scenario": name,
                        "status": result.status,
                        "http_status": http_status,
                        "request_id": result.request_id,
                        "duration_ms": round((time.monotonic() - started) * 1000, 3),
                        "checks": checks,
                        "passed": all(checks.values()),
                        "explanation_mode": result.explanation_mode,
                        "error_code": result.error.code if result.error else None,
                        "fallback_reason": result.explanation_fallback_reason,
                        "calls": [c.model_dump() for c in result.llm_calls],
                    }
                    report["scenarios"].append(row)
                    if not row["passed"]:
                        report["status"] = "failed"
                        return report
        report["status"] = "passed"
        report["compatibility_verified"] = True
        return report
    except Exception:
        report["status"] = "failed"
        report["error_code"] = "CHECK_FAILED_REVIEW_CONFIGURATION_OR_RESULT"
        return report
    finally:
        if engine is not None:
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-paid-api",
        action="store_true",
        help="Approve three real scenarios, at most four transport attempts, no retries",
    )
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    report = asyncio.run(check(allow_paid_api=args.allow_paid_api))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"passed", "awaiting_approval", "needs_configuration"} else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
