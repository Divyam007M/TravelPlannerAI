"""Vercel's Python entry point for the WanderAI FastAPI application."""
from backend.main import app

# Function instances are ephemeral, so each request carries its public chat
# history instead of relying on a process-local session dictionary.
app.state.stateless = True
