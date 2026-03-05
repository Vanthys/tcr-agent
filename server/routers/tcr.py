"""
routers/tcr.py — GET /api/tcr/{tcr_id}

Returns full TCR detail: sequences, annotations, nearest neighbors (lazy cached),
and DecoderTCR predictions.
"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from data.store import DataStore, get_store
from services.neighbors import NeighborService
from services.predictions import PredictionService

router = APIRouter(prefix="/api", tags=["tcr"])


@router.get("/tcr/{tcr_id}")
def get_tcr_detail(
    tcr_id: str,
    store: DataStore = Depends(get_store),
):
    """
    Full TCR detail including lazy-cached nearest neighbors and predictions.
    """
    db = store.tcr_db
    if db.empty:
        raise HTTPException(status_code=503, detail="TCR database not loaded")

    row = db[db["tcr_id"] == tcr_id]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"TCR '{tcr_id}' not found")

    # Serialise row, replacing NaN with None
    tcr_dict: dict = row.iloc[0].where(row.iloc[0].notna(), None).to_dict()

    # Nearest neighbors (lazy cached)
    neighbor_svc = NeighborService(store)
    tcr_dict["nearest_neighbors"] = neighbor_svc.find_neighbors(tcr_id)

    # Predictions
    pred_svc = PredictionService(store)
    tcr_dict["predictions"] = pred_svc.get_predictions(tcr_id)

    return tcr_dict


@router.get("/epitope_distribution")
def get_epitope_distribution(store: DataStore = Depends(get_store)):
    svc = PredictionService(store)
    return svc.get_epitope_distribution()


@router.get("/category_summary")
def get_category_summary(store: DataStore = Depends(get_store)):
    svc = PredictionService(store)
    return svc.get_category_summary()
