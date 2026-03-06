"""
core/lifespan.py — FastAPI application lifespan handler.

Loads all data into the DataStore at startup using the new loaders.
The loading order matters:
  1. Embeddings + TCR DB (from the same NPZ)
  2. UMAP coordinates
  3. Prediction scores (optional)
  4. Mutagenesis cache (optional)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings
from data.db import close_conn
from data.loaders import (
    augment_tcr_db_from_parquet,
    load_embeddings,
    load_mutagenesis_cache,
    load_predictions,
    load_tcr_db_from_npz,
    load_umap,
)
from data.store import get_store

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all data at startup; clean up at shutdown."""
    store = get_store()
    logger.info("=== TCR Agent Server starting ===")

    # ── Step 1: Load embeddings + build TCR DB from NPZ ──────────────────────
    # The NPZ is the source of truth. It contains both the embeddings matrix
    # AND the per-TCR metadata (tcr_ids, cdr3b, sources, etc.).
    npz_path = settings.embed_dir / "esm2_cdr3b_embeddings.npz"

    store.embeddings, store.embed_tcr_ids = load_embeddings(npz_path)
    store.tcr_db = load_tcr_db_from_npz(npz_path)

    # Optionally enrich with TRAV/TRBV from the full parquet (if Oliver shipped it)
    store.tcr_db = augment_tcr_db_from_parquet(
        store.tcr_db,
        parquet_path=settings.data_dir / "tcr_database.parquet",
    )

    # ── Step 2: UMAP coordinates ──────────────────────────────────────────────
    store.umap_df = load_umap(
        settings.embed_dir / "umap_coords.csv",
        mutagenesis_dir=settings.mutagenesis_dir
    )

    # ── Step 3: DecoderTCR prediction scores (optional) ──────────────────────
    store.predictions_df = load_predictions(
        settings.pred_dir / "decoder_tcr_scores_long.csv"
    )

    # ── Step 4: Pre-computed mutagenesis JSONs (optional) ────────────────────
    store.mutagenesis_cache = load_mutagenesis_cache(settings.mutagenesis_dir)

    logger.info("=== Startup complete — %s ===", store.status())

    yield  # ── App is running ──

    # Shutdown
    close_conn()
    logger.info("=== TCR Agent Server shutting down ===")
