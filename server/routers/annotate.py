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

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.config import settings
from data.store import DataStore, get_store
from services import claude, gemini, tools

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

    hero_path = settings.hero_dir / f"{request.tcr_id}.json"
    if hero_path.exists():
        async def _hero_event_generator():
            try:
                with open(hero_path) as f:
                    hero_data = json.load(f)
            except Exception as e:
                logger.error("Failed to load hero file: %s", e)
                hero_data = {}

            logs_path = settings.hero_dir / "agent_reasoning_logs.json"
            steps = []
            if logs_path.exists():
                try:
                    with open(logs_path) as f:
                        logs = json.load(f)
                    if request.tcr_id in logs:
                        steps = logs[request.tcr_id].get("steps", [])
                except Exception as e:
                    logger.error("Failed to load reasoning logs: %s", e)

            for step_data in steps:
                yield _step_event("legacy_step", step_data)
                await asyncio.sleep(step_data.get("duration_ms", 1000) / 1000.0)

            annotation = hero_data.get("annotation", "")
            chunk_size = 15
            for i in range(0, len(annotation), chunk_size):
                yield {"event": "text", "data": json.dumps(annotation[i:i+chunk_size])}
                await asyncio.sleep(0.03)

            yield {"event": "done", "data": "{}"}

        return EventSourceResponse(_hero_event_generator())

    async def event_generator():
        tcr_metadata = _format_tcr_header(tcr_row, request.tcr_id) if tcr_row is not None else ""
        executor = tools.ToolExecutor(store)

        context_parts = [tcr_metadata]

        # 1. Explore (Neighbors)
        yield _step_event("neighbors", {"action": "EXPLORE", "label": "Neighbors", "detail": "Retrieving spatial nearest neighbors..."})
        try:
            n_res = executor.execute("search_neighbors", {"tcr_id": request.tcr_id, "k": 25})
            top_n = n_res.get("top_neighbors", [])
            context_parts.append(_format_neighbors(top_n))
            # Yield results for the UI
            yield _step_event("neighbors", {"neighbors": top_n, "summary": f"Found {len(top_n)} neighbors in the UMAP space."})
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error("Neighbor search failed: %s", e)

        # 2. Score (Predictions)
        yield _step_event("predictions", {"action": "SCORE", "label": "Predictions", "detail": "Retrieving binding predictions..."})
        try:
            p_res = executor.execute("get_predictions", {"tcr_id": request.tcr_id})
            top_p = p_res.get("top_predictions", [])
            context_parts.append(_format_predictions(top_p))
            # Yield results for the UI
            yield _step_event("predictions", {"top": top_p, "summary": f"Identified {len(top_p)} potential epitopes."})
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error("Prediction lookup failed: %s", e)

        # 3. Engineer (Mutagenesis)
        yield _step_event("mutagenesis", {"action": "ENGINEER", "label": "Mutagenesis", "detail": "Checking for mutation landscape..."})
        try:
            m_res = executor.execute("get_mutagenesis", {"tcr_id": request.tcr_id})
            if m_res.get("available"):
                context_parts.append(_format_mutagenesis(m_res))
                # Yield results for the UI
                yield _step_event("mutagenesis", {**m_res, "summary": "Mutation landscape retrieved from cache."})
            else:
                context_parts.append("## Mutagenesis\nNo pre-computed mutation landscape exists for this TCR.")
                yield _step_event("mutagenesis", {"available": False, "summary": "No pre-computed landscape found."})
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error("Mutagenesis lookup failed: %s", e)

        full_context = "\n\n".join(context_parts)

        # 4. Synthesize (LLM generation)
        if request.provider == "gemini":
            provider_stream = gemini.stream_annotation(full_context=full_context, question=request.question)
        else:
            provider_stream = claude.stream_annotation(full_context=full_context, question=request.question)

        async for event_dict in provider_stream:
            yield event_dict

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
