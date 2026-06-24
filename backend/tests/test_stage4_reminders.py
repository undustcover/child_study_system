from datetime import date, datetime, time

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.enums import DailyTaskStatus, ReminderEventStatus, ReminderEventType, TaskKind
from app.models.reminder import ReminderEvent
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.services.calendar_plans import create_schedule_plan
from app.services.daily_tasks import generate_daily_tasks, list_daily_tasks
from app.services.reminders import (
    generate_due_reminders,
    get_or_create_reminder_settings,
    list_pending_reminder_events,
    mark_reminder_consumed,
    update_reminder_settings,
)
from app.services.students import get_or_create_default_student


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def make_daily_tasks(session: Session) -> list[app.models.DailyTask]:
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
                ),
                ScheduleTaskItemCreate(
                    sort_order=2,
                    task_kind=TaskKind.BREAK,
                    title="break",
                    planned_start_time=time(19, 40),
                    planned_end_time=time(19, 50),
                    planned_minutes=10,
                ),
            ],
        ),
    )
    generate_daily_tasks(session, date(2026, 7, 1))
    return list_daily_tasks(session, date(2026, 7, 1))


def test_pre_start_and_start_due_reminders_are_recorded_once() -> None:
    with make_session() as session:
        task = make_daily_tasks(session)[0]

        pre_events = generate_due_reminders(session, datetime(2026, 7, 1, 18, 55))
        start_events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 0))
        duplicate_start_events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 0))

        assert [event.event_type for event in pre_events] == [ReminderEventType.PRE_START]
        assert [event.event_type for event in start_events] == [ReminderEventType.START_DUE]
        assert duplicate_start_events == []
        assert pre_events[0].daily_task_id == task.id
        assert "mathhomework" in pre_events[0].message_text


def test_scheduler_does_not_backfill_missed_punctual_start_reminder() -> None:
    with make_session() as session:
        make_daily_tasks(session)

        events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 2))

        assert events == []


def test_start_due_repeats_every_five_minutes_up_to_three_times() -> None:
    with make_session() as session:
        make_daily_tasks(session)

        first = generate_due_reminders(session, datetime(2026, 7, 1, 19, 0))
        second = generate_due_reminders(session, datetime(2026, 7, 1, 19, 5))
        third = generate_due_reminders(session, datetime(2026, 7, 1, 19, 10))
        fourth = generate_due_reminders(session, datetime(2026, 7, 1, 19, 15))

        assert [event.event_type for event in first + second + third] == [
            ReminderEventType.START_DUE,
            ReminderEventType.START_DUE,
            ReminderEventType.START_DUE,
        ]
        assert [event.event_type for event in fourth] == [ReminderEventType.DELAYED_START]


def test_delayed_start_marks_overdue_after_fifteen_minutes() -> None:
    with make_session() as session:
        task = make_daily_tasks(session)[0]

        events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 15))
        refreshed_task = session.get(app.models.DailyTask, task.id)

        assert [event.event_type for event in events] == [ReminderEventType.DELAYED_START]
        assert refreshed_task.status == DailyTaskStatus.OVERDUE


def test_finish_confirm_and_break_end_events_enter_pending_channel() -> None:
    with make_session() as session:
        study_task, break_task = make_daily_tasks(session)
        study_task.status = DailyTaskStatus.WAITING_FINISH_CONFIRM
        break_task.status = DailyTaskStatus.STUDYING
        session.add(study_task)
        session.add(break_task)
        session.commit()

        finish_events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 40))
        break_events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 50))
        pending_events = list_pending_reminder_events(session)

        assert [event.event_type for event in finish_events] == [ReminderEventType.FINISH_CONFIRM]
        assert [event.event_type for event in break_events] == [ReminderEventType.BREAK_END]
        assert [event.id for event in pending_events] == [event.id for event in finish_events + break_events]


def test_finish_confirm_timeout_marks_parent_confirm_required() -> None:
    with make_session() as session:
        study_task = make_daily_tasks(session)[0]
        study_task.status = DailyTaskStatus.WAITING_FINISH_CONFIRM
        session.add(study_task)
        session.commit()

        generate_due_reminders(session, datetime(2026, 7, 1, 19, 40))
        generate_due_reminders(session, datetime(2026, 7, 1, 19, 43))
        generate_due_reminders(session, datetime(2026, 7, 1, 19, 46))
        timeout_events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 49))
        refreshed_task = session.get(app.models.DailyTask, study_task.id)

        assert timeout_events == []
        assert refreshed_task.status == DailyTaskStatus.PARENT_CONFIRM_REQUIRED


def test_consuming_reminder_marks_device_delivery_metadata() -> None:
    with make_session() as session:
        make_daily_tasks(session)
        event = generate_due_reminders(session, datetime(2026, 7, 1, 19, 0))[0]

        consumed = mark_reminder_consumed(
            session,
            event.id,
            device_id="virtual-box3-001",
            sent_at=datetime(2026, 7, 1, 19, 0, 5),
        )
        pending_events = session.exec(
            select(ReminderEvent).where(ReminderEvent.status == ReminderEventStatus.PENDING)
        ).all()

        assert consumed.status == ReminderEventStatus.CONSUMED
        assert consumed.device_id == "virtual-box3-001"
        assert consumed.sent_at == datetime(2026, 7, 1, 19, 0, 5)
        assert pending_events == []


def test_custom_settings_can_disable_pre_start_reminder() -> None:
    with make_session() as session:
        task = make_daily_tasks(session)[0]
        update_reminder_settings(
            session,
            task.student_id,
            {"pre_start_enabled": False},
        )

        events = generate_due_reminders(session, datetime(2026, 7, 1, 18, 55))

        assert events == []


def test_custom_settings_change_delayed_start_minutes_and_start_repeat_count() -> None:
    with make_session() as session:
        task = make_daily_tasks(session)[0]
        update_reminder_settings(
            session,
            task.student_id,
            {
                "start_due_repeat_interval_minutes": 2,
                "start_due_max_count": 2,
                "delayed_start_minutes": 6,
            },
        )

        first = generate_due_reminders(session, datetime(2026, 7, 1, 19, 0))
        second = generate_due_reminders(session, datetime(2026, 7, 1, 19, 2))
        third = generate_due_reminders(session, datetime(2026, 7, 1, 19, 4))
        delayed = generate_due_reminders(session, datetime(2026, 7, 1, 19, 6))

        assert [event.event_type for event in first + second] == [
            ReminderEventType.START_DUE,
            ReminderEventType.START_DUE,
        ]
        assert third == []
        assert [event.event_type for event in delayed] == [ReminderEventType.DELAYED_START]


def test_custom_template_renders_reminder_text() -> None:
    with make_session() as session:
        task = make_daily_tasks(session)[0]
        update_reminder_settings(
            session,
            task.student_id,
            {"templates": {"start_due": "请开始{subject}的{title}，预计{planned_minutes}分钟。"}},
        )

        events = generate_due_reminders(session, datetime(2026, 7, 1, 19, 0))
        settings = get_or_create_reminder_settings(session, task.student_id)

        assert settings.templates["start_due"] == "请开始{subject}的{title}，预计{planned_minutes}分钟。"
        assert events[0].message_text == "请开始math的homework，预计40分钟。"
