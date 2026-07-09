from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from .calendar_service import (
    get_calendar_service,
    list_upcoming_events,
    list_events_for_day,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    create_reminder,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


class EventCreateRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    description: str | None = None
    location: str | None = None
    reminder_minutes: int | None = 10


class EventUpdateRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    description: str | None = None
    location: str | None = None


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
        reminder_minutes=payload.reminder_minutes or 10,
    )


@router.patch("/event/{event_id}")
def patch_event(event_id: str, payload: EventUpdateRequest):
    try:
        return update_calendar_event(
            event_id=event_id,
            title=payload.title,
            start_time=payload.start_time,
            end_time=payload.end_time,
            description=payload.description,
            location=payload.location,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.put("/event/{event_id}")
def put_event(event_id: str, payload: EventUpdateRequest):
    return patch_event(event_id, payload)

@router.delete("/event/{event_id}")
def remove_event(event_id: str):
    try:
        return delete_calendar_event(event_id)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    
@router.post("/reminder")
def add_reminder(payload: ReminderCreateRequest):
    return create_reminder(
        title=payload.title,
        reminder_time=payload.reminder_time,
        reminder_minutes_before=payload.reminder_minutes_before,
    )