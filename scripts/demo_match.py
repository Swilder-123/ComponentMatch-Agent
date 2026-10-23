"""Three real deterministic service invocations on current-time DEMO data."""

import argparse
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

from componentmatch.core.config import Settings
from componentmatch.db.session import make_engine
from componentmatch.services.matching import MatchingService
from componentmatch_contracts.requirement import ProcurementRequirement


def run_scenarios(service):
    base = dict(
        part_number="LM358DR",
        manufacturer="TI",
        quantity=1000,
        delivery_mode="within_days",
        max_delivery_days=7,
        required_certifications=("ISO9001",),
    )
    results = {}
    for profile in ("balanced", "cost", "quality"):
        result = service.match(ProcurementRequirement(**base, preference_profile=profile))
        results[profile] = {
            "status": result.status,
            "error": result.error.model_dump() if result.error else None,
            "ranking": [
                {
                    "supplier_id": row.supplier_id,
                    "name": row.supplier_name,
                    "score": str(row.total_score),
                    "unit_price_cents": row.unit_price_cents,
                }
                for row in result.recommendations
            ],
        }
    result = service.match(ProcurementRequirement(**base, max_unit_price_cents=1))
    results["strict_budget"] = {
        "status": result.status,
        "recommendations": [r.supplier_id for r in result.recommendations],
        "error": result.error.model_dump() if result.error else None,
        "exclusion_reasons": result.exclusion_summary.reason_counts,
    }
    return {
        "data_label": "DEMO",
        "clock_mode": service.mode,
        "business_time": result.metadata.business_time.isoformat() if result.metadata else None,
        "dataset_snapshot_time": (
            result.metadata.dataset_snapshot_time.isoformat() if result.metadata else None
        ),
        "scenarios": results,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="DEMO only, actual current business time")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    env = dotenv_values(Path(__file__).resolve().parents[1] / ".env", interpolate=False)
    engine = make_engine(args.database_url or env.get("DATABASE_URL") or Settings().database_url)
    try:
        output = run_scenarios(MatchingService(engine))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        if (
            any(
                output["scenarios"][p]["status"] != "success"
                for p in ("balanced", "cost", "quality")
            )
            or output["scenarios"]["strict_budget"]["status"] != "no_match"
        ):
            raise SystemExit(
                "DEMO scenarios not satisfied: inspect errors or stale data; no clock reset"
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
