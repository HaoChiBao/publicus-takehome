"""Vercel Python entrypoint.

Vercel's @vercel/python runtime serves the ASGI `app` exported here. All routes
are handled by the FastAPI app defined in main.py (see vercel.json rewrites).
"""
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv()
load_dotenv(_ROOT / ".env.local", override=True)

from main import app  # noqa: E402  (re-exported for the Vercel runtime)
