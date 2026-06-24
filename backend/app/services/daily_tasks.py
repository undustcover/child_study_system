from datetime import date, datetime, time
from typing import Any

from sqlmodel import Session, select

from app.models.calendar import DailyTask, ScheduleException, SchedulePlan, ScheduleTaskItem
from app.models.enums import ExceptionType, HolidayDayType, TaskKind
from app.services.holiday_calendar import get_holiday_by_date


def _weekday_matches(plan: SchedulePlan, target_date: date) -> bool:
    weekdays = plan.repeat_rule.get("weekdays")
    if weekdays is None:
        return True
    return target_date.isoweekday() in weekdays


def _plan_matches_date(session: Session, plan: SchedulePlan, target_date: date) -> bool:
    if not plan.is_active:
        return False
    if target_date < plan.start_date or target_date > plan.end_date:
        return False
    if not _weekday_matches(plan, target_date):
        return False

    holiday = get_holiday_by_date(session, target_date)
    if not holiday:
        return True
    if holiday.day_type == HolidayDayType.PUBLIC_HOLIDAY and plan.skip_public_holidays:
        return False
    if holiday.day_type == HolidayDayType.WINTER_VACATION and not plan.run_in_winter_vacation:
        return False
    if holiday.day_type == HolidayDayType.SUMMER_VACATION and not plan.run_in_summer_vacation:
        return False
    return True


def _get_exception(session: Session, plan_id: int, target_date: date) -> ScheduleException | None:
    statement = select(ScheduleException).where(
        ScheduleException.schedule_plan_id == plan_id,
        ScheduleException.date == target_date,
    )
    return session.exec(statement).first()


def _existing_task(
    session: Session,
    target_date: date,
    plan_id: int | None,
    item_id: int | None,
    sort_order: int,
) -> DailyTask | None:
    statement = select(DailyTask).where(
        DailyTask.date == target_date,
        DailyTask.source_schedule_plan_id == plan_id,
        DailyTask.source_schedule_task_item_id == item_id,
        DailyTask.sort_order == sort_order,
    )
    return session.exec(statement).first()


def _create_daily_task_from_item(
    session: Session,
    plan: SchedulePlan,
    item: ScheduleTaskItem,
    target_date: date,
) -> DailyTask | None:
    if _existing_task(session, target_date, plan.id, item.id, item.sort_order):
        return None

    start_at = datetime.combine(target_date, item.planned_start_time)
    end_at = datetime.combine(target_date, item.planned_end_time)
    task = DailyTask(
        student_id=plan.student_id,
        source_schedule_plan_id=plan.id,
        source_schedule_task_item_id=item.id,
        date=target_date,
        sort_order=item.sort_order,
        task_kind=item.task_kind,
        subject=item.subject,
        title=item.title,
        content=item.content,
        original_start_at=start_at,
        original_end_at=end_at,
        current_start_at=start_at,
        current_end_at=end_at,
        planned_minutes=item.planned_minutes,
    )
    session.add(task)
    return task


def _create_daily_task_from_override(
    session: Session,
    plan: SchedulePlan,
    item_data: dict[str, Any],
    target_date: date,
    sort_order: int,
) -> DailyTask | None:
    if _existing_task(session, target_date, plan.id, None, sort_order):
        return None

    planned_start_time = _coerce_time(item_data["planned_start_time"])
    planned_end_time = _coerce_time(item_data["planned_end_time"])
    start_at = datetime.combine(target_date, planned_start_time)
    end_at = datetime.combine(target_date, planned_end_time)
    task = DailyTask(
        student_id=plan.student_id,
        source_schedule_plan_id=plan.id,
        source_schedule_task_item_id=None,
        date=target_date,
        sort_order=sort_order,
        task_kind=TaskKind(item_data["task_kind"]),
        subject=item_data.get("subject"),
        title=item_data["title"],
        content=item_data.get("content"),
        original_start_at=start_at,
        original_end_at=end_at,
        current_start_at=start_at,
        current_end_at=end_at,
        planned_minutes=item_data["planned_minutes"],
    )
    session.add(task)
    return task


def _coerce_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    return time.fromisoformat(value)


def generate_daily_tasks(session: Session, target_date: date) -> tuple[list[DailyTask], list[int]]:
    statement = select(SchedulePlan).where(
        SchedulePlan.start_date <= target_date,
        SchedulePlan.end_date >= target_date,
        SchedulePlan.is_active == True,  # noqa: E712
    )
    plans = list(session.exec(statement))
    created: list[DailyTask] = []
    skipped_plan_ids: list[int] = []

    for plan in plans:
        if not _plan_matches_date(session, plan, target_date):
            continue

        exception = _get_exception(session, plan.id, target_date)
        if exception and exception.exception_type == ExceptionType.SKIP:
            skipped_plan_ids.append(plan.id)
            continue

        if exception and exception.exception_type == ExceptionType.OVERRIDE:
            items = (exception.override_payload or {}).get("items", [])
            for index, item_data in enumerate(items):
                task = _create_daily_task_from_override(
                    session=session,
                    plan=plan,
                    item_data=item_data,
                    target_date=target_date,
                    sort_order=item_data.get("sort_order", index),
                )
                if task:
                    created.append(task)
            continue

        items_statement = (
            select(ScheduleTaskItem)
            .where(ScheduleTaskItem.schedule_plan_id == plan.id)
            .order_by(ScheduleTaskItem.sort_order, ScheduleTaskItem.planned_start_time, ScheduleTaskItem.id)
        )
        for item in session.exec(items_statement):
            task = _create_daily_task_from_item(session, plan, item, target_date)
            if task:
                created.append(task)

    session.commit()
    for task in created:
        session.refresh(task)
    return created, skipped_plan_ids


def list_daily_tasks(session: Session, target_date: date) -> list[DailyTask]:
    statement = (
        select(DailyTask)
        .where(DailyTask.date == target_date)
        .order_by(DailyTask.current_start_at, DailyTask.sort_order, DailyTask.id)
    )
    return list(session.exec(statement))
