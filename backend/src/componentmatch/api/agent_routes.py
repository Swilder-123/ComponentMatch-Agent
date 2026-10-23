"""Natural-language route with injectable workflow; no fallback fake in runtime code."""

from typing import Annotated

from componentmatch_contracts.agent import AgentRequest, AgentResult
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from componentmatch.agent.graph import AgentWorkflow
from componentmatch.api.routes import get_matching_service
from componentmatch.core.config import Settings
from componentmatch.llm.client import DeepSeekTransport, JSONModel
from componentmatch.services.matching import MatchingService

router = APIRouter(prefix="/api/v1/agent", tags=["single agent"])


async def get_agent_workflow(
    request: Request,
    matching: Annotated[MatchingService, Depends(get_matching_service)],
) -> AgentWorkflow:
    workflow = getattr(request.app.state, "agent_workflow", None)
    if workflow is None:
        settings = Settings()
        workflow = AgentWorkflow(matching, JSONModel(DeepSeekTransport(settings), settings))
        request.app.state.agent_workflow = workflow
    return workflow


@router.post("/matches", response_model=AgentResult)
async def agent_match(
    request: AgentRequest, workflow: Annotated[AgentWorkflow, Depends(get_agent_workflow)]
):
    result, status = await workflow.run(request)
    if status != 200:
        return JSONResponse(status_code=status, content=result.model_dump(mode="json"))
    return result
