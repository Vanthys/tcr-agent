"""
routers/umap.py — GET /api/umap

The umap_coords.csv already contains all needed columns:
  tcr_id, source, CDR3b, known_epitope, antigen_category, x, y

So we just query the `umap` view directly — no JOIN needed.
"""

from __future__ import annotations

from typing import Optional

import json
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import text
import pandas as pd
import pyarrow as pa

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
                   d1, d2, d3, d4, d5,
                   CDR3b AS c,
                   source AS s,
                   known_epitope AS e,
                   COALESCE(antigen_category, 'unknown') AS a,
                   hero AS h
            FROM umap
            {where}
            LIMIT :limit
        """
        params["limit"] = limit

        rows = con.execute(text(sql), params).fetchall()
        cols = ["id", "d1", "d2", "d3", "d4", "d5", "c", "s", "e", "a", "h"]
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

@router.get("/umap/stream")
def stream_umap(
    source:   Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit:    int            = Query(100_000, le=100_000),
    store:    DataStore      = Depends(get_store),
):
    """
    Streams UMAP points as Newline-Delimited JSON (NDJSON) for high-performance UI loading.
    Each line is a JSON object.
    """
    if store.umap_df.empty:
        return StreamingResponse(iter([]), media_type="application/x-ndjson")

    def generator():
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
                SELECT tcr_id AS id, d1, d2, d3, d4, d5, CDR3b AS c, source AS s,
                       known_epitope AS e, COALESCE(antigen_category, 'unknown') AS a,
                       hero AS h
                FROM umap
                {where}
                LIMIT :limit
            """
            params["limit"] = limit

            # Use server-side cursor equivalent (fetchmany) to stream rows without loading all into RAM
            cursor = con.execute(text(sql), params)
            cols = ["id", "d1", "d2", "d3", "d4", "d5", "c", "s", "e", "a", "h"]
            
            while True:
                rows = cursor.fetchmany(5000)
                if not rows:
                    break
                for row in rows:
                    pt = dict(zip(cols, row))
                    clean_pt = {k: v for k, v in pt.items() if v is not None}
                    yield json.dumps(clean_pt) + "\n"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("UMAP stream failed: %s", exc)

            return StreamingResponse(generator(), media_type="application/x-ndjson")

@router.get("/umap/arrow")
def get_umap_arrow(
    source:   Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit:    int            = Query(100_000, le=100_000),
    store:    DataStore      = Depends(get_store),
):
    """
    Returns UMAP points as an Apache Arrow stream (IPC format).
    Drastically outperforms JSON parsing when loading into tools like deck.gl.
    """
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
            SELECT tcr_id AS id, d1, d2, d3, d4, d5, CDR3b AS c, source AS s,
                   known_epitope AS e, COALESCE(antigen_category, 'unknown') AS a,
                   hero AS h
            FROM umap
            {where}
            LIMIT :limit
        """
        params["limit"] = limit

        # Read directly into pandas DataFrame from SQLAlchemy connection
        df = pd.read_sql(text(sql), con, params=params)
        
        # Pandas may have loaded string columns as 'object'. PyArrow converts them to LargeUtf8 by default.
        # Deck.gl/loaders.gl does not support LargeUtf8, so we must explicitly cast strings to standard Utf8.
        table = pa.Table.from_pandas(df)
        
        schema_fields = []
        for i, field in enumerate(table.schema):
            if pa.types.is_large_string(field.type) or pa.types.is_string(field.type):
                schema_fields.append(pa.field(field.name, pa.string()))
            else:
                schema_fields.append(field)
                
        table = table.cast(pa.schema(schema_fields))
        
        # Write to Apache Arrow IPC stream
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
            
        return Response(content=sink.getvalue().to_pybytes(), media_type="application/vnd.apache.arrow.stream")
        
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("UMAP arrow export failed: %s", exc)
        return Response(status_code=500, content="Failed to generate Arrow file")
