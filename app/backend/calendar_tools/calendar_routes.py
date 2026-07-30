from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .calendar_service import (
    CalendarEventNotFound,
    CalendarServiceError,
    create_calendar_event,
    create_reminder,
    delete_calendar_event,
    get_calendar_service,
    list_events_for_day,
    list_upcoming_events,
    update_calendar_event,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


class EventCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    start_time: str | None = None
    end_time: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    all_day: bool = False
    description: str | None = None
    location: str | None = None
    reminder_minutes: int | None = 10
    calendar_id: str = "primary"

    @model_validator(mode="after")
    def validate_window(self):
        if self.all_day and not self.start_date:
            raise ValueError("start_date is required for an all-day event")
        if not self.all_day and (not self.start_time or not self.end_time):
            raise ValueError("start_time and end_time are required for a timed event")
        return self


class EventUpdateRequest(BaseModel):
    title: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    all_day: bool | None = None
    description: str | None = None
    location: str | None = None
    calendar_id: str = "primary"


class ReminderCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    reminder_time: str
    reminder_minutes_before: int = 0


def _raise_calendar_error(error: Exception) -> None:
    if isinstance(error, CalendarEventNotFound):
        raise HTTPException(status_code=404, detail="Calendar event not found") from error
    if isinstance(error, ValueError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    if isinstance(error, CalendarServiceError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/connect")
def connect_calendar() -> dict[str, Any]:
    try:
        get_calendar_service()
        return {"connected": True, "message": "Google Calendar connected successfully."}
    except Exception as error:
        _raise_calendar_error(error)


@router.get("/upcoming")
def get_upcoming_events(days: int = 7, max_results: int = 20) -> dict[str, Any]:
    try:
        return {"events": list_upcoming_events(days=days, max_results=max_results)}
    except Exception as error:
        _raise_calendar_error(error)


@router.get("/day")
def get_day_events(date: str) -> dict[str, Any]:
    try:
        return {"date": date, "events": list_events_for_day(date)}
    except Exception as error:
        _raise_calendar_error(error)


@router.post("/event")
def add_event(payload: EventCreateRequest) -> dict[str, Any]:
    try:
        return create_calendar_event(**payload.model_dump())
    except Exception as error:
        _raise_calendar_error(error)


@router.patch("/event/{event_id}")
def patch_event(event_id: str, payload: EventUpdateRequest) -> dict[str, Any]:
    try:
        values = payload.model_dump(exclude_unset=True)
        calendar_id = values.pop("calendar_id", "primary")
        return update_calendar_event(event_id, calendar_id=calendar_id, **values)
    except Exception as error:
        _raise_calendar_error(error)


@router.put("/event/{event_id}")
def put_event(event_id: str, payload: EventUpdateRequest) -> dict[str, Any]:
    return patch_event(event_id, payload)


@router.delete("/event/{event_id}")
def remove_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    try:
        return delete_calendar_event(event_id, calendar_id=calendar_id)
    except Exception as error:
        _raise_calendar_error(error)


@router.post("/reminder")
def add_reminder(payload: ReminderCreateRequest) -> dict[str, Any]:
    try:
        return create_reminder(**payload.model_dump())
    except Exception as error:
        _raise_calendar_error(error)
