"""Unified command handler entrypoint."""

from sqlmodel import Session

from app.models.enums import CommandType
from app.schemas.commands import CommandRequest, CommandResult
from app.services.task_state_machine import process_command

SUPPORTED_COMMANDS = {command.value for command in CommandType}


def handle_command(session: Session, request: CommandRequest) -> CommandResult:
    return process_command(session, request)
