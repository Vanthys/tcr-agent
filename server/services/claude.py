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
You are an autonomous TCR scientist embedded in an AI agent pipeline.
You have been given a single T cell receptor (TCR) and a structured evidence chain assembled by the agent:
  1. ESM-2 embedding neighbors — TCRs with structurally similar CDR3 sequences
  2. DecoderTCR binding scores — predicted affinity against 14 HLA-A*02:01 epitopes
  3. An optional in silico CDR3 mutation landscape

Your task is to produce a structured hypothesis report. Be concise and direct. Use this format:

**Predicted Target:** [most likely antigen(s) and why]
**Evidence Chain:** [2–3 sentences synthesising neighbors + scores — note any guilt-by-association]
**Key CDR3 Positions:** [if mutagenesis data available: which positions drive the prediction]
**Proposed Variants:** [if mutagenesis data available: 2–3 testable mutant sequences, framed as hypotheses]
**Confidence & Caveats:** [DecoderTCR is trained predominantly on viral data; flag if top predictions seem like training artifacts; if neighbors include annotated TCRs, note that; be explicit about uncertainty]
**Recommended Next Step:** [one concrete experimental action]

Critical framing rules:
- DecoderTCR scores are language model probabilities, NOT binding energies
- Mutation predictions assume per-residue additivity; real CDR3 loops show epistasis
- Call out when a viral prediction is likely a training data artifact
- All proposals are testable computational hypotheses, not validated findings"""


async def stream_annotation(
    context: str,
    question: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Yield text chunks from Claude as they stream.
    Each yielded value is a raw text delta (not yet SSE-formatted).
    The router wraps these in SSE events.
    """
    api_key = settings.anthropic_api_key
    if not api_key:
        yield "[error] ANTHROPIC_API_KEY is not set on the server."
        return

    user_message = (
        f"TCR Evidence Package:\n{context}\n\n"
        f"Question: {question or 'Analyse this TCR and produce the structured hypothesis report.'}"
    )

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        async with client.messages.stream(
            model=settings.claude_model,
            max_tokens=settings.llm_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    except Exception as exc:
        logger.error("Claude streaming error: %s", exc)
        yield f"\n[error] Claude API error: {exc}"
