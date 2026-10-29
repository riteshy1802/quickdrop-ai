from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.database import get_session_factory
from app.schemas.conversations import MessageResponse
from app.schemas.ops_actions import HumanMessage, Reason
from app.services import human_handoff_service as service
from app.services.auth_service import Operator

router = APIRouter(prefix="/ui/ops/conversations", tags=["Human intervention"])


@router.post("/{identifier}/takeover")
async def takeover(identifier: UUID, operator: Operator, factory=Depends(get_session_factory)):
    return await service.transition(factory, identifier, operator, "takeover")


@router.post("/{identifier}/handoff")
async def handoff(identifier: UUID, operator: Operator, factory=Depends(get_session_factory)):
    return await service.transition(factory, identifier, operator, "handoff")


@router.post("/{identifier}/resolve")
async def resolve(
    identifier: UUID, payload: Reason, operator: Operator, factory=Depends(get_session_factory)
):
    return await service.transition(factory, identifier, operator, "resolve", payload.reason)


@router.post("/{identifier}/messages", response_model=MessageResponse, status_code=201)
async def messages(
    identifier: UUID,
    payload: HumanMessage,
    operator: Operator,
    factory=Depends(get_session_factory),
):
    return await service.post_message(factory, identifier, operator, payload)


@router.post("/{identifier}/notes", response_model=MessageResponse, status_code=201)
async def notes(
    identifier: UUID,
    payload: HumanMessage,
    operator: Operator,
    factory=Depends(get_session_factory),
):
    return await service.post_message(factory, identifier, operator, payload, internal=True)
