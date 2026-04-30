import json
import re
import uuid

from django.conf import settings

from core.models import ChatMessage, ChatSession

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def parse_history(raw_value: str) -> list[dict]:
    value = (raw_value or "").strip()
    if not value:
        return []
    try:
        payload = json.loads(value)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    normalized: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    if settings.LLM_HISTORY_TURNS > 0:
        normalized = normalized[-settings.LLM_HISTORY_TURNS :]
    return normalized


def normalize_session_id(value: str) -> str:
    candidate = (value or "").strip()
    if SESSION_ID_RE.match(candidate):
        return candidate
    return ""


def get_or_create_chat_session(session_id: str, language: str) -> tuple[ChatSession, str]:
    normalized = normalize_session_id(session_id) or uuid.uuid4().hex
    session, _ = ChatSession.objects.get_or_create(
        session_id=normalized,
        defaults={"language": language or ""},
    )
    if language and session.language != language:
        session.language = language
        session.save(update_fields=["language", "updated_at"])
    return session, normalized


def load_history_from_storage(session: ChatSession) -> list[dict]:
    if settings.LLM_HISTORY_TURNS <= 0:
        rows = ChatMessage.objects.filter(session=session).values("role", "content")
        return [{"role": row["role"], "content": row["content"]} for row in rows if row["content"]]

    max_messages = max(2, settings.LLM_HISTORY_TURNS * 2)
    rows = (
        ChatMessage.objects.filter(session=session)
        .order_by("-created_at", "-id")
        .values("role", "content")[:max_messages]
    )
    return [{"role": row["role"], "content": row["content"]} for row in reversed(list(rows)) if row["content"]]


def store_chat_turn(session: ChatSession, user_text: str, assistant_text: str, language: str):
    entries = []
    if (user_text or "").strip():
        entries.append(ChatMessage(session=session, role=ChatMessage.ROLE_USER, content=user_text.strip()))
    if (assistant_text or "").strip():
        entries.append(ChatMessage(session=session, role=ChatMessage.ROLE_ASSISTANT, content=assistant_text.strip()))
    if entries:
        ChatMessage.objects.bulk_create(entries)
    if language and session.language != language:
        session.language = language
        session.save(update_fields=["language", "updated_at"])


def session_preview(session_id: str) -> str:
    latest_user = (
        ChatMessage.objects.filter(session__session_id=session_id, role=ChatMessage.ROLE_USER)
        .order_by("-created_at", "-id")
        .values_list("content", flat=True)
        .first()
    )
    latest_assistant = (
        ChatMessage.objects.filter(session__session_id=session_id, role=ChatMessage.ROLE_ASSISTANT)
        .order_by("-created_at", "-id")
        .values_list("content", flat=True)
        .first()
    )
    preview = (latest_user or latest_assistant or "").strip()
    if len(preview) > 72:
        return preview[:72].rstrip() + "..."
    return preview or "New chat"


def build_frontend_history(session: ChatSession) -> list[dict]:
    rows = (
        ChatMessage.objects.filter(session=session)
        .order_by("created_at", "id")
        .values("id", "role", "content")
    )
    items = []
    for row in rows:
        if row["role"] == ChatMessage.ROLE_USER:
            items.append(
                {
                    "query_id": f"db_user_{row['id']}",
                    "transcript": row["content"],
                    "isUser": True,
                }
            )
        elif row["role"] == ChatMessage.ROLE_ASSISTANT:
            items.append(
                {
                    "query_id": f"db_assistant_{row['id']}",
                    "llm_text": row["content"],
                    "isUser": False,
                }
            )
    return items
