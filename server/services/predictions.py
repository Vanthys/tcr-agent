"""
services/predictions.py — DecoderTCR lookup and epitope aggregations.

All aggregation queries run via DuckDB (SQL) rather than Pandas ops.
This is more readable, more composable, and faster for analytical queries.
"""

from __future__ import annotations

import logging

from data.db import get_conn
from data.store import DataStore
from sqlalchemy import text

logger = logging.getLogger(__name__)


class PredictionService:
    def __init__(self, store: DataStore) -> None:
        self._store = store

    def get_predictions(self, tcr_id: str) -> list[dict]:
        """All predictions for one TCR, sorted by interaction_score DESC."""
        if self._store.predictions_df.empty:
            return []
        try:
            con = get_conn()
            rows = con.execute(
                text("""
                SELECT epitope_name, interaction_score,
                       epitope_category
                FROM predictions
                WHERE tcr_id = :tcr_id
                ORDER BY interaction_score DESC
                """),
                {"tcr_id": tcr_id},
            ).fetchall()
            return [
                {
                    "epitope_name":      r[0],
                    "interaction_score": r[1],
                    "epitope_category":  r[2],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("SQLite predictions lookup failed: %s", exc)
            return []

    def get_epitope_distribution(self, top_n: int = 30) -> list[dict]:
        """Top-N epitope frequencies from annotated TCRs (excl. TCRAFT)."""
        if self._store.tcr_db.empty:
            return []
        try:
            con = get_conn()
            rows = con.execute(
                text("""
                SELECT known_epitope,
                       antigen_category,
                       COUNT(*) AS cnt
                FROM tcrs
                WHERE known_epitope IS NOT NULL
                  AND source != 'TCRAFT'
                GROUP BY known_epitope, antigen_category
                ORDER BY cnt DESC
                LIMIT :top_n
                """),
                {"top_n": top_n},
            ).fetchall()
            return [
                {"epitope": r[0], "category": r[1], "count": r[2]}
                for r in rows
            ]
        except Exception as exc:
            logger.warning("SQLite epitope distribution failed: %s", exc)
            return []

    def get_category_summary(self) -> dict:
        """TCR counts by source and antigen category."""
        if self._store.tcr_db.empty:
            return {}
        try:
            con = get_conn()
            by_source = {
                r[0]: r[1]
                for r in con.execute(
                    text("SELECT source, COUNT(*) FROM tcrs GROUP BY source")
                ).fetchall()
            }
            raw = con.execute(
                text("""
                SELECT source, antigen_category, COUNT(*) AS cnt
                FROM tcrs
                GROUP BY source, antigen_category
                """)
            ).fetchall()
            by_category: dict = {}
            for source, cat, cnt in raw:
                by_category.setdefault(source, {})[cat or "unknown"] = cnt

            return {"by_source": by_source, "by_category": by_category}
        except Exception as exc:
            logger.warning("SQLite category summary failed: %s", exc)
            return {}
