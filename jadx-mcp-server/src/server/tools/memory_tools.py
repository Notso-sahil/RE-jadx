"""
JADX MCP Server - Analysis Memory Tools

MCP-registered tools that expose the persistent analysis memory (SQLite/gzip)
to the LLM client. The pattern is:

  1. Agent calls get_class_analysis(class_name)
  2. If found=True  → use cached summary (no token-heavy file read needed)
  3. If found=False → call get_class_source / get_class_outline, analyse, then
                      call save_class_analysis to persist the finding

Author: jadx-ai-mcp contributors
License: See LICENSE file
"""

import asyncio
from typing import Any, Dict

from src.server import analysis_memory


# Run blocking SQLite calls off the event loop to keep the MCP server responsive
async def _run(fn, *args, **kwargs) -> Any:
    return await asyncio.to_thread(fn, *args, **kwargs)


# ---------------------------------------------------------------------------
# MCP tool implementations
# ---------------------------------------------------------------------------

async def save_class_analysis(
    class_name: str,
    summary: str,
    tags: str = "",
    apk_hint: str = "",
) -> Dict[str, Any]:
    """
    Persist an analysis summary for a Java class into the local memory store.

    Call this AFTER you have finished analysing a class so future queries can
    skip re-fetching the full source.  The summary is stored compressed (gzip)
    in a local SQLite database — no cloud, no tokens wasted on re-analysis.

    Args:
        class_name: Fully-qualified class name, e.g. com.example.crypto.AESHelper
        summary:    Your analysis findings: purpose, vulnerabilities, key methods, etc.
        tags:       Optional comma-separated labels, e.g. "crypto,hardcoded-secret,risky"
        apk_hint:   Optional APK filename/identifier for multi-APK sessions

    Returns:
        dict with status, compression stats
    """
    return await _run(analysis_memory.save, class_name, summary, tags, apk_hint)


async def get_class_analysis(class_name: str) -> Dict[str, Any]:
    """
    Retrieve a previously saved analysis summary for a Java class.

    ALWAYS call this BEFORE fetching the full class source.  If found=True,
    use the cached summary directly — this saves thousands of tokens.
    If found=False, proceed to fetch and analyse the class normally, then
    call save_class_analysis to cache the result.

    Args:
        class_name: Fully-qualified class name, e.g. com.example.LoginActivity

    Returns:
        dict:
          found=True  → summary, tags, apk_hint, created_at, updated_at
          found=False → class_name only (proceed to fresh analysis)
    """
    return await _run(analysis_memory.get, class_name)


async def list_class_analyses(tag_filter: str = "") -> Dict[str, Any]:
    """
    List all cached class analyses (metadata only — no summary text).

    Useful for understanding what has already been analysed in the current
    session or across previous sessions without re-reading the APK.

    Args:
        tag_filter: Optional label to filter by, e.g. "crypto" returns only
                    entries whose tags contain "crypto". Empty = all entries.

    Returns:
        dict with total count and list of {class_name, tags, apk_hint,
        original_chars, compressed_bytes, updated_at}
    """
    return await _run(analysis_memory.list_all, tag_filter)


async def delete_class_analysis(class_name: str) -> Dict[str, Any]:
    """
    Delete the cached analysis for a single class (e.g. after the class was
    renamed or the APK was updated).

    Args:
        class_name: Fully-qualified class name to remove from memory

    Returns:
        dict with deleted=True/False
    """
    return await _run(analysis_memory.delete, class_name)


async def get_memory_stats() -> Dict[str, Any]:
    """
    Return aggregate statistics for the analysis memory store.

    Shows total entries, uncompressed vs compressed sizes, compression ratio,
    and database file path. Use this to assess how much analysis context has
    been accumulated across sessions.

    Returns:
        dict with total_entries, total_original_chars, total_compressed_bytes,
        overall_compression_pct, db_size_bytes, db_path
    """
    return await _run(analysis_memory.stats)


async def clear_all_analyses() -> Dict[str, Any]:
    """
    Wipe ALL stored analyses and reclaim disk space (VACUUM).

    Use this when switching to a completely different APK where no prior
    analysis is relevant.

    Returns:
        dict with count of cleared entries and status message
    """
    return await _run(analysis_memory.clear_all)
