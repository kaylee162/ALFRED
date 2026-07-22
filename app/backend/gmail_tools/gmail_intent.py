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


def _ollama_text(
    prompt: str,
    *,
    timeout: int = 45,
    num_predict: int = 400,
) -> str:
    """Run Ollama and return only the assistant text."""
    message = chat_with_ollama(
        prompt,
        timeout=timeout,
        num_predict=num_predict,
        temperature=0.2,
    )
    return str(message.get("content") or "").strip()


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
    """Read one email and ask Ollama for a concise, useful summary."""
    email = get_email(message_id)

    formatted_email = _format_email_for_ai(
        email,
        include_body=True,
    )

    prompt = f"""
You are ALFRED, a helpful personal desktop assistant.

Summarize the email below.

Include:
- A concise overview
- Any requested action
- Any visible deadline, meeting, payment, or important date
- Whether a reply appears necessary

Do not invent details. Keep the response under 180 words.

EMAIL:
{formatted_email}
""".strip()

    try:
        summary = _ollama_text(
            prompt,
            timeout=45,
            num_predict=300,
        )
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
    query: str = "in:inbox",
    max_results: int = 5,
) -> dict[str, Any]:
    """
    Create a fast email briefing using Gmail metadata and snippets.

    Full message bodies are deliberately not downloaded here. Snippets are
    enough for a multi-email overview and keep the Ollama prompt small.
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

Summarize the following {len(emails)} emails using only the information
provided.

Requirements:
- Begin with a brief overview.
- Give each email one concise bullet.
- Include the sender and subject.
- Mention visible deadlines, meetings, payments, or requested actions.
- State which messages appear to need a reply.
- Do not invent details that are not present.
- Keep the entire response under 300 words.

EMAILS:
{formatted_emails}
""".strip()

    try:
        summary = _ollama_text(
            prompt,
            timeout=45,
            num_predict=400,
        )
    except Exception as exc:
        summary_lines = [
            f"I found {len(emails)} recent email"
            f"{'s' if len(emails) != 1 else ''}:"
        ]

        for email in emails:
            subject = email.get("subject") or "(No subject)"
            sender = email.get("from") or "Unknown sender"
            snippet = email.get("snippet") or "No preview available."

            summary_lines.append(
                f"- {subject} from {sender}: {snippet}"
            )

        summary = "\n".join(summary_lines)

        print(
            "[GMAIL SUMMARY] Ollama summarization failed; "
            f"using fallback: {type(exc).__name__}: {exc}"
        )

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