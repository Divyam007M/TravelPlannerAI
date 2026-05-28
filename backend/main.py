import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()

# Import after env load so GROQ_API_KEY is available
from travel_agent import travel_graph, SYSTEM_PROMPT

app = FastAPI(
    title="WanderAI — Travel Planner API",
    description="LangGraph + Groq powered global travel planning agent",
    version="1.0.0",
)

# Allow all origins in dev; restrict to your Vercel URL in production
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []


class ChatResponse(BaseModel):
    response: str
    success: bool = True


@app.get("/")
def health_check():
    return {"status": "ok", "service": "WanderAI Travel Planner", "version": "1.0.0"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        # Reconstruct LangChain message history for context
        lc_messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for msg in req.history:
            if msg.role == "user":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content))
        # Add the new user message
        lc_messages.append(HumanMessage(content=req.message))

        result = travel_graph.invoke({"messages": lc_messages})
        response_text = result["messages"][-1].content
        return ChatResponse(response=response_text, success=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
