#!/usr/bin/env python3
"""
01_process_tcr_data.py — TCR Dark Matter Explorer: Data Processing Pipeline

Processes multiple data sources into a unified TCR database:
1. TCRAFT 3,808 vitiligo TCRs (Gaglione et al. 2026) → full-length reconstruction
2. Table S2 reactive annotations → 188 TCRAFT TCRs with antigen reactivity
3. Table S2 10X-identified TCRs → 105 TCRAFT TCRs with specific epitope calls
4. VDJdb paired TCR-pMHC entries → known antigen specificities
5. 30,810 PDAC tumor TCRs (Gaglione et al. 2026 Table S2) → pancreatic cancer dark matter
6. Gate et al. 2020 AD CSF TCRs (GSE134578) → Alzheimer's disease dark matter
7. McPAS-TCR pathology-associated database → cross-disease annotations

Output: data/processed/tcr_database.parquet

Author: Oliver Hahn / Claude
Date: 2026-03-03
"""

import os
import sys
import pandas as pd
import numpy as np
from Bio import SeqIO
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
TCRAFT_REF = DATA_DIR / "TCRAFT" / "TCRAFT" / "references"
GAGLIONE_REF = DATA_DIR / "Gaglione-et-al-2025" / "Nanopore_Scripts" / "references_3810"
VDJDB_DIR = DATA_DIR / "vdjdb"
TABLE_S2 = PROJECT_DIR / "Background_info" / "Ganglione_et_al_tableS2.xlsx"
EXTERNAL_DIR = DATA_DIR / "external"
OUTPUT_DIR = DATA_DIR / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Load IMGT reference sequences for full-length TCR reconstruction
# ═══════════════════════════════════════════════════════════════════════════════

def parse_imgt_fasta(fasta_path, v_region_type):
    """
    Parse IMGT FASTA file, keeping only *01 alleles (primary).
    Returns dict: gene_name -> protein sequence (e.g., 'TRAV1-1' -> 'MWGAF...')
    """
    seq_dict = {}
    with open(fasta_path, 'r') as f:
        for record in SeqIO.parse(f, 'fasta'):
            name = record.id
            # Extract gene name (e.g., 'TRAV1-1' from '...TRAV1-1*01...')
            try:
                start = name.index(v_region_type)
                end = name.index('*', start)
                gene_name = name[start:end]
            except ValueError:
                continue
            # Only keep *01 alleles (first encountered)
            if gene_name not in seq_dict:
                seq_dict[gene_name] = str(record.seq)
    return seq_dict


def load_references():
    """Load all IMGT reference data needed for full-length TCR reconstruction."""
    print("Loading IMGT reference sequences...")

    # V gene protein sequences
    trav_seqs = parse_imgt_fasta(TCRAFT_REF / "IMGT_TRAV_download.fasta", "TRAV")
    trbv_seqs = parse_imgt_fasta(TCRAFT_REF / "IMGT_TRBV_download.fasta", "TRBV")

    # J gene joining regions (protein)
    trj_df = pd.read_csv(TCRAFT_REF / "TRJ_seqs.csv")
    trj_seqs = dict(zip(trj_df['TRJ'], trj_df['seq']))

    # Constant regions (protein)
    with open(TCRAFT_REF / "TRAC_protein.txt") as f:
        trac_protein = f.read().strip()
    with open(TCRAFT_REF / "TRBC2_protein.txt") as f:
        trbc2_protein = f.read().strip()

    print(f"  TRAV genes: {len(trav_seqs)}")
    print(f"  TRBV genes: {len(trbv_seqs)}")
    print(f"  TRJ genes: {len(trj_seqs)}")

    return trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein


def get_v_region_up_to_cdr3(v_seq):
    """
    Get V region protein sequence up to and including the conserved Cysteine
    that marks the start of CDR3. This C is included in both V region and CDR3.
    """
    cdr3_start = v_seq.rfind('C')
    if cdr3_start == -1:
        return None
    return v_seq[:cdr3_start + 1]


def reconstruct_full_length_tcr(row, trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein):
    """
    Reconstruct full-length TCR alpha and beta chain protein sequences.

    Logic (from TCRAFT Validate.py):
        TCRbeta  = Vbeta[..C] + CDR3B[1:] + J_beta_join + TRBC2_constant
        TCRalpha = Valpha[..C] + CDR3A[1:] + J_alpha_join + TRAC_constant

    CDR3[1:] skips the first C (already included in V region).
    """
    errors = []

    # Alpha chain
    full_alpha = None
    trav = row.get('TRAV', '')
    cdr3a = row.get('CDR3A', row.get('CDR3a', ''))
    traj = row.get('TRAJ', '')

    if trav and cdr3a and traj:
        if trav in trav_seqs:
            v_alpha = get_v_region_up_to_cdr3(trav_seqs[trav])
            if v_alpha and traj in trj_seqs:
                full_alpha = v_alpha + cdr3a[1:] + trj_seqs[traj] + trac_protein
            else:
                errors.append(f"Missing TRAJ={traj}" if traj not in trj_seqs else "No C in TRAV")
        else:
            errors.append(f"Missing TRAV={trav}")

    # Check for internal stop codons in alpha (orphon V genes like TRAV14-1)
    if full_alpha and '*' in full_alpha:
        errors.append(f"Internal stop codon in alpha at pos {full_alpha.index('*')}")
        full_alpha = None  # Don't use invalid sequences

    # Beta chain
    full_beta = None
    trbv = row.get('TRBV', '')
    cdr3b = row.get('CDR3B', row.get('CDR3b', ''))
    trbj = row.get('TRBJ', '')

    if trbv and cdr3b and trbj:
        if trbv in trbv_seqs:
            v_beta = get_v_region_up_to_cdr3(trbv_seqs[trbv])
            if v_beta and trbj in trj_seqs:
                full_beta = v_beta + cdr3b[1:] + trj_seqs[trbj] + trbc2_protein
            else:
                errors.append(f"Missing TRBJ={trbj}" if trbj not in trj_seqs else "No C in TRBV")
        else:
            errors.append(f"Missing TRBV={trbv}")

    # Check for internal stop codons in beta (orphon V genes like TRBV24/OR9-2)
    if full_beta and '*' in full_beta:
        errors.append(f"Internal stop codon in beta at pos {full_beta.index('*')}")
        full_beta = None  # Don't use invalid sequences

    return full_alpha, full_beta, "; ".join(errors) if errors else None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Process TCRAFT 3,808 vitiligo TCRs
# ═══════════════════════════════════════════════════════════════════════════════

def process_tcraft_tcrs(trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein):
    """
    Process TCRAFT CDR3 table into unified format with full-length reconstruction.
    Source: Gaglione et al. 2025 — 3,808 synthetic TCRs from vitiligo patients.
    """
    print("\n" + "="*70)
    print("Processing TCRAFT vitiligo TCRs (Gaglione et al. 2025)")
    print("="*70)

    cdr3_file = GAGLIONE_REF / "All_3800_CDR3_table.csv"
    df = pd.read_csv(cdr3_file)
    print(f"  Loaded {len(df)} TCRs from CDR3 table")
    print(f"  Columns: {list(df.columns)}")

    # Reconstruct full-length sequences
    results = []
    errors_count = 0
    for idx, row in df.iterrows():
        full_alpha, full_beta, err = reconstruct_full_length_tcr(
            row, trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein
        )
        if err:
            errors_count += 1

        results.append({
            'source': 'TCRAFT',
            'tcr_id': f"TCRAFT_{idx+1:04d}",
            'TRAV': row['TRAV'],
            'TRBV': row['TRBV'],
            'CDR3a': row['CDR3A'],
            'CDR3b': row['CDR3B'],
            'TRAJ': row['TRAJ'],
            'TRBJ': row['TRBJ'],
            'full_alpha_seq': full_alpha,
            'full_beta_seq': full_beta,
            'known_epitope': None,
            'epitope_gene': None,
            'epitope_species': None,
            'mhc_allele': None,
            'disease_context': 'vitiligo',
            'antigen_category': None,  # Will be filled for reactive TCRs
            'confidence_score': None,
            'reconstruction_error': err,
        })

    tcraft_df = pd.DataFrame(results)

    # Stats
    n_alpha = tcraft_df['full_alpha_seq'].notna().sum()
    n_beta = tcraft_df['full_beta_seq'].notna().sum()
    n_both = ((tcraft_df['full_alpha_seq'].notna()) & (tcraft_df['full_beta_seq'].notna())).sum()
    print(f"  Full-length reconstruction: {n_alpha} alpha, {n_beta} beta, {n_both} paired")
    print(f"  Reconstruction errors: {errors_count}")

    return tcraft_df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Process VDJdb for known TCR-pMHC pairs
# ═══════════════════════════════════════════════════════════════════════════════

def categorize_epitope(epitope, gene, species):
    """Categorize epitope into broad functional categories."""
    species_lower = str(species).lower() if pd.notna(species) else ''
    gene_lower = str(gene).lower() if pd.notna(gene) else ''

    # Melanocyte-associated antigens
    melanocyte_genes = {'mart-1', 'mlana', 'melan-a', 'gp100', 'pmel', 'tyr', 'tyrosinase',
                        'trp-1', 'trp-2', 'tyrp1', 'dct', 'trp2'}
    if gene_lower in melanocyte_genes or any(g in gene_lower for g in melanocyte_genes):
        return 'melanocyte'

    # Cancer germline / cancer-testis antigens
    cancer_genes = {'prame', 'mage', 'ny-eso-1', 'ctag1b', 'ssx2', 'bage', 'gage',
                    'survivin', 'birc5', 'wt1', 'her2', 'erbb2', 'tp53', 'p53',
                    'kras', 'nras', 'egfr', 'braf', 'idh1', 'idh2',
                    'tert', 'cdk4', '5t4', 'tpbg', 'bst2', 'mesothelin', 'msln'}
    if gene_lower in cancer_genes or any(g in gene_lower for g in cancer_genes):
        return 'cancer_associated'

    # Viral — comprehensive list including abbreviations used in VDJdb
    viral_species = {'cmv', 'cytomegalovirus', 'ebv', 'epstein', 'hiv',
                     'influenza', 'sars-cov', 'covid', 'hcv', 'hepatitis',
                     'hbv', 'htlv', 'dengue', 'denv', 'yellow fever', 'yfv',
                     'mcmv', 'lcmv', 'vaccinia', 'herpes', 'hsv', 'vzv',
                     'hpv', 'papilloma', 'mcpyv', 'polyoma', 'rsv',
                     'adenovirus', 'rotavirus', 'zika', 'chikungunya',
                     'measles', 'mumps', 'rubella', 'norovirus'}
    if any(v in species_lower for v in viral_species):
        return 'viral'

    # Self/autoimmune
    autoimmune_genes = {'gad65', 'gad67', 'insulin', 'ins', 'mbp', 'mog', 'plp',
                        'slc30a8', 'glia', 'gluten', 'gliadin'}
    if gene_lower in autoimmune_genes:
        return 'autoimmune'

    # Bacterial
    bacterial = {'tuberculosis', 'mycobacterium', 'salmonella', 'listeria',
                 'streptococcus', 'pseudomonas', 'staphylococcus', 'clostridium'}
    if any(b in species_lower for b in bacterial):
        return 'bacterial'

    return 'other'


def process_vdjdb(trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein):
    """
    Process VDJdb database: extract human paired alpha/beta TCRs with known epitopes.
    Filter for confidence score >= 1.
    """
    print("\n" + "="*70)
    print("Processing VDJdb (known TCR-pMHC pairs)")
    print("="*70)

    vdjdb_file = VDJDB_DIR / "vdjdb.txt"
    df = pd.read_csv(vdjdb_file, sep='\t', low_memory=False)
    print(f"  Total VDJdb entries: {len(df)}")

    # Filter: human, confidence >= 1
    df = df[df['species'] == 'HomoSapiens'].copy()
    print(f"  Human entries: {len(df)}")

    df = df[df['vdjdb.score'].astype(float) >= 1].copy()
    print(f"  Confidence >= 1: {len(df)}")

    # Separate alpha and beta chains
    alpha_df = df[df['gene'] == 'TRA'].copy()
    beta_df = df[df['gene'] == 'TRB'].copy()
    print(f"  Alpha (TRA) entries: {len(alpha_df)}")
    print(f"  Beta (TRB) entries: {len(beta_df)}")

    # Pair alpha/beta using complex.id (non-zero complex.id means paired observation)
    alpha_df = alpha_df[alpha_df['complex.id'] != 0].copy()
    beta_df = beta_df[beta_df['complex.id'] != 0].copy()
    print(f"  Paired alpha entries (complex.id != 0): {len(alpha_df)}")
    print(f"  Paired beta entries (complex.id != 0): {len(beta_df)}")

    # Merge on complex.id + epitope to get paired TCRs
    paired = pd.merge(
        alpha_df[['complex.id', 'cdr3', 'v.segm', 'j.segm', 'antigen.epitope',
                  'antigen.gene', 'antigen.species', 'mhc.a', 'mhc.class', 'vdjdb.score']],
        beta_df[['complex.id', 'cdr3', 'v.segm', 'j.segm']],
        on='complex.id',
        suffixes=('_alpha', '_beta')
    )
    print(f"  Paired TCRs (merged): {len(paired)}")

    # Deduplicate by CDR3 alpha + CDR3 beta + epitope
    paired = paired.drop_duplicates(subset=['cdr3_alpha', 'cdr3_beta', 'antigen.epitope'])
    print(f"  After deduplication: {len(paired)}")

    # Clean V/J gene names (remove allele info, handle VDJdb quirks)
    def clean_gene(gene_str):
        if pd.isna(gene_str) or gene_str == '':
            return ''
        gene_str = gene_str.strip()
        # Take first gene if comma-separated (ambiguous calls)
        if ',' in gene_str:
            gene_str = gene_str.split(',')[0].strip()
        # Take first if semicolon-separated
        if ';' in gene_str:
            gene_str = gene_str.split(';')[0].strip()
        # Remove allele info
        gene_str = gene_str.split('*')[0]
        # Handle old IMGT "S1" suffix (e.g., TRAV18S1 → TRAV38-1 is complex,
        # but stripping S1 suffix at least prevents lookup errors for the common cases)
        # Most S1 suffixes in VDJdb correspond to renamed genes — skip these
        return gene_str

    # Build unified records
    results = []
    errors_count = 0
    for idx, row in paired.iterrows():
        trav = clean_gene(row['v.segm_alpha'])
        trbv = clean_gene(row['v.segm_beta'])
        traj = clean_gene(row['j.segm_alpha'])
        trbj = clean_gene(row['j.segm_beta'])

        rec_row = {
            'TRAV': trav, 'TRBV': trbv,
            'CDR3A': row['cdr3_alpha'], 'CDR3B': row['cdr3_beta'],
            'TRAJ': traj, 'TRBJ': trbj,
        }

        full_alpha, full_beta, err = reconstruct_full_length_tcr(
            rec_row, trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein
        )
        if err:
            errors_count += 1

        category = categorize_epitope(
            row['antigen.epitope'], row['antigen.gene'], row['antigen.species']
        )

        results.append({
            'source': 'VDJdb',
            'tcr_id': f"VDJdb_{int(row['complex.id']):06d}",
            'TRAV': trav,
            'TRBV': trbv,
            'CDR3a': row['cdr3_alpha'],
            'CDR3b': row['cdr3_beta'],
            'TRAJ': traj,
            'TRBJ': trbj,
            'full_alpha_seq': full_alpha,
            'full_beta_seq': full_beta,
            'known_epitope': row['antigen.epitope'],
            'epitope_gene': row['antigen.gene'],
            'epitope_species': row['antigen.species'],
            'mhc_allele': row['mhc.a'],
            'disease_context': None,
            'antigen_category': category,
            'confidence_score': float(row['vdjdb.score']),
            'reconstruction_error': err,
        })

    vdjdb_df = pd.DataFrame(results)

    # Stats
    n_paired = ((vdjdb_df['full_alpha_seq'].notna()) & (vdjdb_df['full_beta_seq'].notna())).sum()
    print(f"  Full-length reconstructed pairs: {n_paired}")
    print(f"  Reconstruction errors: {errors_count}")

    # Epitope distribution
    print("\n  Top 10 epitopes:")
    for ep, count in vdjdb_df['known_epitope'].value_counts().head(10).items():
        cat = vdjdb_df[vdjdb_df['known_epitope'] == ep]['antigen_category'].iloc[0]
        print(f"    {ep}: {count} TCRs ({cat})")

    # Category distribution
    print("\n  Antigen categories:")
    for cat, count in vdjdb_df['antigen_category'].value_counts().items():
        print(f"    {cat}: {count}")

    return vdjdb_df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Also process unpaired VDJdb beta-only TCRs (for UMAP density)
# ═══════════════════════════════════════════════════════════════════════════════

def process_vdjdb_beta_only():
    """
    Process VDJdb beta-only entries for additional UMAP coverage.
    These have known epitope but only beta chain (much more common in VDJdb).
    """
    print("\n" + "="*70)
    print("Processing VDJdb beta-only entries (for UMAP enrichment)")
    print("="*70)

    vdjdb_file = VDJDB_DIR / "vdjdb.txt"
    df = pd.read_csv(vdjdb_file, sep='\t', low_memory=False)

    # Filter: human, beta only, confidence >= 1
    beta_df = df[
        (df['species'] == 'HomoSapiens') &
        (df['gene'] == 'TRB') &
        (df['vdjdb.score'].astype(float) >= 1)
    ].copy()

    # Deduplicate by CDR3 + epitope
    beta_df = beta_df.drop_duplicates(subset=['cdr3', 'antigen.epitope'])
    print(f"  Unique beta CDR3 + epitope pairs: {len(beta_df)}")

    results = []
    for idx, row in beta_df.iterrows():
        category = categorize_epitope(
            row['antigen.epitope'], row['antigen.gene'], row['antigen.species']
        )

        results.append({
            'source': 'VDJdb_beta_only',
            'tcr_id': f"VDJdb_b_{idx:06d}",
            'TRAV': None,
            'TRBV': str(row['v.segm']).split('*')[0] if pd.notna(row['v.segm']) else None,
            'CDR3a': None,
            'CDR3b': row['cdr3'],
            'TRAJ': None,
            'TRBJ': str(row['j.segm']).split('*')[0] if pd.notna(row['j.segm']) else None,
            'full_alpha_seq': None,
            'full_beta_seq': None,  # Won't reconstruct full-length for beta-only
            'known_epitope': row['antigen.epitope'],
            'epitope_gene': row['antigen.gene'],
            'epitope_species': row['antigen.species'],
            'mhc_allele': row['mhc.a'] if pd.notna(row.get('mhc.a')) else None,
            'disease_context': None,
            'antigen_category': category,
            'confidence_score': float(row['vdjdb.score']),
            'reconstruction_error': None,
        })

    beta_only_df = pd.DataFrame(results)
    print(f"  Beta-only entries: {len(beta_only_df)}")

    return beta_only_df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Annotate TCRAFT TCRs with Table S2 reactive data
# ═══════════════════════════════════════════════════════════════════════════════

def annotate_tcraft_with_table_s2(tcraft_df):
    """
    Annotate TCRAFT TCRs using Table S2 from Gaglione et al. 2026.

    Two sheets provide ground-truth antigen reactivity:
    1. "3808 - Reactive TCRs" (header at row 2): 188 TCRs activated by peptide pools
       - 138 reactive to melanocyte antigens, 38 to viral, 12 ambiguous
       - 24 reactive to MART-1, 23 to gp100
    2. "3808 - 10X-identified TCRs": 105 TCRs with specific epitope calls from 10X

    These TCRs shift from "dark matter" to annotated.
    """
    if not TABLE_S2.exists():
        print(f"  WARNING: Table S2 not found at {TABLE_S2}, skipping annotations")
        return tcraft_df

    print("\n" + "="*70)
    print("Annotating TCRAFT TCRs with Table S2 reactivity data")
    print("="*70)

    # ── Parse "3808 - Reactive TCRs" (header at row 2) ──────────────────────
    reactive_df = pd.read_excel(TABLE_S2, sheet_name='3808 - Reactive TCRs', header=2)
    print(f"  Reactive TCRs sheet: {len(reactive_df)} rows")

    # Map TCR # to reactivity annotations
    # Column indices from inspection:
    #   [0] TCR #, [5] CDR3B
    #   [19] Reactive (activated...) — 'X' for reactive
    #   [20] Reactive (Melanocyte antigens) — 'X'
    #   [21] Reactive (Viral antigens) — 'X'
    #   [23] Reactive to Mart1 — 'X'
    #   [24] Reactive to gp100 — 'X'
    #   [26] RAPTR 10X Reactivity — epitope string
    reactive_col = [c for c in reactive_df.columns if 'Reactive (activated' in str(c)][0]
    melanocyte_col = [c for c in reactive_df.columns if 'Reactive (Melanocyte' in str(c)][0]
    viral_col = [c for c in reactive_df.columns if 'Reactive (Viral' in str(c)][0]
    mart1_col = [c for c in reactive_df.columns if 'Reactive to Mart1' in str(c)][0]
    gp100_col = [c for c in reactive_df.columns if 'Reactive to gp100' in str(c)][0]
    raptr_col = [c for c in reactive_df.columns if 'RAPTR 10X Reactivity' in str(c)][0]

    # Build lookup: TCR# -> reactivity info
    reactive_lookup = {}
    for _, row in reactive_df.iterrows():
        tcr_num = row['TCR #']
        if pd.isna(tcr_num):
            continue
        tcr_num = int(tcr_num)
        is_reactive = str(row[reactive_col]).strip() == 'X'
        if not is_reactive:
            continue

        is_melanocyte = str(row[melanocyte_col]).strip() == 'X'
        is_viral = str(row[viral_col]).strip() == 'X'
        is_mart1 = str(row[mart1_col]).strip() == 'X'
        is_gp100 = str(row[gp100_col]).strip() == 'X'
        raptr_epitope = row[raptr_col] if pd.notna(row[raptr_col]) else None

        # Determine category and epitope
        if is_melanocyte:
            category = 'melanocyte'
            if is_mart1:
                epitope = 'EAAGIGILTV'  # MART-1
                gene = 'MART-1'
            elif is_gp100:
                epitope = 'IMDQVPFSV'  # gp100
                gene = 'gp100'
            else:
                epitope = 'melanocyte_reactive'
                gene = 'melanocyte_antigen'
        elif is_viral:
            category = 'viral'
            epitope = 'viral_reactive'
            gene = 'viral_antigen'
        else:
            category = 'reactive_unclassified'
            epitope = 'reactive_unclassified'
            gene = None

        # Override with RAPTR 10X if specific epitope available
        if raptr_epitope and str(raptr_epitope).strip() not in ('', 'nan', 'X'):
            epitope = str(raptr_epitope).strip()

        reactive_lookup[tcr_num] = {
            'known_epitope': epitope,
            'epitope_gene': gene,
            'antigen_category': category,
            'reactive_melanocyte': is_melanocyte,
            'reactive_viral': is_viral,
            'reactive_mart1': is_mart1,
            'reactive_gp100': is_gp100,
        }

    print(f"  Reactive TCRs found: {len(reactive_lookup)}")

    # ── Parse "3808 - 10X-identified TCRs" ──────────────────────────────────
    tenx_df = pd.read_excel(TABLE_S2, sheet_name='3808 - 10X-identified TCRs', header=0)
    print(f"  10X-identified TCRs: {len(tenx_df)} entries")

    tenx_lookup = {}
    for _, row in tenx_df.iterrows():
        tcr_num = int(row['TCR #'])
        epitope = str(row['Epitope']).strip()
        tenx_lookup[tcr_num] = epitope

    # ── Apply annotations to TCRAFT DataFrame ───────────────────────────────
    # TCR # in TCRAFT corresponds to 1-indexed row order (TCRAFT_0001 = TCR #1)
    # But the original CDR3 table uses its own TCR numbering from column order
    # We need to match by the original file's row index
    # Read the original CDR3 table to get the TCR# mapping
    cdr3_file = GAGLIONE_REF / "All_3800_CDR3_table.csv"
    orig_df = pd.read_csv(cdr3_file)

    # The reactive sheet has TCR # which may be 1-indexed position in the 3808 table
    # Let's match by CDR3B since it's unique
    cdr3b_to_idx = {}
    for idx, row in orig_df.iterrows():
        cdr3b_to_idx[row['CDR3B']] = idx  # 0-indexed

    # Also build tcr_num to CDR3B from reactive sheet
    reactive_cdr3b_map = {}
    for _, row in reactive_df.iterrows():
        if pd.notna(row.get('TCR #')) and pd.notna(row.get('CDR3B')):
            reactive_cdr3b_map[int(row['TCR #'])] = row['CDR3B']

    # Apply reactive annotations by matching CDR3B
    n_annotated_reactive = 0
    for tcr_num, info in reactive_lookup.items():
        cdr3b = reactive_cdr3b_map.get(tcr_num)
        if cdr3b is None:
            continue
        # Find matching row in tcraft_df by CDR3b
        mask = tcraft_df['CDR3b'] == cdr3b
        if mask.any():
            for col, val in info.items():
                if col in ('reactive_melanocyte', 'reactive_viral', 'reactive_mart1', 'reactive_gp100'):
                    continue  # Skip boolean flags for now (not in schema)
                tcraft_df.loc[mask, col] = val
            n_annotated_reactive += mask.sum()

    # Apply 10X epitope annotations (more specific, override reactive if present)
    n_annotated_10x = 0
    for tcr_num, epitope in tenx_lookup.items():
        cdr3b = reactive_cdr3b_map.get(tcr_num)
        if cdr3b is None:
            # 10X TCRs might not be in the reactive sheet — try matching by TCR# position
            # The TCR# in the sheets corresponds to the row number in the 3808 table
            # The original table is 0-indexed, so TCR# X → index X-1? Or direct position?
            # From the data: TCR #2799 has CDR3B that appears in the 3808 table
            # Let's check: the 3808 table has 3808 rows, and TCR# goes up to 3808
            # TCR# likely corresponds to 1-indexed position
            if tcr_num <= len(orig_df):
                cdr3b = orig_df.iloc[tcr_num - 1]['CDR3B']
            else:
                continue
        mask = tcraft_df['CDR3b'] == cdr3b
        if mask.any():
            tcraft_df.loc[mask, 'known_epitope'] = epitope
            # Categorize the 10X epitope
            if epitope in ('ELAGIGILTV', 'EAAGIGILTV', 'AAGIGILTV'):
                tcraft_df.loc[mask, 'epitope_gene'] = 'MART-1'
                tcraft_df.loc[mask, 'antigen_category'] = 'melanocyte'
            elif epitope in ('IMDQVPFSV', 'ITDQVPFSV', 'YLEPGPVTA'):
                tcraft_df.loc[mask, 'epitope_gene'] = 'gp100'
                tcraft_df.loc[mask, 'antigen_category'] = 'melanocyte'
            elif epitope == 'NLVPMVATV':
                tcraft_df.loc[mask, 'epitope_gene'] = 'pp65'
                tcraft_df.loc[mask, 'epitope_species'] = 'CMV'
                tcraft_df.loc[mask, 'antigen_category'] = 'viral'
            elif epitope in ('VIWEVLNAV', 'MLAVISCAV', 'YLQLVFGIEV', 'FLWGPRALV',
                           'LLFGYPVYV', 'SLYNTVATL', 'FLWGPRAYA', 'SLLMWITQC',
                           'SLLMWITQCFL', 'LKLSGVVRL', 'KTWGQYWQV', 'FLPWHRLFL',
                           'AMAPIKVRL', 'ALSVMGVYV', 'SVYDFFVWL', 'KMVELVHFL',
                           'KVAELVHFL', 'LLAVLYCLL', 'MLMAQEALAFL', 'LLMEKEDYHSL'):
                tcraft_df.loc[mask, 'antigen_category'] = 'viral'
            else:
                # Default: keep whatever was set by reactive annotation
                pass
            n_annotated_10x += mask.sum()

    n_total_annotated = tcraft_df['known_epitope'].notna().sum()
    print(f"  Annotated via reactive sheet: {n_annotated_reactive}")
    print(f"  Annotated via 10X: {n_annotated_10x}")
    print(f"  Total TCRAFT TCRs with annotations: {n_total_annotated}")
    print(f"  TCRAFT dark matter remaining: {len(tcraft_df) - n_total_annotated} "
          f"({(len(tcraft_df) - n_total_annotated) / len(tcraft_df) * 100:.1f}%)")

    return tcraft_df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Process 30,810 PDAC tumor TCRs from Table S2
# ═══════════════════════════════════════════════════════════════════════════════

def process_pdac_tcrs(trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein):
    """
    Process 30,810 PDAC (pancreatic cancer) TCRs from Gaglione et al. 2026 Table S2.
    These are synthetic TCRs from PDAC tumor-infiltrating T cells.
    42 are NLV-reactive (CMV); the rest are dark matter.
    """
    if not TABLE_S2.exists():
        print(f"  WARNING: Table S2 not found, skipping PDAC TCRs")
        return pd.DataFrame()

    print("\n" + "="*70)
    print("Processing PDAC tumor TCRs (Gaglione et al. 2026 Table S2)")
    print("="*70)

    # Load main 30810 TCR sheet
    pdac_df = pd.read_excel(TABLE_S2, sheet_name='30810 TCRs', header=0)
    print(f"  Loaded {len(pdac_df)} PDAC TCRs")

    # Load NLV-reactive subset (header at row 1 — row 0 is title)
    nlv_df = pd.read_excel(TABLE_S2, sheet_name='30810 - NLV-reactive TCRs', skiprows=1)
    print(f"  NLV-reactive TCRs: {len(nlv_df)}")

    # Build set of NLV-reactive CDR3B for annotation
    nlv_cdr3b = set(nlv_df['CDR3B'].dropna().values)
    print(f"  NLV-reactive CDR3B sequences: {len(nlv_cdr3b)}")

    # Reconstruct full-length and build records
    results = []
    errors_count = 0
    for idx, row in pdac_df.iterrows():
        rec_row = {
            'TRAV': row['TRAV'], 'TRBV': row['TRBV'],
            'CDR3A': row['CDR3A'], 'CDR3B': row['CDR3B'],
            'TRAJ': row['TRAJ'], 'TRBJ': row['TRBJ'],
        }
        full_alpha, full_beta, err = reconstruct_full_length_tcr(
            rec_row, trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein
        )
        if err:
            errors_count += 1

        # Check if this TCR is NLV-reactive
        is_nlv = row['CDR3B'] in nlv_cdr3b

        results.append({
            'source': 'PDAC',
            'tcr_id': f"PDAC_{idx+1:05d}",
            'TRAV': row['TRAV'],
            'TRBV': row['TRBV'],
            'CDR3a': row['CDR3A'],
            'CDR3b': row['CDR3B'],
            'TRAJ': row['TRAJ'],
            'TRBJ': row['TRBJ'],
            'full_alpha_seq': full_alpha,
            'full_beta_seq': full_beta,
            'known_epitope': 'NLVPMVATV' if is_nlv else None,
            'epitope_gene': 'pp65' if is_nlv else None,
            'epitope_species': 'CMV' if is_nlv else None,
            'mhc_allele': None,
            'disease_context': 'PDAC',
            'antigen_category': 'viral' if is_nlv else None,
            'confidence_score': None,
            'reconstruction_error': err,
        })

    pdac_result_df = pd.DataFrame(results)

    n_alpha = pdac_result_df['full_alpha_seq'].notna().sum()
    n_beta = pdac_result_df['full_beta_seq'].notna().sum()
    n_nlv = pdac_result_df['known_epitope'].notna().sum()
    print(f"  Full-length reconstruction: {n_alpha} alpha, {n_beta} beta")
    print(f"  NLV-reactive annotated: {n_nlv}")
    print(f"  Dark matter: {len(pdac_result_df) - n_nlv}")
    print(f"  Reconstruction errors: {errors_count}")

    return pdac_result_df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: Process Gate et al. AD CSF TCRs (GSE134578)
# ═══════════════════════════════════════════════════════════════════════════════

def process_gate_ad_csf():
    """
    Process TCR data from Gate et al. 2020 Nature — Alzheimer's CSF T cells.
    Source: GEO GSE134578 (scRNA + scTCR from CSF and blood).

    These are clonally expanded CD8+ T cells found in AD patient CSF.
    All are dark matter — no known antigen specificities in the original paper.
    """
    gate_dir = EXTERNAL_DIR / "gate_ad_csf"
    if not gate_dir.exists():
        print(f"\n  Gate et al. AD CSF data not found at {gate_dir}, skipping")
        return pd.DataFrame()

    print("\n" + "="*70)
    print("Processing Gate et al. AD CSF TCRs (GSE134578)")
    print("="*70)

    # Load sample metadata if available
    meta_path = gate_dir / "sample_metadata.csv"
    sample_meta = {}
    if meta_path.exists():
        meta_df = pd.read_csv(meta_path)
        for _, row in meta_df.iterrows():
            csf_id = row.get('csf_id', '')
            sample_meta[csf_id] = {
                'condition': row.get('condition', 'unknown'),
                'condition_full': row.get('condition_full', ''),
            }
        print(f"  Sample metadata: {len(sample_meta)} samples")

    # Look for filtered_contig_annotations or clonotypes files
    contig_files = list(gate_dir.glob('**/*filtered_contig_annotations*'))
    clonotype_files = list(gate_dir.glob('**/*clonotypes*'))
    csv_files = list(gate_dir.glob('**/*.csv*'))
    tsv_files = list(gate_dir.glob('**/*.tsv*'))
    all_files = list(gate_dir.glob('**/*'))

    print(f"  Found {len(all_files)} files in {gate_dir}")
    print(f"  Contig files: {len(contig_files)}")
    print(f"  Clonotype files: {len(clonotype_files)}")
    print(f"  CSV files: {len(csv_files)}")
    print(f"  TSV files: {len(tsv_files)}")

    results = []

    # Strategy 1: filtered_contig_annotations (10X Genomics format)
    if contig_files:
        for fpath in contig_files:
            print(f"  Processing: {fpath.name}")
            try:
                if fpath.suffix == '.gz':
                    df = pd.read_csv(fpath, compression='gzip')
                else:
                    df = pd.read_csv(fpath)
            except Exception as e:
                print(f"    Error reading {fpath}: {e}")
                continue

            print(f"    Rows: {len(df)}, Columns: {list(df.columns)[:10]}")

            # Extract paired alpha+beta per clonotype/barcode
            if 'chain' in df.columns and 'cdr3' in df.columns:
                # Filter productive chains
                if 'productive' in df.columns:
                    df = df[df['productive'].isin([True, 'True', 'true'])].copy()

                # Get alpha and beta chains per barcode
                alpha = df[df['chain'] == 'TRA'][['barcode', 'cdr3', 'v_gene', 'j_gene']].copy()
                alpha.columns = ['barcode', 'CDR3a', 'TRAV', 'TRAJ']
                beta = df[df['chain'] == 'TRB'][['barcode', 'cdr3', 'v_gene', 'j_gene']].copy()
                beta.columns = ['barcode', 'CDR3b', 'TRBV', 'TRBJ']

                # Keep first chain per barcode if multiple
                alpha = alpha.drop_duplicates(subset='barcode', keep='first')
                beta = beta.drop_duplicates(subset='barcode', keep='first')

                # Merge to get paired TCRs
                paired = pd.merge(alpha, beta, on='barcode', how='outer')
                print(f"    Paired barcodes: {len(paired)}")

                # Extract sample name from filename
                sample_name = fpath.stem.replace('_filtered_contig_annotations', '')

                for idx, row in paired.iterrows():
                    cdr3b = row.get('CDR3b')
                    if pd.isna(cdr3b) or not cdr3b:
                        continue  # Need at least CDR3b for embedding

                    # Clean gene names (remove alleles)
                    trav = str(row.get('TRAV', '')).split('*')[0] if pd.notna(row.get('TRAV')) else None
                    trbv = str(row.get('TRBV', '')).split('*')[0] if pd.notna(row.get('TRBV')) else None
                    traj = str(row.get('TRAJ', '')).split('*')[0] if pd.notna(row.get('TRAJ')) else None
                    trbj = str(row.get('TRBJ', '')).split('*')[0] if pd.notna(row.get('TRBJ')) else None

                    results.append({
                        'source': 'AD_CSF',
                        'tcr_id': f"ADCSF_{len(results)+1:05d}",
                        'TRAV': trav,
                        'TRBV': trbv,
                        'CDR3a': row.get('CDR3a') if pd.notna(row.get('CDR3a')) else None,
                        'CDR3b': cdr3b,
                        'TRAJ': traj,
                        'TRBJ': trbj,
                        'full_alpha_seq': None,
                        'full_beta_seq': None,
                        'known_epitope': None,
                        'epitope_gene': None,
                        'epitope_species': None,
                        'mhc_allele': None,
                        'disease_context': 'Alzheimers',
                        'antigen_category': None,
                        'confidence_score': None,
                        'reconstruction_error': None,
                    })

    # Strategy 2: Try clonotypes files
    elif clonotype_files:
        for fpath in clonotype_files:
            print(f"  Processing clonotypes: {fpath.name}")
            try:
                if fpath.suffix == '.gz':
                    df = pd.read_csv(fpath, compression='gzip')
                else:
                    df = pd.read_csv(fpath)
            except Exception as e:
                print(f"    Error: {e}")
                continue

            print(f"    Rows: {len(df)}, Columns: {list(df.columns)[:10]}")
            # Clonotypes typically have cdr3s_aa, v/j genes
            for idx, row in df.iterrows():
                cdr3b = None
                cdr3a = None
                # Try to extract from combined columns
                if 'cdr3s_aa' in df.columns:
                    cdr3_str = str(row['cdr3s_aa'])
                    parts = cdr3_str.split(';')
                    for p in parts:
                        p = p.strip()
                        if p.startswith('TRB:'):
                            cdr3b = p.replace('TRB:', '')
                        elif p.startswith('TRA:'):
                            cdr3a = p.replace('TRA:', '')
                elif 'cdr3' in df.columns:
                    cdr3b = row['cdr3']

                if not cdr3b:
                    continue

                results.append({
                    'source': 'AD_CSF',
                    'tcr_id': f"ADCSF_{len(results)+1:05d}",
                    'TRAV': None,
                    'TRBV': None,
                    'CDR3a': cdr3a,
                    'CDR3b': cdr3b,
                    'TRAJ': None,
                    'TRBJ': None,
                    'full_alpha_seq': None,
                    'full_beta_seq': None,
                    'known_epitope': None,
                    'epitope_gene': None,
                    'epitope_species': None,
                    'mhc_allele': None,
                    'disease_context': 'Alzheimers',
                    'antigen_category': None,
                    'confidence_score': None,
                    'reconstruction_error': None,
                })

    # Strategy 3: Generic CSV/TSV
    elif csv_files or tsv_files:
        for fpath in (csv_files + tsv_files):
            print(f"  Trying generic file: {fpath.name}")
            try:
                sep = '\t' if fpath.suffix in ('.tsv', '.gz') and 'tsv' in fpath.name else ','
                if fpath.suffix == '.gz':
                    df = pd.read_csv(fpath, compression='gzip', sep=sep)
                else:
                    df = pd.read_csv(fpath, sep=sep)
                print(f"    Columns: {list(df.columns)[:10]}")
                print(f"    Rows: {len(df)}")
            except Exception as e:
                print(f"    Error: {e}")

    if not results:
        print("  No TCR data extracted from Gate et al. dataset")
        return pd.DataFrame()

    ad_df = pd.DataFrame(results)

    # Deduplicate by CDR3b (keep unique clonotypes)
    before = len(ad_df)
    ad_df = ad_df.drop_duplicates(subset=['CDR3b'], keep='first')
    print(f"  Total TCRs extracted: {before}")
    print(f"  Unique CDR3b clonotypes: {len(ad_df)}")
    # Re-index IDs after dedup
    ad_df['tcr_id'] = [f"ADCSF_{i+1:05d}" for i in range(len(ad_df))]

    return ad_df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: Process McPAS-TCR database
# ═══════════════════════════════════════════════════════════════════════════════

def process_mcpas(existing_cdr3b_set=None):
    """
    Process McPAS-TCR (pathology-associated TCR database).
    Source: Friedman lab, Weizmann Institute.

    Extract human entries with CDR3 beta, map pathology categories,
    and deduplicate against existing VDJdb entries.
    """
    mcpas_dir = EXTERNAL_DIR / "mcpas"
    if not mcpas_dir.exists():
        print(f"\n  McPAS-TCR data not found at {mcpas_dir}, skipping")
        return pd.DataFrame()

    print("\n" + "="*70)
    print("Processing McPAS-TCR (pathology-associated TCR database)")
    print("="*70)

    # Find McPAS file
    mcpas_files = list(mcpas_dir.glob('*.csv'))
    if not mcpas_files:
        mcpas_files = list(mcpas_dir.glob('*.tsv'))
    if not mcpas_files:
        print(f"  No CSV/TSV files found in {mcpas_dir}")
        return pd.DataFrame()

    mcpas_path = mcpas_files[0]
    print(f"  Loading: {mcpas_path.name}")

    # McPAS uses varied encodings; try common ones (utf-8-sig handles BOM)
    for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
        try:
            df = pd.read_csv(mcpas_path, encoding=encoding, low_memory=False)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    else:
        print(f"  Failed to read McPAS file with any encoding")
        return pd.DataFrame()

    print(f"  Total entries: {len(df)}")
    print(f"  Columns: {list(df.columns)[:15]}")

    # Filter for human entries
    species_col = None
    for c in df.columns:
        if 'species' in c.lower() or 'organism' in c.lower():
            species_col = c
            break

    if species_col:
        df_human = df[df[species_col].str.lower().str.contains('human', na=False)].copy()
        print(f"  Human entries: {len(df_human)}")
    else:
        df_human = df.copy()
        print(f"  No species column found, using all {len(df_human)} entries")

    # Find CDR3 beta column
    cdr3b_col = None
    for c in df_human.columns:
        cl = c.lower()
        if 'cdr3' in cl and ('beta' in cl or 'b' in cl or 'trb' in cl):
            cdr3b_col = c
            break
    if cdr3b_col is None:
        for c in df_human.columns:
            if 'cdr3' in c.lower():
                cdr3b_col = c
                break

    if cdr3b_col is None:
        print(f"  No CDR3 beta column found")
        return pd.DataFrame()

    # Filter for valid CDR3b
    df_human = df_human[df_human[cdr3b_col].notna() & (df_human[cdr3b_col] != '')].copy()
    print(f"  Entries with CDR3b: {len(df_human)}")

    # Find other relevant columns
    cdr3a_col = None
    for c in df_human.columns:
        cl = c.lower()
        if 'cdr3' in cl and ('alpha' in cl or 'a' in cl or 'tra' in cl) and c != cdr3b_col:
            cdr3a_col = c
            break

    epitope_col = None
    # Prefer 'Epitope.peptide' over generic 'antigen' matches
    for c in df_human.columns:
        if 'epitope' in c.lower() and 'peptide' in c.lower():
            epitope_col = c
            break
    if epitope_col is None:
        for c in df_human.columns:
            cl = c.lower()
            if 'epitope' in cl and 'id' not in cl and 'method' not in cl:
                epitope_col = c
                break

    pathology_col = None
    # Prefer 'Category' over 'Pathology' (Category is broader grouping)
    for c in df_human.columns:
        if c.lower() == 'category':
            pathology_col = c
            break
    if pathology_col is None:
        for c in df_human.columns:
            if 'pathology' in c.lower() or 'disease' in c.lower():
                pathology_col = c
                break

    trbv_col = None
    for c in df_human.columns:
        cl = c.lower()
        if ('trbv' in cl or ('v' in cl and 'beta' in cl)):
            trbv_col = c
            break

    trbj_col = None
    for c in df_human.columns:
        cl = c.lower()
        if ('trbj' in cl or ('j' in cl and 'beta' in cl)):
            trbj_col = c
            break

    print(f"  CDR3b col: {cdr3b_col}")
    print(f"  CDR3a col: {cdr3a_col}")
    print(f"  Epitope col: {epitope_col}")
    print(f"  Pathology col: {pathology_col}")
    print(f"  TRBV col: {trbv_col}")
    print(f"  TRBJ col: {trbj_col}")

    # Map McPAS pathology categories to our scheme
    def map_mcpas_category(pathology, epitope_str=''):
        if pd.isna(pathology):
            return 'other'
        p = str(pathology).lower()
        if any(v in p for v in ['virus', 'viral', 'influenza', 'cmv', 'hiv', 'ebv',
                                 'hepatitis', 'covid', 'sars', 'hcv', 'hbv']):
            return 'viral'
        if any(c in p for c in ['cancer', 'tumor', 'melanoma', 'leukemia', 'lymphoma',
                                 'carcinoma', 'neoplasm']):
            return 'cancer_associated'
        if any(a in p for a in ['autoimmune', 'diabetes', 'arthritis', 'lupus',
                                 'sclerosis', 'celiac', 'crohn']):
            return 'autoimmune'
        if any(b in p for b in ['bacteria', 'tuberculosis', 'mycobacter']):
            return 'bacterial'
        if 'alzheimer' in p or 'neurodegenerat' in p:
            return 'neurodegeneration'
        return 'other'

    # Build records
    results = []
    for idx, row in df_human.iterrows():
        cdr3b = str(row[cdr3b_col]).strip()
        if not cdr3b or cdr3b == 'nan':
            continue

        # Skip if already in VDJdb (dedup by CDR3b)
        if existing_cdr3b_set and cdr3b in existing_cdr3b_set:
            continue

        cdr3a = None
        if cdr3a_col and pd.notna(row.get(cdr3a_col)):
            cdr3a = str(row[cdr3a_col]).strip()
            if cdr3a in ('', 'nan'):
                cdr3a = None

        epitope = None
        if epitope_col and pd.notna(row.get(epitope_col)):
            ep = str(row[epitope_col]).strip()
            if ep and ep != 'nan':
                epitope = ep

        pathology = row.get(pathology_col, '') if pathology_col else ''
        category = map_mcpas_category(pathology, epitope or '')

        trbv = None
        if trbv_col and pd.notna(row.get(trbv_col)):
            trbv = str(row[trbv_col]).split('*')[0].strip()
            if trbv in ('', 'nan'):
                trbv = None

        trbj = None
        if trbj_col and pd.notna(row.get(trbj_col)):
            trbj = str(row[trbj_col]).split('*')[0].strip()
            if trbj in ('', 'nan'):
                trbj = None

        results.append({
            'source': 'McPAS',
            'tcr_id': f"McPAS_{len(results)+1:05d}",
            'TRAV': None,
            'TRBV': trbv,
            'CDR3a': cdr3a,
            'CDR3b': cdr3b,
            'TRAJ': None,
            'TRBJ': trbj,
            'full_alpha_seq': None,
            'full_beta_seq': None,
            'known_epitope': epitope,
            'epitope_gene': None,
            'epitope_species': None,
            'mhc_allele': None,
            'disease_context': str(pathology) if pd.notna(pathology) else None,
            'antigen_category': category if epitope else None,
            'confidence_score': None,
            'reconstruction_error': None,
        })

    mcpas_result_df = pd.DataFrame(results)

    # Deduplicate by CDR3b + epitope
    before = len(mcpas_result_df)
    if not mcpas_result_df.empty:
        mcpas_result_df = mcpas_result_df.drop_duplicates(
            subset=['CDR3b', 'known_epitope'], keep='first'
        )
        # Re-index IDs
        mcpas_result_df['tcr_id'] = [f"McPAS_{i+1:05d}" for i in range(len(mcpas_result_df))]

    print(f"  Total McPAS entries (after VDJdb dedup): {before}")
    print(f"  After CDR3b+epitope dedup: {len(mcpas_result_df)}")
    if not mcpas_result_df.empty:
        n_known = mcpas_result_df['known_epitope'].notna().sum()
        print(f"  With known epitope: {n_known}")
        if pathology_col:
            print(f"  Pathology categories:")
            for cat, count in mcpas_result_df['antigen_category'].value_counts().head(10).items():
                print(f"    {cat}: {count}")

    return mcpas_result_df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9: Compute summary statistics for the "data gap" visualization
# ═══════════════════════════════════════════════════════════════════════════════

def compute_data_gap_stats(combined_df):
    """Compute key statistics that quantify the TCR-antigen data gap."""
    print("\n" + "="*70)
    print("DATA GAP STATISTICS")
    print("="*70)

    tcraft = combined_df[combined_df['source'] == 'TCRAFT']
    vdjdb_paired = combined_df[combined_df['source'] == 'VDJdb']
    vdjdb_beta = combined_df[combined_df['source'] == 'VDJdb_beta_only']
    pdac = combined_df[combined_df['source'] == 'PDAC']
    ad_csf = combined_df[combined_df['source'] == 'AD_CSF']
    mcpas = combined_df[combined_df['source'] == 'McPAS']

    stats = {
        'tcraft_total': len(tcraft),
        'tcraft_with_known_antigen': int(tcraft['known_epitope'].notna().sum()),
        'tcraft_dark_matter': int(tcraft['known_epitope'].isna().sum()),
        'tcraft_dark_matter_pct': float(tcraft['known_epitope'].isna().mean() * 100) if len(tcraft) > 0 else 0,
        'vdjdb_paired_total': len(vdjdb_paired),
        'vdjdb_beta_only_total': len(vdjdb_beta),
        'vdjdb_unique_epitopes': int(combined_df[combined_df['source'].isin(['VDJdb', 'VDJdb_beta_only'])]['known_epitope'].nunique()),
        'pdac_total': len(pdac),
        'pdac_nlv_reactive': int(pdac['known_epitope'].notna().sum()) if len(pdac) > 0 else 0,
        'ad_csf_total': len(ad_csf),
        'mcpas_total': len(mcpas),
        'mcpas_with_epitope': int(mcpas['known_epitope'].notna().sum()) if len(mcpas) > 0 else 0,
        'source_distribution': combined_df['source'].value_counts().to_dict(),
        'category_distribution': combined_df[combined_df['antigen_category'].notna()]['antigen_category'].value_counts().to_dict(),
        'total_tcrs': len(combined_df),
        'total_with_known_antigen': int(combined_df['known_epitope'].notna().sum()),
        'total_dark_matter': int(combined_df['known_epitope'].isna().sum()),
        'total_dark_matter_pct': float(combined_df['known_epitope'].isna().mean() * 100),
        'total_unique_epitopes': int(combined_df['known_epitope'].nunique()),
    }

    print(f"  TCRAFT TCRs: {stats['tcraft_total']}")
    print(f"    Known antigen: {stats['tcraft_with_known_antigen']}")
    print(f"    Dark matter: {stats['tcraft_dark_matter']} ({stats['tcraft_dark_matter_pct']:.1f}%)")
    print(f"  VDJdb paired: {stats['vdjdb_paired_total']}")
    print(f"  VDJdb beta-only: {stats['vdjdb_beta_only_total']}")
    print(f"  VDJdb unique epitopes: {stats['vdjdb_unique_epitopes']}")
    print(f"  PDAC TCRs: {stats['pdac_total']} (NLV-reactive: {stats['pdac_nlv_reactive']})")
    print(f"  AD CSF TCRs: {stats['ad_csf_total']}")
    print(f"  McPAS TCRs: {stats['mcpas_total']} (with epitope: {stats['mcpas_with_epitope']})")
    print(f"  Total TCRs: {stats['total_tcrs']}")
    print(f"  Total with known antigen: {stats['total_with_known_antigen']}")
    print(f"  Overall dark matter: {stats['total_dark_matter_pct']:.1f}%")

    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  TCR Dark Matter Explorer — Data Processing Pipeline v2    ║")
    print("║  TCRAFT + VDJdb + PDAC + AD CSF + McPAS-TCR               ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # Load references
    trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein = load_references()

    # ── Process TCRAFT ────────────────────────────────────────────────────────
    tcraft_df = process_tcraft_tcrs(trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein)

    # ── Annotate TCRAFT with Table S2 reactivity ─────────────────────────────
    tcraft_df = annotate_tcraft_with_table_s2(tcraft_df)

    # ── Process VDJdb paired ──────────────────────────────────────────────────
    vdjdb_df = process_vdjdb(trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein)

    # ── Process VDJdb beta-only ───────────────────────────────────────────────
    vdjdb_beta_df = process_vdjdb_beta_only()

    # ── Process PDAC TCRs ─────────────────────────────────────────────────────
    pdac_df = process_pdac_tcrs(trav_seqs, trbv_seqs, trj_seqs, trac_protein, trbc2_protein)

    # ── Process Gate et al. AD CSF ────────────────────────────────────────────
    ad_csf_df = process_gate_ad_csf()

    # ── Process McPAS-TCR ─────────────────────────────────────────────────────
    # Build set of existing CDR3b for deduplication
    existing_cdr3b = set()
    for df in [tcraft_df, vdjdb_df, vdjdb_beta_df]:
        if not df.empty:
            existing_cdr3b.update(df['CDR3b'].dropna().values)
    mcpas_df = process_mcpas(existing_cdr3b_set=existing_cdr3b)

    # ── Combine all ───────────────────────────────────────────────────────────
    dfs = [tcraft_df, vdjdb_df, vdjdb_beta_df]
    if not pdac_df.empty:
        dfs.append(pdac_df)
    if not ad_csf_df.empty:
        dfs.append(ad_csf_df)
    if not mcpas_df.empty:
        dfs.append(mcpas_df)

    combined_df = pd.concat(dfs, ignore_index=True)
    print(f"\n  Combined database: {len(combined_df)} TCRs")
    print(f"  Sources: {combined_df['source'].value_counts().to_dict()}")

    # ── Compute stats ─────────────────────────────────────────────────────────
    stats = compute_data_gap_stats(combined_df)

    # ── Save outputs ──────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("Saving outputs")
    print("="*70)

    # Main database
    parquet_path = OUTPUT_DIR / "tcr_database.parquet"
    combined_df.to_parquet(parquet_path, index=False)
    print(f"  Saved: {parquet_path}")

    # Also save as CSV for easy inspection
    csv_path = OUTPUT_DIR / "tcr_database.csv"
    combined_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    # Save TCRAFT-only for embedding (smaller, faster)
    tcraft_embed_path = OUTPUT_DIR / "tcraft_for_embedding.csv"
    tcraft_df[['tcr_id', 'CDR3a', 'CDR3b', 'TRAV', 'TRBV', 'TRAJ', 'TRBJ',
               'full_alpha_seq', 'full_beta_seq']].to_csv(tcraft_embed_path, index=False)
    print(f"  Saved: {tcraft_embed_path}")

    # Save VDJdb paired for embedding
    vdjdb_embed_path = OUTPUT_DIR / "vdjdb_paired_for_embedding.csv"
    vdjdb_df[['tcr_id', 'CDR3a', 'CDR3b', 'TRAV', 'TRBV', 'known_epitope',
              'antigen_category', 'full_alpha_seq', 'full_beta_seq']].to_csv(vdjdb_embed_path, index=False)
    print(f"  Saved: {vdjdb_embed_path}")

    # Save stats
    stats_path = OUTPUT_DIR / "data_gap_stats.json"
    # Convert numpy types for JSON serialization
    clean_stats = {}
    for k, v in stats.items():
        if isinstance(v, (np.integer,)):
            clean_stats[k] = int(v)
        elif isinstance(v, (np.floating,)):
            clean_stats[k] = float(v)
        elif isinstance(v, dict):
            clean_stats[k] = {str(kk): int(vv) if isinstance(vv, (int, np.integer)) else float(vv) for kk, vv in v.items()}
        else:
            clean_stats[k] = v

    with open(stats_path, 'w') as f:
        json.dump(clean_stats, f, indent=2)
    print(f"  Saved: {stats_path}")

    print(f"\n✓ Processing complete! {len(combined_df)} total TCRs across {combined_df['source'].nunique()} sources")
    return combined_df


if __name__ == "__main__":
    combined_df = main()
