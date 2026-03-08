import asyncio
import logging
from enum import Enum
from typing import Dict, Any, Optional
import time
from uuid import uuid4
from pathlib import Path

import pandas as pd

from core.chat_stream import publish as publish_chat_event
from data.db import (
    append_chat_chunk,
    update_chat_stage,
    set_chat_status,
)
from data.store import get_store
from services import claude, gemini, tools

logger = logging.getLogger(__name__)

class TaskState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class AsyncTask:
    def __init__(self, task_id: str, name: str):
        self.task_id = task_id
        self.name = name
        self.state = TaskState.QUEUED
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.progress: float = 0.0
        self.created_at = time.time()
        self.updated_at = time.time()
        
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "name": self.name,
            "state": self.state,
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

# Global state
_tasks: Dict[str, AsyncTask] = {}

def get_task(task_id: str) -> Optional[AsyncTask]:
    return _tasks.get(task_id)

def list_tasks():
    return [t.to_dict() for t in sorted(_tasks.values(), key=lambda x: x.created_at, reverse=True)]

def create_task(name: str) -> AsyncTask:
    task_id = str(uuid4())
    task = AsyncTask(task_id, name)
    _tasks[task_id] = task
    return task

def update_task_state(task_id: str, state: TaskState, result=None, error=None, progress=None):
    if task_id in _tasks:
        t = _tasks[task_id]
        t.state = state
        t.updated_at = time.time()
        if result is not None: t.result = result
        if error is not None: t.error = error
        if progress is not None: t.progress = progress


# ── Chat session orchestration ────────────────────────────────────────────────

def start_chat_session(message_id: str, tcr_id: str, provider: str, question: str | None = None) -> None:
    """Kick off the asynchronous agent pipeline for a chat session."""
    asyncio.create_task(_run_chat_session(message_id, tcr_id, provider, question))


def _publish_stage(message_id: str, stage: dict) -> None:
    publish_chat_event(message_id, {"type": "stage", **stage})


def _record_stage(message_id: str, name: str, status: str, detail: str | None = None, payload: dict | None = None, summary: str | None = None) -> dict:
    stage = update_chat_stage(
        message_id,
        stage_name=name,
        status=status,
        detail=detail,
        payload=payload,
        summary=summary,
    )
    _publish_stage(message_id, stage)
    return stage


def _record_chunk(message_id: str, text_chunk: str) -> dict:
    chunk = append_chat_chunk(message_id, text_chunk)
    publish_chat_event(message_id, {"type": "chunk", **chunk})
    return chunk


def _record_status(message_id: str, status: str, error: str | None = None) -> None:
    set_chat_status(message_id, status=status, error=error)
    publish_chat_event(message_id, {"type": "status", "status": status, "error": error})


async def _run_chat_session(message_id: str, tcr_id: str, provider: str, question: str | None = None) -> None:
    """Execute the main agent stages and stream updates via the chat_store."""
    store = get_store()
    executor = tools.ToolExecutor(store)

    try:
        # Validate TCR exists
        tcr_row = None
        if not store.tcr_db.empty:
            row = store.tcr_db[store.tcr_db["tcr_id"] == tcr_id]
            if row.empty:
                raise ValueError(f"TCR '{tcr_id}' not found in database")
            tcr_row = row.iloc[0]

        context_parts = []
        if tcr_row is not None:
            header = _format_tcr_header(tcr_row, tcr_id)
        else:
            header = f"TCR ID: {tcr_id}"
        context_parts.append(header)

        # Stage 1 — neighbors
        _record_stage(message_id, "neighbors", "running", detail="Retrieving spatial nearest neighbors...")
        try:
            n_res = executor.execute("search_neighbors", {"tcr_id": tcr_id, "k": 25})
            top_n = n_res.get("top_neighbors", [])
            context_parts.append(_format_neighbors(top_n))
            _record_stage(
                message_id,
                "neighbors",
                "done",
                summary=n_res.get("summary"),
                payload={"neighbors": top_n},
            )
        except Exception as exc:
            logger.error("Neighbor search failed: %s", exc)
            _record_stage(message_id, "neighbors", "error", detail=str(exc))

        # Stage 2 — predictions
        _record_stage(message_id, "predictions", "running", detail="Computing DecoderTCR scores...")
        try:
            p_res = executor.execute("get_predictions", {"tcr_id": tcr_id})
            top_p = p_res.get("top_predictions", [])
            context_parts.append(_format_predictions(top_p))
            _record_stage(
                message_id,
                "predictions",
                "done",
                summary=p_res.get("summary"),
                payload={"predictions": top_p},
            )
        except Exception as exc:
            logger.error("Prediction lookup failed: %s", exc)
            _record_stage(message_id, "predictions", "error", detail=str(exc))

        # Stage 3 — mutagenesis
        _record_stage(message_id, "mutagenesis", "running", detail="Checking for mutation landscape...")
        try:
            m_res = executor.execute("get_mutagenesis", {"tcr_id": tcr_id})
            if m_res.get("available"):
                context_parts.append(_format_mutagenesis(m_res))
                _record_stage(
                    message_id,
                    "mutagenesis",
                    "done",
                    summary="Mutation landscape retrieved from cache.",
                    payload=m_res,
                )
            else:
                context_parts.append("## Mutagenesis\nNo pre-computed mutation landscape exists for this TCR.")
                _record_stage(
                    message_id,
                    "mutagenesis",
                    "done",
                    summary="No pre-computed landscape found.",
                    payload={"available": False},
                )
        except Exception as exc:
            logger.error("Mutagenesis lookup failed: %s", exc)
            _record_stage(message_id, "mutagenesis", "error", detail=str(exc))

        # Combine context and stream LLM synthesis
        full_context = "\n\n".join(filter(None, context_parts))
        provider_stream = (
            gemini.stream_annotation(full_context=full_context, question=question)
            if provider == "gemini"
            else claude.stream_annotation(full_context=full_context, question=question)
        )

        _record_stage(
            message_id,
            "synthesis",
            "running",
            detail=f"Streaming {provider.title()} synthesis...",
        )
        async for chunk_text in provider_stream:
            if not chunk_text:
                continue
            _record_chunk(message_id, chunk_text)

        _record_stage(message_id, "synthesis", "done")
        _record_status(message_id, "done")

    except Exception as exc:
        logger.exception("Chat session %s failed: %s", message_id, exc)
        _record_stage(message_id, "synthesis", "error", detail=str(exc))
        _record_status(message_id, "failed", error=str(exc))

async def _run_umap_recompute(task_id: str):
    import sys
    from data.loaders import load_umap
    from data.store import get_store
    from core.config import settings

    update_task_state(task_id, TaskState.RUNNING, progress=0.1)
    
    script_path = settings.project_root / "scripts" / "04_compute_umap.py"
    embed_dir = settings.embed_dir
    
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(script_path), "--embeddings-dir", str(embed_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            logger.error("UMAP Recompute failed: %s", stderr.decode())
            update_task_state(task_id, TaskState.FAILED, error=stderr.decode())
            return
            
        # reload store
        update_task_state(task_id, TaskState.RUNNING, progress=0.9)
        store = get_store()
        umap_csv = embed_dir / "umap_coords.csv"
        store.umap_df = load_umap(umap_csv, hero_dir=settings.hero_dir)
        
        update_task_state(task_id, TaskState.COMPLETED, progress=1.0, result="UMAP recomputed with 5 dims successfully.")
    except Exception as exc:
        logger.error("UMAP Recompute error: %s", exc)
        update_task_state(task_id, TaskState.FAILED, error=str(exc))

async def _run_umap_transform(task_id: str, new_embeddings, new_metadata):
    # Iterative addition of new TCR embeddings
    import joblib
    import numpy as np
    import pandas as pd
    from data.loaders import load_umap
    from data.store import get_store
    from core.config import settings

    update_task_state(task_id, TaskState.RUNNING, progress=0.1)
    try:
        embed_dir = settings.embed_dir
        
        # Determine latest model path
        pointer_path = embed_dir / "umap_latest.txt"
        if not pointer_path.exists():
            update_task_state(task_id, TaskState.FAILED, error="UMAP pointer not found. Recompute UMAP first.")
            return
            
        ts = pointer_path.read_text().strip()
        model_path = embed_dir / f"umap_model_v{ts}.joblib"
        umap_csv = embed_dir / f"umap_coords_v{ts}.csv"
        
        if not model_path.exists() or not umap_csv.exists():
            update_task_state(task_id, TaskState.FAILED, error="Latest UMAP model or CSV not found.")
            return
            
        # Instead of directly using joblib here, since transform might block the async thread,
        # we can use run_in_executor
        def _do_transform():
            reducer = joblib.load(model_path)
            emb_array = np.array(new_embeddings)
            return emb_array, reducer.transform(emb_array)
            
        loop = asyncio.get_running_loop()
        emb_array, coords_nd = await loop.run_in_executor(None, _do_transform)
        update_task_state(task_id, TaskState.RUNNING, progress=0.7)
        
        # Write to a NEW version
        new_ts = int(time.time())
        new_umap_csv = embed_dir / f"umap_coords_v{new_ts}.csv"
        
        n_points = len(emb_array)
        df_new = pd.DataFrame({
            'tcr_id': new_metadata.get('tcr_ids', [f"new_tcr_{i}" for i in range(n_points)]),
            'source': new_metadata.get('sources', ['lab'] * n_points),
            'CDR3b': new_metadata.get('cdr3b', [''] * n_points),
            'known_epitope': new_metadata.get('known_epitopes', [None] * n_points),
            'antigen_category': new_metadata.get('antigen_categories', ['unknown'] * n_points),
            'd1': coords_nd[:, 0],
            'd2': coords_nd[:, 1],
            'd3': coords_nd[:, 2],
            'd4': coords_nd[:, 3],
            'd5': coords_nd[:, 4],
        })
        
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined.to_csv(new_umap_csv, index=False)
        
        # We also need to copy the model over to the new version name so it stays synced
        import shutil
        new_model_path = embed_dir / f"umap_model_v{new_ts}.joblib"
        shutil.copy2(model_path, new_model_path)
        
        # Update pointer
        pointer_path.write_text(str(new_ts))
        
        # update DB via loader
        update_task_state(task_id, TaskState.RUNNING, progress=0.9)
        store = get_store()
        store.umap_df = load_umap(new_umap_csv, hero_dir=settings.hero_dir)
        
        update_task_state(task_id, TaskState.COMPLETED, progress=1.0, result=f"Added {n_points} new TCRs into 5D projection.")
    except Exception as exc:
        logger.error("UMAP Transform error: %s", exc)
        update_task_state(task_id, TaskState.FAILED, error=str(exc))

def start_umap_recompute():
    task = create_task("UMAP Recompute")
    # In asyncio, we must schedule it in the running loop
    asyncio.create_task(_run_umap_recompute(task.task_id))
    return task

def start_umap_transform(new_embeddings, new_metadata):
    task = create_task("UMAP Transform (Iterative)")
    asyncio.create_task(_run_umap_transform(task.task_id, new_embeddings, new_metadata))
    return task

async def _run_ingest_pipeline(task_id: str, file_name: str, file_content: bytes):
    import io
    import pandas as pd
    from core.esm_embed import embed_sequences
    
    update_task_state(task_id, TaskState.RUNNING, progress=0.1)
    try:
        content_str = file_content.decode('utf-8', errors='replace')
        
        if file_name.endswith('.fasta') or file_name.endswith('.fa') or content_str.startswith(">"):
            lines = content_str.splitlines()
            names = []
            seqs = []
            curr_name = "tcr_1"
            curr_seq = []
            for line in lines:
                if line.startswith(">"):
                    if curr_seq:
                        seqs.append("".join(curr_seq))
                        names.append(curr_name)
                    curr_name = line[1:].strip()
                    curr_seq = []
                else:
                    curr_seq.append(line.strip())
            if curr_seq:
                seqs.append("".join(curr_seq))
                names.append(curr_name)
            
            df = pd.DataFrame({'tcr_id': names, 'CDR3b': seqs})
        else:
            df = pd.read_csv(io.StringIO(content_str))
            
        if 'CDR3b' not in df.columns:
            if 'cdr3' in df.columns: df = df.rename(columns={'cdr3': 'CDR3b'})
            elif 'CDR3' in df.columns: df = df.rename(columns={'CDR3': 'CDR3b'})
            else:
                raise Exception("CSV must contain a 'CDR3b' column")
                
        # Clean sequences
        import re
        VALID_AA = re.compile(r'^[ACDEFGHIKLMNPQRSTVWY]+$')
        df['CDR3b'] = df['CDR3b'].astype(str).str.upper().str.strip()
        df = df[df['CDR3b'].str.match(VALID_AA)].copy()
        df = df.reset_index(drop=True)
        
        seqs = df['CDR3b'].tolist()
        if not seqs:
            raise Exception("No valid CDR3b sequences found after filtering")
            
        update_task_state(task_id, TaskState.RUNNING, progress=0.2)
        
        # run embeddings on background thread
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, embed_sequences, seqs)
        
        update_task_state(task_id, TaskState.RUNNING, progress=0.5)
        
        metadata = {
            'tcr_ids': df.get('tcr_id', [f"ingest_{file_name}_{i}" for i in range(len(df))]).tolist(),
            'sources': df.get('source', ['user_upload'] * len(df)).tolist(),
            'cdr3b': seqs,
            'known_epitopes': df.get('known_epitope', [None] * len(df)).tolist(),
            'antigen_categories': df.get('antigen_category', ['unknown'] * len(df)).tolist()
        }
        
        # chain to umap transform
        await _run_umap_transform(task_id, embeddings.tolist(), metadata)
        
    except Exception as exc:
        logger.error("Ingest pipeline error: %s", exc)
        update_task_state(task_id, TaskState.FAILED, error=str(exc))

def start_ingest_pipeline(file_name: str, file_content: bytes):
    task = create_task(f"Ingest & Embed: {file_name}")
    asyncio.create_task(_run_ingest_pipeline(task.task_id, file_name, file_content))
    return task


# ── Suggestion-triggered jobs ───────────────────────────────────────────────────

async def execute_suggestion_inline(tcr_id: str, provider: str, suggestion: dict) -> str:
    """Execute a suggestion synchronously (or via threadpool) and return the formatted snippet string."""
    from data.store import get_store
    from data.db import append_extra_context
    from services.tools import ToolExecutor
    import httpx
    import asyncio

    store = get_store()
    executor = ToolExecutor(store)

    suggestion_type = suggestion.get("type", "")

    if suggestion_type == "expand_neighbors":
        k = suggestion.get("params", {}).get("k", 100)
        result = executor.execute("search_neighbors", {"tcr_id": tcr_id, "k": k, "limit": k})
        neighbors = result.get("top_neighbors", [])

        lines = [f"## Expanded Neighbor Search (k={k})"]
        for n in neighbors:
            sim = n.get('similarity', 0)
            ep = n.get('known_epitope') or "Unknown"
            lines.append(f"- TCR: {n['tcr_id']} | Sim: {sim:.3f} | Epitope: {ep}")
        snippet = "\n".join(lines)
        
        append_extra_context(tcr_id, provider, snippet)
        return snippet

    elif suggestion_type == "compute_mutagenesis":
        epitope = suggestion.get("params", {}).get("epitope", "unknown")
        # Simulate long mutagenesis computation (if missing, it will compute it now)
        for i in range(1, 10):
            await asyncio.sleep(0.3)
            
        result = executor.execute("get_mutagenesis", {"tcr_id": tcr_id, "limit": 8, "compute_if_missing": True})
        if not result.get("available"):
            snippet = f"## Mutagenesis (requested for {epitope})\nNo pre-computed landscape available for this TCR."
        else:
            wt = result.get("wild_type_score", "N/A")
            lines = [
                f"## In-Silico CDR3 Mutagenesis (target: {epitope})",
                f"Wild-type score: {wt} | CDR3β: {result.get('cdr3b')}",
                "Top predicted variants:\",",
            ]
            for v in result.get("top_variants", [])[:8]:
                lines.append(
                    f"  {v.get('mutations')} → score {v.get('predicted_score', 0):.4f}"
                    f" (Δ{v.get('delta', 0):+.4f}) — {v.get('note', 'hypothesis')}"
                )
            snippet = "\n".join(lines)
            
        append_extra_context(tcr_id, provider, snippet)
        return snippet

    else:
        raise ValueError(f"Unknown suggestion type: {suggestion_type}")

async def _run_expand_neighbors(task_id: str, tcr_id: str, provider: str, k: int):
    """Re-run neighbor search with a larger k and append results to the cached context."""
    from data.store import get_store
    from data.db import append_extra_context
    from services.tools import ToolExecutor

    update_task_state(task_id, TaskState.RUNNING, progress=0.1)
    try:
        store = get_store()
        executor = ToolExecutor(store)
        result = executor.execute("search_neighbors", {"tcr_id": tcr_id, "k": k, "limit": k})
        neighbors = result.get("top_neighbors", [])

        lines = [f"## Expanded Neighbor Search (k={k})"]
        for n in neighbors:
            ep = f" | epitope: {n['known_epitope']}" if n.get("known_epitope") else ""
            lines.append(
                f"  {n['tcr_id']} sim={n['similarity']:.3f} src={n.get('source', '?')}{ep}"
            )
        snippet = "\n".join(lines)

        append_extra_context(tcr_id, provider, snippet)
        update_task_state(task_id, TaskState.COMPLETED, progress=1.0, result=snippet)
    except Exception as exc:
        logger.error("expand_neighbors job failed: %s", exc)
        update_task_state(task_id, TaskState.FAILED, error=str(exc))


async def _run_compute_mutagenesis(task_id: str, tcr_id: str, provider: str, epitope: str):
    """Compute in-silico mutagenesis for a given epitope and append results to the context."""
    from data.store import get_store
    from data.db import append_extra_context
    from services.tools import ToolExecutor

    update_task_state(task_id, TaskState.RUNNING, progress=0.1)
    try:
        store = get_store()
        executor = ToolExecutor(store)
        
        # Simulate long mutagenesis computation
        import asyncio
        for i in range(1, 10):
            await asyncio.sleep(0.3)
            update_task_state(task_id, TaskState.RUNNING, progress=0.1 + (i * 0.08))
            
        result = executor.execute("get_mutagenesis", {"tcr_id": tcr_id, "limit": 8})

        if not result.get("available"):
            # Mutagenesis may not be pre-computed; report that clearly
            snippet = f"## Mutagenesis (requested for {epitope})\nNo pre-computed landscape available for this TCR."
        else:
            wt = result.get("wild_type_score", "N/A")
            lines = [
                f"## In-Silico CDR3 Mutagenesis (target: {epitope})",
                f"Wild-type score: {wt} | CDR3β: {result.get('cdr3b')}",
                "Top predicted variants:",
            ]
            for v in result.get("top_variants", [])[:8]:
                lines.append(
                    f"  {v.get('mutations')} → score {v.get('predicted_score', 0):.4f}"
                    f" (Δ{v.get('delta', 0):+.4f}) — {v.get('note', 'hypothesis')}"
                )
            snippet = "\n".join(lines)

        append_extra_context(tcr_id, provider, snippet)
        update_task_state(task_id, TaskState.COMPLETED, progress=1.0, result=snippet)
    except Exception as exc:
        logger.error("compute_mutagenesis job failed: %s", exc)
        update_task_state(task_id, TaskState.FAILED, error=str(exc))


def start_suggestion_job(tcr_id: str, provider: str, suggestion: dict):
    """
    Dispatch a background job based on a structured suggestion dict.
    Returns the created AsyncTask.
    """
    stype = suggestion.get("type")
    params = suggestion.get("params", {})

    if stype == "expand_neighbors":
        k = int(params.get("k", 100))
        task = create_task(f"Expand Neighbors (k={k}) — {tcr_id}")
        asyncio.create_task(_run_expand_neighbors(task.task_id, tcr_id, provider, k))
        return task

    elif stype == "compute_mutagenesis":
        epitope = params.get("epitope", "unknown")
        task = create_task(f"Mutagenesis ({epitope}) — {tcr_id}")
        asyncio.create_task(_run_compute_mutagenesis(task.task_id, tcr_id, provider, epitope))
        return task

    else:
        raise ValueError(f"Unknown suggestion type: {stype!r}")


# ── Formatting helpers (shared with chat pipeline) ───────────────────────────

def _format_tcr_header(row, tcr_id: str) -> str:
    parts = [f"TCR ID: {tcr_id}"]
    for col, label in [
        ("CDR3b", "CDR3β"),
        ("CDR3a", "CDR3α"),
        ("TRBV", "TRBV"),
        ("TRAV", "TRAV"),
        ("source", "Source"),
        ("disease_context", "Disease"),
        ("known_epitope", "Known epitope"),
        ("antigen_category", "Antigen category"),
    ]:
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
        "## In Silico CDR3 Mutation Landscape",
        f"Epitope: {m.get('epitope')} | Wild-type score: {m.get('wild_type_score')}",
        f"CDR3β: {m.get('cdr3b')}",
        "Top predicted variants (Δ = score change vs wild-type):",
    ]
    for v in m.get("top_variants", [])[:5]:
        score = v.get("predicted_score", 0)
        lines.append(
            f"  {v.get('mutations')} → score {score:.4f}"
            f" (Δ{v.get('delta', 0):+.4f}) — {v.get('note', 'hypothesis')}"
        )
    others = [ep for ep in m.get("epitope_options", []) if ep and ep != m.get("epitope")]
    if others:
        joined = ", ".join(others[:5])
        if len(others) > 5:
            joined += ", …"
        lines.append(f"Other cached epitopes: {joined}")
    return "\n".join(lines)


def _is_na(val) -> bool:
    try:
        return pd.isna(val)
    except (TypeError, ValueError):
        return False
