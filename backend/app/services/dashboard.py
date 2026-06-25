import datetime as dt

from sqlmodel import Session, select

from app.models.calendar import DailyTask
from app.models.device import Device
from app.models.enums import DailyTaskStatus, ReminderEventStatus, ReminderEventType
from app.models.reminder import ReminderEvent
from app.schemas.dashboard import (
    DashboardCurrentTask,
    DashboardDevice,
    DashboardReminder,
    DashboardStats,
    DashboardTask,
    DashboardToday,
)
from app.services.daily_tasks import list_daily_tasks
from app.services.students import get_or_create_default_student


ACTIVE_STATUSES = {
    DailyTaskStatus.STUDYING,
    DailyTaskStatus.PAUSED,
    DailyTaskStatus.WAITING_FINISH_CONFIRM,
    DailyTaskStatus.REMINDING,
}

STATUS_LABELS = {
    DailyTaskStatus.PENDING: "待开始",
    DailyTaskStatus.REMINDING: "已提醒",
    DailyTaskStatus.STUDYING: "正在做",
    DailyTaskStatus.PAUSED: "已暂停",
    DailyTaskStatus.WAITING_FINISH_CONFIRM: "待确认",
    DailyTaskStatus.PARENT_CONFIRM_REQUIRED: "需家长处理",
    DailyTaskStatus.COMPLETED: "已完成",
    DailyTaskStatus.SKIPPED: "已跳过",
    DailyTaskStatus.OVERDUE: "已延迟",
}

REMINDER_LABELS = {
    ReminderEventType.PRE_START: "提前提醒",
    ReminderEventType.START_DUE: "开始提醒",
    ReminderEventType.DELAYED_START: "延迟提醒",
    ReminderEventType.FINISH_CONFIRM: "完成确认",
    ReminderEventType.BREAK_END: "休息结束",
}

REMINDER_STATUS_LABELS = {
    ReminderEventStatus.PENDING: "待播报",
    ReminderEventStatus.CONSUMED: "已播报",
    ReminderEventStatus.CANCELLED: "已取消",
}

WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def get_today_dashboard(session: Session, target_date: dt.date | None = None) -> DashboardToday:
    dashboard_date = target_date or dt.date.today()
    student = get_or_create_default_student(session)
    tasks = list_daily_tasks(session, dashboard_date)
    dashboard_tasks = [_to_dashboard_task(task) for task in tasks]
    reminders = _list_dashboard_reminders(session, dashboard_date)
    devices = _list_dashboard_devices(session, dashboard_date)
    current = _build_current_task(tasks)
    stats = _build_stats(tasks, reminders, devices)

    return DashboardToday(
        date=dashboard_date,
        date_label=_date_label(dashboard_date),
        student_name=student.name,
        tasks=dashboard_tasks,
        current=current,
        stats=stats,
        devices=devices,
        reminders=reminders,
    )


def _to_dashboard_task(task: DailyTask) -> DashboardTask:
    return DashboardTask(
        id=task.id or 0,
        start_time=task.current_start_at.strftime("%H:%M"),
        end_time=task.current_end_at.strftime("%H:%M"),
        task_kind=task.task_kind,
        subject=task.subject,
        title=task.title,
        content=task.content,
        planned_minutes=task.planned_minutes,
        status=task.status,
        status_label=STATUS_LABELS.get(task.status, task.status.value),
    )


def _build_current_task(tasks: list[DailyTask]) -> DashboardCurrentTask:
    active_task = next((task for task in tasks if task.status in ACTIVE_STATUSES), None)
    if active_task is None:
        next_task = next((task for task in tasks if task.status == DailyTaskStatus.PENDING), None)
        if next_task is None:
            return DashboardCurrentTask()
        return DashboardCurrentTask(
            task=_to_dashboard_task(next_task),
            description=f"下一项：{next_task.title}，计划{next_task.planned_minutes}分钟。",
        )

    now = _normalize_now(active_task.current_start_at)
    elapsed_seconds = max(0, int((now - active_task.current_start_at).total_seconds()))
    elapsed_minutes = elapsed_seconds // 60
    description = _current_description(active_task)
    return DashboardCurrentTask(
        task=_to_dashboard_task(active_task),
        elapsed_minutes=elapsed_minutes,
        elapsed_label=_elapsed_label(elapsed_seconds),
        description=description,
    )


def _normalize_now(reference: dt.datetime) -> dt.datetime:
    now = dt.datetime.now(dt.timezone.utc)
    if reference.tzinfo is None:
        return now.replace(tzinfo=None)
    return now.astimezone(reference.tzinfo)


def _elapsed_label(elapsed_seconds: int) -> str:
    minutes, seconds = divmod(elapsed_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _current_description(task: DailyTask) -> str:
    if task.status == DailyTaskStatus.PAUSED:
        return "当前任务已暂停，等待孩子继续。"
    if task.status == DailyTaskStatus.WAITING_FINISH_CONFIRM:
        return "计划时间已到，等待孩子语音确认完成。"
    if task.status == DailyTaskStatus.REMINDING:
        return "已提醒开始，等待孩子语音回应。"
    return "当前任务正在进行，孩子通过设备语音执行。"


def _build_stats(
    tasks: list[DailyTask],
    reminders: list[DashboardReminder],
    devices: list[DashboardDevice],
) -> DashboardStats:
    return DashboardStats(
        total_tasks=len(tasks),
        completed_tasks=len([task for task in tasks if task.status == DailyTaskStatus.COMPLETED]),
        pending_parent_confirm=len([task for task in tasks if task.status == DailyTaskStatus.PARENT_CONFIRM_REQUIRED]),
        planned_minutes=sum(task.planned_minutes for task in tasks),
        device_status_label="在线" if any(device.is_online for device in devices) else "离线",
        reminder_count=len(reminders),
    )


def _list_dashboard_devices(session: Session, target_date: dt.date) -> list[DashboardDevice]:
    statement = select(Device).order_by(Device.updated_at.desc(), Device.id.desc())
    devices = list(session.exec(statement))
    return [_to_dashboard_device(device, target_date) for device in devices]


def _to_dashboard_device(device: Device, target_date: dt.date) -> DashboardDevice:
    sync_label = "今日计划已同步" if device.last_plan_sync_date == target_date else "今日计划未同步"
    return DashboardDevice(
        device_id=device.device_id,
        device_type=device.device_type,
        hardware_model=device.hardware_model,
        firmware_version=device.firmware_version,
        is_online=device.is_online,
        last_seen_at=device.last_seen_at,
        last_plan_sync_date=device.last_plan_sync_date,
        last_plan_sync_at=device.last_plan_sync_at,
        status_label="在线" if device.is_online else "离线",
        sync_label=sync_label,
    )


def _list_dashboard_reminders(session: Session, target_date: dt.date) -> list[DashboardReminder]:
    start = dt.datetime.combine(target_date, dt.time.min)
    end = dt.datetime.combine(target_date + dt.timedelta(days=1), dt.time.min)
    statement = (
        select(ReminderEvent)
        .where(ReminderEvent.scheduled_at >= start)
        .where(ReminderEvent.scheduled_at < end)
        .order_by(ReminderEvent.scheduled_at.desc(), ReminderEvent.id.desc())
        .limit(6)
    )
    return [_to_dashboard_reminder(event) for event in session.exec(statement)]


def _to_dashboard_reminder(event: ReminderEvent) -> DashboardReminder:
    return DashboardReminder(
        id=event.id or 0,
        event_type=event.event_type,
        event_type_label=REMINDER_LABELS.get(event.event_type, event.event_type.value),
        scheduled_at=event.scheduled_at,
        status=event.status,
        status_label=REMINDER_STATUS_LABELS.get(event.status, event.status.value),
        message_text=event.message_text,
    )


def _date_label(target_date: dt.date) -> str:
    return f"{target_date.month}月{target_date.day}日 {WEEKDAY_LABELS[target_date.weekday()]}"
