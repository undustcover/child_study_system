from app.models.calendar import DailyTask
from app.models.enums import ReminderEventType, TaskKind
from app.models.language_settings import LanguageSettings
from app.models.reminder import ReminderSettings
from app.services.language_settings import render_template


def render_reminder_text(
    event_type: ReminderEventType,
    task: DailyTask,
    settings: ReminderSettings | None = None,
    language_settings: LanguageSettings | None = None,
) -> str:
    subject_prefix = f"{task.subject}" if task.subject else ""
    task_name = f"{subject_prefix}{task.title}"
    legacy_templates = settings.templates if settings else {}
    templates = {**(language_settings.reminder_templates if language_settings else {}), **legacy_templates}
    values = {
        "task_name": task_name,
        "title": task.title,
        "subject": task.subject or "",
        "planned_minutes": task.planned_minutes,
        "pre_start_minutes": settings.pre_start_minutes if settings else 5,
    }

    if event_type == ReminderEventType.PRE_START:
        return render_template(templates.get("pre_start", ""), values) or (
            f"还有{values['pre_start_minutes']}分钟开始{task_name}。"
        )
    if event_type == ReminderEventType.START_DUE:
        if task.task_kind == TaskKind.BREAK:
            return render_template(templates.get("start_due_break", ""), values) or (
                f"现在开始休息，计划{task.planned_minutes}分钟。"
            )
        return render_template(templates.get("start_due", ""), values) or (
            f"现在开始{task_name}，计划{task.planned_minutes}分钟。"
        )
    if event_type == ReminderEventType.DELAYED_START:
        return render_template(templates.get("delayed_start", ""), values) or (
            f"{task_name}已经延迟开始，请确认是否开始学习。"
        )
    if event_type == ReminderEventType.FINISH_CONFIRM:
        return render_template(templates.get("finish_confirm", ""), values) or (
            f"{task_name}计划时间已到，请确认是否完成。"
        )
    if event_type == ReminderEventType.BREAK_END:
        return render_template(templates.get("break_end", ""), values) or (
            "休息时间到了，请准备进入下一项任务。"
        )
    return task_name
