from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
import uuid
from email.utils import parseaddr
from dataclasses import dataclass
from typing import Any

from ai.ollama_client import chat_with_ollama
from gmail_tools.gmail_service import (
    GmailAuthError,
    GmailError,
    GmailValidationError,
    archive_email,
    create_email_draft,
    create_reply_draft,
    get_draft,
    get_email,
    get_latest_email,
    mark_email_read,
    mark_email_unread,
    search_drafts,
    search_emails,
    send_draft,
    send_email,
    update_draft,
)

LOGGER = logging.getLogger(__name__)
MAX_RESULTS = 10
PENDING_TTL_SECONDS = 15 * 60

@dataclass
class PendingAction:
    action: str
    arguments: dict[str, Any]
    preview: dict[str, Any]
    created_at: float

_PENDING: dict[str, PendingAction] = {}
_PENDING_LOCK = threading.Lock()
_LAST_EMAILS: list[dict[str, Any]] = []
_LAST_DRAFT: dict[str, Any] | None = None


def _clean_pending() -> None:
    now = time.time()
    with _PENDING_LOCK:
        expired = [k for k, v in _PENDING.items() if now - v.created_at > PENDING_TTL_SECONDS]
        for key in expired:
            _PENDING.pop(key, None)


def _json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Ollama did not return JSON")
    return json.loads(match.group(0))


def _plan_with_ollama(command: str) -> dict[str, Any]:
    prompt = f"""
You are ALFRED's Gmail intent parser. Convert the user's request into exactly one JSON object.
Allowed actions: list, search, list_drafts, search_drafts, read_latest, read_selected, summarize, draft, reply_draft, update_draft, send, send_draft, mark_read, mark_unread, archive, help.
Return keys: action, query, max_results, message_id, draft_id, to, cc, bcc, subject, body.
Use Gmail search syntax in query. Never invent an email address, message ID, draft ID, subject, or body.
For references such as "that email", leave message_id null. For "send it", use send_draft with draft_id null. Use list_drafts or search_drafts for saved Gmail drafts.
Use list for recent/unread listing and summarize for briefings. Default max_results to 5.
Words such as latest, newest, last, recent, and number words control max_results only.
Never put latest, newest, last, recent, or a requested count into the Gmail query.
Examples:
- "summarize my unread inbox" -> action summarize, query "in:inbox is:unread", max_results 5
- "summarize my last 5 emails" -> action summarize, query "in:inbox", max_results 5
- "summarize my five newest emails" -> action summarize, query "in:inbox", max_results 5
- "read my latest email" -> action read_latest, query "in:inbox", max_results 1
User request: {command}
""".strip()
    result = chat_with_ollama(prompt, timeout=25, num_predict=280, temperature=0.0)
    return _json_from_text(str(result.get("content") or ""))



_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _requested_count(command: str, default: int = 5) -> int:
    lower = command.lower()

    digit_match = re.search(r"\b(10|[1-9])\b", lower)
    if digit_match:
        return min(int(digit_match.group(1)), MAX_RESULTS)

    for word, value in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", lower):
            return min(value, MAX_RESULTS)

    return default


def _is_simple_summary_request(command: str) -> bool:
    lower = command.lower().strip()

    return bool(
        re.fullmatch(
            r"(?:please\s+)?summari[sz]e\s+(?:my\s+)?"
            r"(?:(?:last|latest|newest|most recent)\s+)?"
            r"(?:(?:[1-9]|10|one|two|three|four|five|six|seven|eight|nine|ten)\s+)?"
            r"(?:unread\s+)?(?:emails?|inbox)"
            r"(?:\s+please)?[.!?]?",
            lower,
        )
    )


def _simple_summary_plan(command: str) -> dict[str, Any]:
    lower = command.lower()
    query = "in:inbox"

    if "unread" in lower:
        query += " is:unread"

    return {
        "action": "summarize",
        "query": query,
        "max_results": _requested_count(command),
    }


def _is_latest_read_request(command: str) -> bool:
    lower = command.lower().strip()

    return bool(
        re.fullmatch(
            r"(?:please\s+)?read\s+(?:my\s+)?"
            r"(?:latest|newest|most recent)\s+(?:email|message)"
            r"(?:\s+please)?[.!?]?",
            lower,
        )
    )


def _sanitize_query(query: str, command: str) -> str:
    """Keep natural ordering/count words out of Gmail's search query."""
    value = str(query or "").strip()

    invalid_natural_terms = {
        "latest",
        "newest",
        "last",
        "most recent",
        "five newest",
        "five latest",
        "last five",
    }

    if not value or any(term in value.lower() for term in invalid_natural_terms):
        value = "in:inbox"

    # A plain summary/list request should not become a full-text Gmail search.
    lower = command.lower()
    has_real_filter = any(
        token in lower
        for token in (
            " from ",
            " subject ",
            " about ",
            "has:attachment",
            "after:",
            "before:",
            "newer_than:",
            "older_than:",
        )
    )

    if (
        ("summar" in lower or "read my latest" in lower)
        and not has_real_filter
    ):
        value = "in:inbox"

    if "unread" in lower and "is:unread" not in value:
        value += " is:unread"

    return re.sub(r"\s+", " ", value).strip()



def _fallback_plan(command: str) -> dict[str, Any]:
    lower = command.lower().strip()
    count = _requested_count(command)
    query = "in:inbox"
    if "unread" in lower:
        query += " is:unread"
    sender = re.search(r"(?:from|by)\s+([\w.+-]+@[\w.-]+|[A-Z][\w .'-]+)", command)
    if sender:
        query += f" from:{sender.group(1).strip()}"
    if "draft" in lower and any(x in lower for x in ["show", "list", "find", "search"]):
        action = "search_drafts" if any(x in lower for x in ["find", "search", "about", "subject"]) else "list_drafts"
        query = re.sub(r"^(?:show|list|find|search)\s+(?:my\s+)?drafts?(?:\s+(?:for|about|with|matching))?\s*", "", command, flags=re.I).strip()
    elif "summar" in lower or "brief" in lower or "needs my attention" in lower:
        action = "summarize"
    elif any(x in lower for x in ["draft", "compose", "write an email"]):
        action = "draft"
    elif "reply" in lower:
        action = "reply_draft"
    elif "send" in lower:
        action = "send_draft" if any(x in lower for x in ["it", "draft"]) else "send"
    elif "archive" in lower:
        action = "archive"
    elif "mark" in lower and "unread" in lower:
        action = "mark_unread"
    elif "mark" in lower and "read" in lower:
        action = "mark_read"
    elif "read" in lower and any(x in lower for x in ["latest", "newest", "most recent"]):
        action = "read_latest"
    elif "read" in lower:
        action = "read_selected"
    elif any(x in lower for x in ["search", "find", "about", "from:", "subject:"]):
        action = "search"
    else:
        action = "list"
    return {"action": action, "query": query, "max_results": count}



def _structured_ui_plan(command: str) -> dict[str, Any] | None:
    prefix = "__ALFRED_GMAIL_DRAFT_UPDATE__"
    if not command.startswith(prefix):
        return None
    try:
        payload = json.loads(command[len(prefix):])
    except json.JSONDecodeError as exc:
        raise GmailValidationError("The draft changes were not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise GmailValidationError("The draft changes were invalid.")
    return {
        "action": "update_draft",
        "draft_id": payload.get("draft_id"),
        "to": payload.get("to"),
        "cc": payload.get("cc"),
        "bcc": payload.get("bcc"),
        "subject": payload.get("subject"),
        "body": payload.get("body"),
        "query": "",
        "max_results": 1,
    }


def _plan(command: str) -> dict[str, Any]:
    structured = _structured_ui_plan(command)
    if structured is not None:
        return structured

    # These common inbox commands are intentionally deterministic. They should
    # not depend on a small model correctly translating words like "last,"
    # "newest," or "five" into Gmail search syntax.
    if _is_simple_summary_request(command):
        return _simple_summary_plan(command)

    if _is_latest_read_request(command):
        return {
            "action": "read_latest",
            "query": "in:inbox",
            "max_results": 1,
        }

    try:
        plan = _plan_with_ollama(command)
    except Exception as exc:
        LOGGER.warning("Gmail intent parse fell back: %s", exc)
        plan = _fallback_plan(command)

    plan["action"] = str(plan.get("action") or "help").lower()

    try:
        requested_max = int(plan.get("max_results") or _requested_count(command))
    except (TypeError, ValueError):
        requested_max = _requested_count(command)

    plan["max_results"] = min(max(requested_max, 1), MAX_RESULTS)
    plan["query"] = _sanitize_query(
        str(plan.get("query") or "in:inbox"),
        command,
    )

    return plan


def _remember(emails: list[dict[str, Any]]) -> None:
    global _LAST_EMAILS
    _LAST_EMAILS = emails[:MAX_RESULTS]


def _resolve_message_id(plan: dict[str, Any]) -> str | None:
    explicit = str(plan.get("message_id") or "").strip()
    if explicit:
        return explicit
    return str(_LAST_EMAILS[0].get("id")) if _LAST_EMAILS else None



def _clean_sender_name(value: str | None) -> str:
    """Return a human-friendly sender name without exposing the email address."""
    raw = str(value or "").strip()
    if not raw:
        return "Unknown sender"

    display_name, email_address = parseaddr(raw)
    name = display_name.strip().strip('"').strip()

    if not name and email_address:
        local_part = email_address.split("@", 1)[0]
        name = re.sub(r"[._-]+", " ", local_part).strip().title()

    replacements = {
        "Capital One | Quicksilver": "Capital One",
        "Amazon.com": "Amazon",
        "Amazon Marketplace": "Amazon",
        "AMAZON MKTPLACE PMTS": "Amazon",
        "Supercell": "Supercell",
    }

    return replacements.get(name, name or "Unknown sender")


def _clean_email_text(value: str | None, limit: int = 700) -> str:
    """Remove invisible formatting noise and compress email preview text."""
    text = unicodedata.normalize("NFKC", str(value or ""))

    text = "".join(
        char
        for char in text
        if unicodedata.category(char) not in {"Cf", "Cc"}
        or char in {"\n", "\t"}
    )

    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip() + "…"

    return text


def _human_count(count: int, noun: str) -> str:
    return f"{count} {noun if count == 1 else noun + 's'}"



def _format_list(emails: list[dict[str, Any]]) -> str:
    if not emails:
        return "I checked, but I couldn't find any emails matching that."

    lines = [
        f"I found {_human_count(len(emails), 'email')}:"
    ]

    for index, email in enumerate(emails, 1):
        sender = _clean_sender_name(email.get("from"))
        subject = str(email.get("subject") or "(No subject)").strip()
        preview = _clean_email_text(
            email.get("snippet") or email.get("body"),
            limit=180,
        )
        date = str(email.get("date") or "").strip()

        lines.append(
            "\n".join(
                part
                for part in [
                    f"{index}. {subject}",
                    f"From {sender}" if sender else "",
                    date,
                    preview,
                ]
                if part
            )
        )

    return "\n\n".join(lines)


def _summarize(emails: list[dict[str, Any]]) -> str:
    if not emails:
        return "Looks clear. I couldn't find anything matching that."

    source_items = []

    for index, email in enumerate(emails, 1):
        sender = _clean_sender_name(email.get("from"))
        subject = _clean_email_text(email.get("subject"), limit=180)
        preview = _clean_email_text(
            email.get("snippet") or email.get("body"),
            limit=500,
        )

        source_items.append(
            "\n".join(
                [
                    f"Email {index}",
                    f"Sender: {sender}",
                    f"Subject: {subject or '(No subject)'}",
                    f"Preview: {preview or 'No useful preview available.'}",
                ]
            )
        )

    source = "\n\n---\n\n".join(source_items)

    prompt = f"""
You are ALFRED, Kaylee's personal assistant.

Briefly summarize these emails like a helpful person who just checked the inbox.

Rules:
- Write one short bullet per email.
- Keep each bullet to about 8-18 words.
- Be specific and descriptive.
- Use the sender's friendly name only when it helps.
- Never include an email address.
- Never repeat the subject line word-for-word unless it is already natural.
- Remove filler, tracking text, invisible characters, greetings, and legal text.
- Mention useful amounts, dates, deadlines, shipments, approvals, requests, or next steps.
- Group obviously related emails when that makes the result shorter.
- Sound casual and human.
- Do not say "This email is about," "The sender says," or "You received an email."
- Do not add facts that are not present.
- Return only the bullets, with no heading or introduction.

Examples:
- Amazon refunded $53.85 to your Capital One card.
- Six items from your Amazon order have shipped.
- Supercell has your requested account data ready.
- Version 2 of the project is ready for review.
- Your professor moved tomorrow's lecture to 2 PM.

EMAILS:
{source}
""".strip()

    try:
        result = chat_with_ollama(
            prompt,
            timeout=35,
            num_predict=260,
            temperature=0.2,
        )
        summary = str(result.get("content") or "").strip()

        if summary:
            return summary

    except Exception as exc:
        LOGGER.warning("Gmail summary fallback: %s", exc)

    fallback_lines = []

    for email in emails:
        sender = _clean_sender_name(email.get("from"))
        subject = _clean_email_text(email.get("subject"), limit=120)
        preview = _clean_email_text(
            email.get("snippet") or email.get("body"),
            limit=160,
        )

        if preview:
            fallback_lines.append(
                f"- {sender}: {preview}"
            )
        else:
            fallback_lines.append(
                f"- {sender}: {subject or 'No useful preview available.'}"
            )

    return "\n".join(fallback_lines)


def _confirmation(
    action: str,
    arguments: dict[str, Any],
    preview: dict[str, Any],
    response: str,
    *,
    title: str = "Ready to send?",
    confirm_label: str = "Send email",
    cancel_label: str = "Go back",
    note: str = "Nothing will be sent until you confirm.",
) -> dict[str, Any]:
    _clean_pending()
    token = uuid.uuid4().hex

    with _PENDING_LOCK:
        _PENDING[token] = PendingAction(
            action,
            arguments,
            preview,
            time.time(),
        )

    return {
        "type": "email_confirmation",
        "response": response,
        "overview": response,
        "requires_confirmation": True,
        "confirmation": {
            "token": token,
            "action": action,
            "title": title,
            "confirm_label": confirm_label,
            "cancel_label": cancel_label,
            "note": note,
            "preview": preview,
        },
    }


def handle_gmail_confirmation(
    token: str,
    confirmed: bool,
) -> dict[str, Any]:
    _clean_pending()

    with _PENDING_LOCK:
        pending = _PENDING.pop(token, None)

    if not pending:
        return {
            "type": "email_error",
            "response": (
                "That send confirmation expired. "
                "Ask me to send the draft again and I’ll bring it back up."
            ),
            "requires_confirmation": False,
        }

    if not confirmed:
        return {
            "type": "email_cancelled",
            "response": "No problem. I left the email as-is and didn’t send anything.",
            "draft": pending.preview if pending.action in {"send", "send_draft"} else None,
            "requires_confirmation": False,
        }

    try:
        if pending.action == "send":
            result = send_email(**pending.arguments)
            recipient = pending.preview.get("to") or "the recipient"

            return {
                "type": "email_sent",
                "response": f"Done. Your email is on its way to {recipient}.",
                "sent_email": result,
                "email": {
                    "to": pending.preview.get("to"),
                    "subject": pending.preview.get("subject"),
                    "body": pending.preview.get("body"),
                },
                "requires_confirmation": False,
            }

        if pending.action == "send_draft":
            result = send_draft(pending.arguments["draft_id"])
            recipient = pending.preview.get("to") or "the recipient"

            return {
                "type": "email_sent",
                "response": f"Done. I sent the draft to {recipient}.",
                "sent_email": result,
                "email": {
                    "to": pending.preview.get("to"),
                    "subject": pending.preview.get("subject"),
                    "body": pending.preview.get("body"),
                },
                "requires_confirmation": False,
            }

        if pending.action == "archive":
            result = archive_email(pending.arguments["message_id"])

            return {
                "type": "email_updated",
                "response": (
                    f"Done. I archived “{pending.preview.get('subject')}.”"
                ),
                "email_result": result,
                "requires_confirmation": False,
            }

    except GmailError as exc:
        return {
            "type": "email_error",
            "response": (
                f"I couldn’t finish that Gmail action: {exc} "
                "Nothing else was changed."
            ),
            "requires_confirmation": False,
        }

    return {
        "type": "email_error",
        "response": "I can’t complete that Gmail action anymore.",
        "requires_confirmation": False,
    }


def handle_gmail_command(command: str) -> dict[str, Any]:
    global _LAST_DRAFT
    if not command.strip():
        return {"type": "email_error", "response": "What would you like me to do with your email?", "requires_confirmation": False}
    try:
        plan = _plan(command)
        action = plan["action"]
        if action in {"list", "search"}:
            emails = search_emails(plan["query"], max_results=plan["max_results"])
            _remember(emails)
            return {"type": "email_list", "response": _format_list(emails), "emails": emails, "requires_confirmation": False}
        if action in {"list_drafts", "search_drafts"}:
            query = str(plan.get("query") or "").strip()
            drafts = search_drafts(query, max_results=plan["max_results"])
            if drafts:
                _LAST_DRAFT = drafts[0]
            return {
                "type": "email_drafts",
                "response": (
                    f"I found {_human_count(len(drafts), 'draft')}."
                    if drafts else "I checked your drafts, but nothing matched that search."
                ),
                "drafts": drafts,
                "emails": drafts,
                "requires_confirmation": False,
            }
        if action == "summarize":
            emails = search_emails(plan["query"], max_results=plan["max_results"])
            _remember(emails)
            summary = _summarize(emails)
            return {"type": "email_summary", "response": summary, "summary": summary, "emails": emails, "requires_confirmation": False}
        if action == "read_latest":
            email = get_latest_email(plan["query"], mark_as_read=True)

            if not email:
                return {
                    "type": "email_summary",
                    "response": "I checked, but I couldn’t find a recent email.",
                    "summary": "I checked, but I couldn’t find a recent email.",
                    "email": None,
                    "emails": [],
                    "requires_confirmation": False,
                }

            _remember([email])
            summary = _summarize([email])

            return {
                "type": "email_summary",
                "response": summary,
                "summary": summary,
                "email": email,
                "emails": [email],
                "requires_confirmation": False,
            }
        if action == "read_selected":
            message_id = _resolve_message_id(plan)
            if not message_id:
                return {"type": "email_missing_fields", "response": "Pull up the email first, then ask me to read it.", "requires_confirmation": False}
            email = get_email(message_id, mark_as_read=True)
            _remember([email])
            return {"type": "email", "response": email.get("body") or email.get("snippet"), "email": email, "requires_confirmation": False}
        if action in {"mark_read", "mark_unread"}:
            message_id = _resolve_message_id(plan)
            if not message_id:
                return {"type": "email_missing_fields", "response": "Pull up the email first so I know which one you mean.", "requires_confirmation": False}
            result = mark_email_read(message_id) if action == "mark_read" else mark_email_unread(message_id)
            return {"type": "email_updated", "response": f"Done, I marked it as {'read' if action == 'mark_read' else 'unread'}.", "email_result": result, "requires_confirmation": False}
        if action == "archive":
            message_id = _resolve_message_id(plan)
            if not message_id:
                return {"type": "email_missing_fields", "response": "Pull up the email first so I know which one to archive.", "requires_confirmation": False}
            email = get_email(message_id)
            return _confirmation("archive", {"message_id": message_id}, {"subject": email.get("subject"), "from": email.get("from")}, f"Archive “{email.get('subject')}” from {_clean_sender_name(email.get('from'))}?")
        if action == "draft":
            missing = [x for x in ("to", "subject", "body") if not str(plan.get(x) or "").strip()]
            if missing:
                return {"type": "email_missing_fields", "response": "I’m missing " + ", ".join(missing) + " before I can do that.", "missing_fields": missing, "draft": plan, "requires_confirmation": False}
            draft = create_email_draft(to=plan["to"], subject=plan["subject"], body=plan["body"], cc=plan.get("cc"), bcc=plan.get("bcc"))
            _LAST_DRAFT = draft
            return {
                "type": "email_draft",
                "response": (
                    "I drafted that for you. Give it a quick look, "
                    "then send it when you’re ready."
                ),
                "draft": draft,
                "next_action": {
                    "type": "send_draft",
                    "label": "Review and send",
                },
                "requires_confirmation": False,
            }
        if action == "update_draft":
            draft_id = str(plan.get("draft_id") or (_LAST_DRAFT or {}).get("draft_id") or "").strip()
            missing = [x for x in ("draft_id", "to", "subject", "body") if not str((draft_id if x == "draft_id" else plan.get(x)) or "").strip()]
            if missing:
                return {"type": "email_missing_fields", "response": "I’m missing " + ", ".join(missing) + " before I can save the draft.", "missing_fields": missing, "draft": plan, "requires_confirmation": False}
            draft = update_draft(
                draft_id,
                to=str(plan.get("to") or ""),
                cc=str(plan.get("cc") or "").strip() or None,
                bcc=str(plan.get("bcc") or "").strip() or None,
                subject=str(plan.get("subject") or ""),
                body=str(plan.get("body") or ""),
            )
            _LAST_DRAFT = draft
            return {
                "type": "email_draft",
                "response": "Done. I saved those changes to the Gmail draft.",
                "draft": draft,
                "next_action": {"type": "send_draft", "label": "Review and send"},
                "requires_confirmation": False,
            }
        if action == "reply_draft":
            message_id = _resolve_message_id(plan)
            body = str(plan.get("body") or "").strip()
            if not message_id or not body:
                return {"type": "email_missing_fields", "response": "I need the email and what you want to say before I can draft the reply.", "requires_confirmation": False}
            draft = create_reply_draft(message_id=message_id, body=body)
            _LAST_DRAFT = draft
            return {
                "type": "email_draft",
                "response": (
                    "I drafted the reply. Take a look, and I’ll send it "
                    "once you confirm."
                ),
                "draft": draft,
                "next_action": {
                    "type": "send_draft",
                    "label": "Review and send",
                },
                "requires_confirmation": False,
            }
        if action == "send_draft":
            draft_id = str(plan.get("draft_id") or (_LAST_DRAFT or {}).get("draft_id") or "").strip()
            if not draft_id:
                return {"type": "email_missing_fields", "response": "I couldn’t find a recent draft to send.", "requires_confirmation": False}
            preview = get_draft(draft_id)
            _LAST_DRAFT = preview
            recipient = preview.get("to") or "the recipient"

            return _confirmation(
                "send_draft",
                {"draft_id": draft_id},
                preview,
                f"Everything looks ready. Want me to send this to {recipient}?",
                title="Review before sending",
                confirm_label="Send email",
                cancel_label="Keep as draft",
                note="I’ll keep the draft saved if you decide not to send it.",
            )
        if action == "send":
            missing = [x for x in ("to", "subject", "body") if not str(plan.get(x) or "").strip()]
            if missing:
                return {"type": "email_missing_fields", "response": "I’m missing " + ", ".join(missing) + " before I can do that.", "missing_fields": missing, "draft": plan, "requires_confirmation": False}
            args = {
                key: plan.get(key)
                for key in ("to", "subject", "body", "cc", "bcc")
            }

            return _confirmation(
                "send",
                args,
                args,
                f"I’ve got the email ready for {plan['to']}. "
                "Give it one last look before I send it.",
                title="Review before sending",
                confirm_label="Send email",
                cancel_label="Go back",
                note="Nothing will be sent until you click Send email.",
            )
        return {"type": "email_help", "response": "I can check your inbox, search saved drafts, edit draft details, draft replies, send messages, and clean things up.", "requires_confirmation": False}
    except (GmailAuthError, GmailValidationError, GmailError) as exc:
        LOGGER.warning("Gmail command failed: %s", exc)
        return {"type": "email_error", "response": str(exc), "requires_confirmation": False}
    except Exception:
        LOGGER.exception("Unexpected Gmail command failure")
        return {"type": "email_error", "response": "I hit a problem with that request, but nothing was sent or changed.", "requires_confirmation": False}