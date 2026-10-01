"""WanderAI API. Sessions are in memory and disappear when the server restarts."""
from __future__ import annotations

import math
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from langchain_core.messages import AIMessage, HumanMessage
from groq import APITimeoutError, RateLimitError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(Path(__file__).with_name(".env"))
from Travel_Planner_Agent import make_groq_graph  # noqa: E402

app = FastAPI(title="WanderAI API", version="1.0.0")
app.state.stateless = False
_sessions: dict[str, list] = {}
_locks: dict[str, threading.Lock] = {}
_store_lock = threading.Lock()
_graph = None
_graph_lock = threading.Lock()

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def check_history(self):
        if len(self.history) % 2:
            raise ValueError("History must contain complete user and assistant turns.")
        for index, turn in enumerate(self.history):
            if turn.role != ("user" if index % 2 == 0 else "assistant") or not turn.content.strip():
                raise ValueError("History must alternate nonblank user and assistant turns.")
        return self

class ChatResponse(BaseModel):
    session_id: uuid.UUID
    reply: str

class ClearRequest(BaseModel):
    session_id: uuid.UUID

class ClearResponse(BaseModel):
    session_id: uuid.UUID
    cleared: bool

class HealthResponse(BaseModel):
    status: str
    provider_configured: bool

def get_graph():
    global _graph
    with _graph_lock:
        if _graph is None:
            _graph = make_groq_graph()
        return _graph

@app.get("/api/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "provider_configured": bool(os.getenv("GROQ_API_KEY", "").strip())}

def _chat(message: str, session_id: uuid.UUID) -> str:
    key = str(session_id)
    with _store_lock:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        with _store_lock:
            history = list(_sessions.get(key, []))
        # No checkpoint: add reducer appends node outputs to prior history and one new turn.
        result = get_graph().invoke({"messages": [*history, HumanMessage(content=message)]}, config={"recursion_limit": 12})
        messages = result["messages"]
        if not isinstance(messages[-1], AIMessage) or not isinstance(messages[-1].content, str) or not messages[-1].content.strip():
            raise RuntimeError("Provider returned an empty response")
        with _store_lock:
            _sessions[key] = messages
        return messages[-1].content


def _chat_stateless(message: str, history: list[ChatTurn]) -> str:
    """Use public chat turns for context when requests can reach different instances."""
    prior = [HumanMessage(content=turn.content) if turn.role == "user" else AIMessage(content=turn.content) for turn in history]
    result = get_graph().invoke({"messages": [*prior, HumanMessage(content=message)]}, config={"recursion_limit": 12})
    final = result["messages"][-1]
    if not isinstance(final, AIMessage) or not isinstance(final.content, str) or not final.content.strip():
        raise RuntimeError("Provider returned an empty response")
    return final.content

@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    message = body.message.strip()
    if not message:
        raise HTTPException(422, "Message cannot be blank.")
    session_id = body.session_id or uuid.uuid4()
    if not os.getenv("GROQ_API_KEY", "").strip() and _graph is None:
        raise HTTPException(503, "Travel planning is not configured. Set GROQ_API_KEY on the server.")
    try:
        if app.state.stateless:
            reply = await run_in_threadpool(_chat_stateless, message, body.history)
        else:
            reply = await run_in_threadpool(_chat, message, session_id)
    except RateLimitError as exc:
        raw = exc.response.headers.get("retry-after", "")
        try:
            seconds = math.ceil(float(raw))
            if not 1 <= seconds <= 86400:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            seconds = None
        detail = (f"Groq has reached a usage limit. Please retry in {seconds} seconds."
                  if seconds else "Groq has reached a usage limit. Please try again later.")
        headers = {"Retry-After": str(seconds)} if seconds else None
        raise HTTPException(429, detail, headers=headers) from None
    except APITimeoutError:
        raise HTTPException(504, "The planner timed out. Please retry in a moment.") from None
    except Exception:
        raise HTTPException(502, "The planner could not respond. Please retry in a moment.") from None
    return ChatResponse(session_id=session_id, reply=reply)

@app.post("/api/clear", response_model=ClearResponse)
async def clear(body: ClearRequest):
    if app.state.stateless:
        return ClearResponse(session_id=body.session_id, cleared=True)
    key = str(body.session_id)
    with _store_lock:
        lock = _locks.setdefault(key, threading.Lock())
    await run_in_threadpool(_clear_locked, key, lock)
    return ClearResponse(session_id=body.session_id, cleared=True)

def _clear_locked(key: str, lock: threading.Lock):
    with lock:
        with _store_lock:
            _sessions.pop(key, None)

DIST = ROOT / "frontend" / "dist"

@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "API route not found")
    if not (DIST / "index.html").exists():
        raise HTTPException(503, "Frontend build missing. Run npm install and npm run build in frontend/.")
    asset = (DIST / path).resolve()
    if path and asset.is_file() and asset.is_relative_to(DIST.resolve()):
        return FileResponse(asset)
    if path.startswith("assets/") or "." in Path(path).name:
        raise HTTPException(404, "Asset not found")
    return FileResponse(DIST / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
