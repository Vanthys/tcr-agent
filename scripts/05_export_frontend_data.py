#!/usr/bin/env python3
"""
05_export_frontend_data.py — Export static JSON files for the frontend

Reads pipeline outputs and generates compact JSON files for the
standalone HTML frontend visualization.

Input:
    - embeddings/umap_coords.csv
    - data/processed/tcr_database.parquet (or .csv)
    - data/processed/data_gap_stats.json
    - predictions/decoder_tcr_scores_long.csv (optional)

Output:
    - frontend/umap_data.json (compact point data)
    - frontend/stats.json (stats + top epitopes)

Usage:
    python scripts/05_export_frontend_data.py
    # After UMAP recomputation or data changes, re-run to update frontend.

Author: Oliver Hahn / Claude
Date: 2026-03-03
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
EMBED_DIR = PROJECT_DIR / "embeddings"
DATA_DIR = PROJECT_DIR / "data" / "processed"
PRED_DIR = PROJECT_DIR / "predictions"
FRONTEND_DIR = PROJECT_DIR / "frontend"


def main():
    print("Exporting frontend data...")

    # ── Load UMAP coordinates ────────────────────────────────────────────────
    umap_path = EMBED_DIR / "umap_coords.csv"
    if not umap_path.exists():
        print(f"ERROR: {umap_path} not found. Run 04_compute_umap.py first.")
        return
    umap_df = pd.read_csv(umap_path)
    print(f"  UMAP: {len(umap_df)} points")

    # ── Load TCR database for epitope info ───────────────────────────────────
    db_path = DATA_DIR / "tcr_database.parquet"
    if db_path.exists():
        db = pd.read_parquet(db_path)
    else:
        csv_path = DATA_DIR / "tcr_database.csv"
        if csv_path.exists():
            db = pd.read_csv(csv_path)
        else:
            db = pd.DataFrame()
    if not db.empty:
        print(f"  TCR database: {len(db)} entries")

    # ── Load predictions (optional) ──────────────────────────────────────────
    pred_path = PRED_DIR / "decoder_tcr_scores_long.csv"
    predictions = None
    if pred_path.exists():
        predictions = pd.read_csv(pred_path)
        print(f"  Predictions: {len(predictions)} scores")
    else:
        print(f"  Predictions: not available (will be added when scoring completes)")

    # ── Build compact UMAP JSON ──────────────────────────────────────────────
    print("\n  Building umap_data.json...")

    # Pre-build prediction lookup (top prediction per TCR) for O(1) access
    top_preds_lookup = {}
    if predictions is not None:
        for tcr_id, group in predictions.groupby('tcr_id'):
            top = group.loc[group['interaction_score'].idxmax()]
            top_preds_lookup[tcr_id] = {
                'ep': top['epitope_name'],
                'sc': round(float(top['interaction_score']), 4),
            }
        print(f"  Prediction lookup: {len(top_preds_lookup)} TCRs with predictions")

    points = []
    for _, row in umap_df.iterrows():
        point = {
            'id': row['tcr_id'],
            's': row['source'][0] if pd.notna(row.get('source')) else 'T',
            'x': round(float(row['umap_x']), 4),
            'y': round(float(row['umap_y']), 4),
            'c': row.get('CDR3b', ''),
        }
        # Only include if not NaN
        if point['c'] != point['c']:  # NaN check
            point['c'] = ''

        ep = row.get('known_epitope')
        if pd.notna(ep):
            point['e'] = ep
        cat = row.get('antigen_category')
        if pd.notna(cat):
            point['a'] = cat

        # Add top prediction if available (O(1) lookup)
        pred = top_preds_lookup.get(row['tcr_id'])
        if pred and not np.isnan(pred.get('sc', float('nan'))):
            point['p'] = pred

        points.append(point)

    umap_json_path = FRONTEND_DIR / "umap_data.json"
    with open(umap_json_path, 'w') as f:
        json.dump(points, f, separators=(',', ':'))
    size_mb = umap_json_path.stat().st_size / 1024 / 1024
    print(f"  Saved: {umap_json_path} ({size_mb:.1f} MB, {len(points)} points)")

    # ── Build stats JSON ─────────────────────────────────────────────────────
    print("\n  Building stats.json...")
    stats = {}

    # Load base stats
    stats_path = DATA_DIR / "data_gap_stats.json"
    if stats_path.exists():
        with open(stats_path) as f:
            stats = json.load(f)

    # Compute top epitopes from data
    if not db.empty:
        known = db[db['known_epitope'].notna() & (db['source'] != 'TCRAFT')]
        if not known.empty:
            top_ep = known['known_epitope'].value_counts().head(15)
            stats['top_epitopes'] = {ep: int(count) for ep, count in top_ep.items()}
    elif not umap_df.empty:
        # Fallback: compute from UMAP data
        known = umap_df[umap_df['known_epitope'].notna()]
        if not known.empty:
            top_ep = known['known_epitope'].value_counts().head(15)
            stats['top_epitopes'] = {ep: int(count) for ep, count in top_ep.items()}

    # Add prediction summary if available
    if predictions is not None:
        pred_summary = {}
        for ep_name in predictions['epitope_name'].unique():
            ep_scores = predictions[predictions['epitope_name'] == ep_name]['interaction_score'].dropna()
            if len(ep_scores) == 0:
                continue
            pred_summary[ep_name] = {
                'mean': round(float(ep_scores.mean()), 4),
                'std': round(float(ep_scores.std(ddof=0)), 4),  # ddof=0 avoids NaN for n=1
                'top_5pct': round(float(ep_scores.quantile(0.95)), 4),
            }
        stats['prediction_summary'] = pred_summary

    # Sanitize NaN/Inf before JSON serialization
    def sanitize(obj):
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize(v) for v in obj]
        return obj

    stats_json_path = FRONTEND_DIR / "stats.json"
    with open(stats_json_path, 'w') as f:
        json.dump(sanitize(stats), f, indent=2)
    print(f"  Saved: {stats_json_path}")

    print("\nFrontend data export complete.")


if __name__ == "__main__":
    main()
