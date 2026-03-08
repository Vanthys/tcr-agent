"""
services/gemini.py — Google Gemini API wrapper with async SSE streaming.

Uses the google-genai client to stream tokens as they arrive.
The router forwards these as SSE events directly to the browser.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from core.config import settings
from services.claude import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def stream_annotation(
    full_context: str,
    question: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Yield dicts representing SSE events containing text chunks from Gemini.
    """
    api_key = settings.gemini_api_key
    if not api_key:
        yield {"data": "[error] GEMINI_API_KEY is not set on the server."}
        return

    user_message = (
        f"Investigate TCR using the provided context.\n"
        f"Context:\n{full_context}\n\n"
        f"Question: {question or 'Analyse this TCR and produce the structured hypothesis report. If the context is missing info, you can suggest tool calls.'}"
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        
        # Signal UI that we are streaming synthesize text
        yield {
            "event": "step",
            "data": json.dumps({"step": "synthesis", "action": "SYNTHESIZE", "label": "Gemini Synthesis", "provider": "gemini"})
        }

        # We must use generate_content_stream for streaming tokens.
        # We configure the model with the system instruction.
        response = client.models.generate_content_stream(
            model=settings.gemini_model,
            contents=[user_message],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=settings.llm_max_tokens,
            )
        )
        
        # This is a synchronous generator in google-genai so we iterate over it.
        # (If an async generator method is officially supported, we can swap to await later)
        # However, FastAPI handles these nicely.
        for chunk in response:
            if chunk.text:
                yield {"event": "text", "data": json.dumps(chunk.text)}

    except Exception as exc:
        logger.error("Gemini streaming error: %s", exc)
        yield {"data": f"\n[error] Gemini API error: {exc}"}

async def analyze_tool_result_stream(prompt: str):
    """
    Stream a brief conversational analysis of a tool result.
    Does not use the heavy system prompt or JSON structure.
    """
    from core.config import settings
    # Ensure Gemini is initialized
    if not os.environ.get("GOOGLE_API_KEY"):
        genai.configure(api_key=settings.gemini_api_key)

    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = await model.generate_content_async(
            prompt,
            stream=True
        )

        async for chunk in response:
            if chunk.text:
                yield chunk.text

    except Exception as exc:
        logger.error("Gemini tools analysis error: %s", exc)
        yield f"\n\n*Error analyzing results: {str(exc)}*"
