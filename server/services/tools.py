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

    def search_neighbors(self, tcr_id: str, k: int = 25) -> Dict[str, Any]:
        """Execute the neighbor search. Limit to top 5 returned to save tokens."""
        neighbors = self.neighbor_svc.find_neighbors(tcr_id, k=k)
        annotated = [n for n in neighbors if n.get("known_epitope")]
        return {
            "summary": f"Found {len(neighbors)} neighbors; {len(annotated)} are annotated.",
            "top_neighbors": neighbors[:5] # strictly limit for context length
        }

    def get_predictions(self, tcr_id: str) -> Dict[str, Any]:
        """Execute the prediction lookup."""
        predictions = self.prediction_svc.get_predictions(tcr_id)
        return {
            "summary": f"Retrieved {len(predictions)} DecoderTCR predictions.",
            "top_predictions": predictions[:3]  # strictly limit to 3 to save context window
        }

    def get_mutagenesis(self, tcr_id: str) -> Dict[str, Any]:
        """Execute the mutagenesis lookup."""
        mutagenesis = self.store.mutagenesis_cache.get(tcr_id)
        if not mutagenesis:
            return {"available": False, "reason": "No pre-computed mutation landscape exists for this TCR."}
        
        return {
            "available": True,
            "epitope": mutagenesis.get("epitope"),
            "wild_type_score": mutagenesis.get("wild_type_score"),
            "top_variants": mutagenesis.get("top_variants", [])[:3] # strictly limit to 3 to save context
        }

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
