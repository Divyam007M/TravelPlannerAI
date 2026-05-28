import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()

from travel_agent import travel_graph, SYSTEM_PROMPT

# ── Path constants ─────────────────────────────────────────────────
# Works regardless of CWD because we use __file__ as anchor
BASE_DIR = Path(__file__).parent          # backend/
DIST_DIR = BASE_DIR.parent / "frontend" / "dist"   # frontend/dist/
SERVING_STATIC = DIST_DIR.is_dir()


# ── FastAPI app ────────────────────────────────────────────────────
app = FastAPI(
    title="WanderAI — Travel Planner API",
    description="LangGraph + Groq powered global travel planning agent",
    version="2.0.0",
    # Hide docs in production (when serving the React app)
    docs_url=None if SERVING_STATIC else "/docs",
    redoc_url=None if SERVING_STATIC else "/redoc",
)

# CORS — only needed when frontend runs on a different origin (dev mode).
# In combined/production mode, same-origin so CORS is irrelevant.
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ────────────────────────────────────────
class Message(BaseModel):
    role: str       # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []


class ChatResponse(BaseModel):
    response: str
    success: bool = True


# ── API routes (must be defined BEFORE the static catch-all) ──────
@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "WanderAI",
        "version": "2.0.0",
        "serving_ui": SERVING_STATIC,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        lc_messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for msg in req.history:
            if msg.role == "user":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content))
        lc_messages.append(HumanMessage(content=req.message))

        result = travel_graph.invoke({"messages": lc_messages})
        return ChatResponse(response=result["messages"][-1].content, success=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Serve React frontend (combined production mode) ────────────────
if SERVING_STATIC:
    # Serve hashed assets (JS, CSS, images) — long cache-friendly
    assets_dir = DIST_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Serve other static files at root (favicon, robots.txt, etc.)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """
        SPA catch-all: serve the requested file if it exists in dist/,
        otherwise always return index.html so React Router can handle routing.
        """
        requested = DIST_DIR / full_path
        if requested.is_file():
            return FileResponse(str(requested))
        return FileResponse(str(DIST_DIR / "index.html"))


# ── Dev entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"Starting WanderAI server on http://localhost:{port}")
    if SERVING_STATIC:
        print(f"Serving React UI from: {DIST_DIR}")
    else:
        print("No frontend/dist found — API-only mode (run 'npm run build' in frontend/)")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
