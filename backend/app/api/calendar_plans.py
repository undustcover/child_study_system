from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.calendar import (
    ScheduleExceptionCreate,
    ScheduleExceptionRead,
    SchedulePlanCreate,
    SchedulePlanRead,
    SchedulePlanUpdate,
    ScheduleTaskItemCreate,
    ScheduleTaskItemRead,
    ScheduleTaskItemUpdate,
)
from app.services.calendar_plans import (
    add_schedule_task_item,
    create_schedule_plan,
    deactivate_schedule_plan,
    delete_schedule_task_item,
    get_schedule_plan,
    list_schedule_exceptions,
    list_schedule_plans,
    list_schedule_task_items,
    update_schedule_plan,
    update_schedule_task_item,
    upsert_schedule_exception,
)
from app.services.students import get_or_create_default_student

router = APIRouter(prefix="/calendar-plans", tags=["calendar plans"])


def _to_plan_read(session: Session, plan_id: int) -> SchedulePlanRead:
    plan = get_schedule_plan(session, plan_id)
    items = list_schedule_task_items(session, plan_id)
    return SchedulePlanRead.model_validate(
        {
            **plan.model_dump(),
            "items": [ScheduleTaskItemRead.model_validate(item) for item in items],
        }
    )


@router.post("", response_model=SchedulePlanRead, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: SchedulePlanCreate,
    session: Session = Depends(get_session),
) -> SchedulePlanRead:
    student = get_or_create_default_student(session)
    plan = create_schedule_plan(session, student.id, payload)
    return _to_plan_read(session, plan.id)


@router.get("", response_model=list[SchedulePlanRead])
async def list_plans(session: Session = Depends(get_session)) -> list[SchedulePlanRead]:
    return [_to_plan_read(session, plan.id) for plan in list_schedule_plans(session)]


@router.get("/{plan_id}", response_model=SchedulePlanRead)
async def read_plan(plan_id: int, session: Session = Depends(get_session)) -> SchedulePlanRead:
    return _to_plan_read(session, plan_id)


@router.patch("/{plan_id}", response_model=SchedulePlanRead)
async def patch_plan(
    plan_id: int,
    payload: SchedulePlanUpdate,
    session: Session = Depends(get_session),
) -> SchedulePlanRead:
    plan = update_schedule_plan(session, plan_id, payload)
    return _to_plan_read(session, plan.id)


@router.post("/{plan_id}/deactivate", response_model=SchedulePlanRead)
async def deactivate_plan(plan_id: int, session: Session = Depends(get_session)) -> SchedulePlanRead:
    plan = deactivate_schedule_plan(session, plan_id)
    return _to_plan_read(session, plan.id)


@router.post("/{plan_id}/items", response_model=ScheduleTaskItemRead, status_code=status.HTTP_201_CREATED)
async def create_plan_item(
    plan_id: int,
    payload: ScheduleTaskItemCreate,
    session: Session = Depends(get_session),
) -> ScheduleTaskItemRead:
    item = add_schedule_task_item(session, plan_id, payload)
    return ScheduleTaskItemRead.model_validate(item)


@router.get("/{plan_id}/items", response_model=list[ScheduleTaskItemRead])
async def read_plan_items(
    plan_id: int,
    session: Session = Depends(get_session),
) -> list[ScheduleTaskItemRead]:
    return [ScheduleTaskItemRead.model_validate(item) for item in list_schedule_task_items(session, plan_id)]


@router.patch("/{plan_id}/items/{item_id}", response_model=ScheduleTaskItemRead)
async def patch_plan_item(
    plan_id: int,
    item_id: int,
    payload: ScheduleTaskItemUpdate,
    session: Session = Depends(get_session),
) -> ScheduleTaskItemRead:
    item = update_schedule_task_item(session, plan_id, item_id, payload)
    return ScheduleTaskItemRead.model_validate(item)


@router.delete("/{plan_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_plan_item(
    plan_id: int,
    item_id: int,
    session: Session = Depends(get_session),
) -> Response:
    delete_schedule_task_item(session, plan_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{plan_id}/exceptions", response_model=ScheduleExceptionRead)
async def put_plan_exception(
    plan_id: int,
    payload: ScheduleExceptionCreate,
    session: Session = Depends(get_session),
) -> ScheduleExceptionRead:
    exception = upsert_schedule_exception(session, plan_id, payload)
    return ScheduleExceptionRead.model_validate(exception)


@router.get("/{plan_id}/exceptions", response_model=list[ScheduleExceptionRead])
async def read_plan_exceptions(
    plan_id: int,
    session: Session = Depends(get_session),
) -> list[ScheduleExceptionRead]:
    return [
        ScheduleExceptionRead.model_validate(exception)
        for exception in list_schedule_exceptions(session, plan_id)
    ]
