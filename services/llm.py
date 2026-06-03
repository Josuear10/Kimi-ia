import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise ValueError("ANTHROPIC_API_KEY is not set.")

client = Anthropic(api_key=api_key)
MODEL = "claude-opus-4-7"
MAX_TOKENS = 400


def get_response(user_message: str) -> str:
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        cache_control={"type": "ephemeral"},
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text
