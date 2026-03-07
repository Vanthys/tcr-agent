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
        store.umap_df = load_umap(umap_csv)
        
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
        store.umap_df = load_umap(new_umap_csv)
        
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
