"""Structured-only endpoint, directly backed by the internal deterministic service."""

from functools import lru_cache
from typing import Annotated

from componentmatch_contracts.requirement import MatchRequest
from componentmatch_contracts.result import MatchResult
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from componentmatch.core.config import Settings
from componentmatch.db.session import make_engine
from componentmatch.services.matching import MatchingService

router = APIRouter(prefix="/api/v1", tags=["deterministic matching"])


@lru_cache
def get_matching_service() -> MatchingService:
    return MatchingService(make_engine(Settings().database_url))


@router.post("/matches", response_model=MatchResult)
def match_suppliers(
    request: MatchRequest, service: Annotated[MatchingService, Depends(get_matching_service)]
):
    result = service.match(request.requirement)
    if result.status == "error":
        return JSONResponse(status_code=500, content=result.model_dump(mode="json"))
    return result
