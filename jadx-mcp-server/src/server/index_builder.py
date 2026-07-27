import sqlite3
import os
import logging
import asyncio

logger = logging.getLogger("jadx-mcp-server.index_builder")
DB_PATH = "jadx_fts_index.db"

_build_lock = asyncio.Lock()
_index_built = False

async def ensure_index_built():
    global _index_built
    if _index_built and os.path.exists(DB_PATH):
        return

    async with _build_lock:
        if _index_built and os.path.exists(DB_PATH):
            return

        logger.info("Building FTS5 index. This may take 30-60 seconds on first run...")
        
        # Import tools to fetch data
        from src.server.tools import class_tools, resource_tools, outline_tools
        
        # 1. Fetch manifest
        manifest_res = await resource_tools.get_android_manifest()
        manifest_lines = []
        if isinstance(manifest_res, dict) and "code" in manifest_res:
            manifest_lines = manifest_res["code"].split("\n")
            
        # 2. Fetch strings
        strings_res = await resource_tools.get_strings()
        strings = []
        if isinstance(strings_res, dict) and "code" in strings_res:
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(strings_res["code"])
                for child in root.findall(".//string"):
                    name = child.get("name", "")
                    val = child.text or ""
                    if name or val:
                        strings.append({"value": val, "location": f"strings.xml:{name}"})
            except Exception as e:
                logger.error(f"Failed to parse strings.xml: {e}")

        # 3. Fetch all classes and their outlines
        classes_res = await class_tools.get_all_classes()
        class_names = []
        if isinstance(classes_res, dict) and "data" in classes_res:
            class_names = [c["name"] for c in classes_res["data"]]
        elif isinstance(classes_res, list):
            class_names = classes_res # Fallback
            
        methods = []
        
        # Fetch outlines concurrently with bounded semaphore
        sem = asyncio.Semaphore(20)
        async def fetch_class_outline(cname):
            async with sem:
                try:
                    outline_res = await outline_tools.get_class_outline(cname)
                    if "outline" in outline_res:
                        outline_text = outline_res["outline"]
                        # Very simple heuristic: just store the whole outline as a "snippet" 
                        # for the class, or break by lines.
                        # For FTS5, we can insert each line that looks like a method.
                        lines = outline_text.split('\n')
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith("import ") and not line.startswith("package "):
                                methods.append({
                                    "class_name": cname,
                                    "method_sig": line[:200], # Trucate sig
                                    "snippet": line
                                })
                except Exception:
                    pass

        # Gather outlines
        if class_names:
            tasks = [fetch_class_outline(c) for c in class_names]
            await asyncio.gather(*tasks)

        # Build SQLite DB in a thread
        def _build_db():
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
                
            conn = sqlite3.connect(DB_PATH)
            conn.execute("CREATE VIRTUAL TABLE methods USING fts5(class_name, method_sig, snippet)")
            conn.execute("CREATE VIRTUAL TABLE strings USING fts5(value, location)")
            conn.execute("CREATE VIRTUAL TABLE manifest USING fts5(line, line_no)")
            
            if methods:
                conn.executemany(
                    "INSERT INTO methods(class_name, method_sig, snippet) VALUES(?, ?, ?)",
                    [(m["class_name"], m["method_sig"], m.get("snippet", "")) for m in methods]
                )
                
            if strings:
                conn.executemany(
                    "INSERT INTO strings(value, location) VALUES(?, ?)",
                    [(s["value"], s["location"]) for s in strings]
                )
                
            if manifest_lines:
                conn.executemany(
                    "INSERT INTO manifest(line, line_no) VALUES(?, ?)",
                    [(line, i+1) for i, line in enumerate(manifest_lines)]
                )
                
            conn.commit()
            conn.close()

        await asyncio.to_thread(_build_db)
        _index_built = True
        logger.info(f"FTS5 Index built successfully with {len(methods)} method lines and {len(strings)} strings.")

def get_connection(db_path: str = DB_PATH):
    return sqlite3.connect(db_path)
