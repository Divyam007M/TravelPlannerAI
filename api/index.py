"""
Vercel serverless function — self-contained FastAPI + LangGraph travel agent.
Vercel auto-discovers Python files in api/ and serves them as serverless functions.
All /api/* requests are routed here via vercel.json rewrites.
"""
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import os
import operator
from typing import TypedDict, Annotated, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum

from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage
)
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END

# ── API Key ───────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY environment variable is not set.")

# ── LLM ──────────────────────────────────────────────────────────
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.4, api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are WanderAI — an expert global travel planner with encyclopedic knowledge of every city, country, and destination on Earth.

You can answer detailed questions about ANY city in the world: attractions, culture, food, local transport, safety tips, visa requirements, local etiquette, hidden gems, neighborhoods, shopping, nightlife, and more.

You have access to two specialized tools:
• estimate_budget — for precise cost breakdowns by travel class
• get_packing_list — for curated packing recommendations

Guidelines:
- Be enthusiastic, friendly, and thorough
- Use emojis tastefully to make responses engaging
- Always personalize advice based on the user's context (budget, group type, duration)
- For any city worldwide, draw on your training knowledge — never say you don't know a popular destination
- Structure longer responses with clear headers and bullet points
- When estimating budgets, always mention local currency alongside USD"""

# ── Tools ─────────────────────────────────────────────────────────
@tool
def estimate_budget(city: str, days: int, travel_class: str, travelers: int = 1) -> str:
    """Estimates travel budget for any city worldwide."""
    base_costs = {
        "budget":  {"hotel": 25,  "food": 15,  "activities": 10, "transport": 8},
        "mid":     {"hotel": 90,  "food": 50,  "activities": 40, "transport": 20},
        "luxury":  {"hotel": 280, "food": 130, "activities": 100, "transport": 60},
    }
    key = travel_class.lower()
    for alias, mapped in [("low","budget"),("economy","budget"),("backpacker","budget"),
                           ("mid-range","mid"),("moderate","mid"),("standard","mid"),
                           ("high-end","luxury"),("premium","luxury"),("ultra","luxury")]:
        if alias in key: key = mapped; break
    costs = base_costs.get(key, base_costs["mid"])
    daily = sum(costs.values())
    total = daily * days * travelers
    return (f"Budget Estimate: {travelers} traveler(s) x {days} days in {city} ({travel_class})\n"
            f"Hotel: ~${costs['hotel']}/day | Food: ~${costs['food']}/day | "
            f"Activities: ~${costs['activities']}/day | Transport: ~${costs['transport']}/day\n"
            f"Total: ~${total:,}")


@tool
def get_packing_list(destination_type: str, season: str = "general", duration: str = "week") -> str:
    """Returns a smart packing list for a destination type, season, and duration."""
    lists = {
        "beach": ["Swimwear (2-3 sets)", "Sunscreen SPF 50+", "Sunglasses", "Wide-brim hat",
                  "Sandals", "Light cotton clothes", "Beach towel", "Waterproof dry bag"],
        "mountain": ["Thermal base layers", "Fleece mid-layer", "Waterproof jacket",
                     "Trekking boots", "Warm gloves", "Wool socks", "Headlamp", "First aid kit"],
        "city": ["Comfortable walking shoes", "Smart-casual outfits", "Day backpack",
                 "Power bank", "Universal adapter", "Offline maps", "Compact umbrella"],
        "cold": ["Heavy winter coat", "Thermal underwear", "Waterproof insulated boots",
                 "Wool socks", "Insulated gloves", "Beanie", "Hand warmers"],
        "tropical": ["Lightweight breathable fabrics", "DEET insect repellent",
                     "Waterproof sandals", "Packable rain jacket", "Quick-dry towels"],
    }
    items = lists.get(destination_type.lower(),
                      ["Comfortable clothes", "Toiletries", "Travel documents", "Universal adapter"])
    return f"Packing List for {destination_type} ({season}, {duration}):\n" + \
           "\n".join(f"- {i}" for i in items)


# ── LangGraph ─────────────────────────────────────────────────────
tools = [estimate_budget, get_packing_list]
llm_with_tools = llm.bind_tools(tools)
tool_map = {t.name: t for t in tools}


class TravelState(TypedDict):
    messages: Annotated[List, operator.add]


def travel_agent_node(state: TravelState) -> dict:
    msgs = state["messages"]
    if not msgs or not isinstance(msgs[0], SystemMessage):
        msgs = [SystemMessage(content=SYSTEM_PROMPT)] + list(msgs)
    return {"messages": [llm_with_tools.invoke(msgs)]}


def run_tools(state: TravelState) -> dict:
    last = state["messages"][-1]
    return {"messages": [
        ToolMessage(content=str(tool_map[tc["name"]].invoke(tc["args"])), tool_call_id=tc["id"])
        for tc in last.tool_calls
    ]}


def route(state: TravelState) -> str:
    return "tools" if getattr(state["messages"][-1], "tool_calls", []) else "end"


tg = StateGraph(TravelState)
tg.add_node("agent", travel_agent_node)
tg.add_node("tools", run_tools)
tg.add_edge(START, "agent")
tg.add_conditional_edges("agent", route, {"tools": "tools", "end": END})
tg.add_edge("tools", "agent")
travel_graph = tg.compile()


# ── FastAPI ───────────────────────────────────────────────────────
app = FastAPI(title="WanderAI API", version="2.0.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "WanderAI", "version": "2.0.0"}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        lc_messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for m in req.history:
            lc_messages.append(HumanMessage(content=m.content) if m.role == "user"
                                else AIMessage(content=m.content))
        lc_messages.append(HumanMessage(content=req.message))
        result = travel_graph.invoke({"messages": lc_messages})
        return {"response": result["messages"][-1].content, "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Vercel handler ────────────────────────────────────────────────
handler = Mangum(app, lifespan="off")
