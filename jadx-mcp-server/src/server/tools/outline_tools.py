"""
JADX MCP Server - Code Outline Tool

Fetches a class from JADX and returns only its structural skeleton:
imports, field declarations, and method/constructor signatures — with all
method bodies stripped and replaced by { /* ... */ }.

This typically reduces a large class from 800-5000 tokens down to 50-200
tokens, letting the LLM quickly understand structure before deciding which
specific methods to read in full.

Algorithm: single-pass character scanner that tracks:
  - brace depth
  - string / char literal boundaries
  - line comment / block comment boundaries
At depth 2+ (inside a method body at class-body level), content is replaced
with the { /* ... */ } placeholder.

Author: jadx-ai-mcp contributors
License: See LICENSE file
"""

import re
from typing import Tuple

from src.server.config import get_from_jadx


# ---------------------------------------------------------------------------
# Core outline engine
# ---------------------------------------------------------------------------

def _outline_java(source: str) -> str:
    """
    Strip Java method bodies from *source*, preserving class structure.

    Rules:
      depth 0 → top-level: package/import/class declaration lines kept as-is
      depth 1 → class body: field declarations and method signatures kept
      depth ≥ 2 → method/constructor/initialiser bodies → replaced

    Nested classes are collapsed to their opening brace + placeholder too,
    which is fine for a structural overview.

    Returns the outlined source string.
    """
    result: list[str] = []
    i = 0
    n = len(source)
    depth = 0            # brace nesting level
    in_string = False    # inside "..."
    in_char = False      # inside '...'
    in_lc = False        # inside // line comment
    in_bc = False        # inside /* block comment */

    while i < n:
        c = source[i]

        # ── Line comment ────────────────────────────────────────────────────
        if in_lc:
            result.append(c)
            if c == '\n':
                in_lc = False
            i += 1
            continue

        # ── Block comment ────────────────────────────────────────────────────
        if in_bc:
            result.append(c)
            if c == '*' and i + 1 < n and source[i + 1] == '/':
                result.append('/')
                i += 2
                in_bc = False
            else:
                i += 1
            continue

        # ── String literal ───────────────────────────────────────────────────
        if in_string:
            result.append(c)
            if c == '\\' and i + 1 < n:          # escape sequence
                result.append(source[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue

        # ── Char literal ─────────────────────────────────────────────────────
        if in_char:
            result.append(c)
            if c == '\\' and i + 1 < n:
                result.append(source[i + 1])
                i += 2
                continue
            if c == "'":
                in_char = False
            i += 1
            continue

        # ── Detect comment / literal starts ──────────────────────────────────
        if c == '/' and i + 1 < n:
            nxt = source[i + 1]
            if nxt == '/':
                in_lc = True
                result.append(c)
                i += 1
                continue
            if nxt == '*':
                in_bc = True
                result.append(c)
                i += 1
                continue

        if c == '"':
            in_string = True
            result.append(c)
            i += 1
            continue

        if c == "'":
            in_char = True
            result.append(c)
            i += 1
            continue

        # ── Opening brace ────────────────────────────────────────────────────
        if c == '{':
            depth += 1
            if depth >= 2:
                # We are entering a method/constructor/initialiser body.
                # Emit the opening brace + placeholder, then skip to the
                # matching closing brace (tracking inner depth carefully).
                result.append('{ /* ... */ }')
                inner = 1
                i += 1
                while i < n and inner > 0:
                    ch = source[i]
                    # Must still respect strings/comments inside the body
                    # so we don't mis-count braces inside string literals.
                    if ch == '/' and i + 1 < n:
                        nxt2 = source[i + 1]
                        if nxt2 == '/':
                            # skip line comment
                            i += 2
                            while i < n and source[i] != '\n':
                                i += 1
                            continue
                        if nxt2 == '*':
                            # skip block comment
                            i += 2
                            while i < n - 1:
                                if source[i] == '*' and source[i + 1] == '/':
                                    i += 2
                                    break
                                i += 1
                            continue
                    if ch == '"':
                        i += 1
                        while i < n:
                            if source[i] == '\\':
                                i += 2
                                continue
                            if source[i] == '"':
                                i += 1
                                break
                            i += 1
                        continue
                    if ch == "'":
                        i += 1
                        while i < n:
                            if source[i] == '\\':
                                i += 2
                                continue
                            if source[i] == "'":
                                i += 1
                                break
                            i += 1
                        continue
                    if ch == '{':
                        inner += 1
                    elif ch == '}':
                        inner -= 1
                    i += 1
                # depth returns to what it was before we entered the body
                depth -= 1
                continue
            else:
                result.append(c)
                i += 1
                continue

        # ── Closing brace ────────────────────────────────────────────────────
        if c == '}':
            depth = max(depth - 1, 0)
            result.append(c)
            i += 1
            continue

        result.append(c)
        i += 1

    outlined = ''.join(result)
    # Collapse 3+ consecutive blank lines produced by the stripping into 2
    outlined = re.sub(r'\n{3,}', '\n\n', outlined)
    return outlined.strip()


def _token_estimate(text: str) -> int:
    """Rough token count: ~4 chars per token for code."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------

async def get_class_outline(class_name: str) -> dict:
    """
    Return the structural skeleton of a Java class with method bodies stripped.

    This tool is optimised for token efficiency. Instead of returning the full
    source (potentially thousands of tokens), it returns:
      - Package declaration
      - Import statements
      - Class/interface/enum declaration
      - Field (variable) declarations
      - Method and constructor signatures with { /* ... */ } bodies

    Use this FIRST to understand class structure, then call get_method_by_name
    for specific methods that need deep analysis.  Compared to get_class_source,
    this typically reduces token usage by 70-95% for large classes.

    Args:
        class_name: Fully-qualified class name, e.g. com.example.crypto.AESHelper

    Returns:
        dict:
          class_name:       the requested class
          outline:          the stripped Java source skeleton
          original_chars:   char count of the full source
          outline_chars:    char count after outlining
          reduction_pct:    percentage of chars removed
          est_tokens_saved: rough token savings (÷4 heuristic)
    """
    raw = await get_from_jadx("class-source", {"class_name": class_name})

    # The JADX plugin returns {"source": "..."} or {"code": "..."} or similar
    if "error" in raw:
        return raw

    # Locate the source text key
    source_text: str = ""
    for key in ("source", "code", "content", "response"):
        if key in raw and isinstance(raw[key], str):
            source_text = raw[key]
            break

    if not source_text:
        # Fallback: stringify whatever we got
        import json
        source_text = json.dumps(raw)

    outlined = _outline_java(source_text)

    orig_chars = len(source_text)
    out_chars = len(outlined)
    reduction = round((1 - out_chars / max(orig_chars, 1)) * 100, 1)

    from src.server.tools import class_tools
    class_tools._outline_fetched.add(class_name)

    return {
        "class_name": class_name,
        "outline": outlined,
        "original_chars": orig_chars,
        "outline_chars": out_chars,
        "reduction_pct": reduction,
        "est_tokens_saved": _token_estimate(source_text) - _token_estimate(outlined),
    }
