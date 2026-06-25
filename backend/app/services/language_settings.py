import datetime as dt
from string import Formatter
from typing import Any

from sqlmodel import Session

from app.models.language_settings import LanguageSettings

DEFAULT_LANGUAGE_SETTINGS_KEY = "default"

DEFAULT_TODAY_PLAN_TEMPLATES = {
    "empty": "{date_label}还没有安排任务。",
    "completed": "{date_label}的计划已经完成了，目前没有剩余任务。",
    "completed_after_finish": "今天的安排都完成了，辛苦啦。可以休息了。",
    "single": "{date_label}还有1项安排：{task_summaries}。",
    "multiple": "{date_label}还有{remaining_count}项安排：{task_summaries}{extra_suffix}。",
    "extra_suffix": "；另外还有{extra_count}项安排",
}

DEFAULT_REMINDER_TEMPLATES = {
    "pre_start": "还有{pre_start_minutes}分钟开始{task_name}。",
    "start_due": "现在开始{task_name}，计划{planned_minutes}分钟。",
    "start_due_break": "现在开始休息，计划{planned_minutes}分钟。",
    "delayed_start": "{task_name}已经延迟开始，请确认是否开始学习。",
    "finish_confirm": "{task_name}计划时间已到，请确认是否完成。",
    "break_end": "休息时间到了，请准备进入下一项任务。",
}

DEFAULT_VIRTUAL_REPLY_TEMPLATES = {
    "prompt": "请输入学生说的话，或输入 /quit 退出：",
    "command_sent": "已识别：{command}，已发送到后端。",
    "clarify": "我听到几个可能的意思：{options}。请用肯定句直接说你要哪一个。",
    "clarify_retry": "我还没对齐你的意思。请用肯定句直接说其中一个：{options}。",
    "clarify_abandoned": "我先不执行这句话，继续等下一句。",
    "unrecognized": "刚才你说什么，我没有听清楚。",
    "negated": "我听到你是在否定或取消，所以这次不执行。你想执行哪个动作？",
    "speak_prefix": "播报",
    "display_state_prefix": "后端状态",
    "sync_state_prefix": "同步状态",
    "playback_finished": "播报完成回执已发送：{message_id}",
    "startup_query_sent": "启动后已自动查询今日计划。",
    "disconnect_requested": "收到断开连接指令，正在模拟设备离线。",
    "connection_opened": "虚拟设备已连接：{url}",
    "connection_closed": "连接已关闭。",
    "llm_placeholder": "LLM意图识别接口已预留，阶段6默认不启用。",
}

DEFAULT_COMMAND_LABELS = {
    "START_STUDY": "开始学习",
    "PAUSE_STUDY": "暂停学习",
    "RESUME_STUDY": "继续学习",
    "COMPLETE_STUDY": "完成学习",
    "SKIP_TASK": "跳过任务",
    "QUERY_CURRENT_TASK": "查询当前任务",
    "QUERY_TODAY_PLAN": "查询今天计划",
    "EXTEND_CURRENT_TASK": "延长学习时间",
    "EXTEND_BREAK": "延长休息时间",
}

DEFAULT_COMMAND_PHRASES = {
    "START_STUDY": ["开始学习", "开始", "开始做题", "开始写作业", "我开始了", "现在开始"],
    "PAUSE_STUDY": ["暂停", "暂停学习", "先停一下", "休息一下", "等一下"],
    "RESUME_STUDY": ["继续", "继续学习", "恢复学习", "接着学", "我回来了"],
    "COMPLETE_STUDY": ["完成了", "做完了", "写完了", "学完了", "结束学习", "这项完成"],
    "SKIP_TASK": ["跳过", "跳过这个", "今天不做这个", "先不做这个"],
    "QUERY_CURRENT_TASK": ["现在做什么", "当前任务", "我在做什么", "这是什么任务"],
    "QUERY_TODAY_PLAN": [
        "今天计划",
        "播报本日计划",
        "本日计划",
        "今日安排",
        "今天安排",
        "今天还有什么",
        "今天要做什么",
        "下一个任务",
        "还有什么任务",
    ],
    "EXTEND_CURRENT_TASK": ["再学十分钟", "延长学习", "加十分钟", "多学一会儿", "再给我十分钟"],
    "EXTEND_BREAK": ["再休息十分钟", "延长休息", "休息加十分钟", "多休息一会儿"],
}


class SafeTemplateValues(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def get_or_create_language_settings(session: Session) -> LanguageSettings:
    settings = session.get(LanguageSettings, DEFAULT_LANGUAGE_SETTINGS_KEY)
    if settings is not None:
        _hydrate_defaults(settings)
        return settings

    settings = LanguageSettings(settings_key=DEFAULT_LANGUAGE_SETTINGS_KEY)
    _hydrate_defaults(settings)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def update_language_settings(session: Session, updates: dict[str, object]) -> LanguageSettings:
    settings = get_or_create_language_settings(session)
    for field in (
        "today_plan_templates",
        "reminder_templates",
        "virtual_reply_templates",
        "command_phrases",
        "command_labels",
    ):
        value = updates.get(field)
        if isinstance(value, dict):
            setattr(settings, field, _merged_field(field, value))
    settings.updated_at = utc_now()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def reset_language_settings(session: Session) -> LanguageSettings:
    settings = get_or_create_language_settings(session)
    settings.today_plan_templates = DEFAULT_TODAY_PLAN_TEMPLATES.copy()
    settings.reminder_templates = DEFAULT_REMINDER_TEMPLATES.copy()
    settings.virtual_reply_templates = DEFAULT_VIRTUAL_REPLY_TEMPLATES.copy()
    settings.command_phrases = {key: phrases.copy() for key, phrases in DEFAULT_COMMAND_PHRASES.items()}
    settings.command_labels = DEFAULT_COMMAND_LABELS.copy()
    settings.updated_at = utc_now()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def render_template(template: str, values: dict[str, Any]) -> str:
    return template.format_map(SafeTemplateValues(values))


def template_fields(template: str) -> list[str]:
    return sorted({field for _, field, _, _ in Formatter().parse(template) if field})


def _hydrate_defaults(settings: LanguageSettings) -> None:
    settings.today_plan_templates = {**DEFAULT_TODAY_PLAN_TEMPLATES, **(settings.today_plan_templates or {})}
    settings.reminder_templates = {**DEFAULT_REMINDER_TEMPLATES, **(settings.reminder_templates or {})}
    settings.virtual_reply_templates = {**DEFAULT_VIRTUAL_REPLY_TEMPLATES, **(settings.virtual_reply_templates or {})}
    settings.command_phrases = {
        **{key: phrases.copy() for key, phrases in DEFAULT_COMMAND_PHRASES.items()},
        **(settings.command_phrases or {}),
    }
    settings.command_labels = {**DEFAULT_COMMAND_LABELS, **(settings.command_labels or {})}


def _merged_field(field: str, value: dict) -> dict:
    if field == "today_plan_templates":
        return {**DEFAULT_TODAY_PLAN_TEMPLATES, **_without_blank_strings(value)}
    if field == "reminder_templates":
        return {**DEFAULT_REMINDER_TEMPLATES, **_without_blank_strings(value)}
    if field == "virtual_reply_templates":
        return {**DEFAULT_VIRTUAL_REPLY_TEMPLATES, **_without_blank_strings(value)}
    if field == "command_labels":
        return {**DEFAULT_COMMAND_LABELS, **_without_blank_strings(value)}
    if field == "command_phrases":
        defaults = {key: phrases.copy() for key, phrases in DEFAULT_COMMAND_PHRASES.items()}
        return {**defaults, **{key: list(phrases) for key, phrases in value.items() if isinstance(phrases, list)}}
    return value


def _without_blank_strings(value: dict) -> dict:
    return {key: item for key, item in value.items() if isinstance(item, str) and item.strip()}
