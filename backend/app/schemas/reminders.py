from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ReminderEventStatus, ReminderEventType


class ReminderEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    daily_task_id: int
    event_type: ReminderEventType
    scheduled_at: datetime
    sent_at: datetime | None
    ack_at: datetime | None
    device_id: str | None
    status: ReminderEventStatus
    message_text: str


class ConsumeReminderRequest(BaseModel):
    device_id: str | None = None
    sent_at: datetime


class ReminderSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    pre_start_enabled: bool
    pre_start_minutes: int
    start_due_enabled: bool
    start_due_repeat_interval_minutes: int
    start_due_max_count: int
    delayed_start_enabled: bool
    delayed_start_minutes: int
    finish_confirm_enabled: bool
    finish_confirm_repeat_interval_minutes: int
    finish_confirm_max_count: int
    parent_confirm_required_enabled: bool
    break_end_enabled: bool
    templates: dict[str, str]


class ReminderSettingsUpdate(BaseModel):
    pre_start_enabled: bool | None = None
    pre_start_minutes: int | None = Field(default=None, gt=0)
    start_due_enabled: bool | None = None
    start_due_repeat_interval_minutes: int | None = Field(default=None, gt=0)
    start_due_max_count: int | None = Field(default=None, gt=0)
    delayed_start_enabled: bool | None = None
    delayed_start_minutes: int | None = Field(default=None, gt=0)
    finish_confirm_enabled: bool | None = None
    finish_confirm_repeat_interval_minutes: int | None = Field(default=None, gt=0)
    finish_confirm_max_count: int | None = Field(default=None, gt=0)
    parent_confirm_required_enabled: bool | None = None
    break_end_enabled: bool | None = None
    templates: dict[str, str] | None = None
