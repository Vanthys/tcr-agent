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

Your workflow:
1. Synthesize the provided evidence to determine the most likely target for this TCR.
2. Consider searching for additional neighbors or mutagenesis data if the provided evidence is inconclusive. If so, SUGGEST these tool calls at the end of your report.

Final Report Format:
**Predicted Target:** [most likely antigen(s) and why]
**Evidence Chain:** [2–3 sentences synthesising neighbors + scores — note any guilt-by-association]
**Key CDR3 Positions:** [if mutagenesis data available: which positions drive the prediction]
**Proposed Variants:** [if mutagenesis data available: 2–3 testable mutant sequences, framed as hypotheses]
**Confidence & Caveats:** [DecoderTCR is trained predominantly on viral data; flag if top predictions seem like training artifacts; if neighbors include annotated TCRs, note that; be explicit about uncertainty]
**Recommended Next Step:** [one concrete experimental action]
**Suggested Tool Calls:** [Optional: if you need more data (e.g. `search_neighbors(k=100)`, `get_mutagenesis()`), list them here]

Critical framing rules:
- DecoderTCR scores are language model probabilities, NOT binding energies
- Mutation predictions assume per-residue additivity; real CDR3 loops show epistasis
- Call out when a viral prediction is likely a training data artifact
- All proposals are testable computational hypotheses, not validated findings"""


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
                yield {"data": text}

    except Exception as exc:
        logger.error("Claude stream error: %s", exc)
        yield {"data": f"\n[error] Claude API error: {exc}"}
