from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.commands import CommandRequest, CommandResult
from app.services.commands import handle_command

router = APIRouter(prefix="/commands", tags=["commands"])


@router.post("", response_model=CommandResult)
async def send_command(
    request: CommandRequest,
    session: Session = Depends(get_session),
) -> CommandResult:
    return handle_command(session, request)
