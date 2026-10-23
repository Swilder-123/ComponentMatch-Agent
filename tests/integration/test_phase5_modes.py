"""Structured backend remains available independently of the Agent-only frontend."""

from unittest.mock import Mock

import pytest
from componentmatch.api.main import app as api
from componentmatch.api.routes import get_matching_service
from componentmatch.llm.client import DeepSeekTransport, JSONModel
from componentmatch_contracts.result import MatchResult
from fastapi.testclient import TestClient


@pytest.mark.parametrize("profile", ["balanced", "cost", "quality"])
def test_rule_http_endpoint_matches_service_with_zero_model_calls(
    service, build_requirement, monkeypatch, profile
):
    guard = Mock(side_effect=AssertionError("Structured backend must not call a model"))
    monkeypatch.setattr(JSONModel, "complete", guard)
    monkeypatch.setattr(DeepSeekTransport, "__init__", guard)
    api.dependency_overrides[get_matching_service] = lambda: service
    requirement = build_requirement(preference_profile=profile)
    try:
        with TestClient(api) as backend:
            response = backend.post(
                "/api/v1/matches",
                json={
                    "input_mode": "structured",
                    "requirement": requirement.model_dump(mode="json"),
                },
            )
        assert response.status_code == 200
        result = MatchResult.model_validate(response.json())
        assert result.recommendations == service.match(requirement).recommendations
        assert guard.call_count == 0
    finally:
        api.dependency_overrides.clear()
