from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LanguageSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    settings_key: str
    today_plan_templates: dict[str, str]
    reminder_templates: dict[str, str]
    virtual_reply_templates: dict[str, str]
    command_phrases: dict[str, list[str]]
    command_labels: dict[str, str]
    updated_at: datetime


class LanguageSettingsUpdate(BaseModel):
    today_plan_templates: dict[str, str] | None = None
    reminder_templates: dict[str, str] | None = None
    virtual_reply_templates: dict[str, str] | None = None
    command_phrases: dict[str, list[str]] | None = None
    command_labels: dict[str, str] | None = None


class TemplatePreviewRequest(BaseModel):
    template: str
    values: dict[str, str | int | float | None] = Field(default_factory=dict)


class TemplatePreviewResponse(BaseModel):
    text: str
    fields: list[str]
