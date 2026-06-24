import datetime as dt

from sqlmodel import Field, SQLModel

from app.models.enums import DeviceType


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Device(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    device_id: str = Field(index=True, unique=True)
    device_type: DeviceType = Field(default=DeviceType.ESP32_S3_BOX_3, index=True)
    hardware_model: str = "ESP32-S3-BOX-3"
    chip_model: str = "ESP32-S3-R8"
    firmware_version: str | None = None
    is_online: bool = Field(default=False, index=True)
    last_seen_at: dt.datetime | None = Field(default=None, index=True)
    last_plan_sync_date: dt.date | None = Field(default=None, index=True)
    last_plan_sync_at: dt.datetime | None = Field(default=None, index=True)
    connected_at: dt.datetime | None = None
    disconnected_at: dt.datetime | None = None
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)
