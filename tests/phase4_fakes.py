"""Offline-only fixtures using the real graph and deterministic service. No provider calls."""

import asyncio
import copy

from componentmatch.agent.graph import AgentWorkflow
from componentmatch.core.config import Settings
from componentmatch.llm.client import JSONModel, LLMFailure
from componentmatch_contracts.agent import AgentRequest
from componentmatch_frontend.presentation import PRESETS
from tests.agent_fakes import DRAFT, FakeTransport


def transport_for(text, *, error=False, template=False):
    draft = copy.deepcopy(DRAFT)
    if "1000" not in text:
        draft = {
            "manufacturer": "TI",
            "part_number": "LM358DR",
            "field_evidence": {"manufacturer": "TI", "part_number": "LM358DR"},
        }
    else:
        if "1分" in text:
            draft["max_unit_price"] = {"amount": "1", "unit": "CNY_cent", "quote": "单价不超过1分"}
            draft["field_evidence"]["max_unit_price_cents"] = "单价不超过1分"
        for phrase, profile in (("综合优先", "balanced"), ("成本优先", "cost")):
            if phrase in text:
                draft["preference_profile"] = profile
                draft["field_evidence"]["preference_profile"] = phrase
        for name, evidence_field in (
            ("max_unit_price", "max_unit_price_cents"),
            ("total_budget", "total_budget_cents"),
        ):
            if draft[name]["quote"] not in text:
                draft.pop(name)
                draft["field_evidence"].pop(evidence_field)
        if "ISO9001" not in text:
            draft.pop("required_certifications")
            draft["field_evidence"].pop("required_certifications")
        if draft["field_evidence"]["preference_profile"] not in text:
            draft.pop("preference_profile")
            draft["field_evidence"].pop("preference_profile")
    return FakeTransport(
        draft,
        parse_error=LLMFailure("LLM_TIMEOUT") if error else None,
        explain=LLMFailure("LLM_TIMEOUT") if template else None,
    )


def response_for(service, scenario="质量优先", *, error=False, template=False):
    text = PRESETS[scenario]
    model = JSONModel(
        transport_for(text, error=error, template=template), Settings(llm_max_retries=0)
    )
    return asyncio.run(AgentWorkflow(service, model).run(AgentRequest(text=text)))
