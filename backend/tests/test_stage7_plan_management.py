from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.database import get_session
from app.main import app as fastapi_app
from app.models.enums import TaskKind
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.services.calendar_plans import create_schedule_plan, list_schedule_task_items
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


def make_plan(session: Session) -> int:
    student = get_or_create_default_student(session)
    plan = create_schedule_plan(
        session,
        student.id,
        SchedulePlanCreate(
            name="上午计划",
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
                ),
                ScheduleTaskItemCreate(
                    sort_order=2,
                    task_kind=TaskKind.BREAK,
                    title="休息",
                    planned_start_time=time(9, 30),
                    planned_end_time=time(9, 40),
                    planned_minutes=10,
                ),
            ],
        ),
    )
    return plan.id


def test_patch_plan_item_updates_task_fields() -> None:
    with make_session() as session:
        plan_id = make_plan(session)

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        try:
            plan = TestClient(fastapi_app).get(f"/api/calendar-plans/{plan_id}").json()
            item_id = plan["items"][0]["id"]
            response = TestClient(fastapi_app).patch(
                f"/api/calendar-plans/{plan_id}/items/{item_id}",
                json={
                    "title": "竖式计算",
                    "planned_start_time": "09:05",
                    "planned_end_time": "09:35",
                    "planned_minutes": 30,
                },
            )
        finally:
            fastapi_app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "竖式计算"
        assert payload["planned_start_time"] == "09:05:00"
        assert payload["planned_minutes"] == 30


def test_patch_plan_item_rejects_duplicate_start_time() -> None:
    with make_session() as session:
        plan_id = make_plan(session)

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        try:
            plan = TestClient(fastapi_app).get(f"/api/calendar-plans/{plan_id}").json()
            item_id = plan["items"][0]["id"]
            response = TestClient(fastapi_app).patch(
                f"/api/calendar-plans/{plan_id}/items/{item_id}",
                json={"planned_start_time": "09:30", "planned_end_time": "09:55"},
            )
        finally:
            fastapi_app.dependency_overrides.clear()

        assert response.status_code == 400
        assert response.json()["detail"] == "schedule task items cannot share the same planned_start_time"


def test_plans_page_route_is_registered() -> None:
    assert any(route.path == "/plans" for route in fastapi_app.routes)


def test_creating_today_plan_refreshes_dashboard_tasks() -> None:
    with make_session() as session:
        today = date.today()

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            response = client.post(
                "/api/calendar-plans",
                json={
                    "name": "今日验收计划",
                    "start_date": today.isoformat(),
                    "end_date": today.isoformat(),
                    "repeat_rule": {"weekdays": [today.isoweekday()]},
                    "items": [
                        {
                            "sort_order": 1,
                            "task_kind": "homework",
                            "subject": "数学",
                            "title": "今日数学作业",
                            "planned_start_time": "14:00",
                            "planned_end_time": "14:30",
                            "planned_minutes": 30,
                        }
                    ],
                },
            )
            assert response.status_code == 201

            dashboard = client.get("/api/dashboard/today")
            assert dashboard.status_code == 200
            tasks = dashboard.json()["tasks"]
            assert [task["title"] for task in tasks] == ["今日数学作业"]
        finally:
            fastapi_app.dependency_overrides.clear()


def test_patch_plan_item_refreshes_unstarted_today_task() -> None:
    with make_session() as session:
        today = date.today()
        student = get_or_create_default_student(session)
        plan = create_schedule_plan(
            session,
            student.id,
            SchedulePlanCreate(
                name="今日修改计划",
                start_date=today,
                end_date=today,
                repeat_rule={"weekdays": [today.isoweekday()]},
                items=[
                    ScheduleTaskItemCreate(
                        sort_order=1,
                        task_kind=TaskKind.HOMEWORK,
                        subject="语文",
                        title="旧任务",
                        planned_start_time=time(15, 0),
                        planned_end_time=time(15, 20),
                        planned_minutes=20,
                    )
                ],
            ),
        )
        generate_daily_tasks(session, today)
        item_id = list_schedule_task_items(session, plan.id)[0].id

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            response = client.patch(
                f"/api/calendar-plans/{plan.id}/items/{item_id}",
                json={
                    "title": "新任务",
                    "planned_start_time": "15:10",
                    "planned_end_time": "15:40",
                    "planned_minutes": 30,
                },
            )
            assert response.status_code == 200

            tasks = list_daily_tasks(session, today)
            assert len(tasks) == 1
            assert tasks[0].title == "新任务"
            assert tasks[0].current_start_at.time() == time(15, 10)
            assert tasks[0].planned_minutes == 30
        finally:
            fastapi_app.dependency_overrides.clear()
