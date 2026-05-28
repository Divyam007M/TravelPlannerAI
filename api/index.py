"""
Vercel serverless entry point.
Vercel auto-discovers this file and wraps it as a Lambda function.
All /api/* requests are routed here via vercel.json rewrites.
"""
import sys
import os

# Make backend/ importable inside the Vercel bundle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app          # FastAPI app from backend/main.py
from mangum import Mangum

# Mangum wraps the ASGI app for AWS Lambda / Vercel's serverless runtime
handler = Mangum(app, lifespan="off")
