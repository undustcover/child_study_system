from datetime import date, time

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.models.enums import ExceptionType, HolidayDayType, TaskKind
from app.schemas.calendar import (
    HolidayCreate,
    ScheduleExceptionCreate,
    SchedulePlanCreate,
    ScheduleTaskItemCreate,
)
from app.services.calendar_plans import create_schedule_plan, upsert_schedule_exception
from app.services.daily_tasks import generate_daily_tasks, list_daily_tasks
from app.services.holiday_calendar import upsert_holiday
from app.services.students import get_or_create_default_student


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def make_plan(session: Session, *, skip_public_holidays: bool = False) -> int:
    student = get_or_create_default_student(session)
    plan = create_schedule_plan(
        session,
        student.id,
        SchedulePlanCreate(
            name="上学日晚间计划",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            repeat_rule={"weekdays": [1, 2, 3, 4, 5]},
            skip_public_holidays=skip_public_holidays,
            items=[
                ScheduleTaskItemCreate(
                    sort_order=1,
                    task_kind=TaskKind.HOMEWORK,
                    subject="数学",
                    title="数学作业",
                    planned_start_time=time(19, 0),
                    planned_end_time=time(19, 40),
                    planned_minutes=40,
                ),
                ScheduleTaskItemCreate(
                    sort_order=2,
                    task_kind=TaskKind.BREAK,
                    title="休息",
                    planned_start_time=time(19, 40),
                    planned_end_time=time(19, 50),
                    planned_minutes=10,
                ),
            ],
        ),
    )
    return plan.id


def test_generate_daily_tasks_from_weekday_plan() -> None:
    with make_session() as session:
        make_plan(session)

        created, skipped = generate_daily_tasks(session, date(2026, 7, 1))
        tasks = list_daily_tasks(session, date(2026, 7, 1))

        assert len(created) == 2
        assert skipped == []
        assert [task.title for task in tasks] == ["数学作业", "休息"]
        assert tasks[0].subject == "数学"
        assert tasks[1].task_kind == TaskKind.BREAK


def test_generate_is_idempotent_for_same_date() -> None:
    with make_session() as session:
        make_plan(session)

        first_created, _ = generate_daily_tasks(session, date(2026, 7, 1))
        second_created, _ = generate_daily_tasks(session, date(2026, 7, 1))
        tasks = list_daily_tasks(session, date(2026, 7, 1))

        assert len(first_created) == 2
        assert second_created == []
        assert len(tasks) == 2


def test_no_tasks_generated_when_no_repeat_rule_match() -> None:
    with make_session() as session:
        make_plan(session)

        created, skipped = generate_daily_tasks(session, date(2026, 7, 4))
        tasks = list_daily_tasks(session, date(2026, 7, 4))

        assert created == []
        assert skipped == []
        assert tasks == []


def test_public_holiday_can_skip_plan() -> None:
    with make_session() as session:
        make_plan(session, skip_public_holidays=True)
        upsert_holiday(
            session,
            HolidayCreate(
                date=date(2026, 7, 1),
                label="测试节假日",
                day_type=HolidayDayType.PUBLIC_HOLIDAY,
                source="test",
                is_rest_day=True,
            ),
        )

        created, skipped = generate_daily_tasks(session, date(2026, 7, 1))
        tasks = list_daily_tasks(session, date(2026, 7, 1))

        assert created == []
        assert skipped == []
        assert tasks == []


def test_single_day_skip_exception_prevents_generation() -> None:
    with make_session() as session:
        plan_id = make_plan(session)
        upsert_schedule_exception(
            session,
            plan_id,
            ScheduleExceptionCreate(
                date=date(2026, 7, 1),
                exception_type=ExceptionType.SKIP,
                reason="临时休息",
            ),
        )

        created, skipped = generate_daily_tasks(session, date(2026, 7, 1))
        tasks = list_daily_tasks(session, date(2026, 7, 1))

        assert created == []
        assert skipped == [plan_id]
        assert tasks == []


def test_single_day_override_payload_can_generate_replacement_tasks() -> None:
    with make_session() as session:
        plan_id = make_plan(session)
        upsert_schedule_exception(
            session,
            plan_id,
            ScheduleExceptionCreate(
                date=date(2026, 7, 1),
                exception_type=ExceptionType.OVERRIDE,
                override_payload={
                    "items": [
                        {
                            "sort_order": 1,
                            "task_kind": "reading",
                            "subject": "语文",
                            "title": "阅读",
                            "planned_start_time": "20:00:00",
                            "planned_end_time": "20:30:00",
                            "planned_minutes": 30,
                        }
                    ]
                },
                reason="当天临时调整",
            ),
        )

        created, skipped = generate_daily_tasks(session, date(2026, 7, 1))
        tasks = list_daily_tasks(session, date(2026, 7, 1))

        assert len(created) == 1
        assert skipped == []
        assert len(tasks) == 1
        assert tasks[0].title == "阅读"
        assert tasks[0].subject == "语文"
        assert tasks[0].source_schedule_task_item_id is None
