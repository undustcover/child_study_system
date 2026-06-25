from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeviceSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    settings_key: str
    target_device_id: str | None
    auto_sync_today_plan: bool
    auto_broadcast_today_plan: bool
    replay_today_plan_on_reconnect: bool
    updated_at: datetime
    is_override: bool = False


class DeviceSettingsUpdate(BaseModel):
    auto_sync_today_plan: bool | None = None
    auto_broadcast_today_plan: bool | None = None
    replay_today_plan_on_reconnect: bool | None = None


class DeviceConfigSyncResponse(BaseModel):
    device_id: str
    sent: bool
    payload: dict
