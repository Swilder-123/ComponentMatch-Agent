"""Structured matching and a natural-language agent; database creation is explicit."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from componentmatch import __version__
from componentmatch.api.agent_routes import router as agent_router
from componentmatch.api.routes import get_matching_service, router


@asynccontextmanager
async def lifespan(app):
    app.state.agent_workflow = None
    try:
        yield
    finally:
        workflow = app.state.agent_workflow
        try:
            if workflow is not None:
                await workflow.model.transport.aclose()
        finally:
            app.state.agent_workflow = None
            if get_matching_service.cache_info().currsize:
                get_matching_service().engine.dispose()
                get_matching_service.cache_clear()


app = FastAPI(
    lifespan=lifespan,
    title="ComponentMatch Agent",
    version=__version__,
    description="DEMO deterministic matching and DeepSeek/LangGraph single-agent workflow.",
)
app.include_router(router)
app.include_router(agent_router)


class HealthResponse(BaseModel):
    """Process liveness only; this does not probe the database or model API."""

    status: str = "ok"
    stage: str = "agent_matching"
    version: str = __version__


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
