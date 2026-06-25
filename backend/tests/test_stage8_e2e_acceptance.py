from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.core.database import get_session
from app.main import app as fastapi_app
from app.models.enums import DailyTaskStatus, ReminderEventStatus, StudySessionStatus, TimeSegmentKind
from app.models.reminder import ReminderEvent
from app.models.session import StudySession, TimeSegment
from app.services.task_state_machine import mark_due_tasks_waiting_finish_confirm


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def receive_until(websocket, predicate, limit: int = 8) -> dict:
    for _ in range(limit):
        message = websocket.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected websocket message was not received")


def voice_message(command: str, text: str, timestamp: str, target_date: str = "2026-06-25") -> dict:
    return {
        "type": "voice_command",
        "device_id": "virtual-box3-001",
        "command": command,
        "text": text,
        "timestamp": timestamp,
        "target_date": target_date,
    }


def test_stage8_p1a_end_to_end_acceptance_flow() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            plan_response = client.post(
                "/api/calendar-plans",
                json={
                    "name": "阶段8验收计划",
                    "start_date": "2026-06-25",
                    "end_date": "2026-07-31",
                    "repeat_rule": {"weekdays": [1, 2, 3, 4, 5]},
                    "items": [
                        {
                            "sort_order": 1,
                            "task_kind": "homework",
                            "subject": "数学",
                            "title": "数学作业",
                            "planned_start_time": "09:00",
                            "planned_end_time": "09:25",
                            "planned_minutes": 25,
                        },
                        {
                            "sort_order": 2,
                            "task_kind": "break",
                            "title": "眼睛休息",
                            "planned_start_time": "09:25",
                            "planned_end_time": "09:35",
                            "planned_minutes": 10,
                        },
                    ],
                },
            )
            assert plan_response.status_code == 201

            generated = client.post("/api/daily-tasks/generate?date=2026-06-25")
            assert generated.status_code == 200
            assert [task["title"] for task in generated.json()["tasks"]] == ["数学作业", "眼睛休息"]

            reminder_response = client.post("/api/reminders/generate-due?now=2026-06-25T09:00:00")
            assert reminder_response.status_code == 200
            assert reminder_response.json()[0]["message_text"]

            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                connected = websocket.receive_json()
                assert connected["state"] == "connected"

                websocket.send_json(
                    {
                        "type": "device_hello",
                        "device_id": "virtual-box3-001",
                        "device_type": "virtual_box_3",
                        "firmware_version": "test-stage8",
                    }
                )
                registered = receive_until(websocket, lambda message: message.get("state") == "device_registered")
                today_plan = receive_until(websocket, lambda message: message.get("state") == "today_plan")
                speak = receive_until(websocket, lambda message: message.get("type") == "speak")

                assert registered["payload"]["device_type"] == "virtual_box_3"
                assert [task["title"] for task in today_plan["payload"]["tasks"]] == ["数学作业", "眼睛休息"]

                websocket.send_json({"type": "playback_finished", "message_id": speak["message_id"]})
                playback_ack = receive_until(websocket, lambda message: message.get("state") == "playback_acknowledged")
                assert playback_ack["state"] == "playback_acknowledged"

                websocket.send_json(voice_message("START_STUDY", "开始学习", "2026-06-25T09:00:00"))
                started = receive_until(websocket, lambda message: message.get("type") == "display_state")
                assert started["state"] == "studying"
                study_task_id = started["payload"]["task"]["id"]

                websocket.send_json(voice_message("PAUSE_STUDY", "暂停", "2026-06-25T09:10:00"))
                paused = receive_until(websocket, lambda message: message.get("type") == "display_state")
                assert paused["state"] == "paused"

                websocket.send_json(voice_message("RESUME_STUDY", "继续", "2026-06-25T09:15:00"))
                resumed = receive_until(websocket, lambda message: message.get("type") == "display_state")
                assert resumed["state"] == "studying"

                changed = mark_due_tasks_waiting_finish_confirm(session, datetime(2026, 6, 25, 9, 25))
                assert [task.id for task in changed] == [study_task_id]

                websocket.send_json(voice_message("COMPLETE_STUDY", "完成了", "2026-06-25T09:30:00"))
                completed = receive_until(websocket, lambda message: message.get("type") == "display_state")
                assert completed["state"] == "studying"
                assert completed["payload"]["message"] == "break started automatically"
                assert completed["payload"]["task"]["title"] == "眼睛休息"

            sessions = list(session.exec(select(StudySession).order_by(StudySession.id)))
            segments = list(session.exec(select(TimeSegment).order_by(TimeSegment.id)))
            reminder = session.exec(select(ReminderEvent)).one()
            dashboard = client.get("/api/dashboard/today?date=2026-06-25").json()

            assert sessions[0].status == StudySessionStatus.COMPLETED
            assert sessions[0].effective_seconds == 25 * 60
            assert sessions[1].status == StudySessionStatus.ACTIVE
            assert [segment.segment_kind for segment in segments] == [
                TimeSegmentKind.STUDY,
                TimeSegmentKind.PAUSE,
                TimeSegmentKind.STUDY,
                TimeSegmentKind.BREAK,
            ]
            assert reminder.status == ReminderEventStatus.CONSUMED
            assert dashboard["stats"]["completed_tasks"] == 1
            assert dashboard["current"]["task"]["title"] == "眼睛休息"
        finally:
            fastapi_app.dependency_overrides.clear()


def test_query_today_plan_voice_command_pushes_speak_message() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            client.post(
                "/api/calendar-plans",
                json={
                    "name": "今日计划播报测试",
                    "start_date": "2026-06-25",
                    "end_date": "2026-07-31",
                    "repeat_rule": {"weekdays": [1, 2, 3, 4, 5]},
                    "items": [
                        {
                            "sort_order": 1,
                            "task_kind": "homework",
                            "subject": "数学",
                            "title": "数学作业",
                            "planned_start_time": "09:00",
                            "planned_end_time": "09:25",
                            "planned_minutes": 25,
                        },
                        {
                            "sort_order": 2,
                            "task_kind": "break",
                            "title": "眼睛休息",
                            "planned_start_time": "09:25",
                            "planned_end_time": "09:35",
                            "planned_minutes": 10,
                        },
                    ],
                },
            )
            client.post("/api/daily-tasks/generate?date=2026-06-25")

            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                assert websocket.receive_json()["state"] == "connected"
                websocket.send_json(
                    {
                        "type": "device_hello",
                        "device_id": "virtual-box3-001",
                        "device_type": "virtual_box_3",
                        "firmware_version": "test-stage8-query",
                    }
                )
                receive_until(websocket, lambda message: message.get("state") == "device_registered")
                receive_until(websocket, lambda message: message.get("state") == "today_plan")

                websocket.send_json(
                    voice_message("QUERY_TODAY_PLAN", "播报本日计划", "2026-06-25T08:00:00")
                )
                display_state = receive_until(websocket, lambda message: message.get("type") == "display_state")
                speak = receive_until(websocket, lambda message: message.get("type") == "speak")

                assert display_state["state"] == "pending"
                assert display_state["payload"]["command"] == "QUERY_TODAY_PLAN"
                assert "数学作业" in speak["text"]
                assert "眼睛休息" in speak["text"]
        finally:
            fastapi_app.dependency_overrides.clear()


def test_query_today_plan_without_tasks_still_pushes_speak_message() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                assert websocket.receive_json()["state"] == "connected"
                websocket.send_json(
                    {
                        "type": "device_hello",
                        "device_id": "virtual-box3-001",
                        "device_type": "virtual_box_3",
                        "firmware_version": "test-stage8-empty",
                    }
                )
                receive_until(websocket, lambda message: message.get("state") == "device_registered")
                receive_until(websocket, lambda message: message.get("state") == "today_plan")

                websocket.send_json(
                    voice_message("QUERY_TODAY_PLAN", "今天安排", "2026-06-28T08:00:00", target_date="2026-06-28")
                )
                display_state = receive_until(websocket, lambda message: message.get("type") == "display_state")
                speak = receive_until(websocket, lambda message: message.get("type") == "speak")

                assert display_state["state"] == "idle"
                assert display_state["payload"]["message"] == "no startable task found today"
                assert speak["text"] == "6月28日还没有安排任务。"
        finally:
            fastapi_app.dependency_overrides.clear()


def test_complete_last_task_pushes_today_completed_speak_message() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            client.post(
                "/api/calendar-plans",
                json={
                    "name": "最后一项完成播报测试",
                    "start_date": "2026-06-25",
                    "end_date": "2026-06-25",
                    "repeat_rule": {"weekdays": [4]},
                    "items": [
                        {
                            "sort_order": 1,
                            "task_kind": "homework",
                            "subject": "数学",
                            "title": "数学作业",
                            "planned_start_time": "09:00",
                            "planned_end_time": "09:25",
                            "planned_minutes": 25,
                        }
                    ],
                },
            )
            client.post("/api/daily-tasks/generate?date=2026-06-25")

            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                assert websocket.receive_json()["state"] == "connected"
                websocket.send_json(voice_message("START_STUDY", "开始学习", "2026-06-25T09:00:00"))
                started = receive_until(websocket, lambda message: message.get("type") == "display_state")
                assert started["state"] == "studying"

                websocket.send_json(voice_message("COMPLETE_STUDY", "完成了", "2026-06-25T09:20:00"))
                completed = receive_until(websocket, lambda message: message.get("type") == "display_state")
                speak = receive_until(websocket, lambda message: message.get("type") == "speak")

                assert completed["state"] == "completed"
                assert speak["text"] == "今天的安排都完成了，辛苦啦。可以休息了。"
        finally:
            fastapi_app.dependency_overrides.clear()
