#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [ "fastmcp>=3.0.2", "httpx" ]
# ///

"""
Copyright (c) 2025 jadx mcp server developer(s) (https://github.com/zinja-coder/jadx-ai-mcp)
See the file 'LICENSE' for copying permission
"""

import argparse
import logging
import os
import sys

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

# Force LangSmith tracing on globally if the key exists
if os.environ.get("LANGSMITH_API_KEY"):
    os.environ["LANGSMITH_TRACING"] = "true"

# ---------------------------------------------------------------------------
# Sanitise proxy-related environment variables BEFORE any library reads them.
#
# Problem (GitHub issue #99): if no_proxy (or any *_PROXY var) contains
# non-printable characters such as trailing newlines — common when set via
# .env files or proxy managers — httpx raises InvalidURL on the first request.
# Our own httpx calls use trust_env=False, but third-party code (e.g.
# fastmcp's version check) may not, so we clean the environment globally.
# ---------------------------------------------------------------------------
_PROXY_VARS = (
    "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
    "ALL_PROXY", "all_proxy",
    "NO_PROXY", "no_proxy",
)
for _var in _PROXY_VARS:
    _val = os.environ.get(_var)
    if _val is not None:
        _clean = _val.strip()
        if _clean != _val:
            os.environ[_var] = _clean
        if not _clean:
            del os.environ[_var]
from fastmcp import FastMCP, Context
from src.banner import jadx_mcp_server_banner
from src.server import config, tools

# Initialize MCP Server
mcp = FastMCP("JADX-AI-MCP Plugin Reverse Engineering Server")

# Bootstrap logger — always writes to stderr to keep stdout clean for stdio transport
logger = logging.getLogger("jadx-mcp-server.bootstrap")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


# Import and register ALL tools using correct FastMCP pattern
from src.server.tools.class_tools import (
    fetch_current_class, get_selected_text, get_class_source,
    get_all_classes, get_methods_of_class, get_fields_of_class, get_smali_of_class,
    get_main_application_classes_names, get_main_application_classes_code, get_main_activity_class,
    get_package_tree, get_cache_stats, clear_cache
)
from src.server.tools.search_tools import (
    get_method_by_name, search_method_by_name, search_classes_by_keyword,
    jadx_search_methods, jadx_search_strings
)
from src.server.tools.resource_tools import (
    get_manifest_component, get_android_manifest, get_strings, get_all_resource_file_names,
    get_resource_file
)
from src.server.tools.refactor_tools import (
    rename_class, rename_method, rename_field, rename_package, rename_variable
)
from src.server.tools.debug_tools import (
    debug_get_stack_frames, debug_get_threads, debug_get_variables
)
from src.server.tools.xrefs_tools import (
    get_xrefs_to_class, get_xrefs_to_method, get_xrefs_to_field
)
from src.server.tools.memory_tools import (
    save_class_analysis, get_class_analysis, list_class_analyses,
    delete_class_analysis, get_memory_stats, clear_all_analyses
)
from src.server.tools.outline_tools import get_class_outline
from src.server.config import invalidate_response_cache as _invalidate_response_cache
from src.server.tool_profiles import (
    apply_profile, get_active_profile, PROFILE_DESCRIPTIONS,
    AVAILABLE_PROFILES, PROFILE_ACTIVE_TAGS
)
from src.server.tools import investigation_tools
from src.server import notes_store
from src.server.tracing import _init_langsmith, traced, get_call_stats, is_tracing_enabled

# Initialise optional LangSmith tracing (graceful no-op if key missing)
_init_langsmith()


# Tool registration with tags for selective filtering
# Tags determine which profile makes each tool visible to the LLM.
# discovery = APK structure overview
# analysis  = deep code inspection
# refactor  = rename operations
# debug     = debugger access
# core      = always available (memory, outline, cache, profile)

@mcp.tool(tags=["discovery"])
@traced
async def fetch_current_class() -> dict:
    """Fetch currently selected class from JADX-GUI."""
    return await tools.class_tools.fetch_current_class()


@mcp.tool(tags=["discovery"])
@traced
async def get_selected_text() -> dict:
    """Returns currently selected text in the decompiled code view."""
    return await tools.class_tools.get_selected_text()


@mcp.tool(tags=["analysis"])
@traced
async def get_method_by_name(class_name: str, method_name: str, method_signature: str = None) -> dict:
    """Fetch source of a method from a specific class."""
    return await tools.search_tools.get_method_by_name(class_name, method_name, method_signature)


@mcp.tool(tags=["discovery"])
@traced
async def get_all_classes(offset: int = 0, count: int = 0) -> dict:
    """Returns all classes in the project with pagination."""
    return await tools.class_tools.get_all_classes(offset, count)


@mcp.tool(tags=["analysis"])
@traced
async def get_class_source(class_name: str, force: bool = False) -> dict:
    """Fetch the Java source of a specific class. Pass force=true to bypass the outline check."""
    return await tools.class_tools.get_class_source(class_name, force)


@mcp.tool(tags=["analysis"])
@traced
async def search_method_by_name(method_name: str, ctx: Context = None) -> dict:
    """Search for a method name across all classes."""
    report_progress = ctx.report_progress if ctx else None
    return await tools.search_tools.search_method_by_name(method_name, report_progress=report_progress)


@mcp.tool(tags=["analysis"])
@traced
async def get_methods_of_class(class_name: str) -> dict:
    """List all method names in a class."""
    return await tools.class_tools.get_methods_of_class(class_name)


@mcp.tool(tags=["analysis"])
@traced
async def search_classes_by_keyword(
    search_term: str,
    package: str = "",
    search_in: str = "code",
    offset: int = 0,
    count: int = 20,
    ctx: Context = None,
) -> dict:
    """Search classes by keyword. search_in: class/method/field/code/comment (comma-separated). package filters by package name."""
    report_progress = ctx.report_progress if ctx else None
    return await tools.search_tools.search_classes_by_keyword(
        search_term, package, search_in, offset, count, report_progress=report_progress
    )


@mcp.tool(tags=["analysis"])
@traced
async def search_methods(query: str, limit: int = 10) -> dict:
    """Search for methods using FTS5 (local SQLite index). Use this FIRST to locate relevant code before listing classes."""
    return await tools.search_tools.jadx_search_methods(query, limit)


@mcp.tool(tags=["analysis"])
@traced
async def search_strings(query: str, limit: int = 20) -> dict:
    """Search for strings using FTS5 (local SQLite index). Use this FIRST to locate relevant strings before listing classes."""
    return await tools.search_tools.jadx_search_strings(query, limit)


@mcp.tool(tags=["analysis", "discovery"])
@traced
async def investigate_apk(focus: str) -> dict:
    """
    Runs a deterministic server-side sweep of the APK for a given focus area.
    This saves multiple LLM round-trips by bundling the data into one payload.
    focus must be one of: "network", "crypto", "permissions", "obfuscation"
    """
    return await investigation_tools.jadx_investigate_apk(focus)


@mcp.tool(tags=["analysis"])
@traced
async def get_fields_of_class(class_name: str) -> dict:
    """List all field names in a class."""
    return await tools.class_tools.get_fields_of_class(class_name)


@mcp.tool(tags=["analysis"])
@traced
async def get_smali_of_class(class_name: str) -> dict:
    """Fetch the smali representation of a class."""
    return await tools.class_tools.get_smali_of_class(class_name)


@mcp.tool(tags=["discovery"])
@traced
async def get_manifest_component(component_type: str, only_exported: bool = False) -> dict:
    """Retrieve component from AndroidManifest.xml. component_type: activity/provider/service/receiver."""
    return await tools.resource_tools.get_manifest_component(component_type, only_exported)


@mcp.tool(tags=["discovery"])
@traced
async def get_android_manifest() -> dict:
    """Retrieve and return the AndroidManifest.xml content."""
    return await tools.resource_tools.get_android_manifest()


@mcp.tool(tags=["analysis"])
@traced
async def get_strings(offset: int = 0, count: int = 0) -> dict:
    """Retrieve contents of strings.xml files."""
    return await tools.resource_tools.get_strings(offset, count)


@mcp.tool(tags=["analysis"])
@traced
async def get_all_resource_file_names(offset: int = 0, count: int = 0) -> dict:
    """Retrieve all resource files names."""
    return await tools.resource_tools.get_all_resource_file_names(offset, count)


@mcp.tool(tags=["analysis"])
@traced
async def get_resource_file(resource_name: str) -> dict:
    """Retrieve resource file content."""
    return await tools.resource_tools.get_resource_file(resource_name)


@mcp.tool(tags=["discovery"])
@traced
async def get_main_application_classes_names() -> dict:
    """Fetch main application classes' names from Manifest package."""
    return await tools.class_tools.get_main_application_classes_names()


@mcp.tool(tags=["analysis"])
@traced
async def get_main_application_classes_code(offset: int = 0, count: int = 0) -> dict:
    """Fetch main application classes' code with pagination."""
    return await tools.class_tools.get_main_application_classes_code(offset, count)


@mcp.tool(tags=["discovery"])
@traced
async def get_main_activity_class() -> dict:
    """Fetch the main activity class from AndroidManifest.xml."""
    return await tools.class_tools.get_main_activity_class()


@mcp.tool(tags=["discovery"])
@traced
async def get_package_tree() -> dict:
    """Get all packages in APK sorted by class count. Start here to understand APK structure."""
    return await tools.class_tools.get_package_tree()


@mcp.tool(tags=["core", "cache"])
async def get_cache_stats() -> dict:
    """Get decompilation cache statistics: hits, misses, hit_rate, cached_classes, compressed_mb, compression_ratio."""
    return await tools.class_tools.get_cache_stats()


@mcp.tool(tags=["core", "cache"])
async def clear_cache() -> dict:
    """Clear the decompilation source cache and reset counters. Use when switching APKs or to free memory."""
    return await tools.class_tools.clear_cache()


@mcp.tool(tags=["refactor"])
@traced
async def rename_class(class_name: str, new_name: str) -> dict:
    """Renames a specific class."""
    return await tools.refactor_tools.rename_class(class_name, new_name)


@mcp.tool(tags=["refactor"])
@traced
async def rename_method(method_name: str, new_name: str, method_signature: str = None) -> dict:
    """Renames a specific method."""
    return await tools.refactor_tools.rename_method(method_name, new_name, method_signature)


@mcp.tool(tags=["refactor"])
@traced
async def rename_field(class_name: str, field_name: str, new_name: str) -> dict:
    """Renames a specific field."""
    return await tools.refactor_tools.rename_field(class_name, field_name, new_name)


@mcp.tool(tags=["refactor"])
@traced
async def rename_package(old_package_name: str, new_package_name: str) -> dict:
    """Renames a package and all its classes."""
    return await tools.refactor_tools.rename_package(old_package_name, new_package_name)


@mcp.tool(tags=["refactor"])
@traced
async def rename_variable(class_name: str, method_name: str, variable_name: str, new_name: str, reg: str = None, ssa: str = None) -> dict:
    """Renames a specific variable in a method."""
    return await tools.refactor_tools.rename_variable(class_name, method_name, variable_name, new_name, reg, ssa)


@mcp.tool(tags=["debug"])
@traced
async def debug_get_stack_frames() -> dict:
    """Get current stack frames (call stack)."""
    return await tools.debug_tools.debug_get_stack_frames()


@mcp.tool(tags=["debug"])
@traced
async def debug_get_threads() -> dict:
    """Get all threads in the debugged process."""
    return await tools.debug_tools.debug_get_threads()


@mcp.tool(tags=["debug"])
@traced
async def debug_get_variables() -> dict:
    """Get current variables when process is suspended."""
    return await tools.debug_tools.debug_get_variables()


@mcp.tool(tags=["analysis"])
@traced
async def get_xrefs_to_class(class_name: str, offset: int = 0, count: int = 20) -> dict:
    """Find all references to a class."""
    return await tools.xrefs_tools.get_xrefs_to_class(class_name, offset, count)


@mcp.tool(tags=["analysis"])
@traced
async def get_xrefs_to_method(
    class_name: str, method_name: str, offset: int = 0, count: int = 20
) -> dict:
    """Find all references to a method."""
    return await tools.xrefs_tools.get_xrefs_to_method(
        class_name, method_name, offset, count
    )


@mcp.tool(tags=["analysis"])
@traced
async def get_xrefs_to_field(
    class_name: str, field_name: str, offset: int = 0, count: int = 20
) -> dict:
    """Find all references to a field."""
    return await tools.xrefs_tools.get_xrefs_to_field(
        class_name, field_name, offset, count
    )


# ---------------------------------------------------------------------------
# Analysis Memory Tools
# ---------------------------------------------------------------------------

@mcp.tool(tags=["core", "memory"])
@traced
async def save_class_analysis(
    class_name: str,
    summary: str,
    tags: str = "",
    apk_hint: str = "",
) -> dict:
    """Persist analysis findings for a class (SQLite/gzip). Call AFTER analysis so future calls skip re-scanning."""
    from src.server.tools import memory_tools as _mem
    return await _mem.save_class_analysis(class_name, summary, tags, apk_hint)


@mcp.tool(tags=["core", "memory"])
@traced
async def get_class_analysis(class_name: str) -> dict:
    """Retrieve cached analysis for a class. Call BEFORE get_class_source — if found=True, use summary directly (saves thousands of tokens)."""
    from src.server.tools import memory_tools as _mem
    return await _mem.get_class_analysis(class_name)


@mcp.tool(tags=["core", "memory"])
@traced
async def list_class_analyses(tag_filter: str = "") -> dict:
    """
    List all cached class analyses (metadata only, no summary text).

    Args:
        tag_filter: Optional label filter, e.g. "crypto" returns entries
                    whose tags contain "crypto". Empty = all entries.
    """
    from src.server.tools import memory_tools as _mem
    return await _mem.list_class_analyses(tag_filter)


@mcp.tool(tags=["core", "memory"])
@traced
async def delete_class_analysis(class_name: str) -> dict:
    """
    Delete the cached analysis for a single class.
    Use after a rename or when the APK was updated.

    Args:
        class_name: Fully-qualified class name to remove from memory
    """
    from src.server.tools import memory_tools as _mem
    return await _mem.delete_class_analysis(class_name)


@mcp.tool(tags=["core", "memory"])
@traced
async def get_memory_stats() -> dict:
    """
    Return aggregate statistics for the analysis memory store.
    Shows total entries, uncompressed vs compressed sizes, and db path.
    """
    from src.server.tools import memory_tools as _mem
    return await _mem.get_memory_stats()


@mcp.tool(tags=["core", "memory"])
@traced
async def clear_all_analyses() -> dict:
    """
    Wipe ALL stored analyses and reclaim disk space.
    Use when switching to a completely different APK.
    """
    from src.server.tools import memory_tools as _mem
    return await _mem.clear_all_analyses()


@mcp.tool(tags=["core", "memory"])
@traced
async def add_investigation_note(class_name: str, finding: str, suspicious: bool) -> dict:
    """Add a permanent note about a finding for the current APK."""
    return notes_store.jadx_add_investigation_note(class_name, finding, suspicious)


@mcp.tool(tags=["core", "memory"])
@traced
async def get_investigation_notes() -> dict:
    """Retrieve all previously stored investigation notes for this APK."""
    return notes_store.jadx_get_investigation_notes()


# ---------------------------------------------------------------------------
# Code Outline Tool
# ---------------------------------------------------------------------------

@mcp.tool(tags=["core", "outline"])
@traced
async def get_class_outline(class_name: str) -> dict:
    """
    Return the structural skeleton of a Java class with method bodies stripped.

    Instead of the full source (potentially thousands of tokens), returns:
    - Package / import statements
    - Class declaration
    - Field declarations
    - Method and constructor signatures with { /* ... */ } bodies

    Use this FIRST to understand class structure cheaply, then call
    get_method_by_name for specific methods needing deep analysis.
    Typically reduces token usage by 70-95% for large classes.

    Args:
        class_name: Fully-qualified class name, e.g. com.example.crypto.AESHelper
    """
    from src.server.tools import outline_tools as _out
    return await _out.get_class_outline(class_name)


# ---------------------------------------------------------------------------
# Response Cache Invalidation Tool
# ---------------------------------------------------------------------------

@mcp.tool(tags=["core", "cache"])
async def invalidate_response_cache() -> dict:
    """
    Clear the in-process response cache (class sources, manifest, package tree, etc.).

    Call this after switching to a new APK or after rename/refactor operations
    so stale class sources are not served from cache.
    """
    return _invalidate_response_cache()

# ---------------------------------------------------------------------------
# Profile & Observability Tools
# ---------------------------------------------------------------------------

@mcp.tool(tags=["core", "profile"])
def set_tool_profile(profile_name: str) -> dict:
    """
    Switch the active tool profile to reveal more/fewer tools to the LLM.
    Profiles:
      minimal   : 9 tools (memory + outline + cache management)
      discovery : 17 tools (+ APK structure overview, manifest, classes)
      analysis  : 30 tools (+ deep code inspection, search, xrefs)
      refactor  : 35 tools (+ rename class/method/field/package/variable)
      debug     : 33 tools (+ JADX debugger)
      full      : 38 tools (all tools enabled, highest token cost)
    """
    if profile_name not in AVAILABLE_PROFILES:
        return {"error": f"Invalid profile. Choose from: {AVAILABLE_PROFILES}"}
    return apply_profile(mcp, profile_name)


@mcp.tool(tags=["core", "profile"])
def get_tool_profile() -> dict:
    """Get the currently active tool profile and its enabled features."""
    active = get_active_profile()
    return {
        "profile": active,
        "description": PROFILE_DESCRIPTIONS[active],
        "active_tag_groups": sorted(PROFILE_ACTIVE_TAGS[active])
    }


@mcp.tool(tags=["core", "profile"])
def get_server_stats() -> dict:
    """Get LangSmith tracing status and local tool invocation stats (latency, errors, call counts)."""
    return {
        "tracing_enabled": is_tracing_enabled(),
        "call_stats": get_call_stats()
    }


# ---------------------------------------------------------------------------
# Apply default profile before starting
# ---------------------------------------------------------------------------
apply_profile(mcp, get_active_profile())


def main():
    parser = argparse.ArgumentParser("MCP Server for Jadx")
    parser.add_argument(
        "--http",
        help="Serve MCP Server over HTTP stream.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--host",
        help="Host address to bind for --http (default: 127.0.0.1, use 0.0.0.0 for remote access). "
             "WARNING: non-localhost binds expose the server over plain HTTP with no authentication.",
        default="127.0.0.1",
        type=str
    )
    parser.add_argument(
        "--port", help="Port for --http (default:8651)", default=8651, type=int
    )
    parser.add_argument(
        "--jadx-port",
        help="JADX AI MCP Plugin port (default:8650)",
        default=8650,
        type=int,
    )
    parser.add_argument(
        "--jadx-host",
        help="JADX AI MCP Plugin host (default:127.0.0.1). "
             "Security: non-localhost may expose plugin to network; use trusted network/firewall.",
        default="127.0.0.1",
        type=str,
    )
    args = parser.parse_args()

    # Configure
    config.set_jadx_host(args.jadx_host)
    config.set_jadx_port(args.jadx_port)

    # Security warning for non-localhost bind address
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "\n⚠️  SECURITY WARNING: Binding to non-localhost address '%s'.\n"
            "   The MCP server uses plain HTTP with NO authentication.\n"
            "   Anyone on the network can connect and use all MCP tools.\n"
            "   Only use this on trusted networks or behind a firewall.",
            args.host
        )

    # Banner & Health Check — only log to stderr in HTTP mode to avoid breaking strict stdio clients
    if args.http:
        try:
            logger.info(jadx_mcp_server_banner())
        except Exception:
            logger.info(
                "[JADX AI MCP Server] v3.3.5 | MCP Port: %s | JADX Host: %s | JADX Port: %s",
                args.port,
                args.jadx_host,
                args.jadx_port,
            )

        logger.info("Testing JADX AI MCP Plugin connectivity...")
        result = config.health_ping()
        logger.info("Health check result: %s", result)
    else:
        # Silently test connectivity so the cache is primed, but don't log it
        config.health_ping()

    # Run Server
    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        # StdIO transport must keep stdout/stderr as quiet as possible for strict clients
        # Roo Code throws Connection Closed (-32000) if stderr receives ANY logging during startup.
        logging.getLogger('fastmcp').setLevel(logging.CRITICAL)
        logging.getLogger('mcp').setLevel(logging.CRITICAL)
        logging.getLogger('jadx-mcp-server').setLevel(logging.CRITICAL)
        mcp.run(show_banner=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        import datetime
        import os
        crash_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roo_crash.log")
        with open(crash_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- CRASH AT {datetime.datetime.now()} ---\n")
            f.write(traceback.format_exc())
            f.write("\n")
        raise
