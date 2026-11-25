"""Conversation use cases. Knows nothing about HTTP, Supabase or Anthropic specifics."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from services.llm import ChatModel, Role, Turn

TITLE_MAX_CHARS = 60


class Conversation(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class Message(BaseModel):
    id: int
    role: Role
    content: str
    created_at: datetime


class ChatStore(Protocol):
    """Persistence for the *current user's* conversations (ownership is the store's job)."""

    def list_conversations(self) -> list[Conversation]: ...

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        """Raises NotFoundError if it doesn't exist or belongs to someone else."""
        ...

    def create_conversation(self, title: str) -> Conversation: ...

    def delete_conversation(self, conversation_id: UUID) -> None:
        """Raises NotFoundError if it doesn't exist or belongs to someone else."""
        ...

    def list_messages(self, conversation_id: UUID, limit: int | None = None) -> list[Message]:
        """Oldest first. With `limit`, only the most recent `limit` messages."""
        ...

    def add_exchange(
        self, conversation_id: UUID, user_text: str, assistant_text: str, model: str
    ) -> None:
        """Store a question and its answer together (both or neither)."""
        ...


@dataclass(frozen=True)
class ChatResult:
    conversation_id: UUID
    reply: str


def make_title(prompt: str) -> str:
    """First line of the prompt, whitespace collapsed, cut to TITLE_MAX_CHARS."""
    first_line = prompt.strip().splitlines()[0] if prompt.strip() else ""
    title = re.sub(r"\s+", " ", first_line).strip()
    if len(title) > TITLE_MAX_CHARS:
        title = title[: TITLE_MAX_CHARS - 1].rstrip() + "…"
    return title or "Nueva conversación"


def to_turns(messages: Sequence[Message], prompt: str) -> list[Turn]:
    return [Turn(m.role, m.content) for m in messages] + [Turn("user", prompt)]


class ChatService:
    def __init__(self, store: ChatStore, model: ChatModel, history_limit: int) -> None:
        self._store = store
        self._model = model
        self._history_limit = history_limit

    def send(self, prompt: str, conversation_id: UUID | None) -> ChatResult:
        if conversation_id is None:
            history: list[Message] = []
        else:
            self._store.get_conversation(conversation_id)  # fail fast: 404 before paying
            history = self._store.list_messages(conversation_id, limit=self._history_limit)

        reply = self._model.reply(to_turns(history, prompt))

        # A new conversation is only created once there is an answer to store,
        # so failed first attempts don't leave empty conversations behind.
        if conversation_id is None:
            conversation_id = self._store.create_conversation(make_title(prompt)).id
        self._store.add_exchange(conversation_id, prompt, reply, self._model.name)
        return ChatResult(conversation_id=conversation_id, reply=reply)
