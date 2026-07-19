from __future__ import annotations

import base64
import html
import re
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
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

def get_gmail_service() -> Resource:
    """
    Authenticate with Google and return a Gmail API service.

    ALFRED shares credentials.json and token.json between Calendar and Gmail.
    Delete token.json once after adding the Gmail scopes so Google can request
    permission again.
    """
    creds: Credentials | None = None

    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(TOKEN_PATH),
                SCOPES,
            )
        except (ValueError, OSError):
            # A malformed or outdated token should not crash ALFRED.
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # Refresh may fail when scopes changed or access was revoked.
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
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(
            creds.to_json(),
            encoding="utf-8",
        )

    return build(
        "gmail",
        "v1",
        credentials=creds,
        cache_discovery=False,
    )


def _decode_base64url(data: str | None) -> str:
    """
    Decode Gmail's URL-safe base64 content.
    """
    if not data:
        return ""

    try:
        padding = "=" * (-len(data) % 4)
        decoded = base64.urlsafe_b64decode(data + padding)
        return decoded.decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return ""


def _strip_html(value: str) -> str:
    """
    Convert a basic HTML email body into readable plain text.
    """
    if not value:
        return ""

    value = re.sub(
        r"<(script|style).*?>.*?</\1>",
        "",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p\s*>", "\n\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)

    lines = [line.strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _get_header(
    payload: dict[str, Any],
    header_name: str,
) -> str:
    """
    Read one RFC email header from a Gmail payload.
    """
    headers = payload.get("headers", [])

    for header in headers:
        if header.get("name", "").lower() == header_name.lower():
            return header.get("value", "")

    return ""


def _extract_body_from_part(
    part: dict[str, Any],
) -> tuple[str, str]:
    """
    Recursively inspect a Gmail MIME message.

    Returns:
        A tuple of (plain_text_body, html_body).
    """
    mime_type = part.get("mimeType", "")
    body_data = part.get("body", {}).get("data")

    plain_text = ""
    html_text = ""

    if mime_type == "text/plain" and body_data:
        plain_text = _decode_base64url(body_data)

    elif mime_type == "text/html" and body_data:
        html_text = _decode_base64url(body_data)

    for child in part.get("parts", []) or []:
        child_plain, child_html = _extract_body_from_part(child)

        if child_plain and not plain_text:
            plain_text = child_plain

        if child_html and not html_text:
            html_text = child_html

    return plain_text, html_text


def _message_to_dict(
    message: dict[str, Any],
    include_body: bool = True,
) -> dict[str, Any]:
    """
    Normalize a Gmail API message into a simpler ALFRED-friendly dictionary.
    """
    payload = message.get("payload", {})

    plain_body = ""
    html_body = ""

    if include_body:
        plain_body, html_body = _extract_body_from_part(payload)

        # Some simple emails store their content directly on the top payload.
        if not plain_body and not html_body:
            mime_type = payload.get("mimeType", "")
            body_data = payload.get("body", {}).get("data")

            if mime_type == "text/plain":
                plain_body = _decode_base64url(body_data)
            elif mime_type == "text/html":
                html_body = _decode_base64url(body_data)

    body = plain_body.strip()

    if not body and html_body:
        body = _strip_html(html_body)

    if not body:
        body = message.get("snippet", "").strip()

    label_ids = message.get("labelIds", [])

    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": _get_header(payload, "From"),
        "to": _get_header(payload, "To"),
        "cc": _get_header(payload, "Cc"),
        "subject": _get_header(payload, "Subject") or "(No subject)",
        "date": _get_header(payload, "Date"),
        "message_id_header": _get_header(payload, "Message-ID"),
        "references": _get_header(payload, "References"),
        "snippet": message.get("snippet", ""),
        "body": body,
        "labels": label_ids,
        "is_unread": "UNREAD" in label_ids,
        "is_starred": "STARRED" in label_ids,
    }


def get_email(
    message_id: str,
    mark_as_read: bool = False,
) -> dict[str, Any]:
    """
    Retrieve one complete email by Gmail message ID.
    """
    if not message_id:
        raise ValueError("A Gmail message ID is required.")

    service = get_gmail_service()

    try:
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

        if mark_as_read and "UNREAD" in message.get("labelIds", []):
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()

            message["labelIds"] = [
                label
                for label in message.get("labelIds", [])
                if label != "UNREAD"
            ]

        return _message_to_dict(message, include_body=True)

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail could not read message {message_id}: {exc}"
        ) from exc


def search_emails(
    query: str = "in:inbox",
    max_results: int = 10,
    include_body: bool = False,
) -> list[dict[str, Any]]:
    """
    Search Gmail using standard Gmail search syntax.

    Examples:
        is:unread
        from:person@example.com
        subject:invoice
        newer_than:7d
        has:attachment
        in:inbox is:unread
    """
    max_results = max(1, min(max_results, 50))
    query = query.strip() or "in:inbox"

    service = get_gmail_service()

    try:
        result = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=max_results,
            )
            .execute()
        )

        message_refs = result.get("messages", [])
        emails: list[dict[str, Any]] = []

        for message_ref in message_refs:
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_ref["id"],
                    format="full" if include_body else "metadata",
                    metadataHeaders=[
                        "From",
                        "To",
                        "Cc",
                        "Subject",
                        "Date",
                        "Message-ID",
                        "References",
                    ],
                )
                .execute()
            )

            emails.append(
                _message_to_dict(
                    message,
                    include_body=include_body,
                )
            )

        return emails

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail search failed: {exc}"
        ) from exc


def list_recent_emails(
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Return recent inbox messages.
    """
    return search_emails(
        query="in:inbox",
        max_results=max_results,
        include_body=False,
    )


def list_unread_emails(
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Return unread inbox messages.
    """
    return search_emails(
        query="in:inbox is:unread",
        max_results=max_results,
        include_body=False,
    )


def get_latest_email(
    query: str = "in:inbox",
    mark_as_read: bool = False,
) -> dict[str, Any] | None:
    """
    Find and retrieve the newest message matching a Gmail query.
    """
    emails = search_emails(
        query=query,
        max_results=1,
        include_body=False,
    )

    if not emails:
        return None

    return get_email(
        emails[0]["id"],
        mark_as_read=mark_as_read,
    )


def _build_mime_message(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> dict[str, Any]:
    """
    Build a URL-safe RFC 2822 MIME message for the Gmail API.
    """
    if not to.strip():
        raise ValueError("The recipient email address is required.")

    if not subject.strip():
        raise ValueError("The email subject is required.")

    if not body.strip():
        raise ValueError("The email body is required.")

    message = EmailMessage()
    message["To"] = to.strip()
    message["Subject"] = subject.strip()

    if cc and cc.strip():
        message["Cc"] = cc.strip()

    if bcc and bcc.strip():
        message["Bcc"] = bcc.strip()

    if in_reply_to:
        message["In-Reply-To"] = in_reply_to

    if references:
        message["References"] = references

    message.set_content(body.strip())

    encoded_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    gmail_message: dict[str, Any] = {
        "raw": encoded_message,
    }

    if thread_id:
        gmail_message["threadId"] = thread_id

    return gmail_message


def create_email_draft(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    """
    Create a Gmail draft without sending it.
    """
    service = get_gmail_service()

    message_body = _build_mime_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
    )

    try:
        draft = (
            service.users()
            .drafts()
            .create(
                userId="me",
                body={"message": message_body},
            )
            .execute()
        )

        return {
            "success": True,
            "draft_id": draft.get("id"),
            "message_id": draft.get("message", {}).get("id"),
            "thread_id": draft.get("message", {}).get("threadId"),
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "body": body,
        }

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail could not create the draft: {exc}"
        ) from exc


def create_reply_draft(
    message_id: str,
    body: str,
) -> dict[str, Any]:
    """
    Create a reply draft in the same Gmail conversation.
    """
    original = get_email(message_id)

    original_subject = original.get("subject", "(No subject)")
    reply_subject = (
        original_subject
        if original_subject.lower().startswith("re:")
        else f"Re: {original_subject}"
    )

    original_message_header = original.get("message_id_header", "")
    original_references = original.get("references", "").strip()

    if original_message_header:
        references = (
            f"{original_references} {original_message_header}".strip()
        )
    else:
        references = original_references

    message_body = _build_mime_message(
        to=original.get("from", ""),
        subject=reply_subject,
        body=body,
        thread_id=original.get("thread_id"),
        in_reply_to=original_message_header or None,
        references=references or None,
    )

    service = get_gmail_service()

    try:
        draft = (
            service.users()
            .drafts()
            .create(
                userId="me",
                body={"message": message_body},
            )
            .execute()
        )

        return {
            "success": True,
            "draft_id": draft.get("id"),
            "message_id": draft.get("message", {}).get("id"),
            "thread_id": draft.get("message", {}).get("threadId"),
            "reply_to_message_id": message_id,
            "to": original.get("from", ""),
            "subject": reply_subject,
            "body": body,
        }

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail could not create the reply draft: {exc}"
        ) from exc


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    """
    Send an email immediately.

    ALFRED should only call this after the user explicitly asks to send.
    Normal writing requests should call create_email_draft instead.
    """
    service = get_gmail_service()

    message_body = _build_mime_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
    )

    try:
        sent = (
            service.users()
            .messages()
            .send(
                userId="me",
                body=message_body,
            )
            .execute()
        )

        return {
            "success": True,
            "message_id": sent.get("id"),
            "thread_id": sent.get("threadId"),
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
        }

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail could not send the email: {exc}"
        ) from exc


def send_draft(
    draft_id: str,
) -> dict[str, Any]:
    """
    Send an existing Gmail draft.
    """
    if not draft_id:
        raise ValueError("A Gmail draft ID is required.")

    service = get_gmail_service()

    try:
        sent = (
            service.users()
            .drafts()
            .send(
                userId="me",
                body={"id": draft_id},
            )
            .execute()
        )

        return {
            "success": True,
            "draft_id": draft_id,
            "message_id": sent.get("id"),
            "thread_id": sent.get("threadId"),
        }

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail could not send the draft: {exc}"
        ) from exc


def mark_email_read(
    message_id: str,
) -> dict[str, Any]:
    """
    Remove Gmail's UNREAD label from a message.
    """
    service = get_gmail_service()

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

        return {
            "success": True,
            "message_id": message_id,
            "is_unread": False,
        }

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail could not mark the email as read: {exc}"
        ) from exc


def mark_email_unread(
    message_id: str,
) -> dict[str, Any]:
    """
    Add Gmail's UNREAD label to a message.
    """
    service = get_gmail_service()

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": ["UNREAD"]},
        ).execute()

        return {
            "success": True,
            "message_id": message_id,
            "is_unread": True,
        }

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail could not mark the email as unread: {exc}"
        ) from exc


def archive_email(
    message_id: str,
) -> dict[str, Any]:
    """
    Archive an email by removing the INBOX label.
    """
    service = get_gmail_service()

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()

        return {
            "success": True,
            "message_id": message_id,
            "archived": True,
        }

    except HttpError as exc:
        raise RuntimeError(
            f"Gmail could not archive the email: {exc}"
        ) from exc