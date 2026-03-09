"""
services/tamarind.py - thin client for Tamarind's Boltz2/TCRModel2 API.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

import httpx

from core.config import settings


class TamarindError(RuntimeError):
    """Raised when Tamarind configuration or requests fail."""


class TamarindClient:
    """Convenience wrapper for triggering Tamarind structure jobs."""

    def __init__(self, *, base_url: str, api_key: str | None = None, workspace_id: str | None = None) -> None:
        if not base_url:
            raise TamarindError("TAMARIND_API_BASE is not configured.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.workspace_id = workspace_id

    @classmethod
    def from_settings(cls) -> "TamarindClient":
        return cls(
            base_url=settings.tamarind_api_base,
            api_key=settings.tamarind_api_key or None,
            workspace_id=settings.tamarind_workspace_id or None,
        )

    async def submit_structure_prediction(
        self,
        *,
        tcr_id: str,
        cdr3a: str | None,
        cdr3b: str | None,
        models: Sequence[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        workspace_id: str | None = None,
    ) -> Dict[str, Any]:
        """Kick off a Boltz2/TCRModel2 structure prediction job."""
        if not tcr_id:
            raise TamarindError("tcr_id is required for Tamarind jobs.")

        payload: Dict[str, Any] = {
            "job_type": "tcr_structure_prediction",
            "tcr_id": tcr_id,
            "models": list(models) if models else ["Boltz2", "TCRModel2"],
            "inputs": {
                "cdr3a": cdr3a or "",
                "cdr3b": cdr3b or "",
            },
            "metadata": metadata or {},
        }

        workspace = workspace_id or self.workspace_id
        if workspace:
            payload["workspace_id"] = workspace

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/v1/jobs/structure"
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip()
                raise TamarindError(
                    f"Tamarind request failed ({exc.response.status_code}): {detail or exc}"
                ) from exc
            except httpx.RequestError as exc:
                raise TamarindError(f"Tamarind request failed: {exc}") from exc

        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}
