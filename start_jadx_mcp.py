import os
import sys
import subprocess
from pathlib import Path

# Try to import load_dotenv, but fallback to manual parsing if not found
try:
    from dotenv import load_dotenv
    has_dotenv = True
except ImportError:
    has_dotenv = False

env_path = Path(r"c:\Users\elite\Desktop\RE jadx\.env")

if env_path.exists():
    if has_dotenv:
        load_dotenv(env_path)
    else:
        # Manual fallback
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    os.environ[key] = val

python_exe = r"c:\Users\elite\Desktop\RE jadx\jadx-mcp-server\.venv\Scripts\python.exe"
jadx_server = r"c:\Users\elite\Desktop\RE jadx\jadx-mcp-server\jadx_mcp_server.py"

# Pass all arguments through to the MCP server
cmd = [python_exe, jadx_server] + sys.argv[1:]
sys.exit(subprocess.run(cmd, env=os.environ).returncode)
