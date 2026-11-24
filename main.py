"""
Entry point for hosting platforms (e.g. Render) that run:  uvicorn main:app
The real application lives in app/main.py - this file just re-exports it.
"""
from app.main import app  # noqa: F401
