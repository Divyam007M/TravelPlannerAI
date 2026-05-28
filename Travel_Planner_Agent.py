import warnings
warnings.filterwarnings("ignore", category=UserWarning)
from typing import TypedDict, Annotated, List
import operator
from langgraph.graph import StateGraph, START, END
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

# ── LLM ──────────────────────────────────────────────────────────
# Uses locally running Ollama — make sure `ollama serve` is running
# and you have pulled the model: `ollama pull llama3.1`
llm = ChatOllama(model="llama3.1:latest", temperature=0.3)


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
    return cities.get(city, f"{city}: Beautiful destination. Always worth visiting!")


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
    # Normalize input — strip extra text like "mid-range" -> "mid"
    normalized = travel_class.lower().replace("-range", "").strip()
    costs = base_costs.get(normalized, base_costs["mid"])
    daily = sum(costs.values())
    total = daily * days
    return (
        f"For {days} days in {city} ({travel_class} class): "
        f"Hotel ₹{costs['hotel']}/day + Food ₹{costs['food']}/day + "
        f"Activities ₹{costs['activities']}/day = ₹{daily}/day. "
        f"Total: ₹{total:,}"
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
    return lists.get(
        destination_type.lower(),
        "Standard travel items + weather-appropriate clothing"
    )


# ── Graph setup ───────────────────────────────────────────────────
tools = [get_city_info, estimate_budget, get_packing_list]
llm_with_tools = llm.bind_tools(tools)
tool_map = {t.name: t for t in tools}


class TravelState(TypedDict):
    messages: Annotated[List, operator.add]


def travel_agent(state: TravelState) -> dict:
    print(f"  [travel_agent] Planning... ({len(state['messages'])} messages)")
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


def run_tools(state: TravelState) -> dict:
    last = state["messages"][-1]
    results = []
    for tc in last.tool_calls:
        print(f"  [tools] Calling: {tc['name']}({tc['args']})")
        res = tool_map[tc["name"]].invoke(tc["args"])
        results.append(ToolMessage(content=str(res), tool_call_id=tc["id"]))
    return {"messages": results}


def route(state: TravelState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", []) else "end"


# Build and compile the graph
tg = StateGraph(TravelState)
tg.add_node("agent", travel_agent)
tg.add_node("tools", run_tools)
tg.add_edge(START, "agent")
tg.add_conditional_edges("agent", route, {"tools": "tools", "end": END})
tg.add_edge("tools", "agent")
travel_graph = tg.compile()


# ── CLI entry point (NOT executed on import by Agent_app.py) ──────
if __name__ == "__main__":
    query = (
        "I want to plan a 5-day mid-range trip to Goa with my family. "
        "Can you: 1) Tell me about Goa, 2) Estimate the budget, "
        "3) Give me a packing list. Create a complete trip summary."
    )
    print("🏖️ TRAVEL PLANNER AGENT\n" + "=" * 50)
    result = travel_graph.invoke({"messages": [HumanMessage(content=query)]})
    print("\n📑 FINAL PLAN:\n")
    print(result["messages"][-1].content)