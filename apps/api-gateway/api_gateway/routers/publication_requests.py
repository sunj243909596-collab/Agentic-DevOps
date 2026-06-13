from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from api_gateway.dependencies import require_auth
from api_gateway.schemas.models import PublicationRequestIn, PublicationRequestOut

router = APIRouter(prefix="/v1/publication-requests", tags=["publication-requests"])

_EXTERNAL_CHANNELS = {"pull_request_comment", "issue", "slack", "feishu"}


@router.post("", status_code=202, response_model=PublicationRequestOut)
async def create_publication_request(
    body: PublicationRequestIn,
    _auth: str = Depends(require_auth),
) -> PublicationRequestOut:
    if body.channel in _EXTERNAL_CHANNELS:
        decision = "denied"
    elif body.channel == "internal_markdown":
        decision = "allowed"
    else:
        decision = "approval_required"

    return PublicationRequestOut(
        request_id=uuid.uuid4(),
        policy_decision=decision,
    )
