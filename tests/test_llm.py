from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from config import Settings
from services.llm import (
    AnthropicChatModel,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMUnavailableError,
    Turn,
    build_chat_model,
    extract_text,
)

SETTINGS = Settings(anthropic_api_key="test-key")
REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def message(*blocks: SimpleNamespace, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeMessages:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def make_model(result: Any) -> tuple[AnthropicChatModel, FakeMessages]:
    messages = FakeMessages(result)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return AnthropicChatModel(client, SETTINGS), messages  # type: ignore[arg-type]


def status_error(cls: type[anthropic.APIStatusError], code: int) -> anthropic.APIStatusError:
    return cls(message="boom", response=httpx.Response(code, request=REQUEST), body=None)


def test_extract_text_skips_thinking_blocks() -> None:
    blocks = [SimpleNamespace(type="thinking", thinking=""), text("Hola "), text("mundo")]
    assert extract_text(blocks) == "Hola mundo"


def test_reply_sends_configured_request_and_returns_text() -> None:
    model, messages = make_model(message(text("Hola")))
    history = [Turn("user", "Hola"), Turn("assistant", "¡Hola!"), Turn("user", "Saluda")]

    assert model.reply(history) == "Hola"
    assert model.name == "claude-opus-5-5"
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["max_tokens"] == SETTINGS.max_tokens
    assert call["output_config"] == {"effort": SETTINGS.effort}
    assert call["messages"] == [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "¡Hola!"},
        {"role": "user", "content": "Saluda"},
    ]
    assert call["extra_body"] == {"fallbacks": "default"}


def test_refusal_raises_refusal_error() -> None:
    model, _ = make_model(message(stop_reason="refusal"))
    with pytest.raises(LLMRefusalError):
        model.reply([Turn("user", "x")])


def test_empty_text_raises_llm_error() -> None:
    model, _ = make_model(message(SimpleNamespace(type="thinking", thinking="")))
    with pytest.raises(LLMError):
        model.reply([Turn("user", "x")])


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (status_error(anthropic.AuthenticationError, 401), LLMNotConfiguredError),
        (status_error(anthropic.PermissionDeniedError, 403), LLMNotConfiguredError),
        (status_error(anthropic.RateLimitError, 429), LLMRateLimitError),
        (status_error(anthropic.InternalServerError, 500), LLMUnavailableError),
        (status_error(anthropic.BadRequestError, 400), LLMError),
        (anthropic.APIConnectionError(request=REQUEST), LLMUnavailableError),
        (anthropic.APITimeoutError(request=REQUEST), LLMUnavailableError),
    ],
)
def test_sdk_errors_are_translated(error: Exception, expected: type[LLMError]) -> None:
    model, _ = make_model(error)
    with pytest.raises(expected) as caught:
        model.reply([Turn("user", "x")])
    assert type(caught.value) is expected


def test_build_without_api_key_fails() -> None:
    with pytest.raises(LLMNotConfiguredError):
        build_chat_model(Settings(anthropic_api_key=None))
