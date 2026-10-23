"""Explicit test transport. Responses are not real DeepSeek compatibility evidence."""

import copy
import json

from componentmatch.llm.client import LLMReply

TEXT = (
    "采购TI的LM358DR，1000片，7天内到货，单价不超过1.2元，"
    "总预算不超过1200元，必须ISO9001，质量优先。"
)
DRAFT = {
    "manufacturer": "TI",
    "part_number": "LM358DR",
    "quantity": 1000,
    "delivery_mode": "within_days",
    "max_delivery_days": 7,
    "max_unit_price": {"amount": "1.2", "unit": "CNY_yuan", "quote": "单价不超过1.2元"},
    "total_budget": {"amount": "1200", "unit": "CNY_yuan", "quote": "总预算不超过1200元"},
    "required_certifications": ["ISO9001"],
    "preference_profile": "quality",
    "field_evidence": {
        "manufacturer": "TI",
        "part_number": "LM358DR",
        "quantity": "1000片",
        "delivery_mode": "7天内到货",
        "max_delivery_days": "7天内到货",
        "max_unit_price_cents": "单价不超过1.2元",
        "total_budget_cents": "总预算不超过1200元",
        "required_certifications": "ISO9001",
        "preference_profile": "质量优先",
    },
}


def valid_plan(payload):
    return {
        "suppliers": [
            {
                "supplier_id": row["supplier_id"],
                "reasons": [
                    {"metric": d["metric"], "evidence_ids": d["evidence_ids"]}
                    for d in row["allowed_reasons"][:2]
                ],
                "risk_codes": row["risk_codes"],
            }
            for row in payload["suppliers"]
        ]
    }


class FakeTransport:
    source = "mock"
    model_name = "test-only-fake"

    def __init__(self, draft=None, *, parse_error=None, explain=None):
        self.draft = copy.deepcopy(DRAFT if draft is None else draft)
        self.parse_error, self.explain = parse_error, explain
        self.calls = []

    async def generate(self, system, payload, timeout):
        data = json.loads(payload)
        phase = "parse" if "text" in data else "explain"
        self.calls.append(phase)
        if phase == "parse":
            if self.parse_error:
                raise self.parse_error
            output = self.draft
        elif isinstance(self.explain, Exception):
            raise self.explain
        else:
            output = self.explain(data) if self.explain else valid_plan(data)
        return LLMReply(json.dumps(output), usage={"input_tokens": 10, "output_tokens": 5})
