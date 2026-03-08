"""
data/db.py — SQLAlchemy database layer for SQLite.
"""

from __future__ import annotations

import logging
from pathlib import Path
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
