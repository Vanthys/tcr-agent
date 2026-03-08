"""
data/db.py — SQLAlchemy database layer for SQLite.
"""

from __future__ import annotations

import logging
from pathlib import Path
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from core.config import settings

logger = logging.getLogger(__name__)

# We use a file-backed SQLite database so it persists and doesn't load entirely in RAM every reload.
# If you want it in memory during run, you can use sqlite:///:memory: but file-based is better for reload stability.
db_path = settings.data_dir / "tcr_agent.db"
settings.data_dir.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

def get_conn():
    """Return a scoped engine connection for raw SQL execution."""
    return engine.connect()

def close_conn() -> None:
    """Cleanly close the engine (called at shutdown)."""
    engine.dispose()
    logger.info("SQLite connection closed")

def register_dataframe(name: str, df) -> None:
    """
    Save a Pandas DataFrame to SQLite.
    Creates indexes to speed up the read operations.
    """
    with engine.begin() as conn:
        df.to_sql(name, conn, if_exists="replace", index=False)
        
        # Add basic indices depending on the table name
        if name == "umap":
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_umap_source ON umap (source)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_umap_cat ON umap (antigen_category)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_umap_epitope ON umap (known_epitope)"))
        elif name == "tcrs":
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tcrs_id ON tcrs (tcr_id)"))
        elif name == "predictions":
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_pred_id ON predictions (tcr_id)"))
            
    logger.info("SQLite table '%s' loaded (%d rows)", name, len(df))


# ── Agent Chat Cache ────────────────────────────────────────────────────────────

def init_chat_cache_table() -> None:
    """Create the agent_chats table if it doesn't exist yet."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_chats (
                tcr_id     TEXT NOT NULL,
                provider   TEXT NOT NULL,
                cached_at  TEXT NOT NULL,
                payload    TEXT NOT NULL,
                PRIMARY KEY (tcr_id, provider)
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_chats_date ON agent_chats (cached_at)"
        ))
    logger.info("agent_chats table ready")


def save_chat(tcr_id: str, provider: str, payload: dict) -> None:
    """Upsert a completed agent session into the cache."""
    cached_at = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO agent_chats (tcr_id, provider, cached_at, payload)
            VALUES (:tcr_id, :provider, :cached_at, :payload)
            ON CONFLICT(tcr_id, provider) DO UPDATE SET
                cached_at = excluded.cached_at,
                payload   = excluded.payload
        """), {"tcr_id": tcr_id, "provider": provider,
               "cached_at": cached_at, "payload": payload_json})
    logger.info("Cached agent chat for %s (%s)", tcr_id, provider)


def load_chat(tcr_id: str, provider: str) -> dict | None:
    """Return the cached payload dict, or None if not cached."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT payload, cached_at FROM agent_chats
            WHERE tcr_id = :tcr_id AND provider = :provider
        """), {"tcr_id": tcr_id, "provider": provider}).fetchone()
    if row is None:
        return None
    return {"payload": json.loads(row[0]), "cached_at": row[1]}


def clear_chat(tcr_id: str, provider: str) -> None:
    """Delete a cached agent session."""
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM agent_chats WHERE tcr_id = :tcr_id AND provider = :provider
        """), {"tcr_id": tcr_id, "provider": provider})
    logger.info("Cleared agent chat cache for %s (%s)", tcr_id, provider)


def list_all_chats() -> list[dict]:
    """Return all cached sessions, newest first, without the full payload."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tcr_id, provider, cached_at,
                   length(payload) as payload_size
            FROM agent_chats
            ORDER BY cached_at DESC
        """)).fetchall()
    return [
        {"tcr_id": r[0], "provider": r[1], "cached_at": r[2], "payload_size": r[3]}
        for r in rows
    ]
