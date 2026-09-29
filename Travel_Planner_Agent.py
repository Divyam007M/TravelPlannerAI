"""Server-side LangGraph planner with global location and live data tools."""
import json
import os
import re
from typing import TypedDict, Annotated, List
import operator
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.tools import tool
from backend.travel_services import convert_currency, resolve_location, weather_forecast

SCOPE_REPLY = "I can help with trips and travel only. Ask me about destinations, itineraries, transport, stays, packing, or travel budgets."
SYSTEM_INSTRUCTION = """You are WanderAI, a practical worldwide travel planner. Answer only trip and travel questions; decline unrelated parts briefly. Keep conversation context. For named places, call resolve_destination before a place-specific plan. If it returns multiple places, ask which country or region the user means; if unresolved, do not invent coordinates or place facts. Plan for the supplied destination, dates or season, duration, interests, party size, budget and origin. Dates, origin, budget and home currency are optional: never withhold an itinerary to ask for them; state assumptions and plan now. Ask a question only when the destination or another truly essential detail is missing. Give readable day-by-day sections with short bullets rather than wide Markdown tables. Use destination local time, usual currency and appropriate units. Use get_destination_weather for actual weather and convert_trip_currency for exchange rates; report exact provider source, observation date and retrieval time from tool output. Copy tool values and weather condition descriptions faithfully; do not reinterpret numeric weather codes. Never invent a forecast, rate or tool result. Dates beyond a forecast horizon may receive clearly labeled general seasonal guidance, never a daily forecast. Numerical trip costs are illustrative estimates only when grounded in user-supplied amounts or a cited current source; distinguish local costs from converted amounts and use a single rate for any conversion. Prices, visas, opening hours, transport schedules and availability are not verified here. Do not promise bookings or live prices. Packing suggestions are general."""

TRAVEL_CUE = re.compile(
    r"\b(?:trip|travel|travelling|traveling|tour|tourism|itinerary|holiday|vacation|destination|"
    r"visit|visiting|plan|weekend|explore|sightseeing|attraction|flight|airport|train|bus|"
    r"hotel|hostel|stay|accommodation|restaurant|food|packing|pack|luggage|passport|visa|"
    r"beach|mountain|trek|hike|budget|currency|exchange|convert|weather|forecast|season|booking|journey|"
    r"route|ferry|cruise|museum|landmark|local time|time zone|timezone)\b|"
    r"\b(?:what (?:can|should) (?:i|we) (?:do|see) in|things to do in|tell me about)\b|"
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
    if UNRELATED_CUE.search(message):
        return False
    if TRAVEL_CUE.search(message):
        return True
    has_trip_context = any(
        isinstance(item, HumanMessage) and TRAVEL_CUE.search(str(item.content))
        for item in prior_messages
    )
    if has_trip_context and FOLLOW_UP_CUE.search(message):
        return True
    # A bare place name can start a travel conversation, wherever it is.
    if re.fullmatch(r"[\wÀ-ÿ .,'-]{2,80}", message.strip()) and len(message.split()) <= 5:
        return resolve_location(message)["status"] in {"resolved", "ambiguous"}
    return False


# ── Tools ─────────────────────────────────────────────────────────
@tool
def resolve_destination(destination: str) -> str:
    """Resolve a worldwide city or region and its timezone/usual currency; ask for clarification if ambiguous."""
    return json.dumps(resolve_location(destination), ensure_ascii=False)


@tool
def estimate_budget(city: str, days: int, travel_class: str, daily_local_amount: float | None = None) -> str:
    """
    Computes an illustrative local trip total only from a supplied daily amount.

    Args:
        city: Name of the destination city.
        days: Number of days for the trip.
        travel_class: Budget tier — one of 'low', 'mid', or 'luxury'.
        daily_local_amount: User-supplied estimated cost per person per day in local currency.
    """
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 60:
        return "Invalid day count. Provide a whole number from 1 to 60."
    if not str(city).strip():
        return "A destination is required for the estimate."
    normalized = str(travel_class).lower().replace("-range", "").strip()
    if normalized not in {"low", "mid", "luxury"}:
        return "Unsupported budget tier. Choose low, mid or luxury."
    place = resolve_location(city)
    if place["status"] != "resolved":
        return json.dumps(place, ensure_ascii=False)
    currency = place["location"]["usual_currency"]
    if not currency:
        return "The destination's usual currency could not be determined; ask for a currency before computing a total."
    if daily_local_amount is None:
        return f"No verified local cost data for {place['location']['label']}. Ask for a daily amount in {currency}; do not apply fixed prices from another country."
    try:
        from decimal import Decimal
        daily = Decimal(str(daily_local_amount))
        if not daily.is_finite() or daily < 0 or daily > Decimal("1000000000"):
            raise ValueError
    except (ValueError, TypeError, ArithmeticError):
        return "Invalid daily amount. Provide a nonnegative amount in the destination's usual currency."
    return (f"Illustrative {normalized} budget using the supplied estimate: {daily} {currency} per person per day × "
            f"{days} days = {daily * days} {currency} per person. Local estimate, not a price quote; "
            "excludes origin transport, taxes and changes. Convert separately with one verified rate if requested.")


@tool
def get_destination_weather(destination: str, start_date: str | None = None, days: int = 3) -> str:
    """Get genuine current conditions and dated forecast for a resolved place (ISO start_date, 1–60 days)."""
    return json.dumps(weather_forecast(destination, start_date, days), ensure_ascii=False)


@tool
def convert_trip_currency(amount: float, base: str, target: str) -> str:
    """Convert a nonnegative amount between ISO currencies with a dated Frankfurter rate."""
    return json.dumps(convert_currency(amount, base, target), ensure_ascii=False)


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
tools = [resolve_destination, estimate_budget, get_packing_list, get_destination_weather, convert_trip_currency]
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
