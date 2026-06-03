import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-7"
MAX_TOKENS = 400

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set.")
        _client = Anthropic(api_key=api_key)
    return _client


def get_response(user_message: str) -> str:
    message = _get_client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        cache_control={"type": "ephemeral"},
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text
