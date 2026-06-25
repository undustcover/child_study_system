from datetime import date, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.database import get_session
from app.main import app as fastapi_app
from app.models.enums import DailyTaskStatus, ReminderEventType, TaskKind
from app.models.reminder import ReminderEvent
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.services.calendar_plans import create_schedule_plan
from app.services.daily_tasks import generate_daily_tasks, list_daily_tasks
from app.services.dashboard import get_today_dashboard
from app.services.devices import mark_device_plan_synced, register_or_update_device
from app.services.students import get_or_create_default_student


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def make_dashboard_fixture(session: Session) -> None:
    student = get_or_create_default_student(session)
    create_schedule_plan(
        session,
        student.id,
        SchedulePlanCreate(
            name="weekday morning plan",
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
                    title="喝水和休息",
                    planned_start_time=time(9, 30),
                    planned_end_time=time(9, 40),
                    planned_minutes=10,
                ),
            ],
        ),
    )
    generate_daily_tasks(session, date(2026, 7, 1))
    tasks = list_daily_tasks(session, date(2026, 7, 1))
    tasks[0].status = DailyTaskStatus.STUDYING
    session.add(tasks[0])
    session.add(
        ReminderEvent(
            daily_task_id=tasks[0].id,
            event_type=ReminderEventType.START_DUE,
            scheduled_at=datetime(2026, 7, 1, 9, 0),
            message_text="现在开始数学口算练习，计划25分钟。",
        )
    )
    session.commit()
    register_or_update_device(session, "virtual-box3-001", device_type="virtual_box_3", when=datetime(2026, 7, 1, 8, 59))
    mark_device_plan_synced(session, "virtual-box3-001", date(2026, 7, 1), datetime(2026, 7, 1, 8, 59))


def test_today_dashboard_aggregates_tasks_device_and_reminders() -> None:
    with make_session() as session:
        make_dashboard_fixture(session)

        dashboard = get_today_dashboard(session, date(2026, 7, 1))

        assert dashboard.date_label == "7月1日 周三"
        assert dashboard.student_name == "默认学生"
        assert [task.title for task in dashboard.tasks] == ["口算练习", "喝水和休息"]
        assert dashboard.tasks[0].status_label == "正在做"
        assert dashboard.current.task.title == "口算练习"
        assert dashboard.current.description == "当前任务正在进行，孩子通过设备语音执行。"
        assert dashboard.stats.total_tasks == 2
        assert dashboard.stats.planned_minutes == 35
        assert dashboard.stats.device_status_label == "在线"
        assert dashboard.stats.reminder_count == 1
        assert dashboard.devices[0].device_id == "virtual-box3-001"
        assert dashboard.devices[0].sync_label == "今日计划已同步"
        assert dashboard.reminders[0].event_type_label == "开始提醒"


def test_dashboard_api_route_returns_today_payload() -> None:
    with make_session() as session:
        make_dashboard_fixture(session)

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        try:
            response = TestClient(fastapi_app).get("/api/dashboard/today?date=2026-07-01")
        finally:
            fastapi_app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["date"] == "2026-07-01"
        assert payload["tasks"][0]["title"] == "口算练习"
        assert payload["devices"][0]["status_label"] == "在线"
