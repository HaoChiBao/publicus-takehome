"""Vercel Python entrypoint.

Vercel's @vercel/python runtime serves the ASGI `app` exported here. All routes
are handled by the FastAPI app defined in main.py (see vercel.json rewrites).
"""
from main import app  # noqa: F401  (re-exported for the Vercel runtime)
