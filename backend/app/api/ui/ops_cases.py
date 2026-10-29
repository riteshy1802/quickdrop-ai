from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.database import get_session_factory
from app.integrations.payswift import get_payswift_client
from app.schemas.ops_actions import Assignment, Reason
from app.services import ops_case_service
from app.services.auth_service import Operator

router = APIRouter(prefix="/ui/ops/cases", tags=["Ops cases"])


@router.post("/{identifier}/approve")
async def approve(
    identifier: UUID,
    operator: Operator,
    factory=Depends(get_session_factory),
    client=Depends(get_payswift_client),
):
    return await ops_case_service.act(factory, identifier, operator, "approve", client=client)


@router.post("/{identifier}/reject")
async def reject(
    identifier: UUID, payload: Reason, operator: Operator, factory=Depends(get_session_factory)
):
    return await ops_case_service.act(
        factory, identifier, operator, "reject", reason=payload.reason
    )


@router.post("/{identifier}/assign")
async def assign(
    identifier: UUID,
    operator: Operator,
    payload: Assignment = Assignment(),
    factory=Depends(get_session_factory),
):
    return await ops_case_service.act(
        factory, identifier, operator, "assign", operator_id=payload.operator_id
    )


@router.post("/{identifier}/resolve")
async def resolve(
    identifier: UUID, payload: Reason, operator: Operator, factory=Depends(get_session_factory)
):
    return await ops_case_service.act(
        factory, identifier, operator, "resolve", reason=payload.reason
    )
