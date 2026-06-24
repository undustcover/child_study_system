from datetime import date, datetime, time

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.main import app as fastapi_app
from app.models.calendar import DailyTask
from app.models.enums import CommandSource, DailyTaskStatus, DeviceType, ReminderEventType, TaskKind
from app.models.reminder import ReminderEvent
from app.models.session import StudySession
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.services.calendar_plans import create_schedule_plan
from app.services.daily_tasks import generate_daily_tasks, list_daily_tasks
from app.services.devices import (
    build_today_plan_payload,
    handle_device_voice_command,
    mark_device_disconnected,
    mark_device_plan_synced,
    mark_playback_finished,
    pending_speak_events_for_device,
    register_or_update_device,
)
from app.services.reminders import generate_due_reminders
from app.services.students import get_or_create_default_student
from app.device.protocol import build_speak_message


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def make_daily_task(session: Session) -> DailyTask:
    student = get_or_create_default_student(session)
    create_schedule_plan(
        session,
        student.id,
        SchedulePlanCreate(
            name="weekday evening plan",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            repeat_rule={"weekdays": [1, 2, 3, 4, 5]},
            items=[
                ScheduleTaskItemCreate(
                    sort_order=1,
                    task_kind=TaskKind.HOMEWORK,
                    subject="math",
                    title="homework",
                    planned_start_time=time(19, 0),
                    planned_end_time=time(19, 40),
                    planned_minutes=40,
                )
            ],
        ),
    )
    generate_daily_tasks(session, date(2026, 7, 1))
    return list_daily_tasks(session, date(2026, 7, 1))[0]


def test_device_registers_with_box3_baseline_and_online_status() -> None:
    with make_session() as session:
        device = register_or_update_device(
            session,
            "box3-001",
            device_type="esp32_s3_box_3",
            firmware_version=None,
            when=datetime(2026, 7, 1, 18, 59),
        )

        assert device.device_id == "box3-001"
        assert device.device_type == DeviceType.ESP32_S3_BOX_3
        assert device.hardware_model == "ESP32-S3-BOX-3"
        assert device.chip_model == "ESP32-S3-R8"
        assert device.is_online is True

        disconnected = mark_device_disconnected(session, "box3-001", datetime(2026, 7, 1, 19, 1))
        assert disconnected.is_online is False
        assert disconnected.disconnected_at == datetime(2026, 7, 1, 19, 1)


def test_device_voice_command_enters_unified_command_handler() -> None:
    with make_session() as session:
        task = make_daily_task(session)

        result = handle_device_voice_command(
            session,
            {
                "device_id": "box3-001",
                "command": "START_STUDY",
                "text": "开始学习",
                "daily_task_id": task.id,
                "timestamp": datetime(2026, 7, 1, 19, 0),
            },
        )
        refreshed_task = session.get(app.models.DailyTask, task.id)
        study_session = session.exec(select(StudySession)).one()

        assert result.task_status == DailyTaskStatus.STUDYING
        assert refreshed_task.status == DailyTaskStatus.STUDYING
        assert study_session.command_source == CommandSource.DEVICE_VOICE


def test_pending_reminder_can_be_sent_as_speak_and_acknowledged() -> None:
    with make_session() as session:
        make_daily_task(session)
        events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 0))

        pending = pending_speak_events_for_device(session)
        acknowledged = mark_playback_finished(session, f"reminder-{events[0].id}", datetime(2026, 7, 1, 19, 0, 5))
        refreshed_event = session.get(ReminderEvent, events[0].id)

        assert [event.id for event in pending] == [events[0].id]
        assert acknowledged.id == events[0].id
        assert refreshed_event.ack_at == datetime(2026, 7, 1, 19, 0, 5)
        assert refreshed_event.event_type == ReminderEventType.START_DUE


def test_speak_message_has_no_priority_field() -> None:
    message = build_speak_message("hello", message_id="msg-test")

    assert message == {
        "type": "speak",
        "message_id": "msg-test",
        "text": "hello",
    }


def test_today_plan_payload_can_be_synced_to_device_for_offline_reminders() -> None:
    with make_session() as session:
        make_daily_task(session)
        payload = build_today_plan_payload(session, date(2026, 7, 1))
        device = mark_device_plan_synced(session, "box3-001", date(2026, 7, 1), datetime(2026, 7, 1, 6, 0))

        assert payload["date"] == "2026-07-01"
        assert [task["title"] for task in payload["tasks"]] == ["homework"]
        assert device.last_plan_sync_date == date(2026, 7, 1)
        assert device.last_plan_sync_at == datetime(2026, 7, 1, 6, 0)


def test_device_websocket_route_is_registered() -> None:
    assert any(route.path == "/ws/device/{device_id}" for route in fastapi_app.routes)
