"""
main.py - the entry point of the FoodieHub API.

Run from the project folder:
    source .venv-1/bin/activate
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs
"""
import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import close_pool, open_pool
from app.routers import (
    addresses, auth, cart, categories, customers, delivery, foods, health, orders, payments, restaurants,
)

logger = logging.getLogger("foodiehub")


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()            # connect to Neon when the server starts
    print("✅ Connected to Neon database")
    yield
    close_pool()           # close connections when the server stops


app = FastAPI(
    title="FoodieHub API",
    description="Food delivery backend built with FastAPI + Neon PostgreSQL",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------- Database error handling ----------
# Real error details go to the server log only. The client gets a safe
# message, so table names, SQL and credentials are never exposed.

@app.exception_handler(psycopg.OperationalError)
async def db_unavailable_handler(request: Request, exc: psycopg.OperationalError):
    logger.error("Database unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "Database is temporarily unavailable. Please try again."})


@app.exception_handler(psycopg.Error)
async def db_error_handler(request: Request, exc: psycopg.Error):
    logger.error("Database error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "A database error occurred."})


# ---------- Routers ----------
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(addresses.router)
app.include_router(restaurants.router)
app.include_router(categories.router)
app.include_router(foods.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(delivery.router)
