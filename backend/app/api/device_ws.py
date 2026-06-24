import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.core.database import get_session
from app.device.connection_manager import device_connection_manager
from app.device.protocol import (
    DeviceMessageType,
    build_display_state_message,
    build_speak_message,
    build_sync_state_message,
)
from app.services.devices import (
    handle_device_voice_command,
    build_today_plan_payload,
    mark_device_disconnected,
    mark_device_plan_synced,
    mark_playback_finished,
    pending_speak_events_for_device,
    register_or_update_device,
)
from app.services.reminders import mark_reminder_consumed

router = APIRouter(tags=["device websocket"])


@router.websocket("/ws/device/{device_id}")
async def device_ws(
    websocket: WebSocket,
    device_id: str,
    session: Session = Depends(get_session),
) -> None:
    await device_connection_manager.connect(device_id, websocket)
    register_or_update_device(session, device_id)
    await websocket.send_json(build_sync_state_message(device_id, "connected"))

    try:
        while True:
            payload = await websocket.receive_json()
            message_type = payload.get("type")

            if message_type == DeviceMessageType.DEVICE_HELLO:
                device = register_or_update_device(
                    session,
                    device_id,
                    device_type=payload.get("device_type"),
                    firmware_version=payload.get("firmware_version"),
                )
                await websocket.send_json(
                    build_sync_state_message(
                        device_id,
                        "device_registered",
                        {
                            "device_type": device.device_type,
                            "hardware_model": device.hardware_model,
                            "chip_model": device.chip_model,
                        },
                    )
                )
                today = dt.date.today()
                await websocket.send_json(
                    build_sync_state_message(device_id, "today_plan", build_today_plan_payload(session, today))
                )
                mark_device_plan_synced(session, device_id, today)
                await _push_pending_speak_events(websocket, session, device_id)
                continue

            if message_type == DeviceMessageType.VOICE_COMMAND:
                payload["device_id"] = device_id
                try:
                    result = handle_device_voice_command(session, payload)
                except HTTPException as exc:
                    await websocket.send_json(
                        build_display_state_message(
                            "error",
                            {
                                "command": payload.get("command"),
                                "message": str(exc.detail),
                                "device_id": device_id,
                                "text": payload.get("text"),
                            },
                        )
                    )
                    continue
                await websocket.send_json(
                    build_display_state_message(
                        result.task_status.value if result.task_status else "idle",
                        result.model_dump(mode="json"),
                    )
                )
                continue

            if message_type == DeviceMessageType.PLAYBACK_FINISHED:
                mark_playback_finished(session, payload.get("message_id", ""))
                await websocket.send_json(build_sync_state_message(device_id, "playback_acknowledged"))
                continue

            await websocket.send_json(build_sync_state_message(device_id, "unknown_message"))

    except WebSocketDisconnect:
        mark_device_disconnected(session, device_id)
        device_connection_manager.disconnect(device_id)


async def _push_pending_speak_events(websocket: WebSocket, session: Session, device_id: str) -> None:
    for event in pending_speak_events_for_device(session):
        message_id = f"reminder-{event.id}"
        await websocket.send_json(build_speak_message(event.message_text, message_id=message_id))
        mark_reminder_consumed(session, event.id, device_id=device_id, sent_at=event.scheduled_at)
