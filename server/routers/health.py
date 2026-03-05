"""
routers/health.py — GET /api/health
"""

from fastapi import APIRouter, Depends
from data.store import DataStore, get_store

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(store: DataStore = Depends(get_store)):
    return {"status": "ok", **store.status()}
