"""
data/loaders.py — Data loader functions.

Each function is pure: takes a path, returns a typed value or safe empty
fallback. Errors are logged rather than raised — the server starts even if
some files are missing.

Key changes from v1:
  - load_tcr_db() now builds from the NPZ metadata arrays (tcr_ids, cdr3b,
    sources, known_epitopes, antigen_categories) rather than requiring the
    separate tcr_database.parquet.
  - load_embeddings() returns the full NPZ (all arrays), not just two fields.
  - DuckDB views are registered as a side-effect of each loader so services
    can query via SQL.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.db import get_conn, register_dataframe

logger = logging.getLogger(__name__)


# ── UMAP ──────────────────────────────────────────────────────────────────────

def load_umap(path: Path, hero_dir: Path | None = None) -> pd.DataFrame:
    """Load umap_coords.csv, annotate heroes, and register as a SQLite view."""
    target_path = path
    embed_dir = path.parent

    pointer_path = embed_dir / "umap_latest.txt"
    if pointer_path.exists():
        ts = pointer_path.read_text().strip()
        versioned_path = embed_dir / f"umap_coords_v{ts}.csv"
        if versioned_path.exists():
            target_path = versioned_path

    if not target_path.exists():
        logger.warning("UMAP file not found: %s", target_path)
        return pd.DataFrame()
    try:
        df = pd.read_csv(target_path)
        # Normalise column names (Oliver uses tcr_id / x / y but may vary)
        df = _normalise_umap_cols(df)
        
        # Annotate heroes if hero_dir is provided
        if hero_dir and hero_dir.exists():
            hero_ids = {f.stem for f in hero_dir.glob("*.json")}
            # exclude agent_reasoning_logs from being marked as a hero id
            hero_ids.discard("agent_reasoning_logs")
            df["hero"] = df["tcr_id"].isin(hero_ids)
        else:
            df["hero"] = False
            
        register_dataframe("umap", df)
        logger.info("UMAP loaded: %d points from %s", len(df), path)
        return df
    except Exception as exc:
        logger.error("Failed to load UMAP: %s", exc)
        return pd.DataFrame()


def _normalise_umap_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Handle column name variants from different export scripts."""
    renames = {}
    for col in df.columns:
        low = col.lower()
        if low in ("umap_x", "umap1", "dim1", "d1"):
            renames[col] = "d1"
        elif low in ("umap_y", "umap2", "dim2", "d2"):
            renames[col] = "d2"
        elif low in ("dim3", "d3"):
            renames[col] = "d3"
        elif low in ("dim4", "d4"):
            renames[col] = "d4"
        elif low in ("dim5", "d5"):
            renames[col] = "d5"
        elif low == "tcr_id" and col != "tcr_id":
            renames[col] = "tcr_id"
    return df.rename(columns=renames) if renames else df


# ── TCR Database (built from NPZ) ─────────────────────────────────────────────

def load_tcr_db_from_npz(npz_path: Path) -> pd.DataFrame:
    """
    Build the TCR database directly from the ESM-2 NPZ metadata arrays.

    Oliver embedded the per-TCR metadata alongside the embeddings:
        tcr_ids, sources, cdr3b, known_epitopes, antigen_categories

    We reconstruct a Pandas DataFrame from those arrays so we don't need
    tcr_database.parquet to exist.  If the parquet is also present we merge
    additional columns (TRAV, TRBV, disease_context) on top.
    """
    if not npz_path.exists():
        logger.warning("NPZ not found at %s — TCR DB will be empty", npz_path)
        return pd.DataFrame()

    try:
        npz = np.load(npz_path, allow_pickle=True)
        df = pd.DataFrame({
            "tcr_id":            npz["tcr_ids"].astype(str),
            "CDR3b":             npz["cdr3b"].astype(str),
            "source":            npz["sources"].astype(str),
            "known_epitope":     npz["known_epitopes"].astype(str),
            "antigen_category":  npz["antigen_categories"].astype(str),
        })
        # "nan" strings → None
        for col in ("known_epitope", "antigen_category"):
            df[col] = df[col].replace({"nan": None, "": None})

        # Default unknown antigen_category for dark matter rows
        df["antigen_category"] = df["antigen_category"].fillna("unknown")

        register_dataframe("tcrs", df)
        logger.info("TCR DB built from NPZ: %d rows", len(df))
        return df

    except Exception as exc:
        logger.error("Failed to build TCR DB from NPZ: %s", exc)
        return pd.DataFrame()


def augment_tcr_db_from_parquet(tcr_db: pd.DataFrame, parquet_path: Path) -> pd.DataFrame:
    """
    Optionally merge extra columns (TRAV, TRBV, full sequences, disease_context)
    from tcr_database.parquet if it exists.  Non-destructive — the existing DB is
    returned unchanged if the parquet is missing or fails to load.
    """
    if tcr_db.empty or not parquet_path.exists():
        return tcr_db
    try:
        extra = pd.read_parquet(parquet_path, columns=["tcr_id", "TRAV", "TRBV", "TRAJ", "TRBJ", "CDR3a", "disease_context"])
        merged = tcr_db.merge(extra, on="tcr_id", how="left")
        # Re-register the enriched view
        register_dataframe("tcrs", merged)
        logger.info("TCR DB enriched with parquet columns (TRAV, TRBV, disease_context)")
        return merged
    except Exception as exc:
        logger.warning("Could not merge parquet extras: %s", exc)
        return tcr_db


# ── ESM-2 Embeddings ──────────────────────────────────────────────────────────

def load_embeddings(path: Path) -> tuple[np.ndarray | None, np.ndarray | None]:
    """
    Load embeddings matrix + TCR ID index from NPZ.
    Returns (embeddings float32 array, tcr_ids str array) or (None, None).
    """
    if not path.exists():
        logger.warning("Embeddings file not found: %s", path)
        return None, None
    try:
        npz = np.load(path, allow_pickle=True)
        embeddings = npz["embeddings"].astype(np.float32)
        tcr_ids = npz["tcr_ids"].astype(str)
        logger.info("Embeddings loaded: %s from %s", embeddings.shape, path)
        return embeddings, tcr_ids
    except Exception as exc:
        logger.error("Failed to load embeddings: %s", exc)
        return None, None


# ── DecoderTCR Predictions ────────────────────────────────────────────────────

def load_predictions(path: Path) -> pd.DataFrame:
    """Load decoder_tcr_scores_long.csv and register as DuckDB view."""
    if not path.exists():
        logger.warning("Predictions file not found: %s", path)
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        register_dataframe("predictions", df)
        logger.info("Predictions loaded: %d rows from %s", len(df), path)
        return df
    except Exception as exc:
        logger.error("Failed to load predictions: %s", exc)
        return pd.DataFrame()


# ── Mutagenesis Cache ─────────────────────────────────────────────────────────

def load_mutagenesis_cache(mutagenesis_dir: Path) -> dict[str, dict[str, Any]]:
    """Scan mutagenesis_dir for pre-computed JSON files → {tcr_id: landscape}."""
    cache: dict[str, dict[str, Any]] = {}
    if not mutagenesis_dir.exists():
        logger.info(
            "Mutagenesis directory not found: %s (will serve 404 for /api/mutagenesis)",
            mutagenesis_dir,
        )
        return cache

    for json_file in mutagenesis_dir.glob("*.json"):
        tcr_id = json_file.stem
        try:
            with open(json_file) as f:
                cache[tcr_id] = json.load(f)
        except Exception as exc:
            logger.error("Failed to load mutagenesis file %s: %s", json_file, exc)

    logger.info("Mutagenesis cache: %d pre-computed TCRs loaded", len(cache))
    return cache
