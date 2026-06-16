from __future__ import annotations

from datetime import datetime, timedelta
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from .calendar_service import (
    get_calendar_service,
    list_upcoming_events,
    list_events_for_day,
    create_calendar_event,
    create_reminder,
)
from .planning_service import generate_daily_plan, generate_weekly_summary


router = APIRouter(prefix="/calendar", tags=["calendar"])


class EventCreateRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    description: str | None = None
    location: str | None = None
    reminder_minutes: int = 10


class ReminderCreateRequest(BaseModel):
    title: str
    reminder_time: str
    reminder_minutes_before: int = 0


@router.get("/connect")
def connect_calendar():
    try:
        get_calendar_service()
        return {"connected": True, "message": "Google Calendar connected successfully."}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/upcoming")
def get_upcoming_events(days: int = 7, max_results: int = 20):
    return {
        "events": list_upcoming_events(days=days, max_results=max_results)
    }


@router.get("/day")
def get_day_events(date: str):
    return {
        "date": date,
        "events": list_events_for_day(date),
    }


@router.post("/event")
def add_event(payload: EventCreateRequest):
    return create_calendar_event(
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        description=payload.description,
        location=payload.location,
        reminder_minutes=payload.reminder_minutes,
    )


@router.post("/reminder")
def add_reminder(payload: ReminderCreateRequest):
    return create_reminder(
        title=payload.title,
        reminder_time=payload.reminder_time,
        reminder_minutes_before=payload.reminder_minutes_before,
    )


@router.get("/plan/tomorrow")
def plan_tomorrow():
    tomorrow = datetime.now().date() + timedelta(days=1)
    return generate_daily_plan(tomorrow.isoformat())


@router.get("/plan/day")
def plan_day(date: str):
    return generate_daily_plan(date)


@router.get("/plan/week")
def plan_week(start_date: str):
    return generate_weekly_summary(start_date)