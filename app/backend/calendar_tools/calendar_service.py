from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from dateutil import parser
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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


class CalendarServiceError(RuntimeError):
    pass


class CalendarEventNotFound(CalendarServiceError):
    pass


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _coerce_datetime(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else parser.parse(value)
    return parsed.replace(tzinfo=LOCAL_TZ) if parsed.tzinfo is None else parsed.astimezone(LOCAL_TZ)


def _coerce_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.astimezone(LOCAL_TZ).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return parser.parse(value).date()


def _event_payload(raw: dict[str, Any], calendar_id: str) -> dict[str, Any]:
    start = raw.get("start") or {}
    end = raw.get("end") or {}
    all_day = "date" in start
    return {
        "id": raw.get("id"),
        "calendar_id": calendar_id,
        "title": raw.get("summary") or "Untitled",
        "start": start.get("date") if all_day else start.get("dateTime"),
        "end": end.get("date") if all_day else end.get("dateTime"),
        "all_day": all_day,
        "location": raw.get("location"),
        "description": raw.get("description"),
        "html_link": raw.get("htmlLink"),
        "status": raw.get("status"),
        "recurring_event_id": raw.get("recurringEventId"),
        "original_start": (raw.get("originalStartTime") or {}).get("dateTime")
        or (raw.get("originalStartTime") or {}).get("date"),
        "etag": raw.get("etag"),
    }


def get_calendar_service():
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except (ValueError, OSError):
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError("Missing credentials.json in the backend folder.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(
                host="localhost",
                port=0,
                open_browser=True,
                authorization_prompt_message="Open this URL to authorize ALFRED:\n{url}",
                success_message="ALFRED has been authorized. You can close this window.",
            )
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_calendar_ids() -> list[str]:
    service = get_calendar_service()
    ids: list[str] = []
    token: str | None = None
    while True:
        result = service.calendarList().list(
            pageToken=token, showHidden=False, showDeleted=False
        ).execute()
        for item in result.get("items", []):
            calendar_id = item.get("id")
            if calendar_id and not item.get("hidden", False) and item.get("selected", True):
                ids.append(calendar_id)
        token = result.get("nextPageToken")
        if not token:
            break
    return ids or ["primary"]


def _sort_key(event: dict[str, Any]) -> tuple[datetime, str]:
    value = event.get("start")
    if not value:
        return datetime.max.replace(tzinfo=LOCAL_TZ), event.get("title", "")
    try:
        parsed = parser.parse(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(LOCAL_TZ), event.get("title", "")
    except Exception:
        return datetime.max.replace(tzinfo=LOCAL_TZ), event.get("title", "")


def _dedupe(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in events:
        key = (
            str(event.get("calendar_id") or ""),
            str(event.get("id") or ""),
            str(event.get("original_start") or event.get("start") or ""),
        )
        unique[key] = event
    result = list(unique.values())
    result.sort(key=_sort_key)
    return result


def list_events_between(
    start: str | datetime,
    end: str | datetime,
    *,
    max_results: int = 250,
    calendar_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    start_dt = _coerce_datetime(start)
    end_dt = _coerce_datetime(end)
    if end_dt <= start_dt:
        raise ValueError("end must be after start")

    service = get_calendar_service()
    events: list[dict[str, Any]] = []
    for calendar_id in calendar_ids or list_calendar_ids():
        token: str | None = None
        try:
            while True:
                result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=start_dt.isoformat(),
                    timeMax=end_dt.isoformat(),
                    timeZone=TIMEZONE,
                    singleEvents=True,
                    orderBy="startTime",
                    showDeleted=False,
                    maxResults=min(max_results, 2500),
                    pageToken=token,
                ).execute()
                events.extend(_event_payload(item, calendar_id) for item in result.get("items", []))
                token = result.get("nextPageToken")
                if not token or len(events) >= max_results:
                    break
        except HttpError:
            continue
    return _dedupe(events)[:max_results]


def list_events_for_day(day: str | date) -> list[dict[str, Any]]:
    target = _coerce_date(day)
    start = datetime.combine(target, time.min, tzinfo=LOCAL_TZ)
    return list_events_between(start, start + timedelta(days=1))


def list_upcoming_events(days: int = 7, max_results: int = 20) -> list[dict[str, Any]]:
    now = local_now()
    start = datetime.combine(now.date(), time.min, tzinfo=LOCAL_TZ)
    events = list_events_between(start, start + timedelta(days=max(days, 1) + 1), max_results=500)
    kept: list[dict[str, Any]] = []
    for event in events:
        if event.get("all_day"):
            if _coerce_date(event["start"]) >= now.date():
                kept.append(event)
            continue
        try:
            event_end = _coerce_datetime(event.get("end") or event["start"])
            if event_end > now:
                kept.append(event)
        except Exception:
            pass
    kept.sort(key=_sort_key)
    return kept[:max_results]


def get_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    try:
        raw = get_calendar_service().events().get(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as exc:
        if getattr(exc.resp, "status", None) == 404:
            raise CalendarEventNotFound(event_id) from exc
        raise CalendarServiceError(str(exc)) from exc
    return _event_payload(raw, calendar_id)


def create_calendar_event(
    *,
    title: str,
    start_time: str | None = None,
    end_time: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    all_day: bool = False,
    description: str | None = None,
    location: str | None = None,
    reminder_minutes: int | None = 10,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": title.strip() or "Untitled",
        "location": location or None,
        "description": description or None,
    }
    if all_day:
        if not start_date:
            raise ValueError("start_date is required for all-day events")
        first = _coerce_date(start_date)
        last_exclusive = _coerce_date(end_date) if end_date else first + timedelta(days=1)
        if last_exclusive <= first:
            last_exclusive = first + timedelta(days=1)
        body["start"] = {"date": first.isoformat()}
        body["end"] = {"date": last_exclusive.isoformat()}
    else:
        if not start_time or not end_time:
            raise ValueError("start_time and end_time are required for timed events")
        start_dt = _coerce_datetime(start_time)
        end_dt = _coerce_datetime(end_time)
        if end_dt <= start_dt:
            raise ValueError("end_time must be after start_time")
        body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE}
        body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE}

    if reminder_minutes is None:
        body["reminders"] = {"useDefault": True}
    else:
        body["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": max(0, reminder_minutes)}],
        }

    raw = get_calendar_service().events().insert(calendarId=calendar_id, body=body).execute()
    return _event_payload(raw, calendar_id)


def update_calendar_event(
    event_id: str,
    *,
    calendar_id: str = "primary",
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    all_day: bool | None = None,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    current = get_event(event_id, calendar_id)
    body: dict[str, Any] = {}
    if title is not None:
        body["summary"] = title
    if location is not None:
        body["location"] = location or None
    if description is not None:
        body["description"] = description or None

    resulting_all_day = current["all_day"] if all_day is None else all_day
    if resulting_all_day:
        first = _coerce_date(start_date or current["start"])
        last_exclusive = _coerce_date(end_date or current.get("end") or (first + timedelta(days=1)))
        if last_exclusive <= first:
            last_exclusive = first + timedelta(days=1)
        body["start"] = {"date": first.isoformat()}
        body["end"] = {"date": last_exclusive.isoformat()}
    elif any(value is not None for value in (start_time, end_time, all_day)):
        start_dt = _coerce_datetime(start_time or current["start"])
        end_dt = _coerce_datetime(end_time or current.get("end") or (start_dt + timedelta(hours=1)))
        if end_dt <= start_dt:
            raise ValueError("end_time must be after start_time")
        body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE}
        body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE}

    raw = get_calendar_service().events().patch(
        calendarId=calendar_id, eventId=event_id, body=body
    ).execute()
    return _event_payload(raw, calendar_id)


def delete_calendar_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    try:
        get_calendar_service().events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as exc:
        if getattr(exc.resp, "status", None) == 404:
            raise CalendarEventNotFound(event_id) from exc
        raise CalendarServiceError(str(exc)) from exc
    return {"success": True, "event_id": event_id, "calendar_id": calendar_id}


def create_reminder(title: str, reminder_time: str, reminder_minutes_before: int = 0) -> dict[str, Any]:
    start = _coerce_datetime(reminder_time)
    return create_calendar_event(
        title=f"Reminder: {title}",
        start_time=start.isoformat(),
        end_time=(start + timedelta(minutes=15)).isoformat(),
        description="Created by ALFRED.",
        reminder_minutes=reminder_minutes_before,
    )
