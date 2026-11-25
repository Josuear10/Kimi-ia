"""In-memory test doubles for the ChatStore and ChatModel ports."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from errors import NotFoundError
from services.conversations import Conversation, Message
from services.llm import Turn


class FakeChatModel:
    name = "fake-model"

    def __init__(self, reply: str = "Hola", error: Exception | None = None) -> None:
        self._reply = reply
        self._error = error
        self.calls: list[list[Turn]] = []

    def reply(self, history: Sequence[Turn]) -> str:
        self.calls.append(list(history))
        if self._error:
            raise self._error
        return self._reply


class InMemoryChatStore:
    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.messages: dict[UUID, list[Message]] = {}
        self.models: list[str] = []
        self._next_id = 1

    def add_conversation(self, title: str = "Chat") -> Conversation:
        return self.create_conversation(title)

    def list_conversations(self) -> list[Conversation]:
        return sorted(self.conversations.values(), key=lambda c: c.updated_at, reverse=True)

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        if conversation_id not in self.conversations:
            raise NotFoundError
        return self.conversations[conversation_id]

    def create_conversation(self, title: str) -> Conversation:
        now = datetime.now(UTC)
        conversation = Conversation(id=uuid4(), title=title, created_at=now, updated_at=now)
        self.conversations[conversation.id] = conversation
        self.messages[conversation.id] = []
        return conversation

    def delete_conversation(self, conversation_id: UUID) -> None:
        self.get_conversation(conversation_id)
        del self.conversations[conversation_id]
        del self.messages[conversation_id]

    def list_messages(self, conversation_id: UUID, limit: int | None = None) -> list[Message]:
        messages = self.messages[conversation_id]
        return messages[-limit:] if limit else list(messages)

    def add_exchange(
        self, conversation_id: UUID, user_text: str, assistant_text: str, model: str
    ) -> None:
        self.get_conversation(conversation_id)
        for role, text in (("user", user_text), ("assistant", assistant_text)):
            self.messages[conversation_id].append(
                Message(id=self._next_id, role=role, content=text, created_at=datetime.now(UTC))  # type: ignore[arg-type]
            )
            self._next_id += 1
        self.models.append(model)
