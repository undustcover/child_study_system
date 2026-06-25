from datetime import date, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.database import get_session
from app.main import app as fastapi_app
from app.models.enums import DailyTaskStatus, TaskKind
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.services.calendar_plans import create_schedule_plan
from app.services.daily_tasks import generate_daily_tasks, list_daily_tasks
from app.services.students import get_or_create_default_student


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def make_task(session: Session) -> int:
    student = get_or_create_default_student(session)
    create_schedule_plan(
        session,
        student.id,
        SchedulePlanCreate(
            name="morning plan",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            repeat_rule={"weekdays": [1, 2, 3, 4, 5]},
            items=[
                ScheduleTaskItemCreate(
                    sort_order=1,
                    task_kind=TaskKind.PRACTICE,
                    subject="数学",
                    title="口算练习",
                    planned_start_time=time(9, 0),
                    planned_end_time=time(9, 25),
                    planned_minutes=25,
                )
            ],
        ),
    )
    generate_daily_tasks(session, date(2026, 7, 1))
    return list_daily_tasks(session, date(2026, 7, 1))[0].id


def test_parent_correction_updates_task_status_and_times() -> None:
    with make_session() as session:
        task_id = make_task(session)

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        try:
            response = TestClient(fastapi_app).patch(
                f"/api/daily-tasks/{task_id}/correction",
                json={
                    "status": "completed",
                    "current_start_at": "2026-07-01T09:05:00",
                    "current_end_at": "2026-07-01T09:35:00",
                },
            )
        finally:
            fastapi_app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == DailyTaskStatus.COMPLETED
        assert payload["current_start_at"] == "2026-07-01T09:05:00"
        assert payload["modify_count"] == 1


def test_stage7_remaining_page_routes_are_registered() -> None:
    paths = {route.path for route in fastapi_app.routes}

    assert "/devices" in paths
    assert "/stats" in paths
    assert "/corrections" in paths
