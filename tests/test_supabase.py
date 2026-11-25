from collections.abc import Callable
import json
from uuid import UUID, uuid4

import httpx
import pytest

from config import Settings
from errors import AuthRequiredError, NotFoundError
from services.supabase import (
    StorageError,
    StorageNotConfiguredError,
    SupabaseAuth,
    SupabaseChatStore,
)

SETTINGS = Settings(supabase_url="https://proj.supabase.co", supabase_publishable_key="pk")
CONV_ID = UUID("11111111-1111-1111-1111-111111111111")
CONV_ROW = {
    "id": str(CONV_ID),
    "title": "Chat",
    "created_at": "2026-11-24T10:00:00+00:00",
    "updated_at": "2026-11-24T10:05:00+00:00",
}

Handler = Callable[[httpx.Request], httpx.Response]


def client_with(handler: Handler) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(record)), seen


def store_with(handler: Handler) -> tuple[SupabaseChatStore, list[httpx.Request]]:
    http, seen = client_with(handler)
    return SupabaseChatStore(http, SETTINGS, "user-jwt"), seen


def test_requests_carry_publishable_key_and_user_token() -> None:
    store, seen = store_with(lambda _: httpx.Response(200, json=[CONV_ROW]))

    conversations = store.list_conversations()

    assert conversations[0].id == CONV_ID
    request = seen[0]
    assert request.headers["apikey"] == "pk"
    assert request.headers["authorization"] == "Bearer user-jwt"
    assert request.url.path == "/rest/v1/conversations"
    assert request.url.params["order"] == "updated_at.desc"


def test_get_missing_conversation_raises_not_found() -> None:
    store, _ = store_with(lambda _: httpx.Response(200, json=[]))
    with pytest.raises(NotFoundError):
        store.get_conversation(uuid4())


def test_delete_missing_conversation_raises_not_found() -> None:
    store, seen = store_with(lambda _: httpx.Response(200, json=[]))
    with pytest.raises(NotFoundError):
        store.delete_conversation(CONV_ID)
    assert seen[0].method == "DELETE"
    assert seen[0].url.params["id"] == f"eq.{CONV_ID}"


def test_create_conversation_returns_inserted_row() -> None:
    store, seen = store_with(lambda _: httpx.Response(201, json=[CONV_ROW]))

    conversation = store.create_conversation("Chat")

    assert conversation.title == "Chat"
    assert json.loads(seen[0].content) == {"title": "Chat"}
    assert seen[0].headers["prefer"] == "return=representation"


def test_list_messages_returns_most_recent_in_chronological_order() -> None:
    rows = [
        {"id": 2, "role": "assistant", "content": "a", "created_at": "2026-11-24T10:00:00Z"},
        {"id": 1, "role": "user", "content": "q", "created_at": "2026-11-24T10:00:00Z"},
    ]
    store, seen = store_with(lambda _: httpx.Response(200, json=rows))

    messages = store.list_messages(CONV_ID, limit=2)

    assert [m.id for m in messages] == [1, 2]
    assert seen[0].url.params["order"] == "created_at.desc,id.desc"
    assert seen[0].url.params["limit"] == "2"


def test_add_exchange_inserts_both_rows_in_one_request() -> None:
    store, seen = store_with(lambda _: httpx.Response(201))

    store.add_exchange(CONV_ID, "q", "a", "claude-opus-5-5")

    assert len(seen) == 1
    assert seen[0].url.params["columns"] == "conversation_id,role,content,model"
    assert json.loads(seen[0].content) == [
        {"conversation_id": str(CONV_ID), "role": "user", "content": "q", "model": None},
        {
            "conversation_id": str(CONV_ID),
            "role": "assistant",
            "content": "a",
            "model": "claude-opus-5-5",
        },
    ]


def test_expired_session_raises_auth_required() -> None:
    store, _ = store_with(lambda _: httpx.Response(401, json={"message": "JWT expired"}))
    with pytest.raises(AuthRequiredError):
        store.list_conversations()


def test_database_403_is_a_storage_error_not_a_logout() -> None:
    store, _ = store_with(lambda _: httpx.Response(403, json={"code": "42501"}))
    with pytest.raises(StorageError):
        store.list_conversations()


def test_network_failure_raises_storage_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    store, _ = store_with(fail)
    with pytest.raises(StorageError):
        store.list_conversations()


def test_auth_returns_user_for_valid_token() -> None:
    user_id = uuid4()
    http, seen = client_with(
        lambda _: httpx.Response(200, json={"id": str(user_id), "email": "a@b.co"})
    )

    user = SupabaseAuth(http, SETTINGS, "user-jwt").get_user()

    assert user.id == user_id
    assert seen[0].url.path == "/auth/v1/user"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_rejects_invalid_token(status: int) -> None:
    http, _ = client_with(lambda _: httpx.Response(status, json={}))
    with pytest.raises(AuthRequiredError):
        SupabaseAuth(http, SETTINGS, "bad").get_user()


def test_missing_supabase_settings_fail_fast() -> None:
    with pytest.raises(StorageNotConfiguredError):
        SupabaseChatStore(httpx.Client(), Settings(), "jwt")
