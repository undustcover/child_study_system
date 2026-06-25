from datetime import date, time

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.database import get_session
from app.main import app as fastapi_app
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.services.calendar_plans import create_schedule_plan
from app.services.daily_tasks import generate_daily_tasks
from app.services.students import get_or_create_default_student


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


def create_sample_plan(session: Session) -> None:
    today = date.today()
    student = get_or_create_default_student(session)
    create_schedule_plan(
        session,
        student.id,
        SchedulePlanCreate(
            name="device settings test plan",
            start_date=today,
            end_date=today,
            repeat_rule={"weekdays": [today.isoweekday()]},
            items=[
                ScheduleTaskItemCreate(
                    sort_order=1,
                    task_kind="homework",
                    subject="数学",
                    title="数学作业",
                    planned_start_time=time(19, 0),
                    planned_end_time=time(19, 40),
                    planned_minutes=40,
                )
            ],
        ),
    )
    generate_daily_tasks(session, today)


def test_device_settings_default_api_round_trip() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            response = client.get("/api/devices/settings/default")
            assert response.status_code == 200
            assert response.json()["auto_sync_today_plan"] is True
            assert response.json()["auto_broadcast_today_plan"] is False

            saved = client.put(
                "/api/devices/settings/default",
                json={
                    "auto_sync_today_plan": True,
                    "auto_broadcast_today_plan": True,
                    "replay_today_plan_on_reconnect": True,
                },
            )
            assert saved.status_code == 200
            payload = saved.json()
            assert payload["auto_broadcast_today_plan"] is True
            assert payload["replay_today_plan_on_reconnect"] is True
        finally:
            fastapi_app.dependency_overrides.clear()


def test_device_specific_settings_route_can_create_override() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            inherited = client.get("/api/devices/virtual-box3-001/settings")
            assert inherited.status_code == 200
            assert inherited.json()["is_override"] is False

            override = client.put(
                "/api/devices/virtual-box3-001/settings",
                json={"auto_broadcast_today_plan": True},
            )
            assert override.status_code == 200
            payload = override.json()
            assert payload["is_override"] is True
            assert payload["target_device_id"] == "virtual-box3-001"
            assert payload["auto_broadcast_today_plan"] is True
        finally:
            fastapi_app.dependency_overrides.clear()


def test_device_hello_uses_saved_settings_for_auto_broadcast() -> None:
    with make_session() as session:
        create_sample_plan(session)

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            saved = client.put(
                "/api/devices/settings/default",
                json={
                    "auto_sync_today_plan": True,
                    "auto_broadcast_today_plan": True,
                    "replay_today_plan_on_reconnect": False,
                },
            )
            assert saved.status_code == 200

            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                assert websocket.receive_json()["state"] == "connected"
                websocket.send_json(
                    {
                        "type": "device_hello",
                        "device_id": "virtual-box3-001",
                        "device_type": "virtual_box_3",
                        "firmware_version": "settings-test",
                    }
                )
                receive_until(websocket, lambda message: message.get("state") == "device_registered")
                receive_until(websocket, lambda message: message.get("state") == "today_plan")
                speak = receive_until(websocket, lambda message: message.get("type") == "speak")

                assert "今天" in speak["text"] or "7月1日" in speak["text"]
                assert "数学作业" in speak["text"]
        finally:
            fastapi_app.dependency_overrides.clear()


def test_device_hello_pushes_config_sync_payload() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            client.put(
                "/api/language-settings",
                json={
                    "virtual_reply_templates": {"unrecognized": "设备同步核验未识别。"},
                    "command_phrases": {"QUERY_TODAY_PLAN": ["设备同步今日计划"]},
                },
            )
            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                assert websocket.receive_json()["state"] == "connected"
                websocket.send_json(
                    {
                        "type": "device_hello",
                        "device_id": "virtual-box3-001",
                        "device_type": "virtual_box_3",
                        "firmware_version": "config-sync-test",
                    }
                )
                config_message = receive_until(websocket, lambda message: message.get("state") == "device_config")

                payload = config_message["payload"]
                assert payload["device_id"] == "virtual-box3-001"
                assert payload["config_version"]
                assert payload["device_settings"]["auto_sync_today_plan"] is True
                assert payload["language_settings"]["virtual_reply_templates"]["unrecognized"] == "设备同步核验未识别。"
                assert payload["language_settings"]["command_phrases"]["QUERY_TODAY_PLAN"] == ["设备同步今日计划"]
        finally:
            fastapi_app.dependency_overrides.clear()


def test_manual_config_sync_endpoint_sends_to_online_device() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                assert websocket.receive_json()["state"] == "connected"

                response = client.post("/api/devices/virtual-box3-001/sync-config")
                assert response.status_code == 200
                assert response.json()["sent"] is True

                config_message = receive_until(websocket, lambda message: message.get("state") == "device_config")
                assert config_message["payload"]["device_id"] == "virtual-box3-001"
        finally:
            fastapi_app.dependency_overrides.clear()


def test_device_settings_update_repushes_config_to_online_device() -> None:
    with make_session() as session:

        def override_session():
            return session

        fastapi_app.dependency_overrides[get_session] = override_session
        client = TestClient(fastapi_app)
        try:
            with client.websocket_connect("/ws/device/virtual-box3-001") as websocket:
                assert websocket.receive_json()["state"] == "connected"

                response = client.put(
                    "/api/devices/virtual-box3-001/settings",
                    json={"auto_broadcast_today_plan": True, "replay_today_plan_on_reconnect": True},
                )
                assert response.status_code == 200

                config_message = receive_until(websocket, lambda message: message.get("state") == "device_config")
                device_settings = config_message["payload"]["device_settings"]
                assert device_settings["is_override"] is True
                assert device_settings["auto_broadcast_today_plan"] is True
                assert device_settings["replay_today_plan_on_reconnect"] is True
        finally:
            fastapi_app.dependency_overrides.clear()
