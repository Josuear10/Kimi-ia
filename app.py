"""HTTP layer: authentication, request validation, routing and error responses."""

from functools import lru_cache
import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel, Field

from config import MAX_HISTORY_MESSAGES, MAX_PROMPT_CHARS, Settings, get_settings
from errors import AppError, AuthRequiredError
from services.conversations import ChatService, ChatStore, Conversation, Message
from services.llm import ChatModel, build_chat_model
from services.supabase import (
    StorageNotConfiguredError,
    SupabaseAuth,
    SupabaseChatStore,
    User,
    new_http_client,
)

logger = logging.getLogger(__name__)

PUBLIC_DIR = Path(__file__).parent / "public"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_CHARS)
    # Omit to start a new conversation.
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: UUID


class PublicConfig(BaseModel):
    supabase_url: str
    supabase_publishable_key: str


# ---------------------------------------------------------------------------
# Dependencies (overridden in tests)
# ---------------------------------------------------------------------------
SettingsDep = Annotated[Settings, Depends(get_settings)]
_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_http_client() -> httpx.Client:
    """Shared connection pool for Supabase calls."""
    return new_http_client()


@lru_cache(maxsize=1)
def get_chat_model() -> ChatModel:
    """Built on first use and reused; raises LLMNotConfiguredError if the key is missing."""
    return build_chat_model(get_settings())


def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise AuthRequiredError("Inicia sesión para usar Kiwi.")
    return credentials.credentials


AccessTokenDep = Annotated[str, Depends(get_access_token)]
HttpDep = Annotated[httpx.Client, Depends(get_http_client)]


def get_current_user(settings: SettingsDep, http: HttpDep, token: AccessTokenDep) -> User:
    return SupabaseAuth(http, settings, token).get_user()


def get_chat_store(
    settings: SettingsDep,
    http: HttpDep,
    token: AccessTokenDep,
    _user: Annotated[User, Depends(get_current_user)],  # authenticate before any DB access
) -> ChatStore:
    return SupabaseChatStore(http, settings, token)


StoreDep = Annotated[ChatStore, Depends(get_chat_store)]


def get_chat_service(
    store: StoreDep, model: Annotated[ChatModel, Depends(get_chat_model)]
) -> ChatService:
    return ChatService(store, model, history_limit=MAX_HISTORY_MESSAGES)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def public_config(settings: SettingsDep) -> PublicConfig:
    """Values the browser needs to sign in with Supabase. Both are public by design."""
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise StorageNotConfiguredError
    return PublicConfig(
        supabase_url=settings.supabase_url,
        supabase_publishable_key=settings.supabase_publishable_key,
    )


def chat(
    request: ChatRequest, service: Annotated[ChatService, Depends(get_chat_service)]
) -> ChatResponse:
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="El prompt no puede estar vacío.")
    result = service.send(prompt, request.conversation_id)
    return ChatResponse(response=result.reply, conversation_id=result.conversation_id)


def list_conversations(store: StoreDep) -> list[Conversation]:
    return store.list_conversations()


def list_messages(conversation_id: UUID, store: StoreDep) -> list[Message]:
    store.get_conversation(conversation_id)  # 404 for missing or foreign conversations
    return store.list_messages(conversation_id)


def delete_conversation(conversation_id: UUID, store: StoreDep) -> Response:
    store.delete_conversation(conversation_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
async def handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": AppError.message})


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY is not set; /api/chat will return 503.")
    if not settings.supabase_configured:
        logger.warning("SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY not set; sign-in is disabled.")

    app = FastAPI(title="Kiwi")
    app.add_api_route("/api/config", public_config, methods=["GET"])
    app.add_api_route("/api/chat", chat, methods=["POST"])
    app.add_api_route("/api/conversations", list_conversations, methods=["GET"])
    app.add_api_route(
        "/api/conversations/{conversation_id}/messages", list_messages, methods=["GET"]
    )
    app.add_api_route(
        "/api/conversations/{conversation_id}",
        delete_conversation,
        methods=["DELETE"],
        status_code=204,
    )
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(Exception, handle_unexpected_error)

    if settings.serve_frontend:
        app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="static")
    return app


# Module-level instance: entry point for uvicorn (main.py) and Vercel.
app = create_app()
