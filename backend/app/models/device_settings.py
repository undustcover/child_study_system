import datetime as dt

from sqlmodel import Field, SQLModel


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class DeviceSettings(SQLModel, table=True):
    settings_key: str = Field(primary_key=True)
    target_device_id: str | None = Field(default=None, index=True)
    auto_sync_today_plan: bool = True
    auto_broadcast_today_plan: bool = False
    replay_today_plan_on_reconnect: bool = False
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)
