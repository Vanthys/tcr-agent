#!/usr/bin/env python3
"""
Quick validation of DecoderTCR predictions after syncing from CB2.
Run after: bash scripts/sync_predictions.sh

Checks:
1. All 3,808 TCRAFT TCRs have predictions
2. All 14 epitopes scored
3. Score distributions look reasonable
4. Frontend JSON regenerated correctly
"""

import json
import sys
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PRED_DIR = PROJECT_DIR / "predictions"
FRONTEND_DIR = PROJECT_DIR / "frontend"

errors = []


def check(condition, msg):
    if not condition:
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  OK: {msg}")


print("=== Validating DecoderTCR Predictions ===\n")

# 1. Check prediction files exist
print("1. Files:")
wide_path = PRED_DIR / "decoder_tcr_scores.csv"
long_path = PRED_DIR / "decoder_tcr_scores_long.csv"
summary_path = PRED_DIR / "scoring_summary.json"
check(wide_path.exists(), f"Wide-format scores: {wide_path}")
check(long_path.exists(), f"Long-format scores: {long_path}")
check(summary_path.exists(), f"Scoring summary: {summary_path}")

if not long_path.exists():
    print("\nCannot validate further without prediction files.")
    sys.exit(1)

# 2. Check dimensions
print("\n2. Dimensions:")
long_df = pd.read_csv(long_path)
wide_df = pd.read_csv(wide_path)
n_tcrs = long_df['tcr_id'].nunique()
n_epitopes = long_df['epitope_name'].nunique()
check(n_tcrs == 3808, f"TCR count: {n_tcrs} (expected 3,808)")
check(n_epitopes == 14, f"Epitope count: {n_epitopes} (expected 14)")
check(len(long_df) == 3808 * 14, f"Total pairs: {len(long_df)} (expected {3808*14})")
check(len(wide_df) == 3808, f"Wide rows: {len(wide_df)} (expected 3,808)")

# 3. Score distributions
print("\n3. Score distributions:")
for ep in sorted(long_df['epitope_name'].unique()):
    scores = long_df[long_df['epitope_name'] == ep]['interaction_score']
    nan_count = scores.isna().sum()
    if nan_count > 0:
        print(f"  WARNING: {ep} has {nan_count} NaN scores")
    else:
        print(f"  {ep}: mean={scores.mean():.3f}, std={scores.std():.3f}, "
              f"range=[{scores.min():.3f}, {scores.max():.3f}]")

# 4. Check summary JSON
print("\n4. Summary JSON:")
with open(summary_path) as f:
    summary = json.load(f)
check(len(summary) == 14, f"Summary has {len(summary)} epitopes (expected 14)")
for ep, info in summary.items():
    check(info['n_scored'] == 3808, f"{ep}: n_scored={info['n_scored']} (expected 3,808)")

# 5. Check frontend JSON
print("\n5. Frontend data:")
umap_path = FRONTEND_DIR / "umap_data.json"
stats_path = FRONTEND_DIR / "stats.json"
if umap_path.exists():
    with open(umap_path) as f:
        umap_data = json.load(f)
    with_pred = sum(1 for d in umap_data if 'p' in d)
    check(with_pred == 3808, f"UMAP points with predictions: {with_pred} (expected 3,808)")
else:
    print("  SKIP: umap_data.json not found (run 05_export_frontend_data.py)")

if stats_path.exists():
    with open(stats_path) as f:
        stats = json.load(f)
    has_summary = 'prediction_summary' in stats
    check(has_summary, f"stats.json has prediction_summary: {has_summary}")
    if has_summary:
        check(len(stats['prediction_summary']) == 14,
              f"prediction_summary has {len(stats['prediction_summary'])} epitopes")
else:
    print("  SKIP: stats.json not found")

# Summary
print(f"\n{'='*50}")
if errors:
    print(f"VALIDATION FAILED: {len(errors)} error(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
