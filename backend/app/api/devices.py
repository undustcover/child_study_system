from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.device.connection_manager import device_connection_manager
from app.device.protocol import build_sync_state_message
from app.schemas.devices import DeviceConfigSyncResponse, DeviceSettingsRead, DeviceSettingsUpdate
from app.services.devices import (
    build_device_config_payload,
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
    await _push_config_to_connected_devices(session)
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
    await _push_config_to_device(session, device_id)
    return DeviceSettingsRead.model_validate(settings).model_copy(update={"is_override": True})


@router.post("/{device_id}/sync-config", response_model=DeviceConfigSyncResponse)
async def sync_device_config(
    device_id: str,
    session: Session = Depends(get_session),
) -> DeviceConfigSyncResponse:
    payload = build_device_config_payload(session, device_id)
    sent = await device_connection_manager.send_json(device_id, build_sync_state_message(device_id, "device_config", payload))
    return DeviceConfigSyncResponse(device_id=device_id, sent=sent, payload=payload)


async def _push_config_to_connected_devices(session: Session) -> None:
    for device_id in device_connection_manager.connected_device_ids():
        await _push_config_to_device(session, device_id)


async def _push_config_to_device(session: Session, device_id: str) -> bool:
    payload = build_device_config_payload(session, device_id)
    return await device_connection_manager.send_json(device_id, build_sync_state_message(device_id, "device_config", payload))
