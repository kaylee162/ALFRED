from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

from dateutil import parser
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service():
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    "Missing credentials.json. Download it from Google Cloud Console and place it in backend/."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH),
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def list_upcoming_events(days: int = 7, max_results: int = 20) -> list[dict[str, Any]]:
    service = get_calendar_service()

    now = datetime.utcnow()
    end = now + timedelta(days=days)

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat() + "Z",
            timeMax=end.isoformat() + "Z",
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])

    return [
        {
            "id": event.get("id"),
            "title": event.get("summary", "Untitled"),
            "start": event.get("start", {}).get("dateTime")
            or event.get("start", {}).get("date"),
            "end": event.get("end", {}).get("dateTime")
            or event.get("end", {}).get("date"),
            "location": event.get("location"),
            "description": event.get("description"),
        }
        for event in events
    ]


def list_events_for_day(date_string: str) -> list[dict[str, Any]]:
    service = get_calendar_service()

    local_tz = ZoneInfo("America/New_York")
    day = parser.parse(date_string).date()

    start = datetime.combine(day, datetime.min.time(), tzinfo=local_tz)
    end = start + timedelta(days=1)

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return [
        {
            "id": event.get("id"),
            "title": event.get("summary", "Untitled"),
            "start": event.get("start", {}).get("dateTime")
            or event.get("start", {}).get("date"),
            "end": event.get("end", {}).get("dateTime")
            or event.get("end", {}).get("date"),
            "location": event.get("location"),
            "description": event.get("description"),
        }
        for event in events_result.get("items", [])
    ]

def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    reminder_minutes: int = 10,
) -> dict[str, Any]:
    service = get_calendar_service()

    event_body = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {
            "dateTime": start_time,
            "timeZone": "America/New_York",
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "America/New_York",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {
                    "method": "popup",
                    "minutes": reminder_minutes,
                }
            ],
        },
    }

    created_event = (
        service.events()
        .insert(calendarId="primary", body=event_body)
        .execute()
    )

    return {
        "id": created_event.get("id"),
        "title": created_event.get("summary"),
        "start": created_event.get("start"),
        "end": created_event.get("end"),
        "htmlLink": created_event.get("htmlLink"),
    }

def update_calendar_event(
    event_id: str,
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    service = get_calendar_service()

    updated_event = (
        service.events()
        .patch(
            calendarId="primary",
            eventId=event_id,
            body={
                "summary": title,
                "location": location,
                "description": description,
                "start": {
                    "dateTime": start_time,
                    "timeZone": "America/New_York",
                },
                "end": {
                    "dateTime": end_time,
                    "timeZone": "America/New_York",
                },
            },
        )
        .execute()
    )

    return {
        "id": updated_event.get("id"),
        "title": updated_event.get("summary", "Untitled"),
        "start": updated_event.get("start", {}).get("dateTime")
        or updated_event.get("start", {}).get("date"),
        "end": updated_event.get("end", {}).get("dateTime")
        or updated_event.get("end", {}).get("date"),
        "location": updated_event.get("location"),
        "description": updated_event.get("description"),
        "htmlLink": updated_event.get("htmlLink"),
    }

def create_reminder(
    title: str,
    reminder_time: str,
    reminder_minutes_before: int = 0,
) -> dict[str, Any]:
    start = parser.parse(reminder_time)
    end = start + timedelta(minutes=15)

    return create_calendar_event(
        title=f"Reminder: {title}",
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        description="Created by ALFRED.",
        reminder_minutes=reminder_minutes_before,
    )