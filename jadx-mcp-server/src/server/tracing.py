"""
JADX MCP Server - Observability & Tracing

Optional LangSmith tracing for all MCP tool calls.

Design goals:
  - NEVER raise an error if LANGSMITH_API_KEY is missing/invalid
  - Zero performance overhead when tracing is disabled
  - Capture: tool name, inputs, output, latency, token estimates
  - Works as a transparent async wrapper around any async function

Environment variables read (from .env via start_jadx_mcp.py):
  LANGSMITH_API_KEY      — enables LangSmith tracing (optional)
  LANGSMITH_PROJECT      — project name in LangSmith (default: jadx-mcp-server)
  LANGSMITH_ENDPOINT     — override API endpoint (optional)

Author: jadx-ai-mcp contributors
License: See LICENSE file
"""

import asyncio
import functools
import json
import logging
import os
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("jadx-mcp-server.tracing")

# ---------------------------------------------------------------------------
# LangSmith client — initialised once, None if not configured
# ---------------------------------------------------------------------------
_ls_client = None
_ls_project: str = "jadx-mcp-server"
_tracing_enabled: bool = False
_session_tokens: int = 0
_daily_call_count: int = 0

from collections import deque

class RateLimiter:
    def __init__(self, rpm_limit=15, safety_margin=1):
        self.rpm_limit = rpm_limit - safety_margin
        self.calls = deque()
        self.lock = asyncio.Lock()
        self.forced_wait_until = 0.0

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            if now < self.forced_wait_until:
                await asyncio.sleep(self.forced_wait_until - now)
                now = time.monotonic()
            while self.calls and self.calls[0] < now - 60:
                self.calls.popleft()
            if len(self.calls) >= self.rpm_limit:
                await asyncio.sleep(60 - (now - self.calls[0]) + 0.1)
                now = time.monotonic()
            self.calls.append(now)

    def register_429(self, retry_delay_seconds: float):
        self.forced_wait_until = time.monotonic() + retry_delay_seconds

rate_limiter = RateLimiter(rpm_limit=15)


def _init_langsmith() -> None:
    """
    Attempt to initialise LangSmith. Silently skips if key not present.
    Called once at server startup.
    """
    global _ls_client, _ls_project, _tracing_enabled

    api_key = os.environ.get("LANGSMITH_API_KEY", "").strip()
    if not api_key:
        logger.info("LangSmith: LANGSMITH_API_KEY not set — tracing disabled")
        return

    try:
        from langsmith import Client  # type: ignore

        endpoint = os.environ.get(
            "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"
        ).strip()
        project = os.environ.get("LANGSMITH_PROJECT", "jadx-mcp-server").strip()

        _ls_client = Client(api_key=api_key, api_url=endpoint)
        _ls_project = project
        _tracing_enabled = True
        logger.info("LangSmith: tracing enabled → project=%s", project)
    except Exception as exc:
        logger.warning("LangSmith: init failed (%s) — tracing disabled", exc)


def is_tracing_enabled() -> bool:
    return _tracing_enabled


# ---------------------------------------------------------------------------
# Token estimation (rough: 1 token ≈ 4 chars of JSON)
# ---------------------------------------------------------------------------

import tiktoken
_enc = tiktoken.get_encoding("cl100k_base")

def _estimate_tokens(obj: Any) -> int:
    """Rough token count using tiktoken (approximation for Gemini)."""
    try:
        text = json.dumps(obj, default=str)
        return max(1, len(_enc.encode(text)))
    except Exception:
        return 1


# ---------------------------------------------------------------------------
# LangSmith run logger (async-safe, fire-and-forget)
# ---------------------------------------------------------------------------

async def _log_run(
    tool_name: str,
    inputs: dict,
    outputs: Any,
    error: Optional[str],
    latency_ms: float,
) -> None:
    """Log a single tool call run to LangSmith. Never raises."""
    if not _tracing_enabled or _ls_client is None:
        return

    try:
        from langsmith.schemas import RunTypeEnum  # type: ignore
        import uuid

        run_id = str(uuid.uuid4())
        input_tokens = _estimate_tokens(inputs)
        output_tokens = _estimate_tokens(outputs)

        # Run create/update is synchronous in langsmith SDK;
        # wrap in thread to avoid blocking the event loop.
        def _send():
            try:
                _ls_client.create_run(
                    id=run_id,
                    name=tool_name,
                    run_type="llm",  # Changed from tool to llm so LangSmith shows tokens
                    inputs=inputs,
                    project_name=_ls_project,
                    tags=["mcp", "jadx"],
                    extra={"latency_ms": round(latency_ms, 2)},
                )
                import datetime
                _ls_client.update_run(
                    run_id=run_id,
                    outputs={"result": outputs} if not error else None,
                    error=error,
                    end_time=datetime.datetime.now(datetime.timezone.utc),
                    extra={
                        "metadata": {
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                        }
                    }
                )
            except Exception as e:
                logger.debug("LangSmith: send failed (%s)", e)

        await asyncio.to_thread(_send)
    except Exception as e:
        logger.debug("LangSmith: log_run error (%s)", e)


# ---------------------------------------------------------------------------
# Decorator: wrap an async MCP tool with tracing + latency
# ---------------------------------------------------------------------------

def traced(fn: Callable) -> Callable:
    """
    Wrap an async MCP tool function with:
      - Latency measurement
      - LangSmith run logging (if enabled)
      - Token estimation logging (always, to stderr at DEBUG level)

    Usage:
        @mcp.tool()
        @traced
        async def my_tool(arg: str) -> dict: ...

    Zero overhead if tracing is disabled (skips all logging work).
    """
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        t0 = time.monotonic()
        error_msg: Optional[str] = None
        result: Any = None
        
        global _session_tokens, _daily_call_count
        max_tokens = int(os.environ.get("MAX_DAILY_TOKENS", "240000"))
        max_calls = int(os.environ.get("MAX_DAILY_CALLS", "18"))
        
        if _session_tokens > (max_tokens * 0.99):
            return {"error": "QUOTA EXHAUSTED: You have reached 99% of your budget. All tool execution is blocked."}
        
        if _daily_call_count >= max_calls:
            return {"error": f"QUOTA EXHAUSTED: You have reached the maximum daily API calls ({max_calls})."}

        # Wait for rate limit if needed
        await rate_limiter.acquire()
        _daily_call_count += 1

        try:
            result = await fn(*args, **kwargs)
            
            # Post-check for tracking and 90% warning
            out_tokens = _estimate_tokens(result)
            _session_tokens += out_tokens
            
            if _session_tokens > (max_tokens * 0.90) and isinstance(result, dict):
                warning = f"\n\n[CRITICAL SYSTEM WARNING: You have reached 90% of the user's daily token budget ({_session_tokens}/{max_tokens}). YOU MUST STOP ALL INVESTIGATION NOW. Immediately output a highly detailed summary of everything you have found so far so the user can copy/paste it into a new session.]"
                if "code" in result:
                    result["code"] = str(result["code"]) + warning
                elif "result" in result:
                    result["result"] = str(result["result"]) + warning
                else:
                    result["SYSTEM_WARNING"] = warning
            elif _session_tokens > (max_tokens * 0.70) and getattr(wrapper, "_checkpoint_shown", False) is False and isinstance(result, dict):
                wrapper._checkpoint_shown = True
                warning = f"\n\n[CHECKPOINT: You've used 70% of your token budget ({_session_tokens}/{max_tokens}). Please call `add_investigation_note` for all open findings now, then I recommend starting a fresh Continue.dev session seeded with `get_investigation_notes()` output.]"
                if "code" in result:
                    result["code"] = str(result["code"]) + warning
                elif "result" in result:
                    result["result"] = str(result["result"]) + warning
                else:
                    result["SYSTEM_WARNING"] = warning
                    
            return result
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            
            # If we hit a 429, register the penalty so we back off globally
            exc_str = str(exc).lower()
            if "429" in exc_str or "resource exhausted" in exc_str or "too many requests" in exc_str:
                import re
                # Try to find a retry delay like "54s" or "60 seconds"
                match = re.search(r'(?:retry(?:delay)?|wait).*?(\d+)\s*(?:s|sec)', exc_str)
                delay = int(match.group(1)) if match else 60
                rate_limiter.register_429(delay)
                logger.warning(f"Rate limit hit! Forcing global backoff for {delay} seconds.")
                
            raise
        finally:
            latency_ms = (time.monotonic() - t0) * 1000

            # Always log latency to debug
            logger.debug(
                "TOOL %s | latency=%.1fms | error=%s",
                fn.__name__, latency_ms, error_msg or "none"
            )

            # Async fire-and-forget to LangSmith
            if _tracing_enabled:
                # Build inputs dict from positional + keyword args
                try:
                    import inspect
                    sig = inspect.signature(fn)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()
                    inputs = dict(bound.arguments)
                    # Remove 'ctx' (FastMCP context) — not serialisable
                    inputs.pop("ctx", None)
                except Exception:
                    inputs = {"args": str(args), "kwargs": str(kwargs)}

                asyncio.create_task(
                    _log_run(fn.__name__, inputs, result, error_msg, latency_ms)
                )

    return wrapper


# ---------------------------------------------------------------------------
# Batch tracer: context manager for multi-step operations
# ---------------------------------------------------------------------------

class TracedSession:
    """
    Context manager that groups multiple tool calls under a single
    LangSmith parent run (e.g., an entire APK analysis workflow).

    Usage:
        async with TracedSession("full-apk-analysis") as session:
            await tool_a(...)
            await tool_b(...)
    """
    def __init__(self, name: str, tags: list[str] = None):
        self.name = name
        self.tags = tags or []
        self._run_id: Optional[str] = None
        self._t0: float = 0.0

    async def __aenter__(self):
        self._t0 = time.monotonic()
        if _tracing_enabled and _ls_client is not None:
            try:
                import uuid
                self._run_id = str(uuid.uuid4())
                await asyncio.to_thread(
                    _ls_client.create_run,
                    id=self._run_id,
                    name=self.name,
                    run_type="chain",
                    inputs={},
                    project_name=_ls_project,
                    tags=["mcp", "jadx", "session"] + self.tags,
                )
            except Exception as e:
                logger.debug("TracedSession start failed: %s", e)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if _tracing_enabled and _ls_client is not None and self._run_id:
            latency = (time.monotonic() - self._t0) * 1000
            try:
                error = f"{exc_type.__name__}: {exc_val}" if exc_type else None
                await asyncio.to_thread(
                    _ls_client.update_run,
                    run_id=self._run_id,
                    outputs={"latency_ms": round(latency, 2)},
                    error=error,
                    end_time=datetime.datetime.now(datetime.timezone.utc),
                )
            except Exception as e:
                logger.debug("TracedSession end failed: %s", e)
        return False  # don't suppress exceptions


# ---------------------------------------------------------------------------
# Stats: in-process call counters (always active, zero cost)
# ---------------------------------------------------------------------------

_call_stats: dict[str, dict] = {}   # tool_name → {calls, errors, total_ms}


def record_call(tool_name: str, latency_ms: float, is_error: bool = False) -> None:
    """Record a call in the in-process stats dict. Thread-safe with GIL."""
    s = _call_stats.setdefault(tool_name, {"calls": 0, "errors": 0, "total_ms": 0.0})
    s["calls"] += 1
    s["total_ms"] += latency_ms
    if is_error:
        s["errors"] += 1


def get_call_stats() -> dict:
    """Return a copy of all recorded call stats."""
    result = {}
    for name, s in _call_stats.items():
        avg = round(s["total_ms"] / max(s["calls"], 1), 1)
        result[name] = {
            "calls": s["calls"],
            "errors": s["errors"],
            "avg_latency_ms": avg,
            "total_ms": round(s["total_ms"], 1),
        }
    return dict(sorted(result.items(), key=lambda x: -x[1]["calls"]))
