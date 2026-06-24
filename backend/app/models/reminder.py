import datetime as dt

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel

from app.models.enums import ReminderEventStatus, ReminderEventType


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ReminderEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    daily_task_id: int = Field(index=True)
    event_type: ReminderEventType = Field(index=True)
    scheduled_at: dt.datetime = Field(index=True)
    sent_at: dt.datetime | None = Field(default=None, index=True)
    ack_at: dt.datetime | None = Field(default=None, index=True)
    device_id: str | None = Field(default=None, index=True)
    status: ReminderEventStatus = Field(default=ReminderEventStatus.PENDING, index=True)
    message_text: str
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)


class ReminderSettings(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(index=True, unique=True)
    pre_start_enabled: bool = True
    pre_start_minutes: int = 5
    start_due_enabled: bool = True
    start_due_repeat_interval_minutes: int = 5
    start_due_max_count: int = 3
    delayed_start_enabled: bool = True
    delayed_start_minutes: int = 15
    finish_confirm_enabled: bool = True
    finish_confirm_repeat_interval_minutes: int = 3
    finish_confirm_max_count: int = 3
    parent_confirm_required_enabled: bool = True
    break_end_enabled: bool = True
    templates: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)
