"""
services/claude.py — Claude API wrapper with async SSE streaming.

Uses the Anthropic async client to stream tokens as they arrive.
The router forwards these as SSE events directly to the browser.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from core.config import settings
from core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a highly analytical TCR scientist. You are investigating a specific T cell receptor (TCR).
You have been provided with pre-fetched data including structural nearest neighbors, predicted binding scores, and potentially an in silico mutagenesis landscape.

Your workflow MUST follow this exact XML structure:

<reasoning>
Briefly think step-by-step about the evidence. Consider:
- Do the neighbors strongly point to a specific disease/antigen?
- Are the predictions reliable (e.g., matching HLA restriction)?
- What is the most solid conclusion you can draw?
Keep this section brief (3-4 sentences). 
</reasoning>

<report>
Write a concise, punchy final report for the user. Do not use filler. Use markdown phrasing.
**Predicted Target:** [most likely antigen(s) and why]
**Evidence Chain:** [2-3 sentences synthesizing neighbors + scores. Be explicit if evidence is weak or strong.]
**Key Insights:** [Identify critical CDR3 traits or HLA restrictions based on neighbors.]
**Caveats:** [DecoderTCR is trained heavily on viral data; call out potential biases or missing data].
</report>

<suggestions>
[Optional] Only if you need more data (e.g. `search_neighbors(k=100)`, `get_mutagenesis()`).
List 1-2 concrete tool calls or experimental next steps. Frame them as bullet points.
</suggestions>

Critical rules:
- NEVER use XML tags inside the report.
- The <report> should be punchy and professional.
- Always include all three XML blocks.
"""


async def stream_annotation(
    full_context: str,
    question: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Yield dicts representing SSE events containing text chunks from Claude.
    """
    api_key = settings.anthropic_api_key
    if not api_key:
        yield {"data": "[error] ANTHROPIC_API_KEY is not set on the server."}
        return

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=api_key)

    user_message = (
        f"Investigate TCR using the provided context.\n"
        f"Context:\n{full_context}\n\n"
        f"Question: {question or 'Analyse this TCR and produce the structured hypothesis report. If the context is missing info, you can suggest tool calls.'}"
    )

    messages = [{"role": "user", "content": user_message}]

    try:
        # Before yielding text, yield the synthesis step indicator
        yield {
            "event": "step",
            "data": json.dumps({"step": "synthesis", "action": "SYNTHESIZE", "label": "Claude Synthesis", "provider": "claude"})
        }

        async with client.messages.stream(
            model=settings.claude_model,
            max_tokens=settings.llm_max_tokens,
            system=SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield {"event": "text", "data": json.dumps(text)}

    except Exception as exc:
        logger.error("Claude stream error: %s", exc)
        yield {"data": f"\n[error] Claude API error: {exc}"}
