from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.dashboard import DashboardToday
from app.services.dashboard import get_today_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/today", response_model=DashboardToday)
async def read_today_dashboard(
    target_date: date | None = Query(default=None, alias="date"),
    session: Session = Depends(get_session),
) -> DashboardToday:
    return get_today_dashboard(session, target_date)
