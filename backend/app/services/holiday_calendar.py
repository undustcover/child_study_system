from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.calendar import HolidayCalendar
from app.schemas.calendar import HolidayCreate, HolidayRangeCreate


def upsert_holiday(session: Session, payload: HolidayCreate) -> HolidayCalendar:
    statement = select(HolidayCalendar).where(HolidayCalendar.date == payload.date)
    holiday = session.exec(statement).first()
    if holiday:
        holiday.label = payload.label
        holiday.day_type = payload.day_type
        holiday.source = payload.source
        holiday.is_rest_day = payload.is_rest_day
    else:
        holiday = HolidayCalendar(**payload.model_dump())

    session.add(holiday)
    session.commit()
    session.refresh(holiday)
    return holiday


def upsert_holiday_range(session: Session, payload: HolidayRangeCreate) -> list[HolidayCalendar]:
    if payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be greater than or equal to start_date",
        )

    current = payload.start_date
    holidays: list[HolidayCalendar] = []
    while current <= payload.end_date:
        holidays.append(
            upsert_holiday(
                session,
                HolidayCreate(
                    date=current,
                    label=payload.label,
                    day_type=payload.day_type,
                    source=payload.source,
                    is_rest_day=payload.is_rest_day,
                ),
            )
        )
        current += timedelta(days=1)
    return holidays


def list_holidays(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[HolidayCalendar]:
    statement = select(HolidayCalendar)
    if start_date:
        statement = statement.where(HolidayCalendar.date >= start_date)
    if end_date:
        statement = statement.where(HolidayCalendar.date <= end_date)
    statement = statement.order_by(HolidayCalendar.date)
    return list(session.exec(statement))


def get_holiday_by_date(session: Session, target_date: date) -> HolidayCalendar | None:
    statement = select(HolidayCalendar).where(HolidayCalendar.date == target_date)
    return session.exec(statement).first()


def sync_public_holidays(session: Session, year: int) -> list[HolidayCalendar]:
    """Placeholder for the later selected network source.

    The data source is intentionally not hard-coded yet because it is still a
    product decision. Local holiday storage and cache behavior are already in
    place, so callers can continue using saved data if sync is unavailable.
    """

    return list_holidays(session, date(year, 1, 1), date(year, 12, 31))
