"""
routers/mutagenesis.py — GET /api/mutagenesis/{tcr_id}

Serves pre-computed mutation landscape JSONs dropped into
predictions/mutagenesis/<tcr_id>.json by Oliver's pipeline.
Returns 404 if not yet available for a given TCR.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from data.store import DataStore, get_store

router = APIRouter(prefix="/api", tags=["mutagenesis"])


@router.get("/mutagenesis/{tcr_id}")
def get_mutagenesis(
    tcr_id: str,
    epitope: Optional[str] = None,
    store: DataStore = Depends(get_store),
):
    """
    Return pre-computed CDR3 mutation landscapes for a TCR.

    When `epitope` is provided we return that specific landscape; otherwise we
    return all entries so the client can render epitope tabs. 404 indicates the
    requested TCR (or epitope) has not been pre-computed yet.
    """
    entries = store.mutagenesis_cache.get(tcr_id)
    if not entries:
        raise HTTPException(
            status_code=404,
            detail=f"Mutagenesis data not yet available for '{tcr_id}'",
        )

    if epitope:
        landscape = entries.get(epitope)
        if landscape is None:
            raise HTTPException(
                status_code=404,
                detail=f"Mutagenesis data not yet available for '{tcr_id}' targeting '{epitope}'",
            )
        return landscape

    ordered = sorted(
        entries.values(),
        key=lambda x: x.get("wild_type_score", 0),
        reverse=True,
    )
    return {
        "tcr_id": tcr_id,
        "epitope_count": len(ordered),
        "entries": ordered,
    }
