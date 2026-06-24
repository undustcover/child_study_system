from app.models.calendar import DailyTask
from app.models.enums import ReminderEventType, TaskKind
from app.models.reminder import ReminderSettings


def render_reminder_text(event_type: ReminderEventType, task: DailyTask, settings: ReminderSettings | None = None) -> str:
    subject_prefix = f"{task.subject}" if task.subject else ""
    task_name = f"{subject_prefix}{task.title}"
    custom_template = (settings.templates if settings else {}).get(event_type.value)
    if custom_template:
        return custom_template.format(
            task_name=task_name,
            title=task.title,
            subject=task.subject or "",
            planned_minutes=task.planned_minutes,
        )

    if event_type == ReminderEventType.PRE_START:
        minutes = settings.pre_start_minutes if settings else 5
        return f"还有{minutes}分钟开始{task_name}。"
    if event_type == ReminderEventType.START_DUE:
        if task.task_kind == TaskKind.BREAK:
            return f"现在开始休息，计划{task.planned_minutes}分钟。"
        return f"现在开始{task_name}，计划{task.planned_minutes}分钟。"
    if event_type == ReminderEventType.DELAYED_START:
        return f"{task_name}已经延迟开始，请确认是否开始学习。"
    if event_type == ReminderEventType.FINISH_CONFIRM:
        return f"{task_name}计划时间已到，请确认是否完成。"
    if event_type == ReminderEventType.BREAK_END:
        return "休息时间到了，请准备进入下一项任务。"
    return task_name
