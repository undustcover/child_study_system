import datetime as dt

from sqlmodel import Session, select

from app.models.calendar import DailyTask
from app.models.enums import DailyTaskStatus, ReminderEventStatus, ReminderEventType, TaskKind
from app.models.reminder import ReminderEvent, ReminderSettings
from app.services.language_settings import get_or_create_language_settings
from app.services.speech_templates import render_reminder_text

REMINDER_LOOKBACK_SECONDS = 60


def _is_due_now(scheduled_at: dt.datetime, now: dt.datetime) -> bool:
    return scheduled_at <= now <= scheduled_at + dt.timedelta(seconds=REMINDER_LOOKBACK_SECONDS)


def _existing_event(
    session: Session,
    task_id: int,
    event_type: ReminderEventType,
    scheduled_at: dt.datetime,
) -> ReminderEvent | None:
    statement = select(ReminderEvent).where(
        ReminderEvent.daily_task_id == task_id,
        ReminderEvent.event_type == event_type,
        ReminderEvent.scheduled_at == scheduled_at,
    )
    return session.exec(statement).first()


def _create_event(
    session: Session,
    task: DailyTask,
    settings: ReminderSettings,
    event_type: ReminderEventType,
    scheduled_at: dt.datetime,
) -> ReminderEvent | None:
    if _existing_event(session, task.id, event_type, scheduled_at):
        return None
    language_settings = get_or_create_language_settings(session)
    event = ReminderEvent(
        daily_task_id=task.id,
        event_type=event_type,
        scheduled_at=scheduled_at,
        message_text=render_reminder_text(event_type, task, settings, language_settings),
    )
    session.add(event)
    return event


def get_or_create_reminder_settings(session: Session, student_id: int) -> ReminderSettings:
    statement = select(ReminderSettings).where(ReminderSettings.student_id == student_id)
    settings = session.exec(statement).first()
    if settings:
        return settings
    settings = ReminderSettings(student_id=student_id)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def update_reminder_settings(
    session: Session,
    student_id: int,
    updates: dict[str, object],
) -> ReminderSettings:
    settings = get_or_create_reminder_settings(session, student_id)
    for field_name, value in updates.items():
        if value is not None:
            setattr(settings, field_name, value)
    settings.updated_at = dt.datetime.now(dt.timezone.utc)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def _due_start_reminder_times(task: DailyTask, settings: ReminderSettings, now: dt.datetime) -> list[dt.datetime]:
    scheduled_times: list[dt.datetime] = [task.current_start_at]
    for repeat_index in range(1, settings.start_due_max_count):
        scheduled_times.append(
            task.current_start_at + dt.timedelta(minutes=settings.start_due_repeat_interval_minutes * repeat_index)
        )
    return [scheduled_at for scheduled_at in scheduled_times if _is_due_now(scheduled_at, now)]


def _due_finish_confirm_times(task: DailyTask, settings: ReminderSettings, now: dt.datetime) -> list[dt.datetime]:
    scheduled_times = [
        task.current_end_at + dt.timedelta(minutes=settings.finish_confirm_repeat_interval_minutes * repeat_index)
        for repeat_index in range(settings.finish_confirm_max_count)
    ]
    return [scheduled_at for scheduled_at in scheduled_times if _is_due_now(scheduled_at, now)]


def _finish_confirm_timeout_at(task: DailyTask, settings: ReminderSettings) -> dt.datetime:
    return task.current_end_at + dt.timedelta(
        minutes=settings.finish_confirm_repeat_interval_minutes * settings.finish_confirm_max_count
    )


def generate_due_reminders(session: Session, now: dt.datetime) -> list[ReminderEvent]:
    created: list[ReminderEvent] = []

    task_statement = select(DailyTask).where(
        DailyTask.status.in_(
            [
                DailyTaskStatus.PENDING,
                DailyTaskStatus.REMINDING,
                DailyTaskStatus.STUDYING,
                DailyTaskStatus.WAITING_FINISH_CONFIRM,
            ]
        )
    )
    for task in session.exec(task_statement):
        settings = get_or_create_reminder_settings(session, task.student_id)
        if task.status in {DailyTaskStatus.PENDING, DailyTaskStatus.REMINDING}:
            pre_start_at = task.current_start_at - dt.timedelta(minutes=settings.pre_start_minutes)
            if settings.pre_start_enabled and _is_due_now(pre_start_at, now):
                event = _create_event(session, task, settings, ReminderEventType.PRE_START, pre_start_at)
                if event:
                    created.append(event)

            if settings.start_due_enabled:
                for scheduled_at in _due_start_reminder_times(task, settings, now):
                    event = _create_event(session, task, settings, ReminderEventType.START_DUE, scheduled_at)
                    if event:
                        created.append(event)

            delayed_at = task.current_start_at + dt.timedelta(minutes=settings.delayed_start_minutes)
            if settings.delayed_start_enabled and _is_due_now(delayed_at, now):
                event = _create_event(session, task, settings, ReminderEventType.DELAYED_START, delayed_at)
                if event:
                    task.status = DailyTaskStatus.OVERDUE
                    task.updated_at = now
                    created.append(event)

        if task.status == DailyTaskStatus.STUDYING and task.task_kind == TaskKind.BREAK:
            if settings.break_end_enabled and _is_due_now(task.current_end_at, now):
                event = _create_event(session, task, settings, ReminderEventType.BREAK_END, task.current_end_at)
                if event:
                    created.append(event)

        if task.status == DailyTaskStatus.WAITING_FINISH_CONFIRM:
            if settings.finish_confirm_enabled:
                for scheduled_at in _due_finish_confirm_times(task, settings, now):
                    event = _create_event(session, task, settings, ReminderEventType.FINISH_CONFIRM, scheduled_at)
                    if event:
                        created.append(event)

            timeout_at = _finish_confirm_timeout_at(task, settings)
            if settings.parent_confirm_required_enabled and _is_due_now(timeout_at, now):
                task.status = DailyTaskStatus.PARENT_CONFIRM_REQUIRED
                task.updated_at = now

    session.commit()
    for event in created:
        session.refresh(event)
    return created


def list_pending_reminder_events(session: Session) -> list[ReminderEvent]:
    statement = (
        select(ReminderEvent)
        .where(ReminderEvent.status == ReminderEventStatus.PENDING)
        .order_by(ReminderEvent.scheduled_at, ReminderEvent.id)
    )
    return list(session.exec(statement))


def mark_reminder_consumed(
    session: Session,
    reminder_event_id: int,
    *,
    device_id: str | None,
    sent_at: dt.datetime,
) -> ReminderEvent:
    event = session.get(ReminderEvent, reminder_event_id)
    if event is None:
        raise ValueError("reminder event not found")
    event.status = ReminderEventStatus.CONSUMED
    event.device_id = device_id
    event.sent_at = sent_at
    event.updated_at = sent_at
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
