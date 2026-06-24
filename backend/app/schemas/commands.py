from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CommandSource, CommandType, DailyTaskStatus, StudySessionStatus
from app.schemas.calendar import DailyTaskRead


class CommandRequest(BaseModel):
    command: CommandType
    source: CommandSource
    daily_task_id: int | None = None
    target_date: date | None = None
    timestamp: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class StudySessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    daily_task_id: int
    student_id: int
    status: StudySessionStatus
    started_at: datetime
    ended_at: datetime | None
    effective_seconds: int
    command_source: CommandSource


class CommandResult(BaseModel):
    command: CommandType
    task_status: DailyTaskStatus | None = None
    task: DailyTaskRead | None = None
    study_session: StudySessionRead | None = None
    message: str
