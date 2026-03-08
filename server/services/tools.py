"""
services/tools.py — Modular tools for the TCR agent.

These tools wrap the underlying services (Neighbors, Predictions) into
standalone functions that return clean JSON-serializable dictionaries.
They are decoupled from the LLM execution loop, meaning they can be
used directly by the native Python loop OR exposed via an MCP server later.
"""

from typing import Any, Dict, List

from data.store import DataStore
from services.neighbors import NeighborService
from services.predictions import PredictionService


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Return the JSON Schema definitions for the available tools."""
    return [
        {
            "name": "search_neighbors",
            "description": "Search the ESM-2 latent space for TCRs with similar CDR3 sequences. Use this to find structurally similar TCRs that might share target epitopes. Returns the top k nearest neighbors and their known metadata.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tcr_id": {
                        "type": "string",
                        "description": "The target TCR ID to find neighbors for."
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of neighbors to return (default 25).",
                        "default": 25
                    }
                },
                "required": ["tcr_id"]
            }
        },
        {
            "name": "get_predictions",
            "description": "Lookup pre-computed DecoderTCR binding probability scores for a given TCR. Provides interaction scores against various viral, cancer, and autoimmune epitopes.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tcr_id": {
                        "type": "string",
                        "description": "The target TCR ID to get predictions for."
                    }
                },
                "required": ["tcr_id"]
            }
        },
        {
            "name": "get_mutagenesis",
            "description": "Retrieve the in silico CDR3 mutagenesis landscape for a given TCR. This simulates how single amino acid substitutions affect the DecoderTCR binding score against its top predicted epitope.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tcr_id": {
                        "type": "string",
                        "description": "The target TCR ID to get the mutation landscape for."
                    },
                    "epitope": {
                        "type": "string",
                        "description": "Optional epitope identifier for multi-target landscapes."
                    }
                },
                "required": ["tcr_id"]
            }
        }
    ]


class ToolExecutor:
    """Executes tools by delegating to the underlying services."""

    def __init__(self, store: DataStore):
        self.store = store
        self.neighbor_svc = NeighborService(store)
        self.prediction_svc = PredictionService(store)

    def search_neighbors(self, tcr_id: str, k: int = 25, limit: int = 5) -> Dict[str, Any]:
        """Execute the neighbor search. Limit to top N returned to save tokens."""
        neighbors = self.neighbor_svc.find_neighbors(tcr_id, k=k)
        annotated = [n for n in neighbors if n.get("known_epitope")]
        return {
            "summary": f"Found {len(neighbors)} neighbors; {len(annotated)} are annotated.",
            "top_neighbors": neighbors[:limit] # limit for context length
        }

    def get_predictions(self, tcr_id: str) -> Dict[str, Any]:
        """Execute the prediction lookup."""
        predictions = self.prediction_svc.get_predictions(tcr_id)
        return {
            "summary": f"Retrieved {len(predictions)} DecoderTCR predictions.",
            "top_predictions": predictions[:3]  # strictly limit to 3 to save context window
        }

    def get_mutagenesis(
        self,
        tcr_id: str,
        epitope: str | None = None,
        limit: int = 3,
        compute_if_missing: bool = False,
    ) -> Dict[str, Any]:
        """Execute the mutagenesis lookup. If not cached, simulate computation."""
        entries = self.store.mutagenesis_cache.get(tcr_id)
        selection = None

        if entries:
            if epitope and epitope in entries:
                selection = entries[epitope]
            elif len(entries) == 1:
                selection = next(iter(entries.values()))
            else:
                known = self._lookup_known_epitope(tcr_id)
                if known and known in entries:
                    selection = entries[known]
                else:
                    selection = max(
                        entries.values(),
                        key=lambda item: item.get("wild_type_score", float("-inf")),
                        default=None,
                    )

        if selection is None:
            if compute_if_missing:
                selection = self._compute_mock_mutagenesis(tcr_id)
            if selection is None:
                return {"available": False, "reason": "No pre-computed mutation landscape exists for this TCR."}

        epitope_options = sorted(self.store.mutagenesis_cache.get(tcr_id, {}).keys())
        return {
            "available": True,
            "epitope": selection.get("epitope"),
            "wild_type_score": selection.get("wild_type_score"),
            "cdr3b": selection.get("cdr3b"),
            "top_variants": selection.get("top_variants", [])[:limit],  # limit to save context
            "epitope_options": epitope_options,
        }

    def _compute_mock_mutagenesis(self, tcr_id: str) -> Dict[str, Any]:
        """Dynamically generate a mock mutagenesis landscape for a TCR."""
        import random
        # Get TCR
        tcr_row = self.store.tcr_db[self.store.tcr_db["tcr_id"] == tcr_id]
        if tcr_row.empty: return None
        cdr3b = tcr_row.iloc[0].get("CDR3b", "")
        if not cdr3b: return None
        
        # Get best prediction to act as the target epitope
        preds = self.prediction_svc.get_predictions(tcr_id)
        if not preds: return None
        best_pred = preds[0]
        wt_score = best_pred["score"]
        epitope = best_pred["epitope"]
        
        landscape = []
        top_variants = []
        AA = "ACDEFGHIKLMNPQRSTVWY"
        
        for i, wt_aa in enumerate(cdr3b):
            for mut_aa in AA:
                delta = random.gauss(0, 0.015)
                # bias slightly negative (most mutations hurt binding)
                delta -= 0.005
                score = wt_score + delta
                if mut_aa == wt_aa:
                    delta = 0.0
                    score = wt_score
                
                landscape.append({
                    "position": i + 1,
                    "wt_aa": wt_aa,
                    "mut_aa": mut_aa,
                    "score": round(score, 4),
                    "delta": round(delta, 4)
                })
                
                if delta > 0.01:
                    top_variants.append({
                        "mutations": f"{wt_aa}{i+1}{mut_aa}",
                        "predicted_score": round(score, 4),
                        "delta": round(delta, 4),
                        "note": "Hypothesis — requires experimental validation"
                    })
        
        # Sort top variants
        top_variants.sort(key=lambda x: x["delta"], reverse=True)
        
        mut_data = {
            "tcr_id": tcr_id,
            "epitope": epitope,
            "wild_type_score": wt_score,
            "cdr3b": cdr3b,
            "top_variants": top_variants[:50],  # keep top 50
            "landscape": landscape
        }
        
        # Save to cache so the scatterplot UI can read it!
        bucket = self.store.mutagenesis_cache.setdefault(tcr_id, {})
        bucket[epitope] = mut_data
        return mut_data

    def _lookup_known_epitope(self, tcr_id: str) -> str | None:
        """Best-effort helper to map a TCR to its known epitope in the DB."""
        db = self.store.tcr_db
        if db.empty:
            return None
        row = db[db["tcr_id"] == tcr_id]
        if row.empty:
            return None
        known = row.iloc[0].get("known_epitope")
        if isinstance(known, str) and known.strip():
            return known
        return None

    def execute(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Route the tool call to the correct method."""
        if tool_name == "search_neighbors":
            return self.search_neighbors(**tool_args)
        elif tool_name == "get_predictions":
            return self.get_predictions(**tool_args)
        elif tool_name == "get_mutagenesis":
            return self.get_mutagenesis(**tool_args)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
