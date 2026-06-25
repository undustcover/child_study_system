from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.devices import DeviceSettingsRead, DeviceSettingsUpdate
from app.services.devices import (
    get_effective_device_settings,
    get_or_create_device_settings,
    update_device_settings,
)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/settings/default", response_model=DeviceSettingsRead)
async def read_default_device_settings(session: Session = Depends(get_session)) -> DeviceSettingsRead:
    settings = get_or_create_device_settings(session)
    return DeviceSettingsRead.model_validate(settings)


@router.put("/settings/default", response_model=DeviceSettingsRead)
async def put_default_device_settings(
    payload: DeviceSettingsUpdate,
    session: Session = Depends(get_session),
) -> DeviceSettingsRead:
    settings = update_device_settings(session, payload.model_dump(exclude_unset=True))
    return DeviceSettingsRead.model_validate(settings)


@router.get("/{device_id}/settings", response_model=DeviceSettingsRead)
async def read_device_settings(device_id: str, session: Session = Depends(get_session)) -> DeviceSettingsRead:
    settings, is_override = get_effective_device_settings(session, device_id)
    return DeviceSettingsRead.model_validate(settings).model_copy(update={"is_override": is_override})


@router.put("/{device_id}/settings", response_model=DeviceSettingsRead)
async def put_device_settings(
    device_id: str,
    payload: DeviceSettingsUpdate,
    session: Session = Depends(get_session),
) -> DeviceSettingsRead:
    settings = update_device_settings(session, payload.model_dump(exclude_unset=True), device_id=device_id)
    return DeviceSettingsRead.model_validate(settings).model_copy(update={"is_override": True})
