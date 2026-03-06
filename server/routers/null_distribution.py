import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
import numpy as np

router = APIRouter(prefix="/api/null_distribution", tags=["null_distribution"])

# Paths match the new backend structure
DATA_DIR = Path("../data")
NULL_DIST_DIR = DATA_DIR / "predictions" / "null_distributions"

@router.get("/{epitope}")
def get_null_distribution(epitope: str):
    """Return pre-computed null distribution for an epitope."""
    # Basic validation to prevent path traversal
    if not epitope or "/" in epitope or "\\" in epitope:
        raise HTTPException(400, "Invalid epitope")
        
    null_file = NULL_DIST_DIR / f"null_distribution_{epitope}.json"
    
    if not null_file.exists():
        raise HTTPException(404, f"Null distribution not computed for {epitope}")
        
    with open(null_file) as f:
        data = json.load(f)
        
    # Extract just the scores for a compact response
    scores = [s['score'] for s in data.get('scores', [])]
    
    if not scores:
        return {
            'epitope': epitope,
            'n_scrambles': 0,
            'scores': []
        }
        
    return {
        'epitope': data.get('epitope', epitope),
        'n_scrambles': len(scores),
        'mean': data.get('mean_score', float(np.mean(scores))),
        'std': data.get('std_score', float(np.std(scores))),
        'scores': scores,
        'percentiles': {
            'p50': float(np.percentile(scores, 50)),
            'p90': float(np.percentile(scores, 90)),
            'p95': float(np.percentile(scores, 95)),
            'p99': float(np.percentile(scores, 99)),
            'max': float(max(scores)),
        }
    }
