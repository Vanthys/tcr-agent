#!/usr/bin/env python3
"""
04_compute_umap.py — UMAP Projection of ESM-2 TCR Embeddings

Takes ESM-2 CDR3 beta embeddings and computes 2D UMAP projection.
Can run locally (CPU) or on CB2.

Input:  embeddings/esm2_cdr3b_embeddings.npz
Output: embeddings/umap_coords.csv

Usage:
    python scripts/04_compute_umap.py
    python scripts/04_compute_umap.py --n-neighbors 30 --min-dist 0.2

Author: Oliver Hahn / Claude
Date: 2026-03-03
"""

import argparse
import numpy as np
import pandas as pd
import umap
from pathlib import Path
import time
import joblib


def main():
    parser = argparse.ArgumentParser(description="Compute UMAP from ESM-2 embeddings")
    parser.add_argument("--embeddings-dir", type=str, default=None)
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--min-dist", type=float, default=0.1)
    parser.add_argument("--metric", type=str, default="cosine")
    parser.add_argument("--random-seed", type=int, default=42)
    args = parser.parse_args()

    # Auto-detect paths
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent
    embed_dir = Path(args.embeddings_dir) if args.embeddings_dir else project_dir / "data" / "embeddings"

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  UMAP Projection — TCR CDR3 Beta Embeddings                ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  n_neighbors: {args.n_neighbors}")
    print(f"  min_dist: {args.min_dist}")
    print(f"  metric: {args.metric}")
    print(f"  random_seed: {args.random_seed}")

    # Load embeddings
    embed_path = embed_dir / "esm2_cdr3b_embeddings.npz"
    print(f"\nLoading embeddings from {embed_path}...")
    data = np.load(embed_path, allow_pickle=True)
    embeddings = data['embeddings']
    tcr_ids = data['tcr_ids']
    sources = data['sources']
    cdr3b = data['cdr3b']
    known_epitopes = data['known_epitopes']
    antigen_categories = data['antigen_categories']

    print(f"  Embeddings shape: {embeddings.shape}")
    print(f"  Sources: {dict(zip(*np.unique(sources, return_counts=True)))}")

    # Run UMAP
    print(f"\nRunning UMAP ({embeddings.shape[0]} points, {embeddings.shape[1]} dims)...")
    t0 = time.time()
    reducer = umap.UMAP(
        n_neighbors=args.n_neighbors,
        min_dist=args.min_dist,
        metric=args.metric,
        random_state=args.random_seed,
        n_components=5,
        verbose=True,
    )
    coords_nd = reducer.fit_transform(embeddings)
    t1 = time.time()
    print(f"  UMAP completed in {t1 - t0:.1f}s")

    # Build output DataFrame
    umap_df = pd.DataFrame({
        'tcr_id': tcr_ids,
        'source': sources,
        'CDR3b': cdr3b,
        'known_epitope': known_epitopes,
        'antigen_category': antigen_categories,
        'd1': coords_nd[:, 0],
        'd2': coords_nd[:, 1],
        'd3': coords_nd[:, 2],
        'd4': coords_nd[:, 3],
        'd5': coords_nd[:, 4],
    })

    # Replace empty strings with None for cleaner output
    umap_df['known_epitope'] = umap_df['known_epitope'].replace('', None)
    umap_df.loc[umap_df['antigen_category'] == 'unknown', 'antigen_category'] = None

    # Save
    output_path = embed_dir / "umap_coords.csv"
    umap_df.to_csv(output_path, index=False)
    print(f"\nSaved UMAP coordinates: {output_path}")

    # Summary stats
    print(f"\n  Total points: {len(umap_df)}")
    print(f"  UMAP D1 range: [{coords_nd[:, 0].min():.2f}, {coords_nd[:, 0].max():.2f}]")
    print(f"  UMAP D2 range: [{coords_nd[:, 1].min():.2f}, {coords_nd[:, 1].max():.2f}]")

    # Generate a version timestamp
    timestamp = int(time.time())

    # Save the model so we can run .transform() later for the iterative loop
    model_path = embed_dir / f"umap_model_v{timestamp}.joblib"
    joblib.dump(reducer, model_path)
    print(f"\nSaved UMAP model: {model_path}")

    # Save parameters
    params_path = embed_dir / f"umap_params_v{timestamp}.json"
    import json
    with open(params_path, 'w') as f:
        json.dump({
            'n_neighbors': args.n_neighbors,
            'min_dist': args.min_dist,
            'metric': args.metric,
            'random_seed': args.random_seed,
            'n_points': int(embeddings.shape[0]),
            'embedding_dim': int(embeddings.shape[1]),
        }, f, indent=2)
    print(f"  Saved UMAP params: {params_path}")

    # Save CSV
    output_path = embed_dir / f"umap_coords_v{timestamp}.csv"
    umap_df.to_csv(output_path, index=False)
    print(f"\nSaved UMAP coordinates: {output_path}")

    # Optionally symlink to 'latest' so scripts can find it easily
    latest_csv = embed_dir / "umap_coords_latest.csv"
    latest_model = embed_dir / "umap_model_latest.joblib"
    
    # We write a pointer file so both windows/linux can read it simply
    pointer_path = embed_dir / "umap_latest.txt"
    pointer_path.write_text(str(timestamp))

    print("\n✓ UMAP projection complete!")


if __name__ == "__main__":
    main()
