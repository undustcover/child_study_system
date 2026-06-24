from enum import StrEnum
from uuid import uuid4


class DeviceMessageType(StrEnum):
    DEVICE_HELLO = "device_hello"
    VOICE_COMMAND = "voice_command"
    PLAYBACK_FINISHED = "playback_finished"


class ServerMessageType(StrEnum):
    SPEAK = "speak"
    DISPLAY_STATE = "display_state"
    SYNC_STATE = "sync_state"


def new_message_id(prefix: str = "msg") -> str:
    return f"{prefix}-{uuid4().hex}"


def build_speak_message(text: str, *, message_id: str | None = None) -> dict[str, str]:
    return {
        "type": ServerMessageType.SPEAK,
        "message_id": message_id or new_message_id(),
        "text": text,
    }


def build_display_state_message(state: str, payload: dict | None = None) -> dict:
    return {
        "type": ServerMessageType.DISPLAY_STATE,
        "state": state,
        "payload": payload or {},
    }


def build_sync_state_message(device_id: str, state: str, payload: dict | None = None) -> dict:
    return {
        "type": ServerMessageType.SYNC_STATE,
        "device_id": device_id,
        "state": state,
        "payload": payload or {},
    }
