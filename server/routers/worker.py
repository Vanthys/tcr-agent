from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Any, Dict, List
from pydantic import BaseModel

from core.worker import (
    get_task,
    list_tasks,
    start_umap_recompute,
    start_umap_transform,
    start_ingest_pipeline,
)

router = APIRouter(prefix="/api/worker", tags=["worker"])

class UmapTransformRequest(BaseModel):
    embeddings: List[List[float]]
    metadata: Dict[str, Any]

@router.get("/status")
def get_all_tasks():
    return list_tasks()

@router.get("/status/{task_id}")
def get_task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()

@router.post("/umap/compute")
def trigger_umap_recompute():
    task = start_umap_recompute()
    return {"message": "Task queued", "task_id": task.task_id}

@router.post("/umap/transform")
def trigger_umap_transform(req: UmapTransformRequest):
    if not req.embeddings:
        raise HTTPException(status_code=400, detail="Must provide embeddings")
    task = start_umap_transform(req.embeddings, req.metadata)
    return {"message": "Task queued", "task_id": task.task_id}

@router.post("/ingest")
async def handle_data_ingest(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
        
    task = start_ingest_pipeline(file.filename, content)
    return {"message": "Ingestion pipeline queued", "task_id": task.task_id}
