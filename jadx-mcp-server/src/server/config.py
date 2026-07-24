"""
JADX MCP Server - Configuration Module

This module manages server configuration, HTTP client setup, and communication
with the JADX Java plugin. Handles connection management, error handling,
and request/response processing.

Author: Jafar Pathan (zinja-coder@github)
License: See LICENSE file
"""

import hashlib
import json
import logging
import sys
import time
from typing import Any, Dict, Optional, Tuple, Union

import httpx

# Default Configuration
JADX_HOST = "127.0.0.1"
JADX_PORT = 8650
JADX_HTTP_BASE = f"http://{JADX_HOST}:{JADX_PORT}"

# HTTP read timeouts (seconds) for plugin communication
JADX_DEFAULT_TIMEOUT = 60.0
JADX_SEARCH_TIMEOUT = 3600.0

# Logging Setup
logger = logging.getLogger("jadx-mcp-server")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.ERROR)
logger.propagate = False

# ---------------------------------------------------------------------------
# In-process TTL Response Cache
#
# Caches JADX bridge responses for stable, read-only endpoints (class source,
# manifest, package tree, etc.) for the duration of a session.
# Key  : SHA-1 of "endpoint:json(sorted params)" — constant space regardless
#        of response size.
# Value: (response_data, expiry_monotonic_seconds)
#
# Endpoints that must NEVER be cached (always live data):
#   current-class, selected-text, search-progress, health
# ---------------------------------------------------------------------------
_RESPONSE_CACHE: Dict[str, Tuple[Any, float]] = {}
_DEFAULT_TTL: float = 600.0   # 10 minutes; covers a typical analysis session

_NEVER_CACHE = frozenset({
    "current-class",
    "selected-text",
    "search-progress",
    "health",
    "cache-stats",
})


def _cache_key(endpoint: str, params: Dict[str, Any]) -> str:
    raw = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
    return hashlib.sha1(raw.encode()).hexdigest()


def cache_invalidate(endpoint: str = "", params: Optional[Dict[str, Any]] = None) -> int:
    """
    Evict cache entries.

    Args:
        endpoint: If provided, evict only entries for this endpoint prefix.
                  If empty, evict everything (e.g. after an APK is switched).
        params:   If also provided alongside endpoint, evict only that exact key.

    Returns:
        Number of evicted entries.
    """
    global _RESPONSE_CACHE
    if not endpoint:
        count = len(_RESPONSE_CACHE)
        _RESPONSE_CACHE.clear()
        return count
    if params is not None:
        key = _cache_key(endpoint, params)
        return 1 if _RESPONSE_CACHE.pop(key, None) is not None else 0
    # prefix eviction
    prefix = f"{endpoint}:"
    # recompute prefix heuristic via stored raw key prefixes isn't possible
    # with SHA-1 keys; instead evict all and let callers re-populate.
    # (This path is only taken on explicit invalidation, not hot path.)
    count = len(_RESPONSE_CACHE)
    _RESPONSE_CACHE.clear()
    return count


def _rebuild_jadx_http_base():
    """Rebuild the base URL used for all requests to the JADX plugin."""
    global JADX_HTTP_BASE
    JADX_HTTP_BASE = f"http://{JADX_HOST}:{JADX_PORT}"


def set_jadx_host(host: str):
    """
    Updates the JADX plugin host.

    Args:
        host: Hostname or IP where JADX AI MCP plugin is reachable

    Side Effects:
        Updates global JADX_HOST and JADX_HTTP_BASE configuration
    """
    global JADX_HOST
    JADX_HOST = host
    _rebuild_jadx_http_base()


def set_jadx_port(port: int):
    """
    Updates the JADX plugin port.

    Args:
        port: TCP port number where JADX AI MCP plugin is listening

    Side Effects:
        Updates global JADX_PORT and JADX_HTTP_BASE configuration
    """
    global JADX_PORT
    JADX_PORT = port
    _rebuild_jadx_http_base()


def health_ping() -> Union[str, Dict[str, Any]]:
    """
    Checks if the JADX Java plugin is reachable.

    Returns:
        Union[str, Dict[str, Any]]: Success message or error dictionary

    Note:
        Performs synchronous HTTP health check with 60-second timeout
    """
    try:
        with httpx.Client(trust_env=False) as client:
            resp = client.get(f"{JADX_HTTP_BASE}/health", timeout=60)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"error": str(e)}


async def get_from_jadx(
    endpoint: str,
    params: Dict[str, Any] = None,
    timeout: float = JADX_DEFAULT_TIMEOUT,
) -> Union[str, Dict[str, Any]]:
    """
    Generic async helper to request data from the JADX plugin.

    Args:
        endpoint: API endpoint path (e.g., "class-source", "manifest")
        params: Query parameters dictionary for the request

    Returns:
        Union[str, Dict[str, Any]]: Parsed JSON response or error dictionary

    Raises:
        Returns error dict on HTTP failures or connection issues

    Note:
        Automatically handles JSON parsing with fallback to text response
    """
    params = params or {}
    url = f"{JADX_HTTP_BASE}/{endpoint.lstrip('/')}"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get(url, params=params, timeout=timeout)
            resp.raise_for_status()

            # Try to parse JSON, fallback to text if not valid JSON
            try:
                return resp.json()
            except json.JSONDecodeError:
                return {"response": resp.text}

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error {e.response.status_code}: {e.response.text}"
        logger.error(error_msg)
        return {"error": error_msg}

    except httpx.TimeoutException:
        error_msg = (
            f"Request to JADX plugin timed out after {timeout}s for endpoint '{endpoint}'. "
            "The operation may still be running in JADX-GUI. "
            "For large APKs, code-level searches can take several minutes."
        )
        logger.error(error_msg)
        return {"error": error_msg}

    except httpx.ConnectError:
        error_msg = (
            f"Cannot connect to JADX plugin at {JADX_HTTP_BASE}. "
            "Ensure JADX-GUI is running and the AI MCP plugin is active."
        )
        logger.error(error_msg)
        return {"error": error_msg}

    except Exception as e:
        error_msg = f"Unexpected error communicating with JADX plugin: {type(e).__name__}: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


async def post_to_jadx(endpoint: str, params: Dict[str, Any] = None) -> Union[str, Dict[str, Any]]:
    """
    Generic async helper to POST to the JADX plugin (for mutating operations like cache-clear).
    """
    params = params or {}
    url = f"{JADX_HTTP_BASE}/{endpoint.lstrip('/')}"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(url, params=params, timeout=30)
            resp.raise_for_status()
            try:
                return resp.json()
            except json.JSONDecodeError:
                return {"response": resp.text}
    except httpx.TimeoutException:
        return {
            "error": (
                f"POST to JADX plugin timed out after 30s for endpoint '{endpoint}'. "
                f"Target: {JADX_HTTP_BASE}"
            )
        }
    except httpx.ConnectError:
        return {"error": f"Cannot connect to JADX plugin at {JADX_HTTP_BASE}. Ensure JADX-GUI is running."}
    except Exception as e:
        return {"error": f"POST to {endpoint} failed: {type(e).__name__}: {str(e)}"}


async def get_search_progress() -> Dict[str, Any]:
    """
    Poll the JADX plugin for current search progress.

    Returns:
        Dict with keys: state, scanned, total, matches, search_id, operation_type,
        elapsed_ms.  When state is "failed", also includes "error".
        Returns {"state": "unknown"} on connection failure.
    """
    url = f"{JADX_HTTP_BASE}/search-progress"
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get(url, timeout=5)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"state": "unknown"}


async def get_from_jadx_cached(
    endpoint: str,
    params: Dict[str, Any] = None,
    timeout: float = JADX_DEFAULT_TIMEOUT,
    ttl: float = _DEFAULT_TTL,
) -> Union[str, Dict[str, Any]]:
    """
    Like get_from_jadx but with an in-process TTL cache.

    Suitable for stable, read-only endpoints (class-source, manifest,
    package-tree, all-classes, …).  Endpoints listed in _NEVER_CACHE are
    passed through to get_from_jadx unconditionally.

    Args:
        endpoint: JADX plugin API endpoint
        params:   Query parameters
        timeout:  HTTP timeout in seconds
        ttl:      Cache lifetime in seconds (default 600 = 10 min)

    Returns:
        Cached or freshly-fetched response dict
    """
    params = params or {}

    # Never cache live-data endpoints
    if endpoint in _NEVER_CACHE:
        return await get_from_jadx(endpoint, params, timeout)

    key = _cache_key(endpoint, params)
    now = time.monotonic()

    cached = _RESPONSE_CACHE.get(key)
    if cached is not None:
        data, expiry = cached
        if now < expiry:
            logger.debug("Cache HIT  %s %s", endpoint, params)
            return data
        # expired
        del _RESPONSE_CACHE[key]

    logger.debug("Cache MISS %s %s", endpoint, params)
    result = await get_from_jadx(endpoint, params, timeout)

    # Only cache successful responses (no "error" key)
    if isinstance(result, dict) and "error" not in result:
        _RESPONSE_CACHE[key] = (result, now + ttl)

    return result


def invalidate_response_cache() -> Dict[str, Any]:
    """
    Clear the entire in-process response cache.

    Call this when an APK is swapped or after a rename/refactor so stale
    class sources are not served from cache.

    Returns:
        dict with count of evicted entries
    """
    evicted = cache_invalidate()
    return {"evicted": evicted, "status": "response cache cleared"}
