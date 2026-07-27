import logging
from src.server.tools import resource_tools, class_tools, search_tools
from src.server.index_builder import ensure_index_built, get_connection

logger = logging.getLogger("jadx-mcp-server.investigate")

async def jadx_investigate_apk(focus: str) -> dict:
    """
    Runs a deterministic server-side sweep of the APK for a given focus area.
    This saves multiple LLM round-trips by bundling the data into one payload.
    
    Args:
        focus: Must be one of: "network", "crypto", "permissions", "obfuscation"
        
    Returns:
        dict: A condensed report of findings.
    """
    valid_focus = {"network", "crypto", "permissions", "obfuscation"}
    focus = focus.lower()
    if focus not in valid_focus:
        return {"error": f"Invalid focus. Must be one of {valid_focus}"}

    report = {"focus": focus, "findings": {}}

    try:
        await ensure_index_built()
        conn = get_connection()
    except Exception as e:
        return {"error": f"Failed to build or connect to index: {e}"}

    try:
        if focus == "network":
            # 1. Manifest permissions related to network
            manifest = await resource_tools.get_android_manifest()
            perms = []
            if isinstance(manifest, dict) and "code" in manifest:
                lines = manifest["code"].split("\n")
                perms = [line.strip() for line in lines if "uses-permission" in line and ("INTERNET" in line or "NETWORK" in line)]
            report["findings"]["network_permissions"] = perms

            # 2. FTS search for URLs
            cursor = conn.execute("SELECT value FROM strings WHERE value LIKE '%http://%' OR value LIKE '%https://%' LIMIT 50")
            urls = [row[0] for row in cursor.fetchall()]
            report["findings"]["hardcoded_urls"] = urls
            
            # 3. Method search for common networking keywords
            cursor = conn.execute("SELECT class_name, method_sig FROM methods WHERE methods MATCH 'http OR request OR socket OR retrofit OR okhttp' LIMIT 20")
            methods = [f"{row[0]} -> {row[1]}" for row in cursor.fetchall()]
            report["findings"]["network_methods"] = methods

        elif focus == "crypto":
            # 1. FTS search for crypto keywords in methods
            cursor = conn.execute("SELECT class_name, method_sig FROM methods WHERE methods MATCH 'cipher OR aes OR rsa OR secret OR mac OR hash OR md5 OR sha' LIMIT 30")
            methods = [f"{row[0]} -> {row[1]}" for row in cursor.fetchall()]
            report["findings"]["crypto_methods"] = methods
            
            # 2. Strings related to keys
            cursor = conn.execute("SELECT value FROM strings WHERE strings MATCH 'key OR secret OR password OR token' LIMIT 20")
            keys = [row[0] for row in cursor.fetchall()]
            report["findings"]["suspicious_strings"] = keys

        elif focus == "permissions":
            manifest = await resource_tools.get_android_manifest()
            if isinstance(manifest, dict) and "code" in manifest:
                lines = manifest["code"].split("\n")
                perms = [line.strip() for line in lines if "uses-permission" in line]
                report["findings"]["all_permissions"] = perms
                
                # Also list components
                components = [line.strip() for line in lines if any(t in line for t in ["<activity", "<service", "<receiver", "<provider"])]
                report["findings"]["components"] = components
            else:
                report["findings"]["all_permissions"] = []
                report["findings"]["components"] = []

        elif focus == "obfuscation":
            tree = await class_tools.get_package_tree()
            report["findings"]["package_tree"] = tree
            
            # Count short class names (often a sign of ProGuard)
            cursor = conn.execute("SELECT count(DISTINCT class_name) FROM methods WHERE length(class_name) - length(replace(class_name, '.', '')) = 0 AND length(class_name) <= 2")
            short_classes = cursor.fetchone()[0]
            report["findings"]["single_letter_classes"] = short_classes

        return report
    except Exception as e:
        logger.error(f"Investigation failed: {e}")
        return {"error": str(e)}
    finally:
        conn.close()
