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


class StudySessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class TimeSegmentKind(StrEnum):
    STUDY = "study"
    BREAK = "break"
    PAUSE = "pause"


class CommandType(StrEnum):
    START_STUDY = "START_STUDY"
    PAUSE_STUDY = "PAUSE_STUDY"
    RESUME_STUDY = "RESUME_STUDY"
    COMPLETE_STUDY = "COMPLETE_STUDY"
    SKIP_TASK = "SKIP_TASK"
    QUERY_CURRENT_TASK = "QUERY_CURRENT_TASK"
    QUERY_TODAY_PLAN = "QUERY_TODAY_PLAN"
    EXTEND_CURRENT_TASK = "EXTEND_CURRENT_TASK"
    EXTEND_BREAK = "EXTEND_BREAK"


class CommandSource(StrEnum):
    DEVICE_VOICE = "device_voice"
    VIRTUAL_DEVICE = "virtual_device"
    PARENT_WEB = "parent_web"
    SCHEDULER = "scheduler"


class ExceptionType(StrEnum):
    SKIP = "skip"
    OVERRIDE = "override"


class HolidayDayType(StrEnum):
    PUBLIC_HOLIDAY = "public_holiday"
    MAKEUP_WORKDAY = "makeup_workday"
    WINTER_VACATION = "winter_vacation"
    SUMMER_VACATION = "summer_vacation"
    CUSTOM_LABEL = "custom_label"
