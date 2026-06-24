from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.calendar import HolidayCreate, HolidayRangeCreate, HolidayRead
from app.services.holiday_calendar import (
    list_holidays,
    sync_public_holidays,
    upsert_holiday,
    upsert_holiday_range,
)

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.put("", response_model=HolidayRead)
async def put_holiday(
    payload: HolidayCreate,
    session: Session = Depends(get_session),
) -> HolidayRead:
    return HolidayRead.model_validate(upsert_holiday(session, payload))


@router.post("/ranges", response_model=list[HolidayRead])
async def put_holiday_range(
    payload: HolidayRangeCreate,
    session: Session = Depends(get_session),
) -> list[HolidayRead]:
    return [HolidayRead.model_validate(item) for item in upsert_holiday_range(session, payload)]


@router.get("", response_model=list[HolidayRead])
async def read_holidays(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[HolidayRead]:
    return [
        HolidayRead.model_validate(holiday)
        for holiday in list_holidays(session, start_date=start_date, end_date=end_date)
    ]


@router.post("/sync/{year}", response_model=list[HolidayRead])
async def sync_holidays(
    year: int,
    session: Session = Depends(get_session),
) -> list[HolidayRead]:
    return [HolidayRead.model_validate(holiday) for holiday in sync_public_holidays(session, year)]
