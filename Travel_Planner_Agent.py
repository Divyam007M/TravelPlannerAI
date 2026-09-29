"""Server-side LangGraph planner with curated, non-live India travel tools."""
import os
import re
from typing import TypedDict, Annotated, List
import operator
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.tools import tool

SCOPE_REPLY = "I can help with trips and travel only. Ask me about destinations, itineraries, transport, stays, packing, or travel budgets."
SYSTEM_INSTRUCTION = """You are WanderAI, a practical India travel planner. Answer only questions related to trips and travel. If a request, or part of it, is unrelated to travel (such as math, coding or general trivia), do not answer that part; instead briefly invite a travel question. Treat short follow-ups as travel-related only when they refer to an earlier trip discussion. Give concise, structured plans with day-by-day suggestions and INR budget estimates when useful. Use tools for supported destination notes, budgets and packing. Ask for essential missing details (destination, days, group size or budget); otherwise state assumptions. Built-in facts and budget figures are static estimates, not live prices, weather, hours or availability. Never claim to make bookings or verify reservations. Avoid inventing live facts."""

TRAVEL_CUE = re.compile(
    r"\b(?:trip|travel|travelling|traveling|tour|tourism|itinerary|holiday|vacation|destination|"
    r"visit|visiting|plan|weekend|explore|sightseeing|attraction|flight|airport|train|bus|"
    r"hotel|hostel|stay|accommodation|restaurant|food|packing|pack|luggage|passport|visa|"
    r"beach|mountain|trek|hike|budget|inr|rupees|weather|season|booking|journey|"
    r"goa|jaipur|kerala|manali|bhopal|"
    r"delhi|mumbai|agra|varanasi|udaipur|rishikesh|shimla|darjeeling|amritsar|"
    r"hyderabad|chennai|bangalore|kolkata|pune|jaisalmer|leh)\b|"
    r"\bwhere (?:should|can|could) (?:i|we) go\b",
    re.IGNORECASE,
)
FOLLOW_UP_CUE = re.compile(
    r"\b(?:it|there|that|those|them|this|next|again|more|less|cheaper|shorter|longer)\b|"
    r"\bday\s+\d+\b|^(?:why|when|where|how|and then|then what)\??$|"
    r"^(?:what|how) about\b",
    re.IGNORECASE,
)
UNRELATED_CUE = re.compile(
    r"\b(?:lcm|hcf|gcd|least common multiple|greatest common divisor|photosynthesis|"
    r"quadratic equation|write (?:me )?(?:a )?poem|tell (?:me )?(?:a )?joke|"
    r"write (?:me )?(?:a )?(?:python|javascript|java) (?:program|script|code))\b|"
    r"\b\d+\s*[+*/]\s*\d+\b",
    re.IGNORECASE,
)


def is_travel_request(message: str, prior_messages: list) -> bool:
    """Apply a cheap, conservative topic gate before any provider call."""
    if TRAVEL_CUE.search(message):
        return True
    if UNRELATED_CUE.search(message):
        return False
    has_trip_context = any(
        isinstance(item, HumanMessage) and TRAVEL_CUE.search(str(item.content))
        for item in prior_messages
    )
    return bool(has_trip_context and FOLLOW_UP_CUE.search(message))


# ── Tools ─────────────────────────────────────────────────────────
@tool
def get_city_info(city: str) -> str:
    """Gets information about an Indian travel destination city."""
    cities = {
        "Goa": "Best beaches in India. Famous for: Baga Beach, Old Goa churches, nightlife. Best time: Nov-Feb.",
        "Jaipur": "Pink City. Famous for: Amber Fort, Hawa Mahal, City Palace. Best time: Oct-Mar.",
        "Kerala": "God's Own Country. Famous for: Backwaters, Munnar tea gardens, Ayurveda. Best time: Sep-Mar.",
        "Manali": "Mountain paradise. Famous for: Rohtang Pass, adventure sports, Solang Valley. Best time: Apr-Jun.",
        "Bhopal": "City of Lakes. Famous for: Upper Lake, Lower Lake, Sanchi Stupa, Bhimbetka caves. Best time: Oct-Mar.",
        "Delhi": "Capital city of India. Famous for: Red Fort, India Gate, Qutub Minar, street food. Best time: Oct-Mar.",
        "Mumbai": "Financial capital. Famous for: Gateway of India, Marine Drive, Bollywood, nightlife. Best time: Nov-Feb.",
        "Agra": "Home of the Taj Mahal. Famous for: Taj Mahal, Agra Fort, Fatehpur Sikri. Best time: Oct-Mar.",
        "Varanasi": "Spiritual capital of India. Famous for: Ganga ghats, Kashi Vishwanath Temple, Ganga Aarti. Best time: Oct-Mar.",
        "Udaipur": "City of Lakes. Famous for: Lake Pichola, City Palace, boat rides. Best time: Oct-Mar.",
        "Rishikesh": "Yoga capital of the world. Famous for: Ganga river, yoga retreats, river rafting. Best time: Sep-Apr.",
        "Shimla": "Queen of Hills. Famous for: Mall Road, Ridge, toy train. Best time: Mar-Jun.",
        "Darjeeling": "Tea garden paradise. Famous for: Darjeeling tea, Tiger Hill sunrise, toy train. Best time: Mar-May.",
        "Amritsar": "Spiritual and cultural hub. Famous for: Golden Temple, Wagah Border, Punjabi food. Best time: Oct-Mar.",
        "Hyderabad": "City of Pearls. Famous for: Charminar, Golconda Fort, biryani. Best time: Oct-Mar.",
        "Chennai": "Cultural capital of South India. Famous for: Marina Beach, temples, classical dance. Best time: Nov-Feb.",
        "Bangalore": "Silicon Valley of India. Famous for: IT hubs, gardens, nightlife. Best time: Oct-Feb.",
        "Kolkata": "City of Joy. Famous for: Howrah Bridge, Durga Puja, colonial architecture. Best time: Oct-Feb.",
        "Pune": "Oxford of the East. Famous for: education hubs, forts, pleasant weather. Best time: Oct-Feb.",
        "Jaisalmer": "Golden City. Famous for: sand dunes, desert safari, Jaisalmer Fort. Best time: Oct-Mar.",
        "Leh": "High-altitude desert. Famous for: Pangong Lake, monasteries, bike trips. Best time: May-Sep.",
    }
    match = next((name for name in cities if name.casefold() == str(city).strip().casefold()), None)
    if not match:
        return f"No built-in notes for {city!r}. Supported destinations: {', '.join(cities)}."
    return f"{match}: {cities[match]} General notes only; check current conditions and opening hours."


@tool
def estimate_budget(city: str, days: int, travel_class: str) -> str:
    """
    Estimates the travel budget for a city trip.

    Args:
        city: Name of the destination city.
        days: Number of days for the trip.
        travel_class: Budget tier — one of 'low', 'mid', or 'luxury'.
    """
    # FIX: keys now match the expected travel_class values ('low', 'mid', 'luxury')
    base_costs = {
        "low":    {"hotel": 800,  "food": 400,  "activities": 300},
        "mid":    {"hotel": 3000, "food": 1000, "activities": 900},
        "luxury": {"hotel": 8000, "food": 4000, "activities": 2000},
    }
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 60:
        return "Invalid day count. Provide a whole number from 1 to 60."
    if not str(city).strip():
        return "A destination is required for the estimate."
    normalized = str(travel_class).lower().replace("-range", "").strip()
    if normalized not in base_costs:
        return "Unsupported budget tier. Choose low, mid or luxury."
    costs = base_costs[normalized]
    daily = sum(costs.values())
    total = daily * days
    return (
        f"Static estimate per person for {days} days in {city.strip()} ({normalized} tier): "
        f"Hotel ₹{costs['hotel']}/day + Food ₹{costs['food']}/day + "
        f"Activities ₹{costs['activities']}/day = ₹{daily}/day. "
        f"Total: ₹{total:,}. Excludes transport to the destination, taxes and seasonal changes; verify actual prices."
    )


@tool
def get_packing_list(destination_type: str) -> str:
    """
    Returns a packing list for the given destination type.

    Args:
        destination_type: One of 'beach', 'mountain', 'city', or 'heritage'.
    """
    lists = {
        "beach":    "Sunscreen, swimwear, light cotton clothes, sandals, hat, sunglasses",
        "mountain": "Warm layers, waterproof jacket, trekking shoes, gloves, thermal wear",
        "city":     "Comfortable walking shoes, smart casuals, power bank, camera",
        "heritage": "Conservative clothing, comfortable footwear, water bottle, guidebook",
    }
    kind = str(destination_type).strip().lower()
    return (f"General {kind} packing list: {lists[kind]}. Check actual conditions before departure."
            if kind in lists else "Unsupported destination type. Choose beach, mountain, city or heritage.")


# ── Graph setup ───────────────────────────────────────────────────
tools = [get_city_info, estimate_budget, get_packing_list]
tool_map = {t.name: t for t in tools}


class TravelState(TypedDict):
    messages: Annotated[List, operator.add]


def build_graph(llm):
    """Build a fresh graph; the caller owns the per-session message history."""
    bound = llm.bind_tools(tools)

    def travel_agent(state: TravelState) -> dict:
        response = bound.invoke([SystemMessage(content=SYSTEM_INSTRUCTION), *state["messages"]])
        return {"messages": [response]}

    def route_request(state: TravelState) -> str:
        messages = state["messages"]
        latest_index = next((index for index in range(len(messages) - 1, -1, -1)
                             if isinstance(messages[index], HumanMessage)), None)
        if latest_index is None:
            return "off_topic"
        return ("agent" if is_travel_request(str(messages[latest_index].content), messages[:latest_index])
                else "off_topic")

    def off_topic(_state: TravelState) -> dict:
        return {"messages": [AIMessage(content=SCOPE_REPLY)]}

    def run_tools(state: TravelState) -> dict:
        results = []
        for tc in state["messages"][-1].tool_calls:
            try:
                selected = tool_map.get(tc.get("name"))
                content = str(selected.invoke(tc.get("args", {}))) if selected else "Unknown tool requested."
            except Exception:
                content = "Invalid tool arguments. Check supported values and try again."
            results.append(ToolMessage(content=content, tool_call_id=tc.get("id") or "unknown"))
        return {"messages": results}

    tg = StateGraph(TravelState)
    tg.add_node("agent", travel_agent)
    tg.add_node("off_topic", off_topic)
    tg.add_node("tools", run_tools)
    tg.add_conditional_edges(START, route_request, {"agent": "agent", "off_topic": "off_topic"})
    tg.add_edge("off_topic", END)
    tg.add_conditional_edges("agent", lambda s: "tools" if getattr(s["messages"][-1], "tool_calls", []) else "end", {"tools": "tools", "end": END})
    tg.add_edge("tools", "agent")
    return tg.compile()


def make_groq_graph():
    from langchain_groq import ChatGroq
    if not os.getenv("GROQ_API_KEY", "").strip():
        raise RuntimeError("GROQ_API_KEY is missing")
    return build_graph(ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), temperature=0.3, timeout=45, max_retries=1))


# ── CLI entry point (NOT executed on import by Agent_app.py) ──────
if __name__ == "__main__":
    query = (
        "I want to plan a 5-day mid-range trip to Goa with my family. "
        "Can you: 1) Tell me about Goa, 2) Estimate the budget, "
        "3) Give me a packing list. Create a complete trip summary."
    )
    result = make_groq_graph().invoke({"messages": [HumanMessage(content=query)]})
    print(result["messages"][-1].content)
