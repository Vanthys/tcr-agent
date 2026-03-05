"""
services/neighbors.py — ESM-2 nearest-neighbor search.

Cosine similarity is computed with NumPy (vectorised, fast for 89K × 1280).
Metadata for results is fetched via DuckDB SQL, which is much faster than
iterating a Pandas DataFrame for each result row.

Results are lazy-cached in DataStore.neighbor_cache so repeated clicks on
the same TCR are instant.
"""

from __future__ import annotations

import logging

import numpy as np
from sqlalchemy import text

from data.db import get_conn
from data.store import DataStore

logger = logging.getLogger(__name__)


class NeighborService:
    def __init__(self, store: DataStore) -> None:
        self._store = store

    def find_neighbors(self, tcr_id: str, k: int | None = None) -> list[dict]:
        """
        Return k nearest neighbors in ESM-2 embedding space.
        Results are cached in store.neighbor_cache keyed by tcr_id.
        """
        if tcr_id in self._store.neighbor_cache:
            return self._store.neighbor_cache[tcr_id]

        store = self._store
        if store.embeddings is None or store.embed_tcr_ids is None:
            logger.warning("Embeddings not loaded — cannot find neighbors for %s", tcr_id)
            return []

        if k is None:
            from core.config import settings
            k = settings.neighbor_k

        embeddings = store.embeddings
        tcr_ids = store.embed_tcr_ids

        # Locate query row
        idx_arr = np.where(tcr_ids == tcr_id)[0]
        if len(idx_arr) == 0:
            logger.warning("TCR %s not found in embeddings index", tcr_id)
            return []
        idx = int(idx_arr[0])

        # Vectorised cosine similarity
        query = embeddings[idx]
        query_norm = query / (np.linalg.norm(query) + 1e-10)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
        similarities = (embeddings / norms) @ query_norm  # (N,)

        # Top k+1, drop self
        top_indices = np.argsort(similarities)[::-1][: k + 1]
        top_indices = [i for i in top_indices if i != idx][:k]

        neighbor_ids = [str(tcr_ids[i]) for i in top_indices]
        neighbor_sims = {str(tcr_ids[i]): float(similarities[i]) for i in top_indices}

        # ── Metadata via DuckDB ───────────────────────────────────────────────
        # Single SQL query instead of N Pandas row lookups.
        meta: dict[str, dict] = {}
        if not store.tcr_db.empty:
            try:
                con = get_conn()
                placeholders = ", ".join([f":id_{i}" for i in range(len(neighbor_ids))])
                params = {f"id_{i}": nid for i, nid in enumerate(neighbor_ids)}
                rows = con.execute(
                    text(f"""
                    SELECT tcr_id, CDR3b, source, known_epitope, antigen_category
                    FROM tcrs
                    WHERE tcr_id IN ({placeholders})
                    """),
                    params,
                ).fetchall()
                for row in rows:
                    meta[row[0]] = {
                        "cdr3b":             row[1] or None,
                        "source":            row[2] or None,
                        "known_epitope":     row[3] or None,
                        "antigen_category":  row[4] or None,
                    }
            except Exception as exc:
                logger.warning("SQLite metadata lookup failed: %s", exc)

        # Build result list
        neighbors: list[dict] = []
        for nid in neighbor_ids:
            entry: dict = {"tcr_id": nid, "similarity": round(neighbor_sims[nid], 4)}
            entry.update(meta.get(nid, {}))
            neighbors.append(entry)

        store.neighbor_cache[tcr_id] = neighbors
        return neighbors
