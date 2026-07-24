"""
JADX MCP Server - Analysis Memory

Persistent, token-efficient storage for AI analysis results.
Uses SQLite with gzip compression per entry:
  - SQLite: single-file, zero config, O(log n) indexed lookups, WAL concurrency
  - gzip (level 6): ~70-80% compression on prose text; fully stdlib
  - One row per class = surgical reads (no full-scan on get)

Author: jadx-ai-mcp contributors
License: See LICENSE file
"""

import gzip
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Place the DB next to the server package root (jadx-mcp-server/analysis_memory.db)
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "analysis_memory.db"

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA cache_size   = -8192;   -- 8 MB page cache

CREATE TABLE IF NOT EXISTS class_analysis (
    class_name  TEXT    PRIMARY KEY,   -- fully-qualified Java class name
    summary     BLOB    NOT NULL,      -- gzip-compressed UTF-8 analysis text
    tags        TEXT    NOT NULL DEFAULT '',  -- comma-separated searchable labels
    apk_hint    TEXT    NOT NULL DEFAULT '',  -- optional APK name for context
    char_count  INTEGER NOT NULL DEFAULT 0,   -- uncompressed length (for stats)
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ca_updated ON class_analysis (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ca_tags    ON class_analysis (tags);
"""

_COMPRESS_LEVEL = 6   # balanced speed / ratio; gzip default
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Open a WAL-mode connection and initialise the schema if needed."""
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=10)
    conn.executescript(_DDL)
    return conn


def _compress(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"), compresslevel=_COMPRESS_LEVEL)


def _decompress(blob: bytes) -> str:
    return gzip.decompress(blob).decode("utf-8")


# ---------------------------------------------------------------------------
# Public API  (all sync; callers can run in asyncio via asyncio.to_thread)
# ---------------------------------------------------------------------------

def save(
    class_name: str,
    summary: str,
    tags: str = "",
    apk_hint: str = "",
) -> Dict[str, Any]:
    """
    Persist (or overwrite) an analysis summary for a class.

    Args:
        class_name: Fully-qualified Java class name, e.g. com.example.MainActivity
        summary:    Free-form analysis text (vulnerabilities, purpose, key methods…)
        tags:       Optional comma-separated labels, e.g. "crypto,hardcoded-secret"
        apk_hint:   Optional APK filename for multi-APK sessions

    Returns:
        dict with status, class_name, compression stats
    """
    compressed = _compress(summary)
    now = time.time()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO class_analysis
                    (class_name, summary, tags, apk_hint, char_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(class_name) DO UPDATE SET
                    summary    = excluded.summary,
                    tags       = excluded.tags,
                    apk_hint   = excluded.apk_hint,
                    char_count = excluded.char_count,
                    updated_at = excluded.updated_at
                """,
                (class_name, compressed, tags, apk_hint, len(summary), now, now),
            )
            conn.commit()
        finally:
            conn.close()

    ratio = round(len(compressed) / max(len(summary.encode()), 1) * 100, 1)
    return {
        "status": "saved",
        "class_name": class_name,
        "original_chars": len(summary),
        "compressed_bytes": len(compressed),
        "compression_pct": ratio,
    }


def get(class_name: str) -> Dict[str, Any]:
    """
    Retrieve the stored analysis for a class.

    Returns:
        dict with found=True/False; if found, includes summary, tags, timestamps
    """
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT summary, tags, apk_hint, char_count, created_at, updated_at "
                "FROM class_analysis WHERE class_name = ?",
                (class_name,),
            ).fetchone()
        finally:
            conn.close()

    if row is None:
        return {"found": False, "class_name": class_name}

    return {
        "found": True,
        "class_name": class_name,
        "summary": _decompress(row[0]),
        "tags": row[1],
        "apk_hint": row[2],
        "original_chars": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def list_all(tag_filter: str = "") -> Dict[str, Any]:
    """
    List all stored analyses (metadata only, no summary text).

    Args:
        tag_filter: If non-empty, only return entries whose tags contain this string
    """
    with _lock:
        conn = _connect()
        try:
            if tag_filter:
                rows = conn.execute(
                    "SELECT class_name, tags, apk_hint, char_count, length(summary), updated_at "
                    "FROM class_analysis WHERE tags LIKE ? ORDER BY updated_at DESC",
                    (f"%{tag_filter}%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT class_name, tags, apk_hint, char_count, length(summary), updated_at "
                    "FROM class_analysis ORDER BY updated_at DESC"
                ).fetchall()
        finally:
            conn.close()

    return {
        "total": len(rows),
        "tag_filter": tag_filter,
        "entries": [
            {
                "class_name": r[0],
                "tags": r[1],
                "apk_hint": r[2],
                "original_chars": r[3],
                "compressed_bytes": r[4],
                "updated_at": r[5],
            }
            for r in rows
        ],
    }


def delete(class_name: str) -> Dict[str, Any]:
    """Delete the stored analysis for a single class."""
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "DELETE FROM class_analysis WHERE class_name = ?", (class_name,)
            )
            conn.commit()
            deleted = cur.rowcount > 0
        finally:
            conn.close()
    return {"deleted": deleted, "class_name": class_name}


def clear_all() -> Dict[str, Any]:
    """Wipe all stored analyses and reclaim disk space (VACUUM)."""
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM class_analysis")
            cleared = cur.rowcount
            conn.commit()
            conn.execute("VACUUM")
            conn.commit()
        finally:
            conn.close()
    return {"cleared": cleared, "status": "all analyses deleted and db vacuumed"}


def stats() -> Dict[str, Any]:
    """Return aggregate storage statistics."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*), SUM(char_count), SUM(length(summary)) FROM class_analysis"
            ).fetchone()
        finally:
            conn.close()

    db_size = _DB_PATH.stat().st_size if _DB_PATH.exists() else 0
    total_entries = row[0] or 0
    total_chars = row[1] or 0
    total_compressed = row[2] or 0
    ratio = round(total_compressed / max(total_chars, 1) * 100, 1) if total_chars else 0

    return {
        "total_entries": total_entries,
        "total_original_chars": total_chars,
        "total_compressed_bytes": total_compressed,
        "overall_compression_pct": ratio,
        "db_size_bytes": db_size,
        "db_path": str(_DB_PATH),
    }
