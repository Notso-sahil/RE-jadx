"""
JADX MCP Server - Tool Profiles (Selective Tool Exposure)

Tools are tagged by capability group. The active profile controls which
tags are currently VISIBLE to the LLM client.  Hiding irrelevant tools
eliminates their description tokens from every request, reducing the
constant overhead of the tool manifest.

Profile Hierarchy (subset → superset):
  minimal   → memory + outline + profile switcher only
  discovery → + package-tree, manifest, class list, main-activity
  analysis  → + class source, search, xrefs, methods/fields, smali, strings
  refactor  → + all rename tools
  debug     → + jadx debugger tools
  full      → everything (no filtering)

Author: jadx-ai-mcp contributors
License: See LICENSE file
"""

from typing import Literal, Set

# ---------------------------------------------------------------------------
# Profile Definitions — map profile name to the set of TAG names to enable
# ---------------------------------------------------------------------------

ProfileName = Literal["minimal", "discovery", "analysis", "refactor", "debug", "full"]

# Tag applied to every tool we register in jadx_mcp_server.py
TAGS: dict[str, Set[str]] = {
    # ── Always-on (core tools) ─────────────────────────────────────────────
    "save_class_analysis":      {"core", "memory"},
    "get_class_analysis":       {"core", "memory"},
    "list_class_analyses":      {"core", "memory"},
    "delete_class_analysis":    {"core", "memory"},
    "get_memory_stats":         {"core", "memory"},
    "clear_all_analyses":       {"core", "memory"},
    "get_class_outline":        {"core", "outline"},
    "set_tool_profile":         {"core", "profile"},
    "get_tool_profile":         {"core", "profile"},
    "invalidate_response_cache": {"core", "cache"},
    "get_cache_stats":          {"core", "cache"},
    "clear_cache":              {"core", "cache"},
    # ── Discovery ─────────────────────────────────────────────────────────
    "get_package_tree":             {"discovery"},
    "get_android_manifest":         {"discovery"},
    "get_manifest_component":       {"discovery"},
    "get_all_classes":              {"discovery"},
    "get_main_activity_class":      {"discovery"},
    "get_main_application_classes_names": {"discovery"},
    "fetch_current_class":          {"discovery"},
    "get_selected_text":            {"discovery"},
    # ── Analysis ──────────────────────────────────────────────────────────
    "get_class_source":             {"analysis"},
    "get_methods_of_class":         {"analysis"},
    "get_fields_of_class":          {"analysis"},
    "get_smali_of_class":           {"analysis"},
    "get_method_by_name":           {"analysis"},
    "search_method_by_name":        {"analysis"},
    "search_classes_by_keyword":    {"analysis"},
    "get_main_application_classes_code": {"analysis"},
    "get_strings":                  {"analysis"},
    "get_all_resource_file_names":  {"analysis"},
    "get_resource_file":            {"analysis"},
    "get_xrefs_to_class":           {"analysis"},
    "get_xrefs_to_method":          {"analysis"},
    "get_xrefs_to_field":           {"analysis"},
    # ── Refactor ──────────────────────────────────────────────────────────
    "rename_class":     {"refactor"},
    "rename_method":    {"refactor"},
    "rename_field":     {"refactor"},
    "rename_package":   {"refactor"},
    "rename_variable":  {"refactor"},
    # ── Debug ─────────────────────────────────────────────────────────────
    "debug_get_stack_frames": {"debug"},
    "debug_get_threads":      {"debug"},
    "debug_get_variables":    {"debug"},
}

# Which TAG GROUPS are active for each profile
PROFILE_ACTIVE_TAGS: dict[str, Set[str]] = {
    "minimal":   {"core"},
    "discovery": {"core", "discovery"},
    "analysis":  {"core", "discovery", "analysis"},
    "refactor":  {"core", "discovery", "analysis", "refactor"},
    "debug":     {"core", "discovery", "analysis", "debug"},
    "full":      {"core", "discovery", "analysis", "refactor", "debug"},
}

# Tool counts per profile (for display)
PROFILE_DESCRIPTIONS = {
    "minimal":   "9 tools — memory + outline + cache management only",
    "discovery": "17 tools — + APK structure overview (manifest, packages, class list)",
    "analysis":  "30 tools — + deep code inspection (source, search, xrefs, methods)",
    "refactor":  "35 tools — + rename class/method/field/package/variable",
    "debug":     "33 tools — + JADX debugger (stack frames, threads, variables)",
    "full":      "38 tools — all tools enabled (highest token cost per request)",
}

# ---------------------------------------------------------------------------
# Active profile state — shared across the process
# ---------------------------------------------------------------------------
_active_profile: ProfileName = "analysis"   # sensible default


def get_active_profile() -> ProfileName:
    return _active_profile


def set_active_profile(profile: ProfileName) -> dict:
    """
    Change the active tool profile. Returns a summary dict.
    This function updates the module-level state but does NOT apply
    enable/disable to the FastMCP instance — that is done in apply_profile().
    """
    global _active_profile
    _active_profile = profile
    return {
        "profile": profile,
        "description": PROFILE_DESCRIPTIONS[profile],
        "active_tag_groups": sorted(PROFILE_ACTIVE_TAGS[profile]),
    }


def apply_profile(mcp_instance, profile: ProfileName) -> dict:
    """
    Apply a profile to a FastMCP instance by enabling/disabling tool tags.

    This calls mcp.disable() and mcp.enable() based on which tag groups
    should be active.  The MCP client will receive only the visible tools
    on its next tools/list request.

    Args:
        mcp_instance: The FastMCP server instance
        profile:      The profile to apply

    Returns:
        Summary dict with the new profile state
    """
    global _active_profile
    _active_profile = profile

    active_tags = PROFILE_ACTIVE_TAGS[profile]

    # Collect all unique tags across ALL tools
    all_tags: Set[str] = set()
    for tool_tags in TAGS.values():
        all_tags.update(tool_tags)

    tags_to_disable = all_tags - active_tags
    tags_to_enable = active_tags

    # Apply: first disable inactive, then enable active (enable wins last)
    for tag in tags_to_disable:
        try:
            mcp_instance.disable(tags=[tag])
        except Exception:
            pass

    for tag in tags_to_enable:
        try:
            mcp_instance.enable(tags=[tag])
        except Exception:
            pass

    return {
        "profile": profile,
        "description": PROFILE_DESCRIPTIONS[profile],
        "enabled_tag_groups": sorted(active_tags),
        "disabled_tag_groups": sorted(tags_to_disable),
    }


def get_tool_tags(tool_name: str) -> Set[str]:
    """Return the tag set for a given tool name."""
    return TAGS.get(tool_name, set())


AVAILABLE_PROFILES = list(PROFILE_ACTIVE_TAGS.keys())
