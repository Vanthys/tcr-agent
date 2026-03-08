"""
services/claude.py — Claude API wrapper with async SSE streaming.

Uses the Anthropic async client to stream tokens as they arrive.
The router forwards these as SSE events directly to the browser.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

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
If you recommend further investigation, output a JSON array. Each suggestion MUST follow this exact schema:
[
  {
    "type": "expand_neighbors",
    "label": "Expand neighbor search (k=100)",
    "reason": "The current 25-neighbor window may miss rare disease-specific TCRs. Widening to 100 would improve cluster confidence.",
    "params": {"k": 100}
  },
  {
    "type": "compute_mutagenesis",
    "label": "Compute CDR3 mutation landscape for FLRGRAYGL",
    "reason": "This epitope has the highest predicted binding score. Mutagenesis would reveal which CDR3 positions are critical for specificity.",
    "params": {"epitope": "FLRGRAYGL"}
  }
]
Supported types: expand_neighbors, compute_mutagenesis.
If no further investigation is needed, output an empty array: []
</suggestions>

Critical rules:
- NEVER use XML tags inside the report.
- The <report> should be punchy and professional.
- Always include all three XML blocks.
- The <suggestions> block MUST contain ONLY valid JSON — no markdown, no extra text.
"""


async def stream_annotation(
    full_context: str,
    question: str | None = None,
) -> AsyncGenerator[str, None]:
    """Yield raw text chunks from Claude for the synthesis stage."""
    api_key = settings.anthropic_api_key
    if not api_key:
        yield "[error] ANTHROPIC_API_KEY is not set on the server."
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
        async with client.messages.stream(
            model=settings.claude_model,
            max_tokens=settings.llm_max_tokens,
            system=SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    except Exception as exc:
        logger.error("Claude stream error: %s", exc)
        yield f"\n[error] Claude API error: {exc}"

async def analyze_tool_result_stream(prompt: str):
    """
    Stream a brief conversational analysis of a tool result.
    Does not use the heavy system prompt or XML structure.
    """
    from core.config import settings
    from anthropic import AsyncAnthropic
    import httpx
    # Use standard httpx client config to match main annotate
    client = AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        http_client=httpx.AsyncClient(timeout=60.0, limits=httpx.Limits(max_keepalive_connections=50))
    )
    
    messages = [{"role": "user", "content": prompt}]
    
    try:
        async with client.messages.stream(
            model=settings.claude_model,
            max_tokens=600,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as exc:
        logger.error("Claude tools analysis error: %s", exc)
        yield f"\n\n*Error analyzing results: {str(exc)}*"
