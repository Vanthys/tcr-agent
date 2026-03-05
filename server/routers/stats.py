"""
routers/stats.py — GET /api/stats_summary, GET /api/epitope_distribution
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from data.db import get_conn
from data.store import DataStore, get_store
from sqlalchemy import text

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats_summary")
def get_stats_summary(store: DataStore = Depends(get_store)):
    """Return high-level counts for the Data Gap donut chart."""
    if store.umap_df.empty:
        return {
            "total_tcrs": 0,
            "annotated_tcrs": 0,
            "dark_matter_tcrs": 0,
            "dark_matter_pct": 100,
            "unique_epitopes": 0,
        }

    try:
        con = get_conn()
        res = con.execute(text("""
            SELECT 
                count(*) as total,
                count(known_epitope) as annotated,
                count(DISTINCT known_epitope) as unique_epi
            FROM umap
        """)).fetchone()

        total, ann, unique_epi = res
        dark = total - ann
        dark_pct = (dark / total * 100) if total > 0 else 0

        return {
            "total_tcrs": total,
            "annotated_tcrs": ann,
            "dark_matter_tcrs": dark,
            "dark_matter_pct": dark_pct,
            "unique_epitopes": unique_epi,
        }
    except Exception:
        return {
            "total_tcrs": len(store.umap_df),
            "annotated_tcrs": 0,
            "dark_matter_tcrs": len(store.umap_df),
            "dark_matter_pct": 100,
            "unique_epitopes": 0,
        }


@router.get("/epitope_distribution")
def get_epitope_distribution(store: DataStore = Depends(get_store)):
    """Return top 50 epitopes for the horizontal bar chart."""
    if store.umap_df.empty:
        return []

    try:
        con = get_conn()
        rows = con.execute(text("""
            SELECT 
                known_epitope as epitope, 
                count(*) as count,
                COALESCE(antigen_category, 'unknown') as category
            FROM umap 
            WHERE known_epitope IS NOT NULL 
            GROUP BY 1, 3 
            ORDER BY 2 DESC 
            LIMIT 50
        """)).fetchall()

        return [{"epitope": r[0], "count": r[1], "category": r[2]} for r in rows]
    except Exception:
        return []
