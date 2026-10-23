"""Explicit local visual-test backend. Real HTTP/graph/database, exclusively Mock LLM."""

import os
from pathlib import Path

from fastapi import Request

from componentmatch.agent.graph import AgentWorkflow
from componentmatch.api.agent_routes import get_agent_workflow
from componentmatch.api.main import app
from componentmatch.api.routes import get_matching_service
from componentmatch.core.config import Settings
from componentmatch.db.seed import seed_demo
from componentmatch.db.session import make_engine
from componentmatch.llm.client import JSONModel
from componentmatch.services.matching import MatchingService
from tests.phase4_fakes import transport_for

if os.getenv("COMPONENTMATCH_OFFLINE_UI_TEST") != "1":
    raise RuntimeError("This test-only backend requires an explicit offline UI test environment")

path = Path("logs/phase4/browser-demo.db").resolve()
path.parent.mkdir(parents=True, exist_ok=True)
engine = make_engine(f"sqlite:///{path.as_posix()}")
seed_demo(engine)
service = MatchingService(engine)


async def offline_workflow(request: Request):
    body = await request.json()
    text = body["text"]
    fake = transport_for(text, error="测试超时" in text, template="测试解释降级" in text)
    return AgentWorkflow(service, JSONModel(fake, Settings(llm_max_retries=0)))


app.dependency_overrides[get_matching_service] = lambda: service
app.dependency_overrides[get_agent_workflow] = offline_workflow
