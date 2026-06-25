from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.calendar import DailyTaskCorrectionUpdate, DailyTaskRead, GenerateDailyTasksResult
from app.services.daily_tasks import correct_daily_task, generate_daily_tasks, list_daily_tasks

router = APIRouter(prefix="/daily-tasks", tags=["daily tasks"])


@router.post("/generate", response_model=GenerateDailyTasksResult)
async def generate_tasks(
    target_date: date = Query(alias="date"),
    session: Session = Depends(get_session),
) -> GenerateDailyTasksResult:
    created, skipped_plan_ids = generate_daily_tasks(session, target_date)
    tasks = list_daily_tasks(session, target_date)
    return GenerateDailyTasksResult(
        date=target_date,
        created_count=len(created),
        skipped_plan_ids=skipped_plan_ids,
        tasks=[DailyTaskRead.model_validate(task) for task in tasks],
    )


@router.get("", response_model=list[DailyTaskRead])
async def read_tasks(
    target_date: date = Query(alias="date"),
    session: Session = Depends(get_session),
) -> list[DailyTaskRead]:
    return [DailyTaskRead.model_validate(task) for task in list_daily_tasks(session, target_date)]


@router.patch("/{task_id}/correction", response_model=DailyTaskRead)
async def patch_task_correction(
    task_id: int,
    payload: DailyTaskCorrectionUpdate,
    session: Session = Depends(get_session),
) -> DailyTaskRead:
    return DailyTaskRead.model_validate(correct_daily_task(session, task_id, payload))
