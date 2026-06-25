from datetime import date, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.database import get_session
from app.main import app as fastapi_app
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.services.calendar_plans import create_schedule_plan
from app.services.daily_tasks import generate_daily_tasks
from app.services.reminders import generate_due_reminders
from app.services.students import get_or_create_default_student


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def create_sample_plan(session: Session, target_date: date) -> None:
    student = get_or_create_default_student(session)
    create_schedule_plan(
        session,
        student.id,
        SchedulePlanCreate(
            name="language settings plan",
            start_date=target_date,
            end_date=target_date,
            repeat_rule={"weekdays": [target_date.isoweekday()]},
            items=[
                ScheduleTaskItemCreate(
                    sort_order=1,
                    task_kind="homework",
                    subject="数学",
                    title="数学作业",
                    planned_start_time=time(9, 0),
                    planned_end_time=time(9, 25),
                    planned_minutes=25,
                )
            ],
        ),
    )
    generate_daily_tasks(session, target_date)


def test_language_settings_api_round_trip_and_preview() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            response = client.get("/api/language-settings")
            assert response.status_code == 200
            assert response.json()["virtual_reply_templates"]["unrecognized"] == "刚才你说什么，我没有听清楚。"
            assert "播报本日计划" in response.json()["command_phrases"]["QUERY_TODAY_PLAN"]

            saved = client.put(
                "/api/language-settings",
                json={
                    "today_plan_templates": {
                        "single": "{date_label}自定义播报：{task_summaries}。",
                    },
                    "virtual_reply_templates": {
                        "unrecognized": "没识别到，请再说一次。",
                        "clarify": "你是想说：{options}？",
                    },
                    "command_phrases": {
                        "QUERY_TODAY_PLAN": ["今日播报"],
                    },
                },
            )
            assert saved.status_code == 200
            payload = saved.json()
            assert payload["today_plan_templates"]["single"].startswith("{date_label}自定义播报")
            assert payload["virtual_reply_templates"]["clarify"] == "你是想说：{options}？"
            assert payload["command_phrases"]["QUERY_TODAY_PLAN"] == ["今日播报"]

            preview = client.post(
                "/api/language-settings/preview",
                json={"template": "你好{student}", "values": {"student": "小明"}},
            )
            assert preview.status_code == 200
            assert preview.json() == {"text": "你好小明", "fields": ["student"]}
        finally:
            fastapi_app.dependency_overrides.clear()


def test_today_plan_speak_text_uses_language_template() -> None:
    with make_session() as session:
        target_date = date(2026, 6, 25)
        create_sample_plan(session, target_date)

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            client.put(
                "/api/language-settings",
                json={"today_plan_templates": {"single": "{date_label}自定义播报：{task_summaries}。"}},
            )

            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                assert websocket.receive_json()["state"] == "connected"
                websocket.send_json(
                    {
                        "type": "device_hello",
                        "device_id": "virtual-box3-001",
                        "device_type": "virtual_box_3",
                        "firmware_version": "language-test",
                    }
                )
                for _ in range(4):
                    message = websocket.receive_json()
                    if message.get("state") == "today_plan":
                        break
                websocket.send_json(
                    {
                        "type": "voice_command",
                        "device_id": "virtual-box3-001",
                        "command": "QUERY_TODAY_PLAN",
                        "text": "今日播报",
                        "timestamp": "2026-06-25T08:00:00",
                        "target_date": "2026-06-25",
                    }
                )
                speak = None
                for _ in range(4):
                    message = websocket.receive_json()
                    if message.get("type") == "speak":
                        speak = message
                        break
                assert speak is not None
                assert "自定义播报" in speak["text"]
        finally:
            fastapi_app.dependency_overrides.clear()


def test_reminder_generation_uses_language_template() -> None:
    with make_session() as session:
        target_date = date(2026, 6, 25)
        create_sample_plan(session, target_date)

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            client.put(
                "/api/language-settings",
                json={"reminder_templates": {"start_due": "请开始{task_name}，预计{planned_minutes}分钟。"}},
            )

            events = generate_due_reminders(session, datetime(2026, 6, 25, 9, 0))

            assert events[0].message_text == "请开始数学数学作业，预计25分钟。"
        finally:
            fastapi_app.dependency_overrides.clear()
