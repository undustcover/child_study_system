import datetime as dt

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class LanguageSettings(SQLModel, table=True):
    settings_key: str = Field(default="default", primary_key=True)
    today_plan_templates: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    reminder_templates: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    virtual_reply_templates: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    command_phrases: dict[str, list[str]] = Field(default_factory=dict, sa_column=Column(JSON))
    command_labels: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: dt.datetime = Field(default_factory=utc_now)
