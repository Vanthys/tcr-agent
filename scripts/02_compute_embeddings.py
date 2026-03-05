#!/usr/bin/env python3
"""
02_compute_embeddings.py — ESM-2 Embeddings for TCR CDR3 Beta Sequences

Embeds CDR3 beta sequences from TCRAFT + VDJdb using ESM-2 650M.
Runs on CB2 GPU (RTX 4090).

Input:  data/processed/tcr_database.parquet (or .csv)
Output: embeddings/esm2_cdr3b_embeddings.npz

Usage:
    # On CB2 via SLURM:
    sbatch scripts/submit_embeddings.sh

    # Direct (for testing):
    python scripts/02_compute_embeddings.py --device cuda:0

Author: Oliver Hahn / Claude
Date: 2026-03-03
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
import torch
import esm
from pathlib import Path
from tqdm import tqdm

# ── Config ───────────────────────────────────────────────────────────────────
BATCH_SIZE = 64  # CDR3 sequences are short (~12-18 aa), large batches are fine
MODEL_NAME = "esm2_t33_650M_UR50D"  # 650M parameter ESM-2


def load_data(data_dir):
    """Load TCR database and extract CDR3 beta sequences."""
    parquet_path = data_dir / "processed" / "tcr_database.parquet"
    csv_path = data_dir / "processed" / "tcr_database.csv"

    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        raise FileNotFoundError(f"No tcr_database found in {data_dir / 'processed'}")

    print(f"Loaded {len(df)} TCRs from database")

    # Extract CDR3 beta sequences (non-null only)
    mask = df['CDR3b'].notna() & (df['CDR3b'] != '')
    df_valid = df[mask].copy()
    print(f"TCRs with valid CDR3b: {len(df_valid)}")

    # Clean CDR3b: uppercase and filter sequences with non-standard amino acids
    import re
    VALID_AA = re.compile(r'^[ACDEFGHIKLMNPQRSTVWY]+$')
    df_valid['CDR3b'] = df_valid['CDR3b'].str.upper()
    invalid_mask = ~df_valid['CDR3b'].str.match(VALID_AA)
    n_invalid = invalid_mask.sum()
    if n_invalid > 0:
        print(f"Filtered {n_invalid} sequences with non-standard characters")
        df_valid = df_valid[~invalid_mask].copy()

    # Get unique CDR3 beta sequences (many VDJdb entries share CDR3)
    unique_cdr3b = df_valid['CDR3b'].unique()
    print(f"Unique CDR3b sequences: {len(unique_cdr3b)}")

    return df_valid, unique_cdr3b


def compute_embeddings(sequences, model, alphabet, batch_converter, device, batch_size=64):
    """
    Compute ESM-2 mean-pooled embeddings for a list of sequences.

    Returns: numpy array of shape (n_sequences, embedding_dim)
    """
    model.eval()
    all_embeddings = []
    n_batches = (len(sequences) + batch_size - 1) // batch_size

    for batch_idx in tqdm(range(n_batches), desc="Computing embeddings"):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(sequences))
        batch_seqs = sequences[start:end]

        # Prepare batch for ESM
        data = [(f"seq_{start + i}", seq) for i, seq in enumerate(batch_seqs)]
        _, _, batch_tokens = batch_converter(data)
        batch_tokens = batch_tokens.to(device)

        with torch.no_grad():
            results = model(batch_tokens, repr_layers=[33], return_contacts=False)

        # Extract representations from layer 33 (last layer for 650M)
        representations = results["representations"][33]

        # Mean-pool over sequence length (exclude BOS/EOS tokens)
        # BOS is at position 0, EOS follows the last residue
        for i in range(len(batch_seqs)):
            seq_len = len(batch_seqs[i])
            # Tokens: [BOS, aa1, aa2, ..., aaN, EOS, PAD, ...]
            # We want positions 1 to seq_len (inclusive)
            seq_repr = representations[i, 1:seq_len + 1, :]
            mean_repr = seq_repr.mean(dim=0).cpu().numpy()
            all_embeddings.append(mean_repr)

    return np.array(all_embeddings)


def main():
    parser = argparse.ArgumentParser(description="Compute ESM-2 embeddings for TCR CDR3b sequences")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Path to data/ directory (auto-detected if not specified)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Path to embeddings/ directory (auto-detected if not specified)")
    parser.add_argument("--device", type=str, default="cuda:0",
                        help="Device for inference (default: cuda:0)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help=f"Batch size (default: {BATCH_SIZE})")
    args = parser.parse_args()

    # Auto-detect paths
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    data_dir = Path(args.data_dir) if args.data_dir else project_dir / "data"
    output_dir = Path(args.output_dir) if args.output_dir else project_dir / "embeddings"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ESM-2 Embedding Pipeline — TCR CDR3 Beta Sequences        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Device: {args.device}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Data dir: {data_dir}")
    print(f"  Output dir: {output_dir}")

    # Check device
    if 'cuda' in args.device:
        if not torch.cuda.is_available():
            print("WARNING: CUDA not available, falling back to CPU")
            args.device = 'cpu'
        else:
            print(f"  GPU: {torch.cuda.get_device_name(0)}")
            print(f"  GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    # Load data
    print("\nLoading data...")
    df_valid, unique_cdr3b = load_data(data_dir)

    # Load ESM-2 model
    print(f"\nLoading ESM-2 model ({MODEL_NAME})...")
    model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
    batch_converter = alphabet.get_batch_converter()
    model = model.to(args.device)
    model.eval()
    print(f"  Model loaded, {sum(p.numel() for p in model.parameters()) / 1e6:.0f}M parameters")

    # Compute embeddings for unique CDR3b sequences
    print(f"\nComputing embeddings for {len(unique_cdr3b)} unique CDR3b sequences...")
    unique_embeddings = compute_embeddings(
        unique_cdr3b.tolist(), model, alphabet, batch_converter,
        args.device, args.batch_size
    )
    print(f"  Embedding shape: {unique_embeddings.shape}")

    # Create mapping: CDR3b sequence -> embedding index
    cdr3b_to_idx = {seq: i for i, seq in enumerate(unique_cdr3b)}

    # Map embeddings back to full database
    print("\nMapping embeddings to full database...")
    embedding_indices = df_valid['CDR3b'].map(cdr3b_to_idx).values
    all_embeddings = unique_embeddings[embedding_indices]
    print(f"  Full embedding array shape: {all_embeddings.shape}")

    # Save outputs
    print("\nSaving outputs...")

    # Save unique embeddings + mapping (smaller file)
    unique_path = output_dir / "esm2_cdr3b_unique_embeddings.npz"
    np.savez_compressed(
        unique_path,
        embeddings=unique_embeddings,
        sequences=unique_cdr3b,
    )
    print(f"  Saved unique embeddings: {unique_path} ({unique_embeddings.nbytes / 1e6:.1f} MB)")

    # Save full mapped embeddings with metadata
    full_path = output_dir / "esm2_cdr3b_embeddings.npz"
    np.savez_compressed(
        full_path,
        embeddings=all_embeddings,
        tcr_ids=df_valid['tcr_id'].values,
        sources=df_valid['source'].values,
        cdr3b=df_valid['CDR3b'].values,
        known_epitopes=df_valid['known_epitope'].fillna('').values,
        antigen_categories=df_valid['antigen_category'].fillna('unknown').values,
    )
    print(f"  Saved full embeddings: {full_path} ({all_embeddings.nbytes / 1e6:.1f} MB)")

    # Save metadata CSV for easy joining later
    meta_path = output_dir / "embedding_metadata.csv"
    meta_df = df_valid[['tcr_id', 'source', 'CDR3a', 'CDR3b', 'TRAV', 'TRBV',
                         'known_epitope', 'antigen_category', 'disease_context']].copy()
    meta_df.to_csv(meta_path, index=False)
    print(f"  Saved metadata: {meta_path}")

    print(f"\n✓ Embedding complete! {all_embeddings.shape[0]} TCRs embedded into {all_embeddings.shape[1]}-dim space")


if __name__ == "__main__":
    main()
