"""Supabase adapter: Auth (who is the user) and PostgREST (their conversations).

Every request carries the user's own access token, so the database's Row Level
Security policies decide what each user can see — the backend holds no admin key.
"""

from dataclasses import dataclass
import logging
from typing import Any
from uuid import UUID

import httpx
from pydantic import TypeAdapter

from config import Settings
from errors import AppError, AuthRequiredError, NotFoundError
from services.conversations import Conversation, Message

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
CONVERSATION_LIST_LIMIT = 100
MESSAGE_LIST_LIMIT = 1000

_CONVERSATION_FIELDS = "id,title,created_at,updated_at"
_MESSAGE_FIELDS = "id,role,content,created_at"
_conversations = TypeAdapter(list[Conversation])
_messages = TypeAdapter(list[Message])


class StorageError(AppError):
    status_code = 502
    message = "No se pudieron cargar o guardar tus conversaciones. Inténtalo de nuevo."


class StorageNotConfiguredError(AppError):
    status_code = 503
    message = "El almacenamiento de chats no está configurado. Contacta al administrador."


@dataclass(frozen=True)
class User:
    id: UUID
    email: str | None


def new_http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS)


class _SupabaseClient:
    # Statuses that mean "the session is invalid or expired" for this API.
    _session_error_statuses: frozenset[int] = frozenset({401})

    def __init__(self, http: httpx.Client, settings: Settings, access_token: str) -> None:
        if not settings.supabase_url or not settings.supabase_publishable_key:
            raise StorageNotConfiguredError
        self._http = http
        self._base_url = settings.supabase_url
        self._headers = {
            "apikey": settings.supabase_publishable_key,
            "Authorization": f"Bearer {access_token}",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        try:
            response = self._http.request(
                method, f"{self._base_url}{path}", params=params, json=json, headers=headers
            )
        except httpx.HTTPError as exc:
            logger.warning("Could not reach Supabase: %s", exc)
            raise StorageError from exc

        if response.status_code in self._session_error_statuses:
            logger.info(
                "Supabase rejected the session (%s): %s", response.status_code, response.text
            )
            raise AuthRequiredError
        if response.is_error:
            logger.error(
                "Supabase error %s on %s %s: %s", response.status_code, method, path, response.text
            )
            raise StorageError
        return response.json() if response.content else None


class SupabaseAuth(_SupabaseClient):
    # Supabase Auth answers 403 (bad_jwt) for some invalid tokens.
    _session_error_statuses = frozenset({401, 403})

    def get_user(self) -> User:
        """Validate the access token with Supabase Auth (also catches revoked sessions)."""
        data = self._request("GET", "/auth/v1/user")
        return User(id=UUID(data["id"]), email=data.get("email"))


class SupabaseChatStore(_SupabaseClient):
    """ChatStore backed by the `conversations` and `messages` tables."""

    def list_conversations(self) -> list[Conversation]:
        rows = self._request(
            "GET",
            "/rest/v1/conversations",
            params={
                "select": _CONVERSATION_FIELDS,
                "order": "updated_at.desc",
                "limit": str(CONVERSATION_LIST_LIMIT),
            },
        )
        return _conversations.validate_python(rows)

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        rows = self._request(
            "GET",
            "/rest/v1/conversations",
            params={"select": _CONVERSATION_FIELDS, "id": f"eq.{conversation_id}"},
        )
        conversations = _conversations.validate_python(rows)
        if not conversations:
            raise NotFoundError
        return conversations[0]

    def create_conversation(self, title: str) -> Conversation:
        rows = self._request(
            "POST",
            "/rest/v1/conversations",
            params={"select": _CONVERSATION_FIELDS},
            json={"title": title},
            prefer="return=representation",
        )
        return _conversations.validate_python(rows)[0]

    def delete_conversation(self, conversation_id: UUID) -> None:
        rows = self._request(
            "DELETE",
            "/rest/v1/conversations",
            params={"id": f"eq.{conversation_id}", "select": "id"},
            prefer="return=representation",
        )
        if not rows:
            raise NotFoundError

    def list_messages(self, conversation_id: UUID, limit: int | None = None) -> list[Message]:
        # Newest first so `limit` keeps the most recent ones, then flip to chronological.
        rows = self._request(
            "GET",
            "/rest/v1/messages",
            params={
                "select": _MESSAGE_FIELDS,
                "conversation_id": f"eq.{conversation_id}",
                "order": "created_at.desc,id.desc",
                "limit": str(limit or MESSAGE_LIST_LIMIT),
            },
        )
        return list(reversed(_messages.validate_python(rows)))

    def add_exchange(
        self, conversation_id: UUID, user_text: str, assistant_text: str, model: str
    ) -> None:
        # One bulk insert = one SQL statement, so both rows are stored or neither is.
        # `columns` is explicit: PostgREST would otherwise take the keys of the first row.
        # `user_id` is left out on purpose: the database fills it with auth.uid().
        rows = [
            {"conversation_id": str(conversation_id), "role": role, "content": text, "model": m}
            for role, text, m in (("user", user_text, None), ("assistant", assistant_text, model))
        ]
        self._request(
            "POST",
            "/rest/v1/messages",
            params={"columns": "conversation_id,role,content,model"},
            json=rows,
            prefer="return=minimal",
        )
