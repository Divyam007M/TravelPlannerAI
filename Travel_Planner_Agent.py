"""Server-side LangGraph planner with global location and live data tools."""
import json
import os
import re
import threading
import time
from typing import TypedDict, Annotated, List
import operator
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.tools import tool
from groq import RateLimitError
from backend.travel_services import convert_currency, resolve_location, weather_forecast

SCOPE_REPLY = "I can help with trips and travel only. Ask me about destinations, itineraries, transport, stays, packing, or travel budgets."
SYSTEM_INSTRUCTION = """You are WanderAI, a practical worldwide travel planner. Answer only trip and travel questions; decline unrelated parts briefly. Keep conversation context. For named places in a place-specific plan, call resolve_destination. For weather requests, call get_destination_weather directly; it already resolves the place. If a tool reports ambiguity, ask which country or region the user means. If the tool resolves a place, accept that resolution and fulfill the original request immediately; do not ask the user to confirm it. A short confirmation from the user means proceed with their original travel request, not merely acknowledge the place. Never invent coordinates. Plan for the supplied destination, dates or season, duration, interests, party size, budget and origin. Dates, origin, budget and home currency are optional: never withhold an itinerary to ask for them; state assumptions and plan now. Do not assume a calendar date that the user has not provided; only request dated weather when dates are given or the user asks for current conditions. Ask a question only when the destination or another truly essential detail is missing. Give readable day-by-day sections with short bullets rather than wide Markdown tables. Use destination local time, usual currency and appropriate units. Use get_destination_weather for actual weather and convert_trip_currency for exchange rates; report exact provider source, observation date and retrieval time from tool output. Copy tool values and weather condition descriptions faithfully; do not reinterpret numeric weather codes. Never invent a forecast, rate or tool result. Dates beyond a forecast horizon may receive clearly labeled general seasonal guidance, never a daily forecast. Numerical trip costs are illustrative estimates only when grounded in user-supplied amounts or a cited current source; distinguish local costs from converted amounts and use a single rate for any conversion. Prices, visas, opening hours, transport schedules and availability are not verified here. Do not promise bookings or live prices. Packing suggestions are general."""

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
CONFIRMATION_CUE = re.compile(
    r"^(?:yes|yeah|yep|yup|correct|exactly|right|ok|okay|sure|go ahead|please do|"
    r"sounds good|that'?s correct|thts correct)"
    r"(?:[,\s]+(?:that'?s|thts|is)\s+correct)?[.!?\s]*$",
    re.IGNORECASE,
)
ITINERARY_CUE = re.compile(r"\b(?:plan|itinerary)\b", re.IGNORECASE)
FIRST_DAY_CUE = re.compile(r"\bday[\s\u202f]*1\b", re.IGNORECASE)
CLARIFICATION_CUE = re.compile(r"\?|\b(?:which|confirm|clarify|do you mean|let me know|assuming you mean)\b", re.IGNORECASE)


def _needs_itinerary_retry(messages: list, response: AIMessage) -> bool:
    """Recover a clear plan request when the model only asks for confirmation."""
    if (response.tool_calls or not isinstance(response.content, str)
            or FIRST_DAY_CUE.search(response.content)
            or not CLARIFICATION_CUE.search(response.content)):
        return False
    requests = [str(item.content) for item in messages if isinstance(item, HumanMessage)]
    if not requests or not any(ITINERARY_CUE.search(item) for item in requests):
        return False
    if len(requests) > 1 and not CONFIRMATION_CUE.fullmatch(requests[-1].strip()):
        return False
    if any(isinstance(item, AIMessage) and isinstance(item.content, str)
           and FIRST_DAY_CUE.search(item.content) for item in messages):
        return False  # The itinerary was already given in an earlier turn.
    statuses = []
    for item in messages:
        if isinstance(item, ToolMessage):
            try:
                statuses.append(json.loads(str(item.content)).get("status"))
            except (ValueError, AttributeError):
                pass
    return "ambiguous" not in statuses and ("resolved" in statuses or not statuses)
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
    if has_trip_context and (FOLLOW_UP_CUE.search(message) or CONFIRMATION_CUE.fullmatch(message.strip())):
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
        if _needs_itinerary_retry(state["messages"], response):
            response = bound.invoke([
                SystemMessage(content=SYSTEM_INSTRUCTION), *state["messages"],
                AIMessage(content=str(response.content)),
                HumanMessage(content="Please fulfill my original itinerary request now. If the destination tool resolved the place, use it without asking me to confirm. Include a day-by-day plan beginning with Day 1. Do not assume travel dates or costs."),
            ])
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
        current_turn = []
        for message in reversed(state["messages"]):
            if isinstance(message, HumanMessage):
                break
            current_turn.append(message)
        resolved_place = None
        for message in current_turn:
            if isinstance(message, ToolMessage):
                try:
                    payload = json.loads(str(message.content))
                    if payload.get("status") == "resolved":
                        resolved_place = payload.get("location")
                        break
                except (ValueError, AttributeError):
                    pass
        user_daily_amount = any(
            isinstance(message, HumanMessage)
            and re.search(r"\b(?:daily|per\s+(?:person\s+)?day)\b|/day", str(message.content), re.IGNORECASE)
            and re.search(r"\d", str(message.content))
            for message in state["messages"]
        )
        for tc in state["messages"][-1].tool_calls:
            try:
                selected = tool_map.get(tc.get("name"))
                args = dict(tc.get("args") or {})
                if isinstance(resolved_place, dict):
                    place_name = str(resolved_place.get("name") or "")
                    for field in ("city", "destination"):
                        if field in args and str(args[field]).strip().casefold() == place_name.casefold():
                            args[field] = resolved_place.get("label") or place_name
                if tc.get("name") == "estimate_budget" and not user_daily_amount:
                    args["daily_local_amount"] = None
                content = str(selected.invoke(args)) if selected else "Unknown tool requested."
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


class RateLimitFallback:
    """Try a second Groq model only when the primary model reaches a limit."""

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback

    def bind_tools(self, available_tools):
        primary = self.primary.bind_tools(available_tools)
        fallback = self.fallback.bind_tools(available_tools)

        class Bound:
            def __init__(self):
                self.retry_primary_at = 0.0
                self.lock = threading.Lock()

            def invoke(self, messages):
                with self.lock:
                    limited = time.monotonic() < self.retry_primary_at
                if limited:
                    return fallback.invoke(messages)
                try:
                    return primary.invoke(messages)
                except RateLimitError as exc:
                    try:
                        delay = max(1, min(86400, int(float(exc.response.headers.get("retry-after", "30")))))
                    except (TypeError, ValueError, OverflowError):
                        delay = 30
                    with self.lock:
                        self.retry_primary_at = max(self.retry_primary_at, time.monotonic() + delay)
                    return fallback.invoke(messages)

        return Bound()


def make_groq_graph():
    from langchain_groq import ChatGroq
    if not os.getenv("GROQ_API_KEY", "").strip():
        raise RuntimeError("GROQ_API_KEY is missing")
    primary_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
    fallback_model = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b").strip()

    def configured_model(name):
        kwargs = {"model": name, "temperature": 0.3, "timeout": 40,
                  "max_retries": 0, "max_tokens": 2400}
        if name.startswith("openai/gpt-oss-"):
            kwargs["reasoning_effort"] = "low"
        return ChatGroq(**kwargs)

    primary = configured_model(primary_model)
    if fallback_model and fallback_model != primary_model:
        return build_graph(RateLimitFallback(primary, configured_model(fallback_model)))
    return build_graph(primary)


# ── CLI entry point (NOT executed on import by Agent_app.py) ──────
if __name__ == "__main__":
    query = (
        "I want to plan a 5-day mid-range trip to Goa with my family. "
        "Can you: 1) Tell me about Goa, 2) Estimate the budget, "
        "3) Give me a packing list. Create a complete trip summary."
    )
    result = make_groq_graph().invoke({"messages": [HumanMessage(content=query)]})
    print(result["messages"][-1].content)
