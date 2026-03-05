"""
routers/mutagenesis.py — GET /api/mutagenesis/{tcr_id}

Serves pre-computed mutation landscape JSONs dropped into
predictions/mutagenesis/<tcr_id>.json by Oliver's pipeline.
Returns 404 if not yet available for a given TCR.
"""

from fastapi import APIRouter, Depends, HTTPException

from data.store import DataStore, get_store

router = APIRouter(prefix="/api", tags=["mutagenesis"])


@router.get("/mutagenesis/{tcr_id}")
def get_mutagenesis(
    tcr_id: str,
    store: DataStore = Depends(get_store),
):
    """
    Return pre-computed CDR3 mutation landscape for a TCR.
    404 = data not yet available (not an error — just not computed yet).
    """
    result = store.mutagenesis_cache.get(tcr_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Mutagenesis data not yet available for '{tcr_id}'",
        )
    return result
