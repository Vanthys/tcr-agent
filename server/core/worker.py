import asyncio
import logging
from enum import Enum
from typing import Dict, Any, Optional
import time
from uuid import uuid4
from pathlib import Path

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
_background: set = set()  # prevent GC of background asyncio tasks

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

async def _run_umap_transform(task_id: str, new_embeddings, new_metadata, progress_start: float = 0.1):
    # Iterative addition of new TCR embeddings
    import joblib
    import numpy as np
    import pandas as pd
    from data.loaders import load_umap
    from data.store import get_store
    from core.config import settings

    update_task_state(task_id, TaskState.RUNNING, progress=progress_start)
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
        update_task_state(task_id, TaskState.RUNNING, progress=max(progress_start + 0.1, 0.7))
        
        # Store ingested points in memory only (ephemeral — not persisted to disk)
        # NaN values from UMAP transform must be replaced with 0.0 for JSON serialization
        import math
        def _safe_float(v):
            f = float(v)
            return 0.0 if math.isnan(f) or math.isinf(f) else f

        n_points = len(emb_array)
        store = get_store()
        store.ingested_points = []
        for i in range(n_points):
            store.ingested_points.append({
                'id': new_metadata.get('tcr_ids', [f"new_tcr_{i}" for _ in range(n_points)])[i],
                'd1': _safe_float(coords_nd[i, 0]),
                'd2': _safe_float(coords_nd[i, 1]),
                'd3': _safe_float(coords_nd[i, 2]),
                'd4': _safe_float(coords_nd[i, 3]),
                'd5': _safe_float(coords_nd[i, 4]),
                'c': new_metadata.get('cdr3b', [''])[i],
                's': new_metadata.get('sources', ['user_upload'])[i],
                'e': new_metadata.get('known_epitopes', [None])[i],
                'a': new_metadata.get('antigen_categories', ['unknown'])[i],
                '_ingested': True,
            })

        update_task_state(task_id, TaskState.RUNNING, progress=0.9)
        update_task_state(task_id, TaskState.COMPLETED, progress=1.0, result=f"Added {n_points} new TCRs (ephemeral overlay).")
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error("UMAP Transform error: %s\n%s", exc, tb)
        print(f"[UMAP-TRANSFORM] FAILED:\n{tb}", flush=True)
        update_task_state(task_id, TaskState.FAILED, error=str(exc))

async def start_umap_recompute():
    task = create_task("UMAP Recompute")
    bg = asyncio.create_task(_run_umap_recompute(task.task_id))
    _background.add(bg)
    bg.add_done_callback(_background.discard)
    return task

async def start_umap_transform(new_embeddings, new_metadata):
    task = create_task("UMAP Transform (Iterative)")
    bg = asyncio.create_task(_run_umap_transform(task.task_id, new_embeddings, new_metadata))
    _background.add(bg)
    bg.add_done_callback(_background.discard)
    return task

async def _run_ingest_pipeline(task_id: str, file_name: str, file_content: bytes):
    """Ingest new TCRs by matching CDR3b to existing UMAP coordinates (no ESM-2/transform needed)."""
    import io
    import math
    import pandas as pd
    from data.store import get_store

    print(f"[INGEST] Pipeline STARTED for {file_name}", flush=True)
    update_task_state(task_id, TaskState.RUNNING, progress=0.1)
    try:
        content_str = file_content.decode('utf-8', errors='replace')

        if file_name.endswith('.fasta') or file_name.endswith('.fa') or content_str.startswith(">"):
            lines = content_str.splitlines()
            names, seqs, curr_name, curr_seq = [], [], "tcr_1", []
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

        import re
        VALID_AA = re.compile(r'^[ACDEFGHIKLMNPQRSTVWY]+$')
        df['CDR3b'] = df['CDR3b'].astype(str).str.upper().str.strip()
        df = df[df['CDR3b'].str.match(VALID_AA)].copy().reset_index(drop=True)

        if len(df) == 0:
            raise Exception("No valid CDR3b sequences found after filtering")

        update_task_state(task_id, TaskState.RUNNING, progress=0.3)

        # Look up UMAP coordinates by CDR3b match against existing dataset
        store = get_store()
        umap_df = store.umap_df
        if umap_df.empty:
            raise Exception("No UMAP data loaded — cannot match coordinates")

        # Build CDR3b → coords lookup from existing data
        cdr3_lookup = {}
        for _, row in umap_df.iterrows():
            cdr3 = row.get('CDR3b', '')
            if cdr3 and cdr3 not in cdr3_lookup:
                cdr3_lookup[cdr3] = row

        update_task_state(task_id, TaskState.RUNNING, progress=0.6)

        def _safe(v):
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                return None
            return v

        ingested = []
        matched = 0
        for _, row in df.iterrows():
            cdr3 = row['CDR3b']
            tcr_id = row.get('tcr_id', f"ingest_{file_name}_{len(ingested)}")
            ref = cdr3_lookup.get(cdr3)
            if ref is not None:
                matched += 1
                ingested.append({
                    'id': str(tcr_id),
                    'd1': float(ref.get('d1', 0)),
                    'd2': float(ref.get('d2', 0)),
                    'd3': float(ref.get('d3', 0)),
                    'd4': float(ref.get('d4', 0)),
                    'd5': float(ref.get('d5', 0)),
                    'c': cdr3,
                    's': _safe(row.get('source', 'user_upload')),
                    'e': _safe(row.get('known_epitope')),
                    'a': _safe(row.get('antigen_category', 'unknown')),
                    '_ingested': True,
                })
            else:
                print(f"[INGEST] No CDR3b match for {tcr_id} ({cdr3}) — skipping", flush=True)

        store.ingested_points = ingested
        print(f"[INGEST] Done: {matched}/{len(df)} matched, {len(df)-matched} unmatched", flush=True)

        update_task_state(task_id, TaskState.COMPLETED, progress=1.0,
                          result=f"Mapped {matched}/{len(df)} TCRs to UMAP coordinates.")

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error("Ingest pipeline error: %s\n%s", exc, tb)
        print(f"[INGEST] FAILED:\n{tb}", flush=True)
        update_task_state(task_id, TaskState.FAILED, error=str(exc))

async def start_ingest_pipeline(file_name: str, file_content: bytes):
    task = create_task(f"Ingest & Embed: {file_name}")
    print(f"[INGEST] Creating background task for {file_name}, task_id={task.task_id}", flush=True)
    loop = asyncio.get_running_loop()
    print(f"[INGEST] Got event loop: {loop}", flush=True)
    bg = asyncio.create_task(_run_ingest_pipeline(task.task_id, file_name, file_content))
    _background.add(bg)
    bg.add_done_callback(_background.discard)
    print(f"[INGEST] Background task created: {bg}", flush=True)
    return task
