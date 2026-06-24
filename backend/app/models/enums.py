from enum import StrEnum


class TaskKind(StrEnum):
    STUDY = "study"
    PRACTICE = "practice"
    REVIEW = "review"
    HOMEWORK = "homework"
    RECITATION = "recitation"
    READING = "reading"
    BREAK = "break"


class DailyTaskStatus(StrEnum):
    PENDING = "pending"
    REMINDING = "reminding"
    STUDYING = "studying"
    PAUSED = "paused"
    WAITING_FINISH_CONFIRM = "waiting_finish_confirm"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    OVERDUE = "overdue"


class ExceptionType(StrEnum):
    SKIP = "skip"
    OVERRIDE = "override"


class HolidayDayType(StrEnum):
    PUBLIC_HOLIDAY = "public_holiday"
    MAKEUP_WORKDAY = "makeup_workday"
    WINTER_VACATION = "winter_vacation"
    SUMMER_VACATION = "summer_vacation"
    CUSTOM_LABEL = "custom_label"
