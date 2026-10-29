from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.riders import Session, require_rider
from app.core.config import get_settings
from app.core.demo import COOKIE_AGE, cookie_name, require_demo, signer
from app.models import Conversation
from app.repositories.conversations import get
from app.services.auth_service import check_origin
from app.services.conversation_service import lock_rider, summary

router = APIRouter(tags=["Rider simulator context"])


class Selection(BaseModel):
    rider_id: str = Field(min_length=1, max_length=32)


@router.post("/ui/demo/rider")
async def select_rider(payload: Selection, request: Request, response: Response, session: Session):
    check_origin(request)
    if not get_settings().enable_demo_workspace:
        raise HTTPException(403, "Rider simulator disabled")
    await require_rider(session, payload.rider_id)
    response.set_cookie(
        cookie_name(payload.rider_id),
        signer().dumps(payload.rider_id),
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https" or get_settings().ops_cookie_secure,
        max_age=COOKIE_AGE,
    )
    return {"rider_id": payload.rider_id}


@router.post("/ui/riders/{rider_id}/conversations")
async def new_conversation(rider_id: str, request: Request, session: Session):
    check_origin(request)
    require_demo(request, rider_id)
    await lock_rider(session, rider_id)
    conversation = Conversation(id=uuid4(), rider_id=rider_id)
    session.add(conversation)
    await session.commit()
    return summary(await get(session, conversation.id, rider_id))
