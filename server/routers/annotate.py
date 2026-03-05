"""
routers/annotate.py — POST /api/annotate (SSE streaming)

Streams Claude's TCR analysis as Server-Sent Events.

SSE protocol used:
  data: <text chunk>\\n\\n      — normal text delta
  event: step\\ndata: <json>\\n\\n  — agent step markers (neighbors, predictions, etc.)
  event: done\\ndata: {}\\n\\n      — stream complete signal
  event: error\\ndata: <msg>\\n\\n  — error signal

Frontend consumes via fetch() + ReadableStream (not native EventSource,
since this is a POST).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from data.store import DataStore, get_store
from services import claude, gemini
from services.neighbors import NeighborService
from services.predictions import PredictionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["annotate"])


class AnnotateRequest(BaseModel):
    tcr_id: str
    question: Optional[str] = None
    provider: str = "claude"


@router.post("/annotate")
async def annotate(
    request: AnnotateRequest,
    store: DataStore = Depends(get_store),
):
    """
    Run the full TCR agent pipeline and stream results as SSE.

    Steps (each emits a `step` event before streaming its result):
      1. neighbors  — ESM-2 nearest neighbors
      2. predictions — DecoderTCR scores
      3. mutagenesis — CDR3 landscape (if available)
      4. synthesis   — LLM (Claude or Gemini) streaming annotation
    """
    # Validate TCR exists
    db = store.tcr_db
    if not db.empty:
        row = db[db["tcr_id"] == request.tcr_id]
        if row.empty:
            raise HTTPException(404, f"TCR '{request.tcr_id}' not found")
        tcr_row = row.iloc[0]
    else:
        tcr_row = None

    neighbor_svc = NeighborService(store)
    pred_svc = PredictionService(store)

    async def event_generator():
        context_parts: list[str] = []

        # ── Step 1: Neighbors ────────────────────────────────────────────────
        yield _step_event("neighbors", {"tcr_id": request.tcr_id, "status": "searching"})

        neighbors = neighbor_svc.find_neighbors(request.tcr_id)
        annotated = [n for n in neighbors if n.get("known_epitope")]

        yield _step_event("neighbors", {
            "neighbors": neighbors,
            "annotated_count": len(annotated),
            "summary": (
                f"Found {len(neighbors)} nearest neighbors; "
                f"{len(annotated)} have known epitope annotations."
            ),
        })

        if neighbors:
            context_parts.append(_format_neighbors(neighbors))

        # ── Step 2: Predictions ──────────────────────────────────────────────
        yield _step_event("predictions", {"tcr_id": request.tcr_id, "status": "scoring"})

        predictions = pred_svc.get_predictions(request.tcr_id)
        top_preds = predictions[:5] if predictions else []

        yield _step_event("predictions", {
            "predictions": predictions,
            "top": top_preds,
            "summary": (
                f"Retrieved {len(predictions)} DecoderTCR scores. "
                + (f"Top hit: {top_preds[0]['epitope_name']} ({top_preds[0]['interaction_score']:.4f})"
                   if top_preds else "No scores available.")
            ),
        })

        if predictions:
            context_parts.append(_format_predictions(predictions[:10]))

        # ── Step 3: Mutagenesis (optional) ──────────────────────────────────
        mutagenesis = store.mutagenesis_cache.get(request.tcr_id)
        if mutagenesis:
            yield _step_event("mutagenesis", {
                "available": True,
                "epitope": mutagenesis.get("epitope"),
                "wild_type_score": mutagenesis.get("wild_type_score"),
                "top_variants": mutagenesis.get("top_variants", [])[:3],
                "summary": f"Mutation landscape available for {mutagenesis.get('epitope', 'unknown epitope')}.",
            })
            context_parts.append(_format_mutagenesis(mutagenesis))
        else:
            yield _step_event("mutagenesis", {
                "available": False,
                "summary": "No pre-computed mutation landscape for this TCR.",
            })

        # ── TCR context ──────────────────────────────────────────────────────
        if tcr_row is not None:
            context_parts.insert(0, _format_tcr_header(tcr_row, request.tcr_id))

        full_context = "\n\n".join(context_parts)

        # ── Step 4: LLM streaming synthesis ──────────────────────────────
        yield _step_event("synthesis", {"status": "streaming", "provider": request.provider})

        if request.provider == "gemini":
            async for chunk in gemini.stream_annotation(full_context, request.question):
                yield {"data": chunk}
        else:
            async for chunk in claude.stream_annotation(full_context, request.question):
                yield {"data": chunk}

        # Signal stream end
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())


# ── Formatting helpers ────────────────────────────────────────────────────────

def _step_event(step: str, data: dict) -> dict:
    return {"event": "step", "data": json.dumps({"step": step, **data})}


def _format_tcr_header(row, tcr_id: str) -> str:
    parts = [f"TCR ID: {tcr_id}"]
    for col, label in [("CDR3b", "CDR3β"), ("CDR3a", "CDR3α"),
                        ("TRBV", "TRBV"), ("TRAV", "TRAV"),
                        ("source", "Source"), ("disease_context", "Disease"),
                        ("known_epitope", "Known epitope"),
                        ("antigen_category", "Antigen category")]:
        val = row.get(col)
        if val is not None and not _is_na(val):
            parts.append(f"{label}: {val}")
    return "\n".join(parts)


def _format_neighbors(neighbors: list[dict]) -> str:
    lines = ["## Nearest Neighbors (ESM-2 cosine similarity)"]
    for n in neighbors:
        ep = f" | epitope: {n['known_epitope']}" if n.get("known_epitope") else ""
        lines.append(
            f"  {n['tcr_id']} sim={n['similarity']:.3f}"
            f" src={n.get('source', '?')}{ep}"
        )
    return "\n".join(lines)


def _format_predictions(predictions: list[dict]) -> str:
    lines = ["## DecoderTCR Binding Predictions (top epitopes)"]
    for p in predictions:
        lines.append(
            f"  {p.get('epitope_name', '?')} "
            f"score={p.get('interaction_score', 0):.4f} "
            f"cat={p.get('epitope_category', '?')}"
        )
    return "\n".join(lines)


def _format_mutagenesis(m: dict) -> str:
    lines = [
        f"## In Silico CDR3 Mutation Landscape",
        f"Epitope: {m.get('epitope')} | Wild-type score: {m.get('wild_type_score')}",
        f"CDR3β: {m.get('cdr3b')}",
        "Top predicted variants (Δ = score change vs wild-type):",
    ]
    for v in m.get("top_variants", [])[:5]:
        lines.append(
            f"  {v.get('mutations')} → score {v.get('predicted_score'):.4f}"
            f" (Δ{v.get('delta', 0):+.4f}) — {v.get('note', 'hypothesis')}"
        )
    return "\n".join(lines)


def _is_na(val) -> bool:
    try:
        return pd.isna(val)
    except (TypeError, ValueError):
        return False
