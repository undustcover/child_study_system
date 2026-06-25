from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DailyTaskStatus, ExceptionType, HolidayDayType, TaskKind


class StudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ScheduleTaskItemCreate(BaseModel):
    sort_order: int = 0
    task_kind: TaskKind
    subject: str | None = None
    title: str
    content: str | None = None
    planned_start_time: time
    planned_end_time: time
    planned_minutes: int = Field(gt=0)
    remind_enabled: bool = True
    pre_remind_minutes: int = Field(default=5, ge=0)


class ScheduleTaskItemUpdate(BaseModel):
    sort_order: int | None = None
    task_kind: TaskKind | None = None
    subject: str | None = None
    title: str | None = None
    content: str | None = None
    planned_start_time: time | None = None
    planned_end_time: time | None = None
    planned_minutes: int | None = Field(default=None, gt=0)
    remind_enabled: bool | None = None
    pre_remind_minutes: int | None = Field(default=None, ge=0)


class ScheduleTaskItemRead(ScheduleTaskItemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_plan_id: int


class SchedulePlanCreate(BaseModel):
    name: str
    start_date: date
    end_date: date
    repeat_rule: dict[str, Any] = Field(default_factory=dict)
    skip_public_holidays: bool = False
    run_in_winter_vacation: bool = True
    run_in_summer_vacation: bool = True
    is_active: bool = True
    items: list[ScheduleTaskItemCreate] = Field(default_factory=list)


class SchedulePlanUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    repeat_rule: dict[str, Any] | None = None
    skip_public_holidays: bool | None = None
    run_in_winter_vacation: bool | None = None
    run_in_summer_vacation: bool | None = None
    is_active: bool | None = None


class SchedulePlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    name: str
    start_date: date
    end_date: date
    repeat_rule: dict[str, Any]
    skip_public_holidays: bool
    run_in_winter_vacation: bool
    run_in_summer_vacation: bool
    is_active: bool
    items: list[ScheduleTaskItemRead] = Field(default_factory=list)


class ScheduleExceptionCreate(BaseModel):
    date: date
    exception_type: ExceptionType
    override_payload: dict[str, Any] | None = None
    reason: str | None = None


class ScheduleExceptionRead(ScheduleExceptionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_plan_id: int


class HolidayCreate(BaseModel):
    date: date
    label: str
    day_type: HolidayDayType
    source: str = "manual"
    is_rest_day: bool = True


class HolidayRangeCreate(BaseModel):
    start_date: date
    end_date: date
    label: str
    day_type: HolidayDayType
    source: str = "parent"
    is_rest_day: bool = True


class HolidayRead(HolidayCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class DailyTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    source_schedule_plan_id: int | None
    source_schedule_task_item_id: int | None
    date: date
    sort_order: int
    task_kind: TaskKind
    subject: str | None
    title: str
    content: str | None
    original_start_at: datetime
    original_end_at: datetime
    current_start_at: datetime
    current_end_at: datetime
    planned_minutes: int
    status: DailyTaskStatus
    modify_count: int


class GenerateDailyTasksResult(BaseModel):
    date: date
    created_count: int
    skipped_plan_ids: list[int] = Field(default_factory=list)
    tasks: list[DailyTaskRead] = Field(default_factory=list)
