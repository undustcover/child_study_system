import datetime as dt

from sqlmodel import Session, select

from app.models.calendar import DailyTask
from app.models.device import Device
from app.models.device_settings import DeviceSettings
from app.models.enums import CommandSource, CommandType, DailyTaskStatus, DeviceType, ReminderEventStatus
from app.models.reminder import ReminderEvent
from app.schemas.commands import CommandRequest, CommandResult
from app.services.commands import handle_command
from app.services.daily_tasks import list_daily_tasks
from app.services.language_settings import get_or_create_language_settings, render_template


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


DEFAULT_DEVICE_SETTINGS_KEY = "default"


def get_device(session: Session, device_id: str) -> Device | None:
    statement = select(Device).where(Device.device_id == device_id)
    return session.exec(statement).first()


def get_device_settings(session: Session, device_id: str | None = None) -> DeviceSettings | None:
    statement = select(DeviceSettings).where(DeviceSettings.settings_key == _device_settings_key(device_id))
    return session.exec(statement).first()


def get_or_create_device_settings(session: Session, device_id: str | None = None) -> DeviceSettings:
    settings = get_device_settings(session, device_id)
    if settings is not None:
        return settings

    settings = DeviceSettings(
        settings_key=_device_settings_key(device_id),
        target_device_id=device_id,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def get_effective_device_settings(session: Session, device_id: str) -> tuple[DeviceSettings, bool]:
    override = get_device_settings(session, device_id)
    if override is not None:
        return override, True
    return get_or_create_device_settings(session), False


def update_device_settings(
    session: Session,
    updates: dict,
    *,
    device_id: str | None = None,
) -> DeviceSettings:
    settings = get_or_create_device_settings(session, device_id)
    for field in ("auto_sync_today_plan", "auto_broadcast_today_plan", "replay_today_plan_on_reconnect"):
        if field in updates and updates[field] is not None:
            setattr(settings, field, bool(updates[field]))
    settings.updated_at = utc_now()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def register_or_update_device(
    session: Session,
    device_id: str,
    *,
    device_type: str | None = None,
    firmware_version: str | None = None,
    when: dt.datetime | None = None,
) -> Device:
    seen_at = when or utc_now()
    device = get_device(session, device_id)
    if device is None:
        device = Device(device_id=device_id)
    if device_type:
        device.device_type = DeviceType(device_type)
    if firmware_version is not None:
        device.firmware_version = firmware_version
    device.is_online = True
    device.last_seen_at = seen_at
    device.connected_at = device.connected_at or seen_at
    device.disconnected_at = None
    device.updated_at = seen_at
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def mark_device_disconnected(session: Session, device_id: str, when: dt.datetime | None = None) -> Device | None:
    disconnected_at = when or utc_now()
    device = get_device(session, device_id)
    if device is None:
        return None
    device.is_online = False
    device.disconnected_at = disconnected_at
    device.updated_at = disconnected_at
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def mark_device_plan_synced(
    session: Session,
    device_id: str,
    target_date: dt.date,
    when: dt.datetime | None = None,
) -> Device:
    synced_at = when or utc_now()
    device = get_device(session, device_id)
    if device is None:
        device = Device(device_id=device_id)
    device.last_plan_sync_date = target_date
    device.last_plan_sync_at = synced_at
    device.updated_at = synced_at
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def serialize_daily_task_for_device(task: DailyTask) -> dict:
    return {
        "id": task.id,
        "date": task.date.isoformat(),
        "sort_order": task.sort_order,
        "task_kind": task.task_kind.value,
        "subject": task.subject,
        "title": task.title,
        "content": task.content,
        "current_start_at": task.current_start_at.isoformat(),
        "current_end_at": task.current_end_at.isoformat(),
        "planned_minutes": task.planned_minutes,
        "status": task.status.value,
    }


def build_today_plan_payload(session: Session, target_date: dt.date) -> dict:
    tasks = list_daily_tasks(session, target_date)
    return {
        "date": target_date.isoformat(),
        "tasks": [serialize_daily_task_for_device(task) for task in tasks],
    }


def build_device_config_payload(session: Session, device_id: str) -> dict:
    device_settings, is_override = get_effective_device_settings(session, device_id)
    language_settings = get_or_create_language_settings(session)
    latest_updated_at = max(device_settings.updated_at, language_settings.updated_at)
    return {
        "device_id": device_id,
        "config_version": latest_updated_at.isoformat(),
        "generated_at": utc_now().isoformat(),
        "device_settings": {
            "settings_key": device_settings.settings_key,
            "target_device_id": device_settings.target_device_id,
            "is_override": is_override,
            "auto_sync_today_plan": device_settings.auto_sync_today_plan,
            "auto_broadcast_today_plan": device_settings.auto_broadcast_today_plan,
            "replay_today_plan_on_reconnect": device_settings.replay_today_plan_on_reconnect,
            "updated_at": device_settings.updated_at.isoformat(),
        },
        "language_settings": {
            "settings_key": language_settings.settings_key,
            "today_plan_templates": language_settings.today_plan_templates,
            "reminder_templates": language_settings.reminder_templates,
            "virtual_reply_templates": language_settings.virtual_reply_templates,
            "command_phrases": language_settings.command_phrases,
            "command_labels": language_settings.command_labels,
            "updated_at": language_settings.updated_at.isoformat(),
        },
    }


TASK_KIND_LABELS = {
    "study": "学习",
    "practice": "练习",
    "review": "复习",
    "homework": "作业",
    "recitation": "背诵",
    "reading": "阅读",
    "break": "休息",
}

FINISHED_TASK_STATUSES = {DailyTaskStatus.COMPLETED, DailyTaskStatus.SKIPPED}


def build_today_plan_speak_text(session: Session, target_date: dt.date) -> str:
    tasks = list_daily_tasks(session, target_date)
    language_settings = get_or_create_language_settings(session)
    templates = language_settings.today_plan_templates
    date_label = _date_label(target_date)
    if not tasks:
        return render_template(templates["empty"], {"date_label": date_label, "target_date": target_date.isoformat()})

    remaining_tasks = [task for task in tasks if task.status not in FINISHED_TASK_STATUSES]
    if not remaining_tasks:
        return render_template(
            templates["completed"],
            {"date_label": date_label, "target_date": target_date.isoformat()},
        )

    summaries = "；".join(_task_summary(task) for task in remaining_tasks[:3])
    if len(remaining_tasks) == 1:
        return render_template(
            templates["single"],
            {
                "date_label": date_label,
                "target_date": target_date.isoformat(),
                "remaining_count": 1,
                "task_summaries": summaries,
                "extra_suffix": "",
            },
        )

    remaining_count = len(remaining_tasks)
    extra_suffix = ""
    if remaining_count > 3:
        extra_suffix = render_template(
            templates["extra_suffix"],
            {"extra_count": remaining_count - 3, "remaining_count": remaining_count},
        )
    return render_template(
        templates["multiple"],
        {
            "date_label": date_label,
            "target_date": target_date.isoformat(),
            "remaining_count": remaining_count,
            "task_summaries": summaries,
            "extra_suffix": extra_suffix,
        },
    )


def handle_device_voice_command(session: Session, payload: dict) -> CommandResult:
    command = CommandType(payload["command"])
    command_payload = {"device_id": payload.get("device_id"), "text": payload.get("text")}
    if payload.get("minutes") is not None:
        command_payload["minutes"] = payload.get("minutes")
    request = CommandRequest(
        command=command,
        source=CommandSource.DEVICE_VOICE,
        daily_task_id=payload.get("daily_task_id"),
        target_date=payload.get("target_date"),
        timestamp=payload.get("timestamp"),
        payload=command_payload,
    )
    return handle_command(session, request)


def _date_label(target_date: dt.date) -> str:
    today = dt.date.today()
    if target_date == today:
        return "今天"
    return f"{target_date.month}月{target_date.day}日"


def _task_summary(task: DailyTask) -> str:
    time_range = f"{task.current_start_at.strftime('%H:%M')}到{task.current_end_at.strftime('%H:%M')}"
    kind_label = TASK_KIND_LABELS.get(task.task_kind.value, task.task_kind.value)
    subject_prefix = f"{task.subject}的" if task.subject else ""
    return f"{time_range}{subject_prefix}{task.title}，类型是{kind_label}，计划{task.planned_minutes}分钟"


def _device_settings_key(device_id: str | None) -> str:
    if not device_id:
        return DEFAULT_DEVICE_SETTINGS_KEY
    return f"device:{device_id}"


def pending_speak_events_for_device(session: Session) -> list[ReminderEvent]:
    statement = (
        select(ReminderEvent)
        .where(ReminderEvent.status == ReminderEventStatus.PENDING)
        .order_by(ReminderEvent.scheduled_at, ReminderEvent.id)
    )
    return list(session.exec(statement))


def mark_playback_finished(session: Session, message_id: str, when: dt.datetime | None = None) -> ReminderEvent | None:
    if not message_id.startswith("reminder-"):
        return None
    event_id = int(message_id.removeprefix("reminder-"))
    event = session.get(ReminderEvent, event_id)
    if event is None:
        return None
    finished_at = when or utc_now()
    event.ack_at = finished_at
    event.updated_at = finished_at
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
