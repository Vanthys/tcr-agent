#!/usr/bin/env python3
"""
03_decoder_tcr_scoring.py — DecoderTCR Scoring of TCR Database

Scores TCRs from the unified database against a panel of candidate epitopes
using DecoderTCR 650M. Runs on CB2 GPU.

Input:
    - data/processed/tcr_database.parquet (unified TCR database, 88,962 TCRs)
      Only TCRs with both full_alpha_seq and full_beta_seq are scored (~38,934)
    - models/650M_DecoderTCR.ckpt

Output:
    - predictions/decoder_tcr_scores_long.csv (all TCR x epitope scores, long format)
    - predictions/decoder_tcr_scores.csv (wide-format matrix)
    - predictions/scoring_summary.json (per-epitope summary stats)

Usage:
    sbatch scripts/submit_decoder_scoring.sh
    # or directly:
    python scripts/03_decoder_tcr_scoring.py --checkpoint models/650M_DecoderTCR.ckpt --device cuda:0
    # score only new TCRs (skip already-scored):
    python scripts/03_decoder_tcr_scoring.py --skip-scored --device cuda:0

Author: Oliver Hahn / Claude
Date: 2026-03-03
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np
import torch
from pathlib import Path
from tqdm import tqdm
import json
import time

# ── HLA-A*02:01 protein sequence (from DecoderTCR demo) ──────────────────────
# This is the dominant HLA allele in the TCRAFT vitiligo cohort
HLA_A0201 = (
    "GSHSMRYFFTSVSRPGRGEPRFIAVGYVDDTQFVRFDSDAASQRMEPRAPWIEQEGPEYWDGETRKVKAH"
    "SQTHRVDLGTLRGYYNQSEAGSHTVQRMYGCDVGSDWRFLRGYHQYAYDGKDYIALKEDLRSWTAADMAA"
    "QTTKHKWEAAHVAEQLRAYLEGTCVEWLRRYLENGKETLQRTDAPKTHMTHHAVSDHEATLRCWALSFYPA"
    "EITLTWQRDGEDQTQDTELVETRPAGDGTFQKWAAVVVPSGQEQRYTCHVQHEGLPKPLTLRWEPSSQPT"
    "IPIVGIIAGLVLFGAVITGAVVAAVMWRRKSSDRKGGSYSQAASSDSAQGSDVSLTACKVMIQRTPKIQVY"
    "SRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEHSDLSFSKDWSFYLLYYTEFTPTEKDEYACR"
    "VNHVTLSQPKIVKWDRDM"
)

# ── Candidate epitope panel ──────────────────────────────────────────────────
# Key epitopes for vitiligo, melanoma, and common viral controls
# All HLA-A*02:01 restricted
EPITOPE_PANEL = {
    # Melanocyte-associated (vitiligo/melanoma relevance)
    'MART1_ELAGIGILTV': {'epitope': 'ELAGIGILTV', 'gene': 'MLANA/MART-1', 'category': 'melanocyte'},
    'MART1_AAGIGILTV': {'epitope': 'AAGIGILTV', 'gene': 'MLANA/MART-1', 'category': 'melanocyte'},
    'gp100_KTWGQYWQV': {'epitope': 'KTWGQYWQV', 'gene': 'PMEL/gp100', 'category': 'melanocyte'},
    'gp100_IMDQVPFSV': {'epitope': 'IMDQVPFSV', 'gene': 'PMEL/gp100', 'category': 'melanocyte'},
    'gp100_YLEPGPVTA': {'epitope': 'YLEPGPVTA', 'gene': 'PMEL/gp100', 'category': 'melanocyte'},
    'TYR_YMNGTMSQV': {'epitope': 'YMNGTMSQV', 'gene': 'TYR', 'category': 'melanocyte'},
    'TRP2_SVYDFFVWL': {'epitope': 'SVYDFFVWL', 'gene': 'DCT/TRP-2', 'category': 'melanocyte'},

    # Cancer germline antigens
    'NYESO1_SLLMWITQC': {'epitope': 'SLLMWITQC', 'gene': 'NY-ESO-1', 'category': 'cancer'},
    'PRAME_SLYSFPEPEA': {'epitope': 'SLYSFPEPEA', 'gene': 'PRAME', 'category': 'cancer'},

    # Viral controls (well-studied TCR-pMHC pairs)
    'CMV_NLVPMVATV': {'epitope': 'NLVPMVATV', 'gene': 'pp65/CMV', 'category': 'viral'},
    'EBV_GLCTLVAML': {'epitope': 'GLCTLVAML', 'gene': 'BMLF1/EBV', 'category': 'viral'},
    'FLU_GILGFVFTL': {'epitope': 'GILGFVFTL', 'gene': 'M1/Influenza', 'category': 'viral'},
    'COVID_YLQPRTFLL': {'epitope': 'YLQPRTFLL', 'gene': 'Spike/SARS-CoV-2', 'category': 'viral'},
    'HIV_SLYNTVATL': {'epitope': 'SLYNTVATL', 'gene': 'Gag/HIV', 'category': 'viral'},
}


def load_tcrs(data_dir, skip_scored=False, existing_scores_dir=None):
    """Load TCRs from unified database, optionally skipping already-scored ones."""
    # Try parquet first, fall back to CSV
    parquet_file = data_dir / "processed" / "tcr_database.parquet"
    csv_file = data_dir / "processed" / "tcr_database.csv"
    legacy_file = data_dir / "processed" / "tcraft_for_embedding.csv"

    if parquet_file.exists():
        df = pd.read_parquet(parquet_file)
        print(f"Loaded {len(df)} TCRs from {parquet_file.name}")
    elif csv_file.exists():
        df = pd.read_csv(csv_file)
        print(f"Loaded {len(df)} TCRs from {csv_file.name}")
    elif legacy_file.exists():
        df = pd.read_csv(legacy_file)
        print(f"Loaded {len(df)} TCRs from {legacy_file.name} (legacy)")
    else:
        raise FileNotFoundError(
            f"No TCR data found. Looked for:\n"
            f"  {parquet_file}\n  {csv_file}\n  {legacy_file}"
        )

    # Filter to those with both full-length chains (required for DecoderTCR)
    mask = df['full_alpha_seq'].notna() & df['full_beta_seq'].notna()
    n_before = len(df)
    df = df[mask].copy()
    print(f"  {len(df)} / {n_before} have both full-length chains")

    # Report breakdown by source
    if 'source' in df.columns:
        print(f"  Source breakdown:")
        for source, count in df['source'].value_counts().items():
            print(f"    {source}: {count}")

    # Skip already-scored TCRs if requested
    if skip_scored and existing_scores_dir:
        existing_wide = existing_scores_dir / "decoder_tcr_scores.csv"
        if existing_wide.exists():
            scored_df = pd.read_csv(existing_wide, usecols=['tcr_id'])
            scored_ids = set(scored_df['tcr_id'].unique())
            n_before_skip = len(df)
            df = df[~df['tcr_id'].isin(scored_ids)].copy()
            print(f"  Skipping {n_before_skip - len(df)} already-scored TCRs")
            print(f"  {len(df)} new TCRs to score")
        else:
            print(f"  No existing scores found at {existing_wide}, scoring all TCRs")

    return df


def score_tcr_epitope_pairs(model, tcr_df, epitope_panel, hla_seq, device,
                            output_dir=None, checkpoint_interval=1000):
    """
    Score all TCR x epitope combinations using DecoderTCR.

    For each pair, computes the interaction score:
        score = avg_log_prob(peptide | HLA + TCR) - avg_log_prob(peptide | HLA)

    Higher score = stronger predicted TCR-pMHC interaction.

    Saves checkpoints every `checkpoint_interval` TCRs (all epitopes for that TCR).
    """
    from DecoderTCR.utils.predict_TpM import predict_single

    results = []
    total_pairs = len(tcr_df) * len(epitope_panel)
    n_epitopes = len(epitope_panel)
    print(f"Scoring {len(tcr_df)} TCRs x {n_epitopes} epitopes = {total_pairs} pairs")

    # Check for partial checkpoint to resume from
    checkpoint_path = output_dir / "decoder_tcr_checkpoint.csv" if output_dir else None
    start_idx = 0
    if checkpoint_path and checkpoint_path.exists():
        checkpoint_df = pd.read_csv(checkpoint_path)
        completed_tcrs = checkpoint_df['tcr_id'].unique()
        n_completed = len(completed_tcrs)
        print(f"  Found checkpoint with {n_completed} TCRs already scored, resuming...")
        # Filter out already-completed TCRs
        tcr_df = tcr_df[~tcr_df['tcr_id'].isin(completed_tcrs)].copy()
        results = checkpoint_df.to_dict('records')
        total_pairs = len(tcr_df) * n_epitopes
        print(f"  {len(tcr_df)} TCRs remaining ({total_pairs} pairs)")

    progress = tqdm(total=total_pairs, desc="Scoring TCR-epitope pairs")
    tcr_count = 0
    ep_names = list(epitope_panel.keys())

    for _, tcr_row in tcr_df.iterrows():
        tcr_seq = tcr_row['full_alpha_seq'] + tcr_row['full_beta_seq']

        for ep_name in ep_names:
            ep_info = epitope_panel[ep_name]
            sample = {
                'HLA_seq': hla_seq,
                'epitope': ep_info['epitope'],
                'TCR_seq': tcr_seq,
            }

            try:
                with torch.no_grad():
                    score = predict_single(model, sample, device=device)
            except Exception as e:
                score = np.nan
                if tcr_count < 3:  # Only print first few errors
                    print(f"  Error scoring {tcr_row['tcr_id']} vs {ep_name}: {e}")

            results.append({
                'tcr_id': tcr_row['tcr_id'],
                'CDR3a': tcr_row['CDR3a'],
                'CDR3b': tcr_row['CDR3b'],
                'epitope_name': ep_name,
                'epitope_seq': ep_info['epitope'],
                'epitope_gene': ep_info['gene'],
                'epitope_category': ep_info['category'],
                'interaction_score': score,
            })
            progress.update(1)

        tcr_count += 1

        # Save checkpoint periodically
        if checkpoint_path and tcr_count % checkpoint_interval == 0:
            ckpt_df = pd.DataFrame(results)
            ckpt_df.to_csv(checkpoint_path, index=False)
            n_unique = ckpt_df['tcr_id'].nunique()
            elapsed = progress.format_dict['elapsed']
            rate = progress.format_dict['rate'] or 0
            remaining = (total_pairs - progress.n) / rate if rate > 0 else 0
            print(f"\n  [Checkpoint] {n_unique} TCRs scored, "
                  f"elapsed: {elapsed:.0f}s, est. remaining: {remaining/3600:.1f}h")

    progress.close()
    return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description="Score TCRs with DecoderTCR")
    parser.add_argument("--data-dir", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--checkpoint", type=str, default=None,
                        help="Path to DecoderTCR model checkpoint")
    parser.add_argument("--device", type=str, default="cuda:0")
    parser.add_argument("--max-tcrs", type=int, default=None,
                        help="Limit number of TCRs to score (for testing)")
    parser.add_argument("--skip-scored", action="store_true",
                        help="Skip TCRs that already have scores in output dir")
    parser.add_argument("--checkpoint-interval", type=int, default=1000,
                        help="Save checkpoint every N TCRs (default: 1000)")
    args = parser.parse_args()

    # Auto-detect paths
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    data_dir = Path(args.data_dir) if args.data_dir else project_dir / "data"
    output_dir = Path(args.output_dir) if args.output_dir else project_dir / "predictions"
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = args.checkpoint
    if checkpoint is None:
        checkpoint = str(project_dir / "models" / "650M_DecoderTCR.ckpt")

    print("=" * 64)
    print("  DecoderTCR Scoring — Unified TCR Database vs Epitope Panel")
    print("=" * 64)
    print(f"  Checkpoint: {checkpoint}")
    print(f"  Device: {args.device}")
    print(f"  Epitope panel: {len(EPITOPE_PANEL)} epitopes")
    print(f"  Skip scored: {args.skip_scored}")
    print(f"  Checkpoint interval: every {args.checkpoint_interval} TCRs")

    # Add DecoderTCR to path
    decoder_src = project_dir / "data" / "DecoderTCR" / "src"
    if str(decoder_src) not in sys.path:
        sys.path.insert(0, str(decoder_src))

    # Load model
    print("\nLoading DecoderTCR model...")
    from DecoderTCR.utils.predict_TpM import load_model
    model = load_model(checkpoint_path=checkpoint, device=args.device)
    print("  Model loaded")

    # Load TCRs
    print("\nLoading TCRs from unified database...")
    tcr_df = load_tcrs(
        data_dir,
        skip_scored=args.skip_scored,
        existing_scores_dir=output_dir
    )

    if args.max_tcrs:
        tcr_df = tcr_df.head(args.max_tcrs)
        print(f"  Limited to first {args.max_tcrs} TCRs (testing mode)")

    if len(tcr_df) == 0:
        print("\nNo TCRs to score. All may already be scored.")
        return

    # Score
    print("\nStarting scoring...")
    t0 = time.time()
    scores_df = score_tcr_epitope_pairs(
        model, tcr_df, EPITOPE_PANEL, HLA_A0201, args.device,
        output_dir=output_dir,
        checkpoint_interval=args.checkpoint_interval,
    )
    t1 = time.time()
    elapsed_h = (t1 - t0) / 3600
    print(f"\nScoring completed in {elapsed_h:.2f}h ({len(scores_df)} total scores)")

    # If we skipped scored, merge with existing scores
    if args.skip_scored:
        existing_long = output_dir / "decoder_tcr_scores_long.csv"
        if existing_long.exists():
            print("\nMerging with existing scores...")
            old_df = pd.read_csv(existing_long)
            # Remove any overlap (shouldn't be any, but be safe)
            new_ids = set(scores_df['tcr_id'].unique())
            old_df = old_df[~old_df['tcr_id'].isin(new_ids)]
            scores_df = pd.concat([old_df, scores_df], ignore_index=True)
            print(f"  Combined: {scores_df['tcr_id'].nunique()} total TCRs")

    # Save long-format scores
    long_path = output_dir / "decoder_tcr_scores_long.csv"
    scores_df.to_csv(long_path, index=False)
    print(f"  Saved long-format scores: {long_path}")

    # Pivot to wide format (TCR x epitope matrix)
    wide_df = scores_df.pivot_table(
        index=['tcr_id', 'CDR3a', 'CDR3b'],
        columns='epitope_name',
        values='interaction_score'
    ).reset_index()
    wide_path = output_dir / "decoder_tcr_scores.csv"
    wide_df.to_csv(wide_path, index=False)
    print(f"  Saved wide-format scores: {wide_path}")

    # Summary statistics
    print("\n  Score statistics per epitope:")
    for ep_name in EPITOPE_PANEL:
        ep_scores = scores_df[scores_df['epitope_name'] == ep_name]['interaction_score']
        if len(ep_scores) > 0 and ep_scores.notna().sum() > 0:
            print(f"    {ep_name}: mean={ep_scores.mean():.4f}, "
                  f"std={ep_scores.std():.4f}, "
                  f"range=[{ep_scores.min():.4f}, {ep_scores.max():.4f}]")

    # Save summary stats
    stats = {}
    for ep_name, ep_info in EPITOPE_PANEL.items():
        ep_scores = scores_df[scores_df['epitope_name'] == ep_name]['interaction_score']
        if len(ep_scores) > 0 and ep_scores.notna().sum() > 0:
            stats[ep_name] = {
                'epitope': ep_info['epitope'],
                'gene': ep_info['gene'],
                'category': ep_info['category'],
                'mean_score': float(ep_scores.mean()),
                'std_score': float(ep_scores.std()),
                'min_score': float(ep_scores.min()),
                'max_score': float(ep_scores.max()),
                'n_scored': int(ep_scores.notna().sum()),
            }
    stats['_meta'] = {
        'total_tcrs': int(scores_df['tcr_id'].nunique()),
        'total_pairs': int(len(scores_df)),
        'elapsed_hours': round(elapsed_h, 2),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    stats_path = output_dir / "scoring_summary.json"
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Saved scoring summary: {stats_path}")

    # Clean up checkpoint file on successful completion
    checkpoint_file = output_dir / "decoder_tcr_checkpoint.csv"
    if checkpoint_file.exists():
        checkpoint_file.unlink()
        print("  Removed checkpoint file (scoring complete)")

    print("\nDecoderTCR scoring complete!")


if __name__ == "__main__":
    main()
