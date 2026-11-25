from uuid import uuid4

import pytest

from errors import NotFoundError
from services.conversations import TITLE_MAX_CHARS, ChatService, make_title
from services.llm import LLMError, Turn
from tests.fakes import FakeChatModel, InMemoryChatStore


def make_service(
    model: FakeChatModel | None = None, history_limit: int = 40
) -> tuple[ChatService, InMemoryChatStore, FakeChatModel]:
    store, model = InMemoryChatStore(), model or FakeChatModel()
    return ChatService(store, model, history_limit), store, model


def test_first_message_creates_titled_conversation_and_stores_exchange() -> None:
    service, store, model = make_service(FakeChatModel(reply="Argentina"))

    result = service.send("¿Quién ganó el Mundial 2022?", conversation_id=None)

    conversation = store.get_conversation(result.conversation_id)
    assert conversation.title == "¿Quién ganó el Mundial 2022?"
    assert result.reply == "Argentina"
    assert [(m.role, m.content) for m in store.messages[conversation.id]] == [
        ("user", "¿Quién ganó el Mundial 2022?"),
        ("assistant", "Argentina"),
    ]
    assert store.models == ["fake-model"]
    assert model.calls == [[Turn("user", "¿Quién ganó el Mundial 2022?")]]


def test_follow_up_sends_previous_messages_as_context() -> None:
    service, store, model = make_service(FakeChatModel(reply="Lionel Messi"))
    conversation = store.add_conversation()
    store.add_exchange(conversation.id, "¿Quién ganó?", "Argentina", "m")

    service.send("¿Quién fue el mejor jugador?", conversation.id)

    assert model.calls[0] == [
        Turn("user", "¿Quién ganó?"),
        Turn("assistant", "Argentina"),
        Turn("user", "¿Quién fue el mejor jugador?"),
    ]
    assert len(store.messages[conversation.id]) == 4


def test_history_is_limited_to_most_recent_messages() -> None:
    service, store, model = make_service(history_limit=2)
    conversation = store.add_conversation()
    store.add_exchange(conversation.id, "q1", "a1", "m")
    store.add_exchange(conversation.id, "q2", "a2", "m")

    service.send("q3", conversation.id)

    assert model.calls[0] == [Turn("user", "q2"), Turn("assistant", "a2"), Turn("user", "q3")]


def test_unknown_conversation_fails_before_calling_model() -> None:
    service, _, model = make_service()

    with pytest.raises(NotFoundError):
        service.send("hola", uuid4())
    assert model.calls == []


def test_model_failure_on_first_message_leaves_no_empty_conversation() -> None:
    service, store, _ = make_service(FakeChatModel(error=LLMError()))

    with pytest.raises(LLMError):
        service.send("hola", None)
    assert store.conversations == {}


@pytest.mark.parametrize(
    ("prompt", "title"),
    [
        ("  Hola   mundo  ", "Hola mundo"),
        ("Primera línea\nsegunda línea", "Primera línea"),
        ("x" * 100, "x" * (TITLE_MAX_CHARS - 1) + "…"),
        ("   ", "Nueva conversación"),
    ],
)
def test_make_title(prompt: str, title: str) -> None:
    assert make_title(prompt) == title
    assert len(make_title(prompt)) <= TITLE_MAX_CHARS
