from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.language_settings import (
    LanguageSettingsRead,
    LanguageSettingsUpdate,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
)
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
    return LanguageSettingsRead.model_validate(settings)


@router.post("/reset", response_model=LanguageSettingsRead)
async def reset_language_settings_api(session: Session = Depends(get_session)) -> LanguageSettingsRead:
    settings = reset_language_settings(session)
    return LanguageSettingsRead.model_validate(settings)


@router.post("/preview", response_model=TemplatePreviewResponse)
async def preview_template(payload: TemplatePreviewRequest) -> TemplatePreviewResponse:
    return TemplatePreviewResponse(
        text=render_template(payload.template, payload.values),
        fields=template_fields(payload.template),
    )
