"""
routers/chat.py — resilient agent chat endpoints with stage logging.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.chat_stream import subscribe, unsubscribe
from core.worker import start_chat_session
from data.db import (
    append_followup,
    create_chat_message_record,
    delete_chat_message,
    get_chat_message,
    list_chat_messages,
)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatCreateRequest(BaseModel):
    tcr_id: str
    provider: str = "claude"
    question: Optional[str] = None


@router.post("/chat")
async def create_chat_session(req: ChatCreateRequest):
    message = create_chat_message_record(req.tcr_id, req.provider)
    start_chat_session(message["message_id"], req.tcr_id, req.provider, req.question)
    return {
        "message_id": message["message_id"],
        "status": message["status"],
        "tcr_id": message["tcr_id"],
        "provider": message["provider"],
    }


@router.get("/chat/{message_id}")
def get_chat_snapshot(message_id: str):
    message = get_chat_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return message


@router.get("/chat")
def list_recent_chats(limit: int = 25):
    return list_chat_messages(limit=limit)


@router.delete("/chat/{message_id}")
def remove_chat(message_id: str):
    delete_chat_message(message_id)
    return {"ok": True}


@router.get("/chat/{message_id}/stream")
async def stream_chat(message_id: str):
    message = get_chat_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Chat session not found")

    async def event_generator():
        data = message.get("data", {})
        stages = data.get("stages", {})
        for name in data.get("stage_order", []):
            stage = stages.get(name)
            if stage:
                yield {"event": "stage", "data": json.dumps(stage)}
        for chunk in data.get("chunks", []):
            yield {"event": "chunk", "data": json.dumps(chunk)}
        if message.get("status") != "running":
            yield {
                "event": "status",
                "data": json.dumps({"status": message["status"], "error": message.get("error")}),
            }

        queue = await subscribe(message_id)
        try:
            while True:
                event = await queue.get()
                payload = {k: v for k, v in event.items() if k != "type"}
                yield {"event": event["type"], "data": json.dumps(payload)}
        except asyncio.CancelledError:
            raise
        finally:
            await unsubscribe(message_id, queue)

    return EventSourceResponse(event_generator())


class SuggestionRequest(BaseModel):
    tcr_id: str
    provider: str = "claude"
    suggestion: dict


@router.post("/chat/suggestion")
async def dispatch_suggestion(req: SuggestionRequest):
    """Run a structured suggestion tool inline and stream its analysis."""
    from core.worker import execute_suggestion_inline

    async def event_generator():
        try:
            sug_type = req.suggestion.get("type", "unknown")
            yield _step_event("running", {"label": f"Running {sug_type}..."})
            result_snippet = await execute_suggestion_inline(req.tcr_id, req.provider, req.suggestion)

            yield _step_event("raw_result", {"snippet": result_snippet})
            yield _step_event("analyzing", {"label": "Analyzing findings..."})

            prompt = (
                f"You are a TCR analysis assistant. You just suggested the user run the tool `{sug_type}`.\n"
                f"The tool has finished running for TCR {req.tcr_id}.\n\n"
                f"Here are the raw results:\n```\n{result_snippet}\n```\n\n"
                "Please provide a very brief (2-3 sentences max) analysis of what these results mean "
                "in the context of this TCR. Be direct, do not use XML tags, just conversational markdown text."
            )

            if req.provider == "gemini":
                from services.gemini import analyze_tool_result_stream
            else:
                from services.claude import analyze_tool_result_stream

            accumulated_text: list[str] = []
            async for chunk in analyze_tool_result_stream(prompt):
                accumulated_text.append(chunk)
                yield {"event": "text", "data": json.dumps(chunk)}

            append_followup(req.tcr_id, req.provider, {
                "suggestion": req.suggestion,
                "result_snippet": result_snippet,
                "analysis": "".join(accumulated_text),
            })

        except Exception as exc:
            yield {"event": "error", "data": json.dumps(f"Job failed: {exc}")}
        finally:
            yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())


def _step_event(step: str, data: dict) -> dict:
    return {"event": "step", "data": json.dumps({"step": step, **data})}
