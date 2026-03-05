"""
core/config.py — Application settings via pydantic-settings.

All paths are derived from PROJECT_ROOT so the server can be
started from any working directory.
"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API keys ──────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # ── LLMs ───────────────────────────────────────────────────────────────
    claude_model: str = "claude-3-5-sonnet-latest"
    gemini_model: str = "gemini-2.5-flash"
    llm_max_tokens: int = 2048

    # ── Paths — override via env vars if your layout differs ─────────────────
    # Default: resolve relative to this file's location (server/)
    project_root: Path = Path(__file__).resolve().parents[2]

    data_dir_override: Path | None = Field(None, alias="data_dir")
    embed_dir_override: Path | None = Field(None, alias="embed_dir")
    pred_dir_override: Path | None = Field(None, alias="pred_dir")
    mutagenesis_dir_override: Path | None = Field(None, alias="mutagenesis_dir")

    @property
    def data_dir(self) -> Path:
        return self.data_dir_override or (self.project_root / "data" / "processed")

    @property
    def embed_dir(self) -> Path:
        return self.embed_dir_override or (self.project_root / "data" / "embeddings")

    @property
    def pred_dir(self) -> Path:
        return self.pred_dir_override or (self.project_root / "data" / "predictions")

    @property
    def mutagenesis_dir(self) -> Path:
        return self.mutagenesis_dir_override or (self.pred_dir / "mutagenesis")

    # ── Feature flags ─────────────────────────────────────────────────────────
    # Maximum points returned from /api/umap (client-side canvas handles 89K fine)
    umap_max_points: int = 100_000
    # k for nearest-neighbor search
    neighbor_k: int = 10


# Module-level singleton — import this everywhere
settings = Settings()
