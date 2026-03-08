"""
data/db.py — SQLAlchemy database layer for SQLite.
"""

from __future__ import annotations

import logging
from pathlib import Path
import json
from datetime import datetime, timezone
from uuid import uuid4
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


def append_extra_context(tcr_id: str, provider: str, snippet: str) -> None:
    """Append a context snippet to the cached session so it is included in re-synthesis."""
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT payload FROM agent_chats WHERE tcr_id = :tcr_id AND provider = :provider
        """), {"tcr_id": tcr_id, "provider": provider}).fetchone()
        if row is None:
            return  # Nothing to append to
        payload = json.loads(row[0])
        extra = payload.get("extra_context", [])
        extra.append(snippet)
        payload["extra_context"] = extra
        conn.execute(text("""
            UPDATE agent_chats SET payload = :payload WHERE tcr_id = :tcr_id AND provider = :provider
        """), {"tcr_id": tcr_id, "provider": provider, "payload": json.dumps(payload)})
    logger.info("Appended extra context for %s (%s)", tcr_id, provider)


def append_followup(tcr_id: str, provider: str, followup: dict) -> None:
    """Append a complete tool analysis interaction to the cached session."""
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT payload FROM agent_chats WHERE tcr_id = :tcr_id AND provider = :provider
        """), {"tcr_id": tcr_id, "provider": provider}).fetchone()
        if row is None:
            return  # Nothing to append to
        payload = json.loads(row[0])
        followups = payload.get("followups", [])
        followups.append(followup)
        payload["followups"] = followups
        conn.execute(text("""
            UPDATE agent_chats SET payload = :payload WHERE tcr_id = :tcr_id AND provider = :provider
        """), {"tcr_id": tcr_id, "provider": provider, "payload": json.dumps(payload)})
    logger.info("Appended followup message for %s (%s)", tcr_id, provider)


# ── Chat session (message-based) storage ──────────────────────────────────────

def init_chat_messages_table() -> None:
    """Create the agent_chat_messages table for durable stage logging."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_chat_messages (
                message_id TEXT PRIMARY KEY,
                tcr_id     TEXT NOT NULL,
                provider   TEXT NOT NULL,
                status     TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                data       TEXT NOT NULL
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_tcr ON agent_chat_messages (tcr_id)"
        ))
    logger.info("agent_chat_messages table ready")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_chat_row(message_id: str):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT message_id, tcr_id, provider, status, created_at, updated_at, data
            FROM agent_chat_messages WHERE message_id = :message_id
        """), {"message_id": message_id}).mappings().fetchone()
    return row


def create_chat_message_record(tcr_id: str, provider: str) -> dict:
    """Create a new chat session row and return its metadata."""
    message_id = uuid4().hex
    now = _now_iso()
    data = {
        "stages": {},
        "stage_order": [],
        "chunks": [],
        "followups": [],
    }
    payload = json.dumps(data)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO agent_chat_messages (message_id, tcr_id, provider, status, created_at, updated_at, data)
            VALUES (:message_id, :tcr_id, :provider, :status, :created_at, :updated_at, :data)
        """), {
            "message_id": message_id,
            "tcr_id": tcr_id,
            "provider": provider,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "data": payload,
        })
    return {
        "message_id": message_id,
        "tcr_id": tcr_id,
        "provider": provider,
        "status": "running",
        "created_at": now,
        "updated_at": now,
        "data": data,
    }


def _persist_chat_data(message_id: str, data: dict, status: str | None = None, error: str | None = None) -> None:
    now = _now_iso()
    if error is not None:
        data.setdefault("meta", {})["error"] = error
    payload = json.dumps(data)
    update_fields = {
        "updated_at": now,
        "data": payload,
        "message_id": message_id,
    }
    set_clauses = ["updated_at = :updated_at", "data = :data"]
    if status:
        update_fields["status"] = status
        set_clauses.append("status = :status")

    with engine.begin() as conn:
        conn.execute(text(f"""
            UPDATE agent_chat_messages
            SET {", ".join(set_clauses)}
            WHERE message_id = :message_id
        """), update_fields)


def update_chat_stage(message_id: str, stage_name: str, status: str, detail: str | None = None, payload: dict | None = None, summary: str | None = None) -> dict:
    """Insert or update a stage entry and persist the change."""
    row = _load_chat_row(message_id)
    if row is None:
        raise ValueError(f"Chat message {message_id} not found")
    data = json.loads(row["data"])
    stages = data.setdefault("stages", {})
    stage_order = data.setdefault("stage_order", [])
    stage = stages.get(stage_name, {"name": stage_name})
    now = _now_iso()
    if "name" not in stage:
        stage["name"] = stage_name
    if "created_at" not in stage:
        stage["created_at"] = now
    if stage_name not in stage_order:
        stage_order.append(stage_name)

    stage.update({
        "status": status,
        "detail": detail,
        "payload": payload,
        "summary": summary,
        "updated_at": now,
    })
    if status == "running" and "started_at" not in stage:
        stage["started_at"] = now
    if status in ("done", "error"):
        stage["finished_at"] = now
    stages[stage_name] = stage

    _persist_chat_data(message_id, data)
    return stage


def append_chat_chunk(message_id: str, text_chunk: str) -> dict:
    """Append a streamed LLM chunk to the chat record."""
    row = _load_chat_row(message_id)
    if row is None:
        raise ValueError(f"Chat message {message_id} not found")
    data = json.loads(row["data"])
    chunks = data.setdefault("chunks", [])
    chunk = {
        "index": len(chunks),
        "text": text_chunk,
        "timestamp": _now_iso(),
    }
    chunks.append(chunk)
    _persist_chat_data(message_id, data)
    return chunk


def set_chat_status(message_id: str, status: str, error: str | None = None) -> dict:
    """Update the message-level status (running/done/failed/canceled)."""
    row = _load_chat_row(message_id)
    if row is None:
        raise ValueError(f"Chat message {message_id} not found")
    data = json.loads(row["data"])
    if error is not None:
        data.setdefault("meta", {})["error"] = error
    _persist_chat_data(message_id, data, status=status, error=error)
    return {
        "message_id": message_id,
        "status": status,
        "error": error,
        "updated_at": _now_iso(),
    }


def append_chat_followup(message_id: str, followup: dict) -> dict:
    row = _load_chat_row(message_id)
    if row is None:
        raise ValueError(f"Chat message {message_id} not found")
    data = json.loads(row["data"])
    followups = data.setdefault("followups", [])
    followups.append(followup)
    _persist_chat_data(message_id, data)
    return followup


def get_chat_message(message_id: str) -> dict | None:
    row = _load_chat_row(message_id)
    if row is None:
        return None
    data = json.loads(row["data"])
    return {
        "message_id": row["message_id"],
        "tcr_id": row["tcr_id"],
        "provider": row["provider"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "data": data,
        "error": data.get("meta", {}).get("error"),
    }


def list_chat_messages(limit: int = 50) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT message_id, tcr_id, provider, status, created_at, updated_at
            FROM agent_chat_messages
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
    return [
        {
            "message_id": r[0],
            "tcr_id": r[1],
            "provider": r[2],
            "status": r[3],
            "created_at": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]


def delete_chat_message(message_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_chat_messages WHERE message_id = :message_id"), {"message_id": message_id})

