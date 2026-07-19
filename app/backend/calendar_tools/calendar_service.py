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

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

TIMEZONE = "America/New_York"
LOCAL_TZ = ZoneInfo(TIMEZONE)


def _local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _as_local_datetime(value: str) -> datetime:
    parsed = parser.parse(value)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=LOCAL_TZ)

    return parsed.astimezone(LOCAL_TZ)


def _format_google_event(event: dict[str, Any]) -> dict[str, Any]:
    start_data = event.get("start", {})
    end_data = event.get("end", {})

    is_all_day = "date" in start_data

    return {
        "id": event.get("id"),
        "title": event.get("summary", "Untitled"),
        "start": start_data.get("dateTime") or start_data.get("date"),
        "end": end_data.get("dateTime") or end_data.get("date"),
        "all_day": is_all_day,
        "location": event.get("location"),
        "description": event.get("description"),
        "htmlLink": event.get("htmlLink"),
    }


def get_calendar_service():
    creds = None

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(TOKEN_PATH),
                SCOPES,
            )
        except (ValueError, OSError) as exc:
            print(f"Could not load token.json: {exc}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                print(f"Could not refresh Google token: {exc}")
                creds = None

        if not creds:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    "Missing credentials.json. Place it in the backend folder."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH),
                SCOPES,
            )

            creds = flow.run_local_server(
                host="localhost",
                port=0,
                open_browser=True,
                authorization_prompt_message=(
                    "Open this URL in your browser to authorize ALFRED:\n{url}"
                ),
                success_message=(
                    "ALFRED has been authorized. You can close this window."
                ),
            )

        TOKEN_PATH.write_text(
            creds.to_json(),
            encoding="utf-8",
        )

    return build(
        "calendar",
        "v3",
        credentials=creds,
        cache_discovery=False,
    )

def list_upcoming_events(days: int = 7, max_results: int = 20) -> list[dict[str, Any]]:
    service = get_calendar_service()

    now = _local_now()
    end = now + timedelta(days=days)

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            timeZone=TIMEZONE,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return [_format_google_event(event) for event in events_result.get("items", [])]


def list_events_for_day(date_string: str) -> list[dict[str, Any]]:
    service = get_calendar_service()

    day = parser.parse(date_string).date()
    start = datetime.combine(day, datetime.min.time(), tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            timeZone=TIMEZONE,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return [_format_google_event(event) for event in events_result.get("items", [])]


def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    reminder_minutes: int = 10,
) -> dict[str, Any]:
    service = get_calendar_service()

    start_dt = _as_local_datetime(start_time)
    end_dt = _as_local_datetime(end_time)

    event_body = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": TIMEZONE,
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

    return _format_google_event(created_event)


def update_calendar_event(
    event_id: str,
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    service = get_calendar_service()

    start_dt = _as_local_datetime(start_time)
    end_dt = _as_local_datetime(end_time)

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
                    "dateTime": start_dt.isoformat(),
                    "timeZone": TIMEZONE,
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": TIMEZONE,
                },
            },
        )
        .execute()
    )

    return _format_google_event(updated_event)


def delete_calendar_event(event_id: str) -> dict[str, Any]:
    service = get_calendar_service()

    service.events().delete(
        calendarId="primary",
        eventId=event_id,
    ).execute()

    return {
        "success": True,
        "deleted_event_id": event_id,
    }


def create_reminder(
    title: str,
    reminder_time: str,
    reminder_minutes_before: int = 0,
) -> dict[str, Any]:
    start = _as_local_datetime(reminder_time)
    end = start + timedelta(minutes=15)

    return create_calendar_event(
        title=f"Reminder: {title}",
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        description="Created by ALFRED.",
        reminder_minutes=reminder_minutes_before,
    )