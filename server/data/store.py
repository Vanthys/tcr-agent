"""
data/store.py — DataStore singleton.

Holds all in-memory state loaded at startup. Services inject this
via FastAPI dependency `get_store()` rather than touching globals.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataStore:
    """Single source of truth for all pre-loaded data."""

    def __init__(self) -> None:
        self.umap_df: pd.DataFrame = pd.DataFrame()
        self.tcr_db: pd.DataFrame = pd.DataFrame()
        self.embeddings: np.ndarray | None = None
        self.embed_tcr_ids: np.ndarray | None = None
        self.predictions_df: pd.DataFrame = pd.DataFrame()

        # Lazy caches — populated on first request
        self.neighbor_cache: dict[str, list[dict]] = {}
        self.mutagenesis_cache: dict[str, dict[str, Any]] = {}

    # ── Status helpers ────────────────────────────────────────────────────────

    @property
    def umap_loaded(self) -> bool:
        return not self.umap_df.empty

    @property
    def tcr_db_loaded(self) -> bool:
        return not self.tcr_db.empty

    @property
    def embeddings_loaded(self) -> bool:
        return self.embeddings is not None

    @property
    def predictions_loaded(self) -> bool:
        return not self.predictions_df.empty

    def status(self) -> dict[str, Any]:
        return {
            "umap_loaded": self.umap_loaded,
            "umap_points": len(self.umap_df),
            "tcr_db_loaded": self.tcr_db_loaded,
            "tcr_count": len(self.tcr_db),
            "embeddings_loaded": self.embeddings_loaded,
            "embeddings_shape": list(self.embeddings.shape) if self.embeddings is not None else None,
            "predictions_loaded": self.predictions_loaded,
            "prediction_rows": len(self.predictions_df),
            "mutagenesis_cached": len(self.mutagenesis_cache),
            "neighbor_cache_size": len(self.neighbor_cache),
        }


# ── Module-level singleton ────────────────────────────────────────────────────
_store = DataStore()


def get_store() -> DataStore:
    """FastAPI dependency — returns the shared DataStore instance."""
    return _store
