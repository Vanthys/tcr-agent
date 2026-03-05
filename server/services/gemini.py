"""
services/gemini.py — Google Gemini API wrapper with async SSE streaming.

Uses the google-genai client to stream tokens as they arrive.
The router forwards these as SSE events directly to the browser.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from core.config import settings
from services.claude import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def stream_annotation(
    context: str,
    question: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Yield text chunks from Gemini as they stream.
    Each yielded value is a raw text delta (not yet SSE-formatted).
    The router wraps these in SSE events.
    """
    api_key = settings.gemini_api_key
    if not api_key:
        yield "[error] GEMINI_API_KEY is not set on the server."
        return

    user_message = (
        f"TCR Evidence Package:\n{context}\n\n"
        f"Question: {question or 'Analyse this TCR and produce the structured hypothesis report.'}"
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        
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
                yield chunk.text

    except Exception as exc:
        logger.error("Gemini streaming error: %s", exc)
        yield f"\n[error] Gemini API error: {exc}"
