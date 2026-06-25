from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.device.connection_manager import device_connection_manager
from app.device.protocol import build_sync_state_message
from app.schemas.language_settings import (
    LanguageSettingsRead,
    LanguageSettingsUpdate,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
)
from app.services.devices import build_device_config_payload
from app.services.language_settings import (
    get_or_create_language_settings,
    render_template,
    reset_language_settings,
    template_fields,
    update_language_settings,
)

router = APIRouter(prefix="/language-settings", tags=["language settings"])


@router.get("", response_model=LanguageSettingsRead)
async def read_language_settings(session: Session = Depends(get_session)) -> LanguageSettingsRead:
    settings = get_or_create_language_settings(session)
    return LanguageSettingsRead.model_validate(settings)


@router.put("", response_model=LanguageSettingsRead)
async def put_language_settings(
    payload: LanguageSettingsUpdate,
    session: Session = Depends(get_session),
) -> LanguageSettingsRead:
    settings = update_language_settings(session, payload.model_dump(exclude_unset=True))
    await _push_language_config_to_connected_devices(session)
    return LanguageSettingsRead.model_validate(settings)


@router.post("/reset", response_model=LanguageSettingsRead)
async def reset_language_settings_api(session: Session = Depends(get_session)) -> LanguageSettingsRead:
    settings = reset_language_settings(session)
    await _push_language_config_to_connected_devices(session)
    return LanguageSettingsRead.model_validate(settings)


@router.post("/preview", response_model=TemplatePreviewResponse)
async def preview_template(payload: TemplatePreviewRequest) -> TemplatePreviewResponse:
    return TemplatePreviewResponse(
        text=render_template(payload.template, payload.values),
        fields=template_fields(payload.template),
    )


async def _push_language_config_to_connected_devices(session: Session) -> None:
    for device_id in device_connection_manager.connected_device_ids():
        payload = build_device_config_payload(session, device_id)
        await device_connection_manager.send_json(device_id, build_sync_state_message(device_id, "device_config", payload))
