"""
main.py — TCR Agent FastAPI application factory.

Start with:
    uv run uvicorn main:app --reload --port 3001
"""

import logging
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.lifespan import lifespan
from routers import chat, health, mutagenesis, stats, tcr, umap, synthesis, null_distribution, worker

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

# Log ALL unhandled exceptions so we can see what's really failing
from fastapi import Request
from fastapi.responses import JSONResponse
import traceback as _tb

@app.exception_handler(Exception)
async def _debug_exception_handler(request: Request, exc: Exception):
    print(f"\n{'='*60}", flush=True)
    print(f"UNHANDLED EXCEPTION on {request.method} {request.url.path}", flush=True)
    _tb.print_exc()
    print(f"{'='*60}\n", flush=True)
    return JSONResponse(status_code=500, content={"detail": str(exc)})

from fastapi.staticfiles import StaticFiles

app.include_router(health.router)
app.include_router(umap.router)
app.include_router(tcr.router)
app.include_router(mutagenesis.router)
app.include_router(chat.router)
app.include_router(stats.router)

app.include_router(worker.router)
app.include_router(synthesis.router)
app.include_router(null_distribution.router)

app.mount("/data", StaticFiles(directory=settings.project_root / "data"), name="data")


# ── Ingested points endpoints (in main.py to avoid reload issues) ────────────
from data.store import get_store as _get_store


@app.get("/api/umap/ingested")
def get_ingested_points():
    return getattr(_get_store(), 'ingested_points', [])


@app.delete("/api/umap/ingested")
def clear_ingested_points():
    _get_store().ingested_points = []
    return {"cleared": True}
