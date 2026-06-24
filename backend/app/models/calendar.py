import datetime as dt
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel

from app.models.enums import DailyTaskStatus, ExceptionType, HolidayDayType, TaskKind


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class SchedulePlan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(index=True)
    name: str
    start_date: dt.date = Field(index=True)
    end_date: dt.date = Field(index=True)
    repeat_rule: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    skip_public_holidays: bool = False
    run_in_winter_vacation: bool = True
    run_in_summer_vacation: bool = True
    is_active: bool = True
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)


class ScheduleTaskItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    schedule_plan_id: int = Field(index=True)
    sort_order: int = Field(default=0, index=True)
    task_kind: TaskKind
    subject: str | None = Field(default=None, index=True)
    title: str
    content: str | None = None
    planned_start_time: dt.time
    planned_end_time: dt.time
    planned_minutes: int
    remind_enabled: bool = True
    pre_remind_minutes: int = 5
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)


class ScheduleException(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    schedule_plan_id: int = Field(index=True)
    date: dt.date = Field(index=True)
    exception_type: ExceptionType
    override_payload: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    reason: str | None = None
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)


class HolidayCalendar(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    date: dt.date = Field(index=True, unique=True)
    label: str
    day_type: HolidayDayType = Field(index=True)
    source: str = Field(default="manual", index=True)
    is_rest_day: bool = True
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)


class DailyTask(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(index=True)
    source_schedule_plan_id: int | None = Field(default=None, index=True)
    source_schedule_task_item_id: int | None = Field(default=None, index=True)
    date: dt.date = Field(index=True)
    sort_order: int = Field(default=0, index=True)
    task_kind: TaskKind
    subject: str | None = Field(default=None, index=True)
    title: str
    content: str | None = None
    original_start_at: dt.datetime
    original_end_at: dt.datetime
    current_start_at: dt.datetime
    current_end_at: dt.datetime
    planned_minutes: int
    status: DailyTaskStatus = Field(default=DailyTaskStatus.PENDING, index=True)
    modify_count: int = 0
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)
