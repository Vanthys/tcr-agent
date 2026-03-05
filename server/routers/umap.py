"""
routers/umap.py — GET /api/umap

The umap_coords.csv already contains all needed columns:
  tcr_id, source, CDR3b, known_epitope, antigen_category, x, y

So we just query the `umap` view directly — no JOIN needed.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from core.config import settings
from data.db import get_conn
from data.store import DataStore, get_store

router = APIRouter(prefix="/api", tags=["umap"])


@router.get("/umap")
def get_umap(
    source:   Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit:    int            = Query(100_000, le=100_000),
    store:    DataStore      = Depends(get_store),
):
    if store.umap_df.empty:
        return []

    try:
        con = get_conn()

        conditions: list[str] = []
        params = {}

        if source:
            conditions.append("source = :source")
            params["source"] = source
        if category:
            conditions.append("COALESCE(antigen_category, 'unknown') = :category")
            params["category"] = category

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sql = f"""
            SELECT tcr_id AS id,
                   x, y,
                   CDR3b AS c,
                   source AS s,
                   known_epitope AS e,
                   COALESCE(antigen_category, 'unknown') AS a
            FROM umap
            {where}
            LIMIT :limit
        """
        params["limit"] = limit

        rows = con.execute(text(sql), params).fetchall()
        cols = ["id", "x", "y", "c", "s", "e", "a"]
        result = []
        for row in rows:
            pt = dict(zip(cols, row))
            # Drop None values so the JSON stays compact (dark matter has no 'e')
            result.append({k: v for k, v in pt.items() if v is not None})
        return result

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("UMAP query failed: %s", exc)
        # Fallback to DataFrame
        df = store.umap_df
        if source and "source" in df.columns:
            df = df[df["source"] == source]
        if category and "antigen_category" in df.columns:
            df = df[df["antigen_category"] == category]
        return df.head(limit).where(df.notna(), None).to_dict(orient="records")
