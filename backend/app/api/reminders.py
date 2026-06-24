from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.reminders import (
    ConsumeReminderRequest,
    ReminderEventRead,
    ReminderSettingsRead,
    ReminderSettingsUpdate,
)
from app.services.reminders import (
    generate_due_reminders,
    get_or_create_reminder_settings,
    list_pending_reminder_events,
    mark_reminder_consumed,
    update_reminder_settings,
)
from app.services.students import get_or_create_default_student

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/settings", response_model=ReminderSettingsRead)
async def read_settings(session: Session = Depends(get_session)) -> ReminderSettingsRead:
    student = get_or_create_default_student(session)
    settings = get_or_create_reminder_settings(session, student.id)
    return ReminderSettingsRead.model_validate(settings)


@router.put("/settings", response_model=ReminderSettingsRead)
async def put_settings(
    payload: ReminderSettingsUpdate,
    session: Session = Depends(get_session),
) -> ReminderSettingsRead:
    student = get_or_create_default_student(session)
    settings = update_reminder_settings(
        session,
        student.id,
        payload.model_dump(exclude_unset=True),
    )
    return ReminderSettingsRead.model_validate(settings)


@router.post("/generate-due", response_model=list[ReminderEventRead])
async def generate_due(
    now: datetime = Query(),
    session: Session = Depends(get_session),
) -> list[ReminderEventRead]:
    return [ReminderEventRead.model_validate(event) for event in generate_due_reminders(session, now)]


@router.get("/pending", response_model=list[ReminderEventRead])
async def read_pending(session: Session = Depends(get_session)) -> list[ReminderEventRead]:
    return [ReminderEventRead.model_validate(event) for event in list_pending_reminder_events(session)]


@router.post("/{reminder_event_id}/consume", response_model=ReminderEventRead)
async def consume_reminder(
    reminder_event_id: int,
    payload: ConsumeReminderRequest,
    session: Session = Depends(get_session),
) -> ReminderEventRead:
    event = mark_reminder_consumed(
        session,
        reminder_event_id,
        device_id=payload.device_id,
        sent_at=payload.sent_at,
    )
    return ReminderEventRead.model_validate(event)
