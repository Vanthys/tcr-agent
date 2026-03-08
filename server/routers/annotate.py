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
from core.worker import start_suggestion_job
from data.db import save_chat, load_chat, clear_chat, list_all_chats, append_followup
from data.store import DataStore, get_store
from services import claude, gemini, tools

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["annotate"])


class AnnotateRequest(BaseModel):
    tcr_id: str
    question: Optional[str] = None
    provider: str = "claude"
    force_refresh: bool = False  # if True, skip cache


class SuggestionRequest(BaseModel):
    tcr_id: str
    provider: str = "claude"
    suggestion: dict  # {type, label, reason, params}


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



    # ── Cache check (skip if force_refresh) ─────────────────────────────────
    if not request.force_refresh:
        cached = load_chat(request.tcr_id, request.provider)
        if cached:
            async def _cached_event_generator():
                payload = cached["payload"]
                # Instantly replay all steps — no artificial delay
                for step in payload.get("steps", []):
                    yield {"event": "step", "data": json.dumps(step)}
                # Send full text in one shot — no chunking animation
                text = payload.get("text", "")
                if text:
                    yield {"event": "text", "data": json.dumps(text)}
                    
                # Replay any followups
                for f in payload.get("followups", []):
                    yield {"event": "followup", "data": json.dumps(f)}
                    
                yield {"event": "cached", "data": json.dumps({"cached_at": cached["cached_at"]})}
                yield {"event": "done", "data": "{}"}
            return EventSourceResponse(_cached_event_generator())

    async def event_generator():
        tcr_metadata = _format_tcr_header(tcr_row, request.tcr_id) if tcr_row is not None else ""
        executor = tools.ToolExecutor(store)

        context_parts = [tcr_metadata]
        # Accumulate steps for caching
        accumulated_steps: list[dict] = []
        accumulated_text: list[str] = []

        def _track_step(step: str, data: dict) -> dict:
            event = _step_event(step, data)
            accumulated_steps.append({"step": step, **data})
            return event

        # 1. Explore (Neighbors)
        yield _track_step("neighbors", {"action": "EXPLORE", "label": "Neighbors", "detail": "Retrieving spatial nearest neighbors..."})
        try:
            n_res = executor.execute("search_neighbors", {"tcr_id": request.tcr_id, "k": 25})
            top_n = n_res.get("top_neighbors", [])
            context_parts.append(_format_neighbors(top_n))
            yield _track_step("neighbors", {"neighbors": top_n, "summary": f"Found {len(top_n)} neighbors in the UMAP space."})
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error("Neighbor search failed: %s", e)

        # 2. Score (Predictions)
        yield _track_step("predictions", {"action": "SCORE", "label": "Predictions", "detail": "Retrieving binding predictions..."})
        try:
            p_res = executor.execute("get_predictions", {"tcr_id": request.tcr_id})
            top_p = p_res.get("top_predictions", [])
            context_parts.append(_format_predictions(top_p))
            yield _track_step("predictions", {"top": top_p, "summary": f"Identified {len(top_p)} potential epitopes."})
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error("Prediction lookup failed: %s", e)

        # 3. Engineer (Mutagenesis)
        yield _track_step("mutagenesis", {"action": "ENGINEER", "label": "Mutagenesis", "detail": "Checking for mutation landscape..."})
        try:
            m_res = executor.execute("get_mutagenesis", {"tcr_id": request.tcr_id})
            if m_res.get("available"):
                context_parts.append(_format_mutagenesis(m_res))
                yield _track_step("mutagenesis", {**m_res, "summary": "Mutation landscape retrieved from cache."})
            else:
                context_parts.append("## Mutagenesis\nNo pre-computed mutation landscape exists for this TCR.")
                yield _track_step("mutagenesis", {"available": False, "summary": "No pre-computed landscape found."})
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error("Mutagenesis lookup failed: %s", e)

        full_context = "\n\n".join(context_parts)

        # 3b. Append any extra_context from previous suggestion jobs
        cached_for_extra = load_chat(request.tcr_id, request.provider)
        extra = []
        if cached_for_extra:
            extra = cached_for_extra["payload"].get("extra_context", [])
            if extra:
                full_context += "\n\n## Additional Context from Suggestion Jobs\n" + "\n\n".join(extra)

        # 4. Synthesize (LLM generation) — accumulate text for caching
        if request.provider == "gemini":
            provider_stream = gemini.stream_annotation(full_context=full_context, question=request.question)
        else:
            provider_stream = claude.stream_annotation(full_context=full_context, question=request.question)

        async for event_dict in provider_stream:
            # Extract text from JSON-encoded text events to accumulate for cache
            if event_dict.get("event") == "text":
                try:
                    accumulated_text.append(json.loads(event_dict["data"]))
                except Exception:
                    pass
            yield event_dict

        # Save completed session to cache
        try:
            save_chat(request.tcr_id, request.provider, {
                "steps": accumulated_steps,
                "text": "".join(accumulated_text),
                "extra_context": extra
            })
        except Exception as e:
            logger.error("Failed to save chat cache: %s", e)

        # Signal stream end
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())


@router.post("/annotate/suggestion")
async def dispatch_suggestion(
    request: SuggestionRequest,
    store: DataStore = Depends(get_store),
):
    """
    Executes a structured suggestion inline, then streams a brief LLM analysis of the result.
    Returns an SSE stream so the frontend JobCard can show the live text.
    """
    from core.worker import execute_suggestion_inline

    async def event_generator():
        try:
            sug_type = request.suggestion.get("type", "unknown")
            # 1. Execute the tool directly and get the raw string result
            yield _step_event("running", {"label": f"Running {sug_type}..."})
            result_snippet = await execute_suggestion_inline(request.tcr_id, request.provider, request.suggestion)
            
            # 2. Yield the raw result so the UI can display it immediately if needed
            yield _step_event("raw_result", {"snippet": result_snippet})
            
            # 3. Call the LLM to analyze this specific result inline
            yield _step_event("analyzing", {"label": "Analyzing findings..."})
            
            prompt = (
                f"You are a TCR analysis assistant. You just suggested the user run the tool `{sug_type}`.\n"
                f"The tool has finished running for TCR {request.tcr_id}.\n\n"
                f"Here are the raw results:\n```\n{result_snippet}\n```\n\n"
                "Please provide a very brief (2-3 sentences max) analysis of what these results mean "
                "in the context of this TCR. Be direct, do not use XML tags, just conversational markdown text."
            )
            
            if request.provider == "gemini":
                from services.gemini import analyze_tool_result_stream
            else:
                from services.claude import analyze_tool_result_stream
                
            accumulated_text = []
            async for chunk in analyze_tool_result_stream(prompt):
                 accumulated_text.append(chunk)
                 yield {"event": "text", "data": json.dumps(chunk)}
                 
            # Save this followup interaction to the cache!
            append_followup(request.tcr_id, request.provider, {
                "suggestion": request.suggestion,
                "result_snippet": result_snippet,
                "analysis": "".join(accumulated_text)
            })
                 
        except Exception as e:
            logger.error("Suggestion error: %s", e)
            yield {"event": "error", "data": json.dumps(f"Job failed: {str(e)}")}
            
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())


# ── Cache REST endpoints ─────────────────────────────────────────────────────────

@router.get("/annotate/cache/{tcr_id}")
def get_chat_cache_status(tcr_id: str, provider: str = "claude"):
    cached = load_chat(tcr_id, provider)
    if cached:
        return {"cached": True, "cached_at": cached["cached_at"]}
    return {"cached": False, "cached_at": None}


@router.get("/annotate/caches")
def get_all_chats():
    """Return all cached sessions, newest first (no payload body)."""
    return list_all_chats()


@router.delete("/annotate/cache/{tcr_id}")
def delete_chat_cache(tcr_id: str, provider: str = "claude"):
    clear_chat(tcr_id, provider)
    return {"ok": True}


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
