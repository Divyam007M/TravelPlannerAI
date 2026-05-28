"""
Vercel Python Serverless Function
==================================
Vercel auto-detects this file and wraps it as a serverless function.
The `handler` variable is the Mangum-wrapped FastAPI ASGI app.
All /api/* requests are routed here via vercel.json rewrites.
"""
import sys
import os

# Add backend/ to path so Vercel bundles it alongside this function
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app          # FastAPI app from backend/main.py
from mangum import Mangum

# Vercel looks for a variable named `handler`
handler = Mangum(app, lifespan="off")
