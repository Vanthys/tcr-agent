"""
main.py — TCR Agent FastAPI application factory.

Start with:
    uv run uvicorn main:app --reload --port 8000
"""

import logging
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.lifespan import lifespan
from routers import annotate, health, mutagenesis, stats, tcr, umap, synthesis, null_distribution, worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="TCR Agent API",
    description="Autonomous AI agent for TCR dark matter analysis",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(umap.router)
app.include_router(tcr.router)
app.include_router(mutagenesis.router)
app.include_router(annotate.router)
app.include_router(stats.router)

app.include_router(worker.router)
app.include_router(synthesis.router)
app.include_router(null_distribution.router)
