from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DailyTaskStatus, DeviceType, ReminderEventStatus, ReminderEventType, TaskKind


class DashboardTask(BaseModel):
    id: int
    date: date
    start_time: str
    end_time: str
    task_kind: TaskKind
    subject: str | None
    title: str
    content: str | None
    planned_minutes: int
    status: DailyTaskStatus
    status_label: str


class DashboardCurrentTask(BaseModel):
    task: DashboardTask | None = None
    elapsed_minutes: int = 0
    elapsed_label: str = "00:00"
    description: str = "当前没有正在进行的任务。"


class DashboardStats(BaseModel):
    total_tasks: int = 0
    completed_tasks: int = 0
    pending_parent_confirm: int = 0
    planned_minutes: int = 0
    device_status_label: str = "离线"
    reminder_count: int = 0


class DashboardDevice(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    device_type: DeviceType
    hardware_model: str
    firmware_version: str | None
    is_online: bool
    last_seen_at: datetime | None
    last_plan_sync_date: date | None
    last_plan_sync_at: datetime | None
    status_label: str
    sync_label: str


class DashboardReminder(BaseModel):
    id: int
    event_type: ReminderEventType
    event_type_label: str
    scheduled_at: datetime
    status: ReminderEventStatus
    status_label: str
    message_text: str


class DashboardToday(BaseModel):
    date: date
    date_label: str
    student_name: str
    tasks: list[DashboardTask] = Field(default_factory=list)
    current: DashboardCurrentTask = Field(default_factory=DashboardCurrentTask)
    stats: DashboardStats = Field(default_factory=DashboardStats)
    devices: list[DashboardDevice] = Field(default_factory=list)
    reminders: list[DashboardReminder] = Field(default_factory=list)
