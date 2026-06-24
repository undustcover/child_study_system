import datetime as dt

from sqlmodel import Session, select

from app.models.calendar import DailyTask
from app.models.device import Device
from app.models.enums import CommandSource, CommandType, DeviceType, ReminderEventStatus
from app.models.reminder import ReminderEvent
from app.schemas.commands import CommandRequest, CommandResult
from app.services.commands import handle_command
from app.services.daily_tasks import list_daily_tasks


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def get_device(session: Session, device_id: str) -> Device | None:
    statement = select(Device).where(Device.device_id == device_id)
    return session.exec(statement).first()


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
