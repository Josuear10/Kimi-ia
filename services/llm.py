"""Chat model integration: the only module that knows about the Anthropic SDK."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import logging
from typing import Any, Literal, Protocol

import anthropic

from config import Settings
from errors import AppError

logger = logging.getLogger(__name__)


class LLMError(AppError):
    status_code = 502
    message = "No se pudo obtener una respuesta del modelo. Inténtalo de nuevo."


class LLMNotConfiguredError(LLMError):
    status_code = 503
    message = "El servicio no está configurado correctamente. Contacta al administrador."


class LLMRateLimitError(LLMError):
    status_code = 429
    message = "Hay demasiadas solicitudes. Espera unos segundos e inténtalo de nuevo."


class LLMUnavailableError(LLMError):
    status_code = 503
    message = "El modelo no está disponible en este momento. Inténtalo más tarde."


class LLMRefusalError(LLMError):
    status_code = 422
    message = "El modelo no puede responder a esta solicitud."


Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class Turn:
    role: Role
    content: str


class ChatModel(Protocol):
    @property
    def name(self) -> str: ...

    def reply(self, history: Sequence[Turn]) -> str:
        """Answer the last user turn of `history` (oldest turn first)."""
        ...


def extract_text(blocks: Iterable[Any]) -> str:
    """Join the text blocks of a response, skipping thinking and other block types."""
    return "".join(block.text for block in blocks if getattr(block, "type", None) == "text")


class AnthropicChatModel:
    def __init__(self, client: anthropic.Anthropic, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @property
    def name(self) -> str:
        return self._settings.model

    def reply(self, history: Sequence[Turn]) -> str:
        try:
            message = self._client.beta.messages.create(
                model=self._settings.model,
                max_tokens=self._settings.max_tokens,
                betas=["server-side-fallback-2026-07-01"],
                cache_control={"type": "ephemeral"},
                output_config={"effort": self._settings.effort},
                messages=[{"role": turn.role, "content": turn.content} for turn in history],
                # Not yet a named argument in the pinned SDK version.
                extra_body={"fallbacks": "default"},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            logger.error("Anthropic rejected the API key: %s", exc)
            raise LLMNotConfiguredError from exc
        except anthropic.RateLimitError as exc:
            logger.warning("Anthropic rate limit reached: %s", exc)
            raise LLMRateLimitError from exc
        except anthropic.APIConnectionError as exc:
            logger.warning("Could not reach Anthropic: %s", exc)
            raise LLMUnavailableError from exc
        except anthropic.APIStatusError as exc:
            logger.error("Anthropic API error %s: %s", exc.status_code, exc)
            if exc.status_code >= 500:
                raise LLMUnavailableError from exc
            raise LLMError from exc

        if message.stop_reason == "refusal":
            raise LLMRefusalError

        text = extract_text(message.content)
        if not text:
            logger.error("Empty response from model (stop_reason=%s)", message.stop_reason)
            raise LLMError("El modelo devolvió una respuesta vacía. Inténtalo de nuevo.")
        return text


def build_chat_model(settings: Settings) -> AnthropicChatModel:
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError
    return AnthropicChatModel(anthropic.Anthropic(api_key=settings.anthropic_api_key), settings)
