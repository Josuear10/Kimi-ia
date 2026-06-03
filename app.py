from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services.llm import get_response

app = FastAPI(title="Chat con Claude")

STATIC_DIR = Path(__file__).parent / "static"


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
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo obtener una respuesta del modelo: {exc}",
        ) from exc

    return ChatResponse(response=text)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
