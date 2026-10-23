"""Opt-in UI verification: real DB/clock/routes, Mock model only, call audit per request."""

import os

from fastapi import Request

from componentmatch.agent.graph import AgentWorkflow
from componentmatch.api.agent_routes import get_agent_workflow
from componentmatch.api.main import app
from componentmatch.api.routes import get_matching_service
from componentmatch.core.config import Settings
from componentmatch.llm.client import DeepSeekTransport, JSONModel
from tests.phase4_fakes import transport_for

if os.getenv("COMPONENTMATCH_OFFLINE_UI_TEST") != "1":
    raise RuntimeError("Explicit offline test switch required")

audit = []
real_attempts = []


async def deny_paid_call(*args, **kwargs):
    real_attempts.append(True)
    raise AssertionError("Paid calls forbidden during UI verification")


DeepSeekTransport.generate = deny_paid_call


async def offline_workflow(request: Request):
    text = (await request.json())["text"]
    fake = transport_for(text, error="测试超时" in text, template="测试解释降级" in text)
    request.state.fake = fake
    return AgentWorkflow(get_matching_service(), JSONModel(fake, Settings(llm_max_retries=0)))


app.dependency_overrides[get_agent_workflow] = offline_workflow


@app.middleware("http")
async def record_calls(request, call_next):
    response = await call_next(request)
    if request.method == "POST":
        fake = getattr(request.state, "fake", None)
        audit.append(
            {
                "path": request.url.path,
                "http_status": response.status_code,
                "mock_model_calls": len(fake.calls) if fake else 0,
                "real_model_attempts": len(real_attempts),
                "authorization_present": "authorization" in request.headers,
            }
        )
    return response


@app.get("/__test__/calls")
def call_records():
    return {"requests": audit, "paid_attempts": len(real_attempts)}
