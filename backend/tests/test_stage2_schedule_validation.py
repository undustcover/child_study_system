from datetime import date, time

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.models.enums import TaskKind
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.services.calendar_plans import create_schedule_plan
from app.services.students import get_or_create_default_student


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_schedule_plan_rejects_duplicate_start_times() -> None:
    with make_session() as session:
        student = get_or_create_default_student(session)

        with pytest.raises(HTTPException) as exc_info:
            create_schedule_plan(
                session,
                student.id,
                SchedulePlanCreate(
                    name="duplicate start time plan",
                    start_date=date(2026, 7, 1),
                    end_date=date(2026, 7, 31),
                    repeat_rule={"weekdays": [1, 2, 3, 4, 5]},
                    items=[
                        ScheduleTaskItemCreate(
                            sort_order=1,
                            task_kind=TaskKind.HOMEWORK,
                            title="math",
                            planned_start_time=time(19, 0),
                            planned_end_time=time(19, 30),
                            planned_minutes=30,
                        ),
                        ScheduleTaskItemCreate(
                            sort_order=2,
                            task_kind=TaskKind.READING,
                            title="reading",
                            planned_start_time=time(19, 0),
                            planned_end_time=time(19, 20),
                            planned_minutes=20,
                        ),
                    ],
                ),
            )

        assert exc_info.value.status_code == 400
