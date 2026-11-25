from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from app import create_app, get_chat_model, get_chat_store, get_current_user
from config import MAX_PROMPT_CHARS, Settings, get_settings
from errors import AuthRequiredError
from services.llm import LLMNotConfiguredError, LLMRateLimitError, LLMRefusalError
from services.supabase import User
from tests.fakes import FakeChatModel, InMemoryChatStore

AUTH = {"Authorization": "Bearer user-jwt"}
SETTINGS = Settings(
    anthropic_api_key="test-key",
    supabase_url="https://proj.supabase.co",
    supabase_publishable_key="sb_publishable_x",
    serve_frontend=False,
)


def make_client(
    model: FakeChatModel | None = None,
    store: InMemoryChatStore | None = None,
    settings: Settings = SETTINGS,
) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_chat_model] = lambda: model or FakeChatModel()
    app.dependency_overrides[get_chat_store] = lambda: store or InMemoryChatStore()
    return TestClient(app, raise_server_exceptions=False)


# --- /api/chat --------------------------------------------------------------
def test_chat_starts_conversation_and_returns_its_id() -> None:
    store = InMemoryChatStore()
    response = make_client(FakeChatModel(reply="**Argentina**"), store).post(
        "/api/chat", json={"prompt": "  ¿Quién ganó?  "}, headers=AUTH
    )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "**Argentina**"
    assert UUID(body["conversation_id"]) in store.conversations


def test_chat_continues_existing_conversation() -> None:
    store = InMemoryChatStore()
    conversation = store.add_conversation()

    response = make_client(store=store).post(
        "/api/chat",
        json={"prompt": "hola", "conversation_id": str(conversation.id)},
        headers=AUTH,
    )

    assert response.json()["conversation_id"] == str(conversation.id)
    assert len(store.messages[conversation.id]) == 2


def test_chat_with_unknown_conversation_returns_404() -> None:
    response = make_client().post(
        "/api/chat", json={"prompt": "hola", "conversation_id": str(uuid4())}, headers=AUTH
    )
    assert response.status_code == 404


def test_whitespace_prompt_is_rejected_without_calling_model() -> None:
    model = FakeChatModel()
    response = make_client(model).post("/api/chat", json={"prompt": "   "}, headers=AUTH)

    assert response.status_code == 400
    assert response.json() == {"detail": "El prompt no puede estar vacío."}
    assert model.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"prompt": ""},
        {"prompt": "x" * (MAX_PROMPT_CHARS + 1)},
        {"prompt": "hola", "conversation_id": "not-a-uuid"},
    ],
)
def test_invalid_payload_is_rejected(body: dict[str, str]) -> None:
    model = FakeChatModel()
    response = make_client(model).post("/api/chat", json=body, headers=AUTH)

    assert response.status_code == 422
    assert model.calls == []


@pytest.mark.parametrize(
    ("error", "status"),
    [(LLMNotConfiguredError(), 503), (LLMRateLimitError(), 429), (LLMRefusalError(), 422)],
)
def test_llm_errors_map_to_status_and_safe_message(error: Exception, status: int) -> None:
    response = make_client(FakeChatModel(error=error)).post(
        "/api/chat", json={"prompt": "hola"}, headers=AUTH
    )

    assert response.status_code == status
    assert response.json() == {"detail": error.message}  # type: ignore[attr-defined]


def test_unexpected_error_does_not_leak_internal_details() -> None:
    error = RuntimeError("secret internal detail sk-ant-123")
    response = make_client(FakeChatModel(error=error)).post(
        "/api/chat", json={"prompt": "hola"}, headers=AUTH
    )

    assert response.status_code == 500
    assert "secret" not in response.text


# --- Authentication -----------------------------------------------------------
def make_unauthenticated_client() -> TestClient:
    """Real auth/store dependencies, so a missing token is checked for real."""
    app = create_app(SETTINGS)
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_chat_model] = FakeChatModel
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/chat"),
        ("GET", "/api/conversations"),
        ("GET", f"/api/conversations/{uuid4()}/messages"),
        ("DELETE", f"/api/conversations/{uuid4()}"),
    ],
)
def test_endpoints_require_a_session(method: str, path: str) -> None:
    response = make_unauthenticated_client().request(method, path, json={"prompt": "hola"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Inicia sesión para usar Kiwi."}


def test_invalid_session_returns_401_before_touching_storage() -> None:
    def reject() -> User:
        raise AuthRequiredError

    app = create_app(SETTINGS)
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_current_user] = reject
    response = TestClient(app).get("/api/conversations", headers=AUTH)

    assert response.status_code == 401


# --- Conversations ----------------------------------------------------------
def test_list_conversations() -> None:
    store = InMemoryChatStore()
    store.add_conversation("Mundial")

    response = make_client(store=store).get("/api/conversations", headers=AUTH)

    assert response.status_code == 200
    assert [c["title"] for c in response.json()] == ["Mundial"]


def test_list_messages_of_conversation() -> None:
    store = InMemoryChatStore()
    conversation = store.add_conversation()
    store.add_exchange(conversation.id, "q", "a", "m")

    response = make_client(store=store).get(
        f"/api/conversations/{conversation.id}/messages", headers=AUTH
    )

    assert [(m["role"], m["content"]) for m in response.json()] == [
        ("user", "q"),
        ("assistant", "a"),
    ]


def test_messages_of_unknown_conversation_return_404() -> None:
    response = make_client().get(f"/api/conversations/{uuid4()}/messages", headers=AUTH)
    assert response.status_code == 404


def test_delete_conversation() -> None:
    store = InMemoryChatStore()
    conversation = store.add_conversation()
    client = make_client(store=store)

    assert client.delete(f"/api/conversations/{conversation.id}", headers=AUTH).status_code == 204
    assert client.delete(f"/api/conversations/{conversation.id}", headers=AUTH).status_code == 404


# --- Config & frontend --------------------------------------------------------
def test_public_config_exposes_only_public_supabase_values() -> None:
    response = make_client().get("/api/config")

    assert response.json() == {
        "supabase_url": "https://proj.supabase.co",
        "supabase_publishable_key": "sb_publishable_x",
    }
    assert "test-key" not in response.text


def test_public_config_without_supabase_returns_503() -> None:
    response = make_client(settings=Settings(serve_frontend=False)).get("/api/config")
    assert response.status_code == 503


def test_frontend_is_served_when_enabled() -> None:
    response = make_client(settings=Settings(serve_frontend=True)).get("/")

    assert response.status_code == 200
    assert "<title>Kiwi</title>" in response.text


def test_frontend_is_not_served_when_disabled() -> None:
    assert make_client().get("/").status_code == 404
