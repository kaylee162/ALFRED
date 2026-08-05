from __future__ import annotations

import base64
import html
import logging
import re
import threading
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Any, Iterable

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

_SERVICE: Resource | None = None
_SERVICE_LOCK = threading.Lock()


class GmailError(RuntimeError):
    """Base Gmail integration error safe for the intent layer to catch."""


class GmailAuthError(GmailError):
    pass


class GmailNotFoundError(GmailError):
    pass


class GmailValidationError(GmailError):
    pass


def _http_error_message(exc: HttpError) -> str:
    status = getattr(exc.resp, "status", None)
    if status == 401:
        return "Gmail authorization expired. Delete token.json and reconnect Google."
    if status == 403:
        return "Google denied this Gmail action. Check the enabled Gmail API and OAuth scopes."
    if status == 404:
        return "That Gmail message or draft no longer exists."
    if status == 429:
        return "Gmail is temporarily rate-limiting ALFRED. Try again shortly."
    if status and status >= 500:
        return "Gmail is temporarily unavailable. No changes were made."
    return "Gmail could not complete that request."


def _load_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except (ValueError, OSError) as exc:
            LOGGER.warning("Ignoring invalid token.json: %s", exc)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            LOGGER.warning("Google token refresh failed: %s", exc)
            creds = None

    if not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            raise GmailAuthError(
                "Missing credentials.json in the backend folder. Add it, then reconnect Google."
            )
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)
        except Exception as exc:
            raise GmailAuthError(
                "Google sign-in could not be completed. Check credentials.json and retry."
            ) from exc

        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_gmail_service(*, force_rebuild: bool = False) -> Resource:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None or force_rebuild:
            _SERVICE = build(
                "gmail",
                "v1",
                credentials=_load_credentials(),
                cache_discovery=False,
            )
        return _SERVICE


def gmail_health() -> dict[str, Any]:
    global _SERVICE

    creds = _load_existing_credentials()

    if not creds:
        return {
            "connected": False,
            "requires_authentication": True,
            "error": (
                "Gmail is not authenticated. Run a Gmail command "
                "or use the reconnect endpoint."
            ),
        }

    try:
        with _SERVICE_LOCK:
            if _SERVICE is None:
                _SERVICE = build(
                    "gmail",
                    "v1",
                    credentials=creds,
                    cache_discovery=False,
                )

            service = _SERVICE

        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        return {
            "connected": True,
            "requires_authentication": False,
            "email": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal"),
        }

    except HttpError as exc:
        LOGGER.warning("Gmail health check failed: %s", exc)

        return {
            "connected": False,
            "requires_authentication": True,
            "error": _http_error_message(exc),
        }

    except Exception as exc:
        LOGGER.exception("Unexpected Gmail health-check failure")

        return {
            "connected": False,
            "requires_authentication": False,
            "error": f"Gmail health check failed: {exc}",
        }
    
def _load_existing_credentials() -> Credentials | None:
    if not TOKEN_PATH.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_PATH),
            SCOPES,
        )
    except (ValueError, OSError) as exc:
        LOGGER.warning("Could not load token.json: %s", exc)
        return None

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(
                creds.to_json(),
                encoding="utf-8",
            )
        except RefreshError as exc:
            LOGGER.warning("Google token refresh failed: %s", exc)
            return None

    return creds if creds.valid else None

def _decode_base64url(data: str | None) -> str:
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<(script|style).*?>.*?</\1>", "", value, flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</p\s*>", "\n\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    return "\n".join(line.strip() for line in value.splitlines() if line.strip())


def _header(payload: dict[str, Any], name: str) -> str:
    for item in payload.get("headers", []) or []:
        if str(item.get("name", "")).lower() == name.lower():
            return str(item.get("value") or "")
    return ""


def _extract_body(part: dict[str, Any]) -> tuple[str, str]:
    mime = str(part.get("mimeType") or "")
    data = (part.get("body") or {}).get("data")
    plain = _decode_base64url(data) if mime == "text/plain" else ""
    rich = _decode_base64url(data) if mime == "text/html" else ""
    for child in part.get("parts", []) or []:
        child_plain, child_rich = _extract_body(child)
        if child_plain and not plain:
            plain = child_plain
        if child_rich and not rich:
            rich = child_rich
    return plain, rich


def _normalize_message(message: dict[str, Any], *, include_body: bool) -> dict[str, Any]:
    payload = message.get("payload") or {}
    body = ""
    if include_body:
        plain, rich = _extract_body(payload)
        body = plain.strip() or _strip_html(rich)
    if not body:
        body = str(message.get("snippet") or "").strip()

    labels = list(message.get("labelIds") or [])
    sender_name, sender_email = parseaddr(_header(payload, "From"))
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": _header(payload, "From"),
        "from_name": sender_name,
        "from_email": sender_email,
        "to": _header(payload, "To"),
        "cc": _header(payload, "Cc"),
        "subject": _header(payload, "Subject") or "(No subject)",
        "date": _header(payload, "Date"),
        "internal_date": int(message.get("internalDate") or 0),
        "message_id_header": _header(payload, "Message-ID"),
        "references": _header(payload, "References"),
        "snippet": str(message.get("snippet") or ""),
        "body": body,
        "labels": labels,
        "is_unread": "UNREAD" in labels,
        "is_starred": "STARRED" in labels,
    }


def get_email(message_id: str, *, mark_as_read: bool = False) -> dict[str, Any]:
    if not message_id:
        raise GmailValidationError("A Gmail message ID is required.")
    service = get_gmail_service()
    try:
        message = (
            service.users().messages().get(userId="me", id=message_id, format="full").execute()
        )
        if mark_as_read and "UNREAD" in (message.get("labelIds") or []):
            modify_labels(message_id, remove_labels=["UNREAD"])
            message["labelIds"] = [x for x in message.get("labelIds", []) if x != "UNREAD"]
        return _normalize_message(message, include_body=True)
    except HttpError as exc:
        if getattr(exc.resp, "status", None) == 404:
            raise GmailNotFoundError(_http_error_message(exc)) from exc
        raise GmailError(_http_error_message(exc)) from exc


def search_emails(
    query: str = "in:inbox",
    *,
    max_results: int = 10,
    include_body: bool = False,
) -> list[dict[str, Any]]:
    query = (query or "in:inbox").strip()
    max_results = max(1, min(int(max_results), 50))
    service = get_gmail_service()
    try:
        listing = (
            service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
        )
        emails: list[dict[str, Any]] = []
        for ref in listing.get("messages", []) or []:
            kwargs: dict[str, Any] = {
                "userId": "me",
                "id": ref["id"],
                "format": "full" if include_body else "metadata",
            }
            if not include_body:
                kwargs["metadataHeaders"] = [
                    "From", "To", "Cc", "Subject", "Date", "Message-ID", "References"
                ]
            message = service.users().messages().get(**kwargs).execute()
            emails.append(_normalize_message(message, include_body=include_body))
        emails.sort(key=lambda item: item.get("internal_date", 0), reverse=True)
        return emails
    except HttpError as exc:
        raise GmailError(_http_error_message(exc)) from exc


def get_latest_email(query: str = "in:inbox", *, mark_as_read: bool = False) -> dict[str, Any] | None:
    matches = search_emails(query, max_results=1)
    return get_email(matches[0]["id"], mark_as_read=mark_as_read) if matches else None


def _validate_addresses(value: str | None, field: str, *, required: bool = False) -> str | None:
    value = (value or "").strip()
    if not value:
        if required:
            raise GmailValidationError(f"{field} is required.")
        return None
    parsed = getaddresses([value])
    invalid = [address for _, address in parsed if "@" not in address]
    if not parsed or invalid:
        raise GmailValidationError(f"{field} contains an invalid email address.")
    return value


def _build_message(
    *,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, Any]:
    to = _validate_addresses(to, "Recipient", required=True) or ""
    cc = _validate_addresses(cc, "CC")
    bcc = _validate_addresses(bcc, "BCC")
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not subject:
        raise GmailValidationError("Subject is required.")
    if not body:
        raise GmailValidationError("Email body is required.")

    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references
    message.set_content(body)
    result: dict[str, Any] = {
        "raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    }
    if thread_id:
        result["threadId"] = thread_id
    return result



def _normalize_draft(draft: dict[str, Any], *, include_body: bool = True) -> dict[str, Any]:
    message = draft.get("message") or {}
    normalized = _normalize_message(message, include_body=include_body)
    return {
        **normalized,
        "draft_id": draft.get("id"),
        "is_draft": True,
    }


def get_draft(draft_id: str) -> dict[str, Any]:
    if not draft_id:
        raise GmailValidationError("A Gmail draft ID is required.")
    try:
        draft = get_gmail_service().users().drafts().get(
            userId="me", id=draft_id, format="full"
        ).execute()
        return _normalize_draft(draft, include_body=True)
    except HttpError as exc:
        if getattr(exc.resp, "status", None) == 404:
            raise GmailNotFoundError(_http_error_message(exc)) from exc
        raise GmailError(_http_error_message(exc)) from exc


def search_drafts(query: str = "", *, max_results: int = 10) -> list[dict[str, Any]]:
    query = (query or "").strip()
    max_results = max(1, min(int(max_results), 50))
    service = get_gmail_service()
    try:
        listing = service.users().drafts().list(
            userId="me", q=query or None, maxResults=max_results
        ).execute()
        drafts = [get_draft(str(ref.get("id") or "")) for ref in listing.get("drafts", []) or []]
        drafts.sort(key=lambda item: item.get("internal_date", 0), reverse=True)
        return drafts
    except HttpError as exc:
        raise GmailError(_http_error_message(exc)) from exc


def update_draft(
    draft_id: str,
    *,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    if not draft_id:
        raise GmailValidationError("A Gmail draft ID is required.")
    existing = get_draft(draft_id)
    raw = _build_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        thread_id=str(existing.get("thread_id") or "") or None,
    )
    try:
        updated = get_gmail_service().users().drafts().update(
            userId="me",
            id=draft_id,
            body={"id": draft_id, "message": raw},
        ).execute()
        return {
            "success": True,
            "draft_id": updated.get("id") or draft_id,
            "message_id": (updated.get("message") or {}).get("id"),
            "thread_id": (updated.get("message") or {}).get("threadId"),
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "body": body,
            "is_draft": True,
        }
    except HttpError as exc:
        raise GmailError(_http_error_message(exc)) from exc

def create_email_draft(*, to: str, subject: str, body: str, cc: str | None = None, bcc: str | None = None) -> dict[str, Any]:
    raw = _build_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
    try:
        draft = get_gmail_service().users().drafts().create(
            userId="me", body={"message": raw}
        ).execute()
        return {
            "success": True,
            "draft_id": draft.get("id"),
            "message_id": (draft.get("message") or {}).get("id"),
            "thread_id": (draft.get("message") or {}).get("threadId"),
            "to": to, "cc": cc, "bcc": bcc, "subject": subject, "body": body,
        }
    except HttpError as exc:
        raise GmailError(_http_error_message(exc)) from exc


def create_reply_draft(*, message_id: str, body: str) -> dict[str, Any]:
    original = get_email(message_id)
    subject = str(original.get("subject") or "(No subject)")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    header_id = str(original.get("message_id_header") or "")
    refs = " ".join(x for x in [str(original.get("references") or "").strip(), header_id] if x)
    raw = _build_message(
        to=str(original.get("from_email") or original.get("from") or ""),
        subject=subject,
        body=body,
        thread_id=str(original.get("thread_id") or "") or None,
        in_reply_to=header_id or None,
        references=refs or None,
    )
    try:
        draft = get_gmail_service().users().drafts().create(
            userId="me", body={"message": raw}
        ).execute()
        return {
            "success": True,
            "draft_id": draft.get("id"),
            "message_id": (draft.get("message") or {}).get("id"),
            "thread_id": (draft.get("message") or {}).get("threadId"),
            "reply_to_message_id": message_id,
            "to": original.get("from"),
            "subject": subject,
            "body": body,
        }
    except HttpError as exc:
        raise GmailError(_http_error_message(exc)) from exc


def send_email(*, to: str, subject: str, body: str, cc: str | None = None, bcc: str | None = None) -> dict[str, Any]:
    raw = _build_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
    try:
        sent = get_gmail_service().users().messages().send(userId="me", body=raw).execute()
        return {
            "success": True, "message_id": sent.get("id"),
            "thread_id": sent.get("threadId"), "to": to,
            "cc": cc, "bcc": bcc, "subject": subject,
        }
    except HttpError as exc:
        raise GmailError(_http_error_message(exc)) from exc


def send_draft(draft_id: str) -> dict[str, Any]:
    if not draft_id:
        raise GmailValidationError("A Gmail draft ID is required.")
    try:
        sent = get_gmail_service().users().drafts().send(
            userId="me", body={"id": draft_id}
        ).execute()
        return {
            "success": True, "draft_id": draft_id,
            "message_id": sent.get("id"), "thread_id": sent.get("threadId"),
        }
    except HttpError as exc:
        raise GmailError(_http_error_message(exc)) from exc


def modify_labels(message_id: str, *, add_labels: Iterable[str] = (), remove_labels: Iterable[str] = ()) -> dict[str, Any]:
    if not message_id:
        raise GmailValidationError("A Gmail message ID is required.")
    try:
        result = get_gmail_service().users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": list(add_labels), "removeLabelIds": list(remove_labels)},
        ).execute()
        return {"success": True, "message_id": message_id, "labels": result.get("labelIds", [])}
    except HttpError as exc:
        raise GmailError(_http_error_message(exc)) from exc


def mark_email_read(message_id: str) -> dict[str, Any]:
    return modify_labels(message_id, remove_labels=["UNREAD"])


def mark_email_unread(message_id: str) -> dict[str, Any]:
    return modify_labels(message_id, add_labels=["UNREAD"])


def archive_email(message_id: str) -> dict[str, Any]:
    result = modify_labels(message_id, remove_labels=["INBOX"])
    return {**result, "archived": True}