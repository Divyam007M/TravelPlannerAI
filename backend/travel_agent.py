import warnings
warnings.filterwarnings("ignore", category=UserWarning)
from typing import TypedDict, Annotated, List
import operator
import os
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

# API key is loaded exclusively from the .env file (never hardcoded)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY is not set. "
        "Create backend/.env with: GROQ_API_KEY=your_key_here"
    )

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.4,
    api_key=GROQ_API_KEY,
)

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
    """
    Estimates travel budget for any city worldwide.

    Args:
        city: Destination city name (any city in the world)
        days: Number of trip days
        travel_class: Budget tier — 'budget', 'mid', or 'luxury'
        travelers: Number of travelers (default 1)
    """
    # Base costs in USD per person per day — rough global averages
    base_costs = {
        "budget":  {"hotel": 25,  "food": 15,  "activities": 10, "transport": 8},
        "mid":     {"hotel": 90,  "food": 50,  "activities": 40, "transport": 20},
        "luxury":  {"hotel": 280, "food": 130, "activities": 100, "transport": 60},
    }
    # Handle variations like "mid-range", "low", "economy" etc.
    key = travel_class.lower()
    for alias, mapped in [("low", "budget"), ("economy", "budget"), ("backpacker", "budget"),
                           ("mid-range", "mid"), ("moderate", "mid"), ("standard", "mid"),
                           ("high-end", "luxury"), ("premium", "luxury"), ("ultra", "luxury")]:
        if alias in key:
            key = mapped
            break
    costs = base_costs.get(key, base_costs["mid"])

    daily_per_person = sum(costs.values())
    total_per_person = daily_per_person * days
    group_total = total_per_person * travelers

    lines = [
        f"💰 **Budget Estimate: {travelers} traveler(s) × {days} days in {city} ({travel_class} class)**",
        "",
        f"| Category | Per Person/Day |",
        f"|---|---|",
        f"| 🏨 Accommodation | ~${costs['hotel']} |",
        f"| 🍽️ Food & Drinks | ~${costs['food']} |",
        f"| 🎭 Activities & Sightseeing | ~${costs['activities']} |",
        f"| 🚌 Local Transport | ~${costs['transport']} |",
        f"| **Daily total** | **~${daily_per_person}** |",
        "",
        f"**Per-person trip cost:** ~${total_per_person:,}",
    ]
    if travelers > 1:
        lines.append(f"**Group total ({travelers} people):** ~${group_total:,}")
    lines.append("")
    lines.append("_Note: Costs vary by exact neighborhood, season, and booking time. Budget class costs in major Western cities (NYC, London, Paris, Zurich) may be 2–3× higher._")
    return "\n".join(lines)


@tool
def get_packing_list(destination_type: str, season: str = "general", duration: str = "week") -> str:
    """
    Returns a smart packing list for a destination type, season, and duration.

    Args:
        destination_type: Type of destination — 'beach', 'mountain', 'city', 'desert', 'tropical', 'cold', 'heritage', 'safari'
        season: Travel season — 'summer', 'winter', 'monsoon/rainy', 'spring', or 'general'
        duration: Trip length — 'weekend', 'week', or 'month'
    """
    base_lists = {
        "beach": [
            "👙 Swimwear (2–3 sets)", "🧴 Sunscreen SPF 50+", "🕶️ UV-protection sunglasses",
            "👒 Wide-brim hat", "🩴 Sandals & flip-flops", "👕 Light cotton/linen clothes",
            "🏖️ Beach towel or sarong", "💧 Reusable water bottle", "🎒 Waterproof dry bag",
            "🧴 After-sun lotion / aloe vera", "💊 Motion sickness tablets (for boat trips)"
        ],
        "mountain": [
            "🧥 Thermal base layers", "🧣 Fleece mid-layer", "🌧️ Waterproof shell jacket",
            "🥾 Broken-in trekking boots", "🧤 Warm gloves", "🎿 Wool/merino socks (multiple pairs)",
            "🔦 Headlamp + extra batteries", "🏥 First aid kit", "🏔️ Trekking poles",
            "🍫 High-energy snacks (nuts, bars)", "☀️ Sunscreen (UV is intense at altitude)",
            "💊 Altitude sickness medication (consult doctor)"
        ],
        "city": [
            "👟 Comfortable walking shoes", "👔 Smart-casual outfits (2–3 sets)", "🎒 Day backpack",
            "🔋 Portable power bank", "🔌 Universal travel adapter", "🗺️ Offline maps downloaded",
            "🧴 Hand sanitizer", "☂️ Compact umbrella", "📷 Camera or phone with good camera",
            "💳 Credit/debit cards + small cash", "🧾 Copies of important documents"
        ],
        "desert": [
            "👕 Loose, light-colored long-sleeve shirts", "🧢 Wide-brim hat", "🕶️ Polarized sunglasses",
            "🧴 SPF 50+ sunscreen", "💄 Lip balm with SPF", "💧 Large insulated water bottles (3L+ capacity)",
            "🧣 Lightweight scarf/shawl (dust & sun protection)", "👢 Closed-toe shoes (scorpions!)",
            "🦟 Insect repellent (for oases)", "🧴 Moisturizer (extreme dryness)"
        ],
        "tropical": [
            "👕 Lightweight breathable fabrics (linen, bamboo)", "🦟 DEET insect repellent",
            "💊 Malaria prophylaxis (consult doctor)", "👡 Waterproof sandals",
            "🌧️ Packable rain jacket", "🏊 Quick-dry towels", "🧴 Reef-safe sunscreen",
            "💧 Water purification tablets", "🩺 Traveler's diarrhea kit", "🧴 Hand sanitizer"
        ],
        "cold": [
            "🧥 Heavy-duty winter coat", "🧣 Thermal underwear set", "👢 Waterproof insulated boots",
            "🧦 Wool/thermal socks (multiple pairs)", "🧤 Insulated waterproof gloves",
            "🎿 Beanie/winter hat", "💨 Face mask/balaclava", "🔥 Hand warmers (disposable)",
            "🧴 Heavy-duty moisturizer (prevents cracking)", "💄 Protective lip balm"
        ],
        "heritage": [
            "👗 Modest, conservative clothing (shoulders & knees covered)", "👞 Comfortable flat shoes",
            "💧 Reusable water bottle", "📚 Pocket guidebook or downloaded Wikipedia articles",
            "📷 Camera", "🎒 Small day bag", "💵 Local currency cash (many sites are cash-only)",
            "🧻 Pocket tissues (restrooms may lack paper)", "☂️ Umbrella (for sun shade too)"
        ],
        "safari": [
            "👕 Neutral-colored clothes (khaki, olive, beige — not white!)", "🥾 Sturdy closed-toe shoes",
            "🦟 Strong insect repellent (DEET-based)", "🔭 Binoculars", "📷 Telephoto camera lens",
            "🎩 Wide-brim hat", "🧥 Light jacket (early mornings are cold)",
            "💊 Malaria prophylaxis (consult doctor)", "☀️ High-SPF sunscreen", "💧 Water bottle"
        ],
    }
    season_extras = {
        "summer": ["🧊 Cooling towel", "💨 Portable mini fan", "💧 Extra water bottle"],
        "winter": ["🔥 Extra hand warmers", "🧴 Rich moisturizer", "💊 Vitamin D supplements"],
        "monsoon": ["☔ Heavy-duty umbrella", "🌧️ Waterproof jacket", "👟 Waterproof shoes",
                    "🎒 Dry bags for electronics", "👕 Quick-dry clothing"],
        "rainy": ["☔ Heavy-duty umbrella", "🌧️ Waterproof jacket", "🎒 Dry bags for electronics"],
        "spring": ["🤧 Antihistamines (allergy season)", "🌸 Light layers for temperature swings"],
    }
    duration_extras = {
        "month": ["🧺 Travel laundry detergent strips", "✂️ Travel sewing kit", "💊 Full medication supply",
                  "☁️ Cloud storage setup for photos"],
        "weekend": ["🎒 Pack light — carry-on only", "💊 Just essentials, travel-size toiletries"],
    }

    key = destination_type.lower()
    items = base_lists.get(key, [
        "👕 Comfortable clothes appropriate for the climate",
        "🧴 Toiletries (travel size)", "💊 Personal medications",
        "📄 Travel documents (passport, visa, insurance)",
        "🔌 Universal adapter", "💳 Cards + cash", "🎒 Day backpack"
    ])

    result_lines = [f"🎒 **Packing List — {destination_type.title()} destination"]
    if season != "general":
        result_lines[0] += f" ({season} season)"
    result_lines[0] += "**"
    result_lines.append("")
    result_lines.extend([f"• {item}" for item in items])

    s_extra = season_extras.get(season.lower(), [])
    if s_extra:
        result_lines.append(f"\n🌡️ **Seasonal additions ({season}):**")
        result_lines.extend([f"• {item}" for item in s_extra])

    d_extra = duration_extras.get(duration.lower(), [])
    if d_extra:
        result_lines.append(f"\n⏱️ **{duration.title()} trip tips:**")
        result_lines.extend([f"• {item}" for item in d_extra])

    result_lines.append("\n✅ **Always bring:** Passport/ID, travel insurance docs, prescription medications, emergency contacts list")
    return "\n".join(result_lines)


# ── LangGraph ─────────────────────────────────────────────────────
tools = [estimate_budget, get_packing_list]
llm_with_tools = llm.bind_tools(tools)
tool_map = {t.name: t for t in tools}

# Argument types the LLM might pass as strings — coerce them before invocation
_ARG_TYPES: dict[str, dict[str, type]] = {
    "estimate_budget": {"days": int, "travelers": int},
    "get_packing_list": {},
}


def _coerce_args(tool_name: str, args: dict) -> dict:
    """Cast tool arguments to their expected Python types to handle LLM string leakage."""
    coercions = _ARG_TYPES.get(tool_name, {})
    coerced = dict(args)
    for key, cast in coercions.items():
        if key in coerced and not isinstance(coerced[key], cast):
            try:
                coerced[key] = cast(coerced[key])
            except (ValueError, TypeError):
                pass  # leave the original value; let the tool surface a meaningful error
    return coerced


class TravelState(TypedDict):
    messages: Annotated[List, operator.add]


def travel_agent(state: TravelState) -> dict:
    messages = state["messages"]
    # Ensure system message is first
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def run_tools(state: TravelState) -> dict:
    last = state["messages"][-1]
    results = []
    for tc in last.tool_calls:
        args = _coerce_args(tc["name"], tc["args"])
        res = tool_map[tc["name"]].invoke(args)
        results.append(ToolMessage(content=str(res), tool_call_id=tc["id"]))
    return {"messages": results}


def route(state: TravelState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", []) else "end"


tg = StateGraph(TravelState)
tg.add_node("agent", travel_agent)
tg.add_node("tools", run_tools)
tg.add_edge(START, "agent")
tg.add_conditional_edges("agent", route, {"tools": "tools", "end": END})
tg.add_edge("tools", "agent")
travel_graph = tg.compile()


if __name__ == "__main__":
    from langchain_core.messages import HumanMessage
    query = "Plan a 7-day luxury trip to Tokyo, Japan for 2 people. Include budget estimate and packing list."
    print("🌍 TRAVEL PLANNER AGENT\n" + "=" * 50)
    result = travel_graph.invoke({"messages": [HumanMessage(content=query)]})
    print(result["messages"][-1].content)
