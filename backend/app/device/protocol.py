from enum import StrEnum


class DeviceMessageType(StrEnum):
    DEVICE_HELLO = "device_hello"
    VOICE_COMMAND = "voice_command"
    PLAYBACK_FINISHED = "playback_finished"


class ServerMessageType(StrEnum):
    SPEAK = "speak"
    DISPLAY_STATE = "display_state"
    SYNC_STATE = "sync_state"
