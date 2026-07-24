# JADX AI MCP Server (Optimized Version)

An advanced, token-optimized Model Context Protocol (MCP) server that bridges AI coding agents (like Claude Desktop or Cursor) with the [JADX](https://github.com/skylot/jadx) reverse engineering suite.

This server acts as a bridge, allowing your AI to programmatically explore, decompile, search, and analyze Android APKs directly through JADX, without you needing to copy-paste code.

## 🚀 Features

* **Token-Optimized Code Outlining**: Extract the structural skeleton of a Java class (methods, fields, imports) with method bodies stripped. Reduces AI token consumption by 70–95% during the discovery phase.
* **Analysis Memory Engine**: A local SQLite/GZIP storage engine that allows the AI to persist its findings and summaries of classes. The AI can instantly recall its previous analysis without wasting tokens re-reading source code.
* **Dynamic Tool Profiles**: Filter which tools the AI sees to prevent manifest bloat. Switch seamlessly between `minimal`, `discovery`, `analysis` (default), `refactor`, and `debug` profiles on the fly.
* **LangSmith Observability**: (Optional) Fully integrated with LangSmith for zero-overhead asynchronous tracing. Track token usage, latency, and tool error rates automatically.
* **Complete JADX Integration**: Access Smali, AndroidManifest.xml, Resources, Xrefs, search by keyword, and even interact with the JADX debugger.

## 📦 Installation

### Prerequisites
1. **Python 3.10+**
2. **JADX GUI** installed with the AI MCP Plugin enabled.

### Setup

1. The MCP server code is located in the `jadx-mcp-server` folder.
2. Open a terminal in that folder, create a virtual environment and install the dependencies:
   ```bash
   cd jadx-mcp-server
   python -m venv .venv
   
   # Windows
   .\.venv\Scripts\activate
   # Linux/Mac
   source .venv/bin/activate
   
   pip install -r requirements.txt
   ```
3. Edit the `.env` file at the root of the workspace (next to this README) and add your `LANGSMITH_API_KEY` (optional) to enable tracing.

### Connecting to your AI Client

You need to add the server to your AI's MCP configuration file (e.g., `claude_desktop_config.json` for Claude Desktop, or `mcp.json` for Cursor).

**Example Configuration:**
```json
{
  "mcpServers": {
    "jadx-mcp-plugin": {
      "command": "c:\\Users\\elite\\Desktop\\RE jadx\\jadx-mcp-server\\.venv\\Scripts\\python.exe",
      "args": [
        "c:\\Users\\elite\\Desktop\\RE jadx\\jadx-mcp-server\\jadx_mcp_server.py",
        "--jadx-host", "127.0.0.1",
        "--jadx-port", "8650"
      ],
      "env": {
        "LANGSMITH_API_KEY": "your_langsmith_key_here"
      }
    }
  }
}
```

## 🧠 The Optimal AI Workflow

To get the most out of this tool and save API costs, use the following workflow when prompting your AI:

1. **Discovery**:
   Ask the AI to use `get_package_tree` and `get_android_manifest` to understand the app's structure and permissions.
2. **Skeleton Analysis**:
   Instead of fetching a whole class, tell the AI to use `get_class_outline("com.example.MainActivity")`. This returns the class structure (methods and fields) while stripping the heavy method bodies.
3. **Deep Inspection**:
   Once the AI identifies a specific method of interest from the outline, it can use `get_method_by_name` to fetch just that method.
4. **Memory Persistence**:
   Instruct the AI: *"Save your findings on MainActivity to memory."* The AI will use `save_class_analysis`.
5. **Recall**:
   Later in the session, the AI can use `get_class_analysis` to retrieve its findings without needing to re-read the Java code.

## ⚙️ Configuration & Observability

### Tool Profiles
To minimize token waste in the tool manifest, the server hides niche tools (like the debugger or refactoring suite) by default. You or the AI can change this on the fly:
* Call `set_tool_profile("debug")` to enable debugger tools.
* Call `set_tool_profile("full")` to expose all 38 tools.

### Tracing (LangSmith)
If `LANGSMITH_API_KEY` is provided in your `.env` or MCP config, all tool calls are logged to LangSmith under the project `jadx-mcp-server`. This includes latency, input/output, and estimated token counts.

Even without LangSmith, you can ask the AI to call `get_server_stats()` to retrieve local, in-memory statistics about tool latency and usage.

## 🛡️ Security Warning
By default, the server expects to connect to JADX on `127.0.0.1`. If you run the MCP server in HTTP mode (`--http --host 0.0.0.0`), be aware that the connection is unauthenticated. Only expose the server on trusted networks.

Prompt to give in the chat:
Begin the forensic analysis on the loaded APK. I want you to find the attacker's database URL or any API keys. If anything is encrypted, write a Python script to decrypt it based on the Java code