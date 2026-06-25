from datetime import date

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.calendar import ScheduleException, SchedulePlan, ScheduleTaskItem
from app.schemas.calendar import (
    ScheduleExceptionCreate,
    SchedulePlanCreate,
    SchedulePlanUpdate,
    ScheduleTaskItemCreate,
    ScheduleTaskItemUpdate,
)


def _validate_date_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be greater than or equal to start_date",
        )


def _validate_unique_start_times(items: list[ScheduleTaskItemCreate]) -> None:
    seen: set = set()
    for item in items:
        if item.planned_start_time in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="schedule task items cannot share the same planned_start_time",
            )
        seen.add(item.planned_start_time)


def create_schedule_plan(
    session: Session,
    student_id: int,
    payload: SchedulePlanCreate,
) -> SchedulePlan:
    _validate_date_range(payload.start_date, payload.end_date)
    _validate_unique_start_times(payload.items)
    plan = SchedulePlan(
        student_id=student_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        repeat_rule=payload.repeat_rule,
        skip_public_holidays=payload.skip_public_holidays,
        run_in_winter_vacation=payload.run_in_winter_vacation,
        run_in_summer_vacation=payload.run_in_summer_vacation,
        is_active=payload.is_active,
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)

    for item_payload in payload.items:
        add_schedule_task_item(session, plan.id, item_payload)

    session.refresh(plan)
    return plan


def list_schedule_plans(session: Session) -> list[SchedulePlan]:
    return list(session.exec(select(SchedulePlan).order_by(SchedulePlan.start_date, SchedulePlan.id)))


def get_schedule_plan(session: Session, plan_id: int) -> SchedulePlan:
    plan = session.get(SchedulePlan, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule plan not found")
    return plan


def update_schedule_plan(
    session: Session,
    plan_id: int,
    payload: SchedulePlanUpdate,
) -> SchedulePlan:
    plan = get_schedule_plan(session, plan_id)
    update_data = payload.model_dump(exclude_unset=True)
    start_date = update_data.get("start_date", plan.start_date)
    end_date = update_data.get("end_date", plan.end_date)
    _validate_date_range(start_date, end_date)

    for key, value in update_data.items():
        setattr(plan, key, value)
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def deactivate_schedule_plan(session: Session, plan_id: int) -> SchedulePlan:
    plan = get_schedule_plan(session, plan_id)
    plan.is_active = False
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def list_schedule_task_items(session: Session, plan_id: int) -> list[ScheduleTaskItem]:
    get_schedule_plan(session, plan_id)
    statement = (
        select(ScheduleTaskItem)
        .where(ScheduleTaskItem.schedule_plan_id == plan_id)
        .order_by(ScheduleTaskItem.sort_order, ScheduleTaskItem.planned_start_time, ScheduleTaskItem.id)
    )
    return list(session.exec(statement))


def add_schedule_task_item(
    session: Session,
    plan_id: int,
    payload: ScheduleTaskItemCreate,
) -> ScheduleTaskItem:
    get_schedule_plan(session, plan_id)
    if payload.planned_end_time <= payload.planned_start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="planned_end_time must be later than planned_start_time",
        )
    duplicate_statement = select(ScheduleTaskItem).where(
        ScheduleTaskItem.schedule_plan_id == plan_id,
        ScheduleTaskItem.planned_start_time == payload.planned_start_time,
    )
    if session.exec(duplicate_statement).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="schedule task items cannot share the same planned_start_time",
        )

    item = ScheduleTaskItem(schedule_plan_id=plan_id, **payload.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def update_schedule_task_item(
    session: Session,
    plan_id: int,
    item_id: int,
    payload: ScheduleTaskItemUpdate,
) -> ScheduleTaskItem:
    get_schedule_plan(session, plan_id)
    item = session.get(ScheduleTaskItem, item_id)
    if not item or item.schedule_plan_id != plan_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule task item not found")

    update_data = payload.model_dump(exclude_unset=True)
    start_time = update_data.get("planned_start_time", item.planned_start_time)
    end_time = update_data.get("planned_end_time", item.planned_end_time)
    if end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="planned_end_time must be later than planned_start_time",
        )
    duplicate_statement = select(ScheduleTaskItem).where(
        ScheduleTaskItem.schedule_plan_id == plan_id,
        ScheduleTaskItem.planned_start_time == start_time,
        ScheduleTaskItem.id != item_id,
    )
    if session.exec(duplicate_statement).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="schedule task items cannot share the same planned_start_time",
        )

    for key, value in update_data.items():
        setattr(item, key, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def delete_schedule_task_item(session: Session, plan_id: int, item_id: int) -> None:
    get_schedule_plan(session, plan_id)
    item = session.get(ScheduleTaskItem, item_id)
    if not item or item.schedule_plan_id != plan_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule task item not found")
    session.delete(item)
    session.commit()


def upsert_schedule_exception(
    session: Session,
    plan_id: int,
    payload: ScheduleExceptionCreate,
) -> ScheduleException:
    get_schedule_plan(session, plan_id)
    statement = select(ScheduleException).where(
        ScheduleException.schedule_plan_id == plan_id,
        ScheduleException.date == payload.date,
    )
    exception = session.exec(statement).first()
    if exception:
        exception.exception_type = payload.exception_type
        exception.override_payload = payload.override_payload
        exception.reason = payload.reason
    else:
        exception = ScheduleException(schedule_plan_id=plan_id, **payload.model_dump())
    session.add(exception)
    session.commit()
    session.refresh(exception)
    return exception


def list_schedule_exceptions(session: Session, plan_id: int) -> list[ScheduleException]:
    get_schedule_plan(session, plan_id)
    statement = (
        select(ScheduleException)
        .where(ScheduleException.schedule_plan_id == plan_id)
        .order_by(ScheduleException.date, ScheduleException.id)
    )
    return list(session.exec(statement))
