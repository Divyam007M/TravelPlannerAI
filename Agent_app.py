import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

# Import the compiled LangGraph travel agent
from Travel_Planner_Agent import travel_graph

# ── Page Config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Travel Planner",
    page_icon="🏖️",
    layout="centered",
)

st.title("🏖️ AI Travel Planner")
st.caption("Plan your perfect Indian trip with AI ✈️  |  Powered by LangGraph + Ollama (llama3.1)")

# ── Session State ─────────────────────────────────────────────────
# chat_history stores dicts for display: {"role": "user"|"assistant", "content": "..."}
# lc_messages stores LangChain message objects passed to the graph for context
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "lc_messages" not in st.session_state:
    st.session_state.lc_messages = []

# ── Display Chat History ──────────────────────────────────────────
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── User Input ────────────────────────────────────────────────────
user_input = st.chat_input("E.g. Plan a 5-day trip to Goa for 2 people on a mid budget...")

if user_input:
    # 1. Show the user's message immediately
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. Add user message to LangChain message history for context
    st.session_state.lc_messages.append(HumanMessage(content=user_input))

    # 3. Invoke the LangGraph agent with full conversation history
    with st.spinner("Planning your trip... ✈️"):
        try:
            result = travel_graph.invoke(
                {"messages": st.session_state.lc_messages}
            )
            # The last message in the result is the final AI response
            ai_message = result["messages"][-1]
            response_text = ai_message.content

            # Update the LangChain message list with everything the graph produced
            # (tool calls, tool results, and final AI reply are all included)
            st.session_state.lc_messages = result["messages"]

        except Exception as e:
            response_text = (
                f"⚠️ Something went wrong: `{e}`\n\n"
                "Please make sure **Ollama is running** (`ollama serve`) "
                "and the model is pulled (`ollama pull llama3.1`)."
            )

    # 4. Show and store the assistant's reply
    st.session_state.chat_history.append({"role": "assistant", "content": response_text})
    with st.chat_message("assistant"):
        st.markdown(response_text)

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.header("ℹ️ How to use")
    st.markdown(
        """
        Ask me anything about trip planning, for example:
        - *"Plan a 5-day low-budget trip to Manali"*
        - *"What should I pack for Goa?"*
        - *"Estimate cost for 3 days in Jaipur (luxury)"*
        - *"Tell me about Kerala"*

        **Supported cities:** Goa, Jaipur, Kerala, Manali, Delhi, Mumbai,
        Agra, Varanasi, Udaipur, Rishikesh, Shimla, Darjeeling, Amritsar,
        Hyderabad, Chennai, Bangalore, Kolkata, Pune, Jaisalmer, Leh, Bhopal
        """
    )
    st.divider()
    if st.button("🗑️ Clear Conversation"):
        st.session_state.chat_history = []
        st.session_state.lc_messages = []
        st.rerun()
    st.divider()
    st.caption("Requires Ollama running locally with `llama3.1` model.")