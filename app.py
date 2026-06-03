import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.llm import get_response

app = FastAPI(title="Kimi")

PUBLIC_DIR = Path(__file__).parent / "public"


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    response: str


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="El prompt no puede estar vacío.")

    try:
        text = get_response(prompt)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo obtener una respuesta del modelo: {exc}",
        ) from exc

    return ChatResponse(response=text)


if not os.getenv("VERCEL"):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="static")
