import datetime as dt

from sqlmodel import Field, SQLModel

from app.models.enums import CommandSource, StudySessionStatus, TimeSegmentKind


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class StudySession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    daily_task_id: int = Field(index=True)
    student_id: int = Field(index=True)
    status: StudySessionStatus = Field(default=StudySessionStatus.ACTIVE, index=True)
    started_at: dt.datetime
    ended_at: dt.datetime | None = Field(default=None, index=True)
    effective_seconds: int = 0
    command_source: CommandSource = Field(default=CommandSource.PARENT_WEB, index=True)
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)


class TimeSegment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    study_session_id: int = Field(index=True)
    daily_task_id: int = Field(index=True)
    segment_kind: TimeSegmentKind = Field(index=True)
    started_at: dt.datetime
    ended_at: dt.datetime | None = Field(default=None, index=True)
    duration_seconds: int = 0
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)
