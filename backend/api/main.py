"""CYNTHERA FastAPI Application Factory.

Start the server with:
    python -m uvicorn backend.api.main:app --reload --port 8000

Or from main directory:
    uvicorn backend.api.main:app --reload
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager — runs startup/shutdown logic."""
    logger.info("CYNTHERA API starting up...")
    yield
    logger.info("CYNTHERA API shutting down.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app instance.
    """
    app = FastAPI(
        title="CYNTHERA Drug Repurposing API",
        description=(
            "Contradiction-Aware Mechanistic Reasoning for Explainable Drug Repurposing. "
            "API contracts defined in 07_API_CONTRACTS.md."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow localhost for Streamlit and development tools
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8501",   # Streamlit default
            "http://localhost:3000",   # React dev
            "http://localhost:8000",   # FastAPI self
            "*",                       # Relaxed for development; tighten in production
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    app.include_router(router)

    return app


# Application instance — imported by uvicorn
app = create_app()
