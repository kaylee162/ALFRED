from __future__ import annotations

from typing import Any

from ai.ollama_client import chat_with_ollama
from gmail_tools.gmail_service import (
    create_email_draft,
    create_reply_draft,
    get_email,
    get_latest_email,
    list_recent_emails,
    list_unread_emails,
    search_emails,
)


def _truncate(
    value: str,
    limit: int = 5000,
) -> str:
    value = value.strip()

    if len(value) <= limit:
        return value

    return value[:limit].rstrip() + "\n[Email shortened for summarization]"


def _format_email_for_ai(
    email: dict[str, Any],
    include_body: bool = True,
) -> str:
    """
    Convert an email dictionary into text that Ollama can summarize.
    """
    lines = [
        f"From: {email.get('from') or 'Unknown sender'}",
        f"To: {email.get('to') or 'Unknown recipient'}",
        f"Date: {email.get('date') or 'Unknown date'}",
        f"Subject: {email.get('subject') or '(No subject)'}",
    ]

    if include_body:
        body = email.get("body") or email.get("snippet") or ""
        lines.extend(
            [
                "",
                "Body:",
                _truncate(body),
            ]
        )
    else:
        lines.extend(
            [
                "",
                f"Preview: {email.get('snippet') or 'No preview available.'}",
            ]
        )

    return "\n".join(lines)


def _format_email_list(
    emails: list[dict[str, Any]],
) -> str:
    """
    Format email search results for ALFRED's normal text response.
    """
    if not emails:
        return "I couldn't find any emails matching that request."

    lines = [
        f"I found {len(emails)} email{'s' if len(emails) != 1 else ''}:"
    ]

    for index, email in enumerate(emails, start=1):
        unread_text = "Unread" if email.get("is_unread") else "Read"

        lines.extend(
            [
                "",
                f"{index}. {email.get('subject') or '(No subject)'}",
                f"From: {email.get('from') or 'Unknown sender'}",
                f"Date: {email.get('date') or 'Unknown date'}",
                f"Status: {unread_text}",
                f"Preview: {email.get('snippet') or 'No preview available.'}",
                f"Email ID: {email.get('id')}",
            ]
        )

    return "\n".join(lines)


def summarize_email(
    message_id: str,
) -> dict[str, Any]:
    """
    Read one email and ask Ollama for a concise, useful summary.
    """
    email = get_email(message_id)

    formatted_emails = "\n\n--- EMAIL ---\n\n".join(
        _format_email_for_ai(
            email,
            include_body=False,
        )
        for email in emails
    )

    prompt = f"""
You are ALFRED, a helpful personal desktop assistant.

Create a concise inbox briefing from the emails below.

Use this exact plain-text format:

Inbox Briefing

Overview:
- One or more short overview items.

Important/Missing Actions:
- Every important action the user should take.
- Write "No important actions found." if there are none.

Visible Deadlines/Meetings/Payments:
- List visible dates, deadlines, meetings, reservations, or payments.
- Write "No visible deadlines, meetings, or payments." if there are none.

Replies Needed:
- List emails that appear to need a reply and explain why.
- Write "No replies appear necessary." if there are none.

FYI Section:
- List informational messages that require no action.

Rules:
- Use only the headings shown above.
- Put each item on a line beginning with "- ".
- Do not use Markdown asterisks.
- Do not expose Gmail message IDs.
- Do not invent details.
- Keep each item concise.
- Ignore signatures and promotional filler.

EMAILS:
{formatted_emails}
""".strip()

    try:
        summary = chat_with_ollama(prompt).strip()
    except Exception:
        summary = (
            f"This email is from {email.get('from') or 'an unknown sender'} "
            f"about {email.get('subject') or 'an unspecified subject'}. "
            f"{email.get('snippet') or 'No preview is available.'}"
        )

    return {
        "response": summary,
        "email": email,
        "summary": summary,
    }


def summarize_emails(
    query: str = "in:inbox is:unread",
    max_results: int = 10,
) -> dict[str, Any]:
    """
    Create a concise inbox briefing.

    This intentionally uses message metadata and snippets instead of
    downloading every complete email body. That keeps Gmail summaries fast
    enough for the frontend request timeout.
    """
    max_results = max(1, min(max_results, 10))

    emails = search_emails(
        query=query,
        max_results=max_results,
        include_body=False,
    )

    if not emails:
        return {
            "response": (
                "Looks clear. I couldn't find any emails matching that request."
            ),
            "emails": [],
            "summary": "No matching emails.",
        }

    formatted_emails = "\n\n--- EMAIL ---\n\n".join(
        _format_email_for_ai(
            email,
            include_body=False,
        )
        for email in emails
    )

    prompt = f"""
You are ALFRED, a helpful personal desktop assistant.

Create a concise inbox briefing from the email previews below.

Include:
- A one-sentence overview.
- Important or urgent messages first.
- Any visible deadlines, dates, meetings, payments, or requested actions.
- Which emails probably need a reply.
- A brief FYI section for messages that appear informational.

Do not invent details that are not present in the previews.
Do not expose Gmail message IDs.
Keep the response concise and easy to scan.

EMAIL PREVIEWS:
{formatted_emails}
""".strip()

    try:
        summary = chat_with_ollama(prompt).strip()
    except Exception as exc:
        print("Email summarization failed:", exc)

        lines = [
            f"Absolutely, I found {len(emails)} matching emails."
        ]

        for email in emails:
            lines.append(
                f"- {email.get('subject') or '(No subject)'} "
                f"from {email.get('from') or 'Unknown sender'}: "
                f"{email.get('snippet') or 'No preview available.'}"
            )

        summary = "\n".join(lines)

    return {
        "response": summary,
        "emails": emails,
        "summary": summary,
    }

def handle_list_unread_emails(
    max_results: int = 10,
) -> dict[str, Any]:
    emails = list_unread_emails(max_results=max_results)

    return {
        "response": _format_email_list(emails),
        "emails": emails,
    }


def handle_list_recent_emails(
    max_results: int = 10,
) -> dict[str, Any]:
    emails = list_recent_emails(max_results=max_results)

    return {
        "response": _format_email_list(emails),
        "emails": emails,
    }


def handle_search_emails(
    query: str,
    max_results: int = 10,
) -> dict[str, Any]:
    emails = search_emails(
        query=query,
        max_results=max_results,
        include_body=False,
    )

    return {
        "response": _format_email_list(emails),
        "emails": emails,
    }


def handle_read_email(
    message_id: str,
    mark_as_read: bool = True,
) -> dict[str, Any]:
    email = get_email(
        message_id=message_id,
        mark_as_read=mark_as_read,
    )

    response = "\n".join(
        [
            f"From: {email.get('from') or 'Unknown sender'}",
            f"To: {email.get('to') or 'Unknown recipient'}",
            f"Date: {email.get('date') or 'Unknown date'}",
            f"Subject: {email.get('subject') or '(No subject)'}",
            "",
            email.get("body") or email.get("snippet") or "This email has no readable body.",
        ]
    )

    return {
        "response": response,
        "email": email,
    }


def handle_read_latest_email(
    query: str = "in:inbox",
    mark_as_read: bool = True,
) -> dict[str, Any]:
    email = get_latest_email(
        query=query,
        mark_as_read=mark_as_read,
    )

    if not email:
        return {
            "response": "I couldn't find an email matching that request.",
            "email": None,
        }

    response = "\n".join(
        [
            f"From: {email.get('from') or 'Unknown sender'}",
            f"Date: {email.get('date') or 'Unknown date'}",
            f"Subject: {email.get('subject') or '(No subject)'}",
            "",
            email.get("body") or email.get("snippet") or "This email has no readable body.",
        ]
    )

    return {
        "response": response,
        "email": email,
    }


def handle_create_email_draft(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
) -> dict[str, Any]:
    draft = create_email_draft(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
    )

    response = "\n".join(
        [
            "Absolutely, I created an email draft.",
            "",
            f"To: {to}",
            f"Subject: {subject}",
            "",
            body,
        ]
    )

    return {
        "response": response,
        "draft": {
            **draft,
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc,
            "bcc": bcc,
        },
    }


def handle_create_reply_draft(
    message_id: str,
    body: str,
) -> dict[str, Any]:
    draft = create_reply_draft(
        message_id=message_id,
        body=body,
    )

    response = "\n".join(
        [
            "Absolutely, I created a reply draft.",
            "",
            f"To: {draft.get('to') or 'Unknown recipient'}",
            f"Subject: {draft.get('subject') or '(No subject)'}",
            "",
            body,
        ]
    )

    return {
        "response": response,
        "draft": {
            **draft,
            "body": body,
        },
    }