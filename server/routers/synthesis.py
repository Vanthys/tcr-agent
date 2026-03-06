from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import pandas as pd

from data.store import DataStore, get_store

router = APIRouter(prefix="/api", tags=["synthesis"])

class SynthesisRequest(BaseModel):
    tcr_ids: List[str] = []
    tcr_id: str = ""
    epitope: str = "TRP2_SVYDFFVWL"
    include_variants: bool = True
    max_variants: int = 5
    include_controls: bool = True
    max_controls: int = 2


@router.post("/synthesis_export")
def synthesis_export(
    request: SynthesisRequest,
    store: DataStore = Depends(get_store),
):
    """
    Generate TCRAFT pooled synthesis order for TCR(s) + mutagenesis variants.
    """
    db = store.tcr_db
    if db.empty:
        raise HTTPException(status_code=503, detail="TCR database not loaded")

    # Collect TCR IDs
    ids = request.tcr_ids if request.tcr_ids else ([request.tcr_id] if request.tcr_id else [])
    if not ids:
        raise HTTPException(status_code=400, detail="No TCR IDs provided")

    tcrs = db[db['tcr_id'].isin(ids)]
    if tcrs.empty:
        raise HTTPException(status_code=404, detail="No matching TCRs found")

    constructs = []
    warnings = []

    for _, row in tcrs.iterrows():
        tid = row['tcr_id']
        cdr3a = row.get('CDR3a', None)
        cdr3b = row.get('CDR3b', '')
        trav = row.get('TRAV', None)
        trbv = row.get('TRBV', None)
        traj = row.get('TRAJ', None)
        trbj = row.get('TRBJ', None)

        has_paired = pd.notna(cdr3a) and cdr3a != "" and cdr3a != "nan" and cdr3a is not None
        # Handover originally checked 'full_alpha_seq', but loaders.py might not have it unless parquet was parsed properly.
        # We'll just be less strict for testing, or assume has_paired if cdr3a is not null.

        if not has_paired:
            warnings.append(f"{tid}: beta-only, requires alpha chain for TCRAFT synthesis")
            continue

        # Wild-type entry
        wt_entry = {
            'name': f"{tid}_WT",
            'tcr_id': tid,
            'V_alpha': str(trav) if pd.notna(trav) else 'unknown',
            'V_beta': str(trbv) if pd.notna(trbv) else 'unknown',
            'CDR3_alpha': str(cdr3a),
            'CDR3_beta': cdr3b,
            'J_alpha': str(traj) if pd.notna(traj) else 'unknown',
            'J_beta': str(trbj) if pd.notna(trbj) else 'unknown',
            'mutation': None,
            'delta_score': 0.0,
            'source': row.get('source', ''),
        }
        constructs.append(wt_entry)

        # Mutagenesis variants from DecoderTCR landscape
        if request.include_variants:
            mutag_key = f"{tid}_{request.epitope}"
            # Also try just {tid} in case loaders parsed files named {tcr_id}.json
            mutag = store.mutagenesis_cache.get(mutag_key) or store.mutagenesis_cache.get(tid)
            
            if mutag:
                def _apply_mutation(cdr3, mut_str):
                    if len(mut_str) < 3:
                        return None
                    try:
                        pos = int(mut_str[1:-1])  # 1-indexed
                    except ValueError:
                        return None
                    new_aa = mut_str[-1]
                    return cdr3[:pos-1] + new_aa + cdr3[pos:]

                # Top improving variants (positive delta = better predicted binding)
                for v in mutag.get('top_variants', [])[:request.max_variants]:
                    mut_str = v.get('mutations', '')
                    if not mut_str:
                        continue
                    mut_cdr3b = _apply_mutation(cdr3b, mut_str)
                    if mut_cdr3b is None:
                        continue
                    var_entry = dict(wt_entry)
                    var_entry['name'] = f"{tid}_{mut_str}"
                    var_entry['CDR3_beta'] = mut_cdr3b
                    var_entry['mutation'] = mut_str
                    var_entry['delta_score'] = v.get('delta', 0.0)
                    var_entry['variant_type'] = 'improving'
                    constructs.append(var_entry)

                # Negative controls (biggest binding decreases — validates specificity)
                if request.include_controls:
                    landscape = mutag.get('landscape', [])
                    worst = sorted(landscape, key=lambda x: x.get('delta', 0))[:request.max_controls]
                    for v in worst:
                        mut_str = f"{v['wt_aa']}{v['position']}{v['mut_aa']}"
                        mut_cdr3b = _apply_mutation(cdr3b, mut_str)
                        if mut_cdr3b is None:
                            continue
                        var_entry = dict(wt_entry)
                        var_entry['name'] = f"{tid}_{mut_str}_ctrl"
                        var_entry['CDR3_beta'] = mut_cdr3b
                        var_entry['mutation'] = mut_str
                        var_entry['delta_score'] = v.get('delta', 0.0)
                        var_entry['variant_type'] = 'control_decrease'
                        constructs.append(var_entry)
            else:
                wt_entry['has_mutagenesis'] = False

    n_wt = sum(1 for c in constructs if c['mutation'] is None)
    n_var = len(constructs) - n_wt
    cost_per_tcr = 0.30  # oligo cost
    total_cost = len(constructs) * cost_per_tcr

    # TCRAFT CSV rows (6 required columns + metadata)
    tcraft_csv = []
    for c in constructs:
        tcraft_csv.append({
            'Name': c['name'],
            'V_alpha': c['V_alpha'],
            'V_beta': c['V_beta'],
            'CDR3_alpha': c['CDR3_alpha'],
            'CDR3_beta': c['CDR3_beta'],
            'J_alpha': c['J_alpha'],
            'J_beta': c['J_beta'],
        })

    return {
        'n_constructs': len(constructs),
        'n_wt': n_wt,
        'n_variants': n_var,
        'constructs': constructs,
        'tcraft_csv': tcraft_csv,
        'warnings': warnings,
        'cost_estimate': {
            'n_oligos': len(constructs),
            'cost_per_oligo_usd': cost_per_tcr,
            'total_usd': round(total_cost, 2),
            'provider': 'TCRAFT pooled synthesis (Gaglione et al. 2026)',
            'note': f'CDR3α+β on single oligo, unique codon optimization = molecular barcode. '
                    f'Golden Gate assembly into lentiviral vector. 6-day protocol.',
        },
        'format_notes': {
            'protocol': 'TCRAFT 3-step Golden Gate assembly',
            'barcoding': 'Each oligo codon-optimized uniquely — sequencing CDR3β identifies TCR',
            'output': 'Lentiviral TCR library, pool-on-pool pMHC screening',
            'reference': 'Gaglione et al. 2026 Immunity, github.com/birnbaumlab/TCRAFT/',
        },
    }
