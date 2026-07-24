# Python Module Reference

Complete reference for the JADX-MCP-Server Python codebase.

## Module: `jadx_mcp_server.py`

Main entry point for the MCP server.

### Overview

This module initializes the FastMCP server and registers all MCP tools. It handles:
- Command-line argument parsing
- Server configuration
- Health check validation
- Tool registration
- Server startup

### Command-Line Arguments

```python
parser = argparse.ArgumentParser("MCP Server for Jadx")
parser.add_argument("--http", help="Serve MCP Server over HTTP stream", action="store_true", default=False)
parser.add_argument("--host", help="Host interface to bind for --http (default: 127.0.0.1)", default="127.0.0.1", type=str)
parser.add_argument("--port", help="Port for --http (default: 8651)", default=8651, type=int)
parser.add_argument("--jadx-host", help="JADX AI MCP Plugin host (default: 127.0.0.1)", default="127.0.0.1", type=str)
parser.add_argument("--jadx-port", help="JADX AI MCP Plugin port (default: 8650)", default=8650, type=int)
```

### Usage Examples

```bash
# Standard stdio mode (for Claude Desktop)
uv run jadx_mcp_server.py

# HTTP mode (for remote/web clients)
uv run jadx_mcp_server.py --http --port 8651

# Custom JADX plugin port
uv run jadx_mcp_server.py --jadx-port 8652
```

### Function: `main()`

**Description**: Initializes and runs the MCP server.

**Flow**:
1. Parse command-line arguments
2. Configure JADX plugin connection
3. Display banner
4. Perform health check
5. Start appropriate transport (stdio or HTTP)

**Code**:
```python
def main():
    parser = argparse.ArgumentParser("MCP Server for Jadx")
    # ... argument setup ...
    args = parser.parse_args()

    # Configure
    config.set_jadx_port(args.jadx_port)

    # Health check
    print(jadx_mcp_server_banner())
    result = config.health_ping()
    print(f"Health check result: {result}")

    # Run server
    if args.http:
        mcp.run(transport="streamable-http", port=args.port)
    else:
        mcp.run()
```

---

## Module: `src.server.config`

Configuration and HTTP client management for communicating with the JADX plugin.

### Global Configuration

```python
JADX_HOST: str = "127.0.0.1"
JADX_PORT: int = 8650  # Default plugin port
JADX_HTTP_BASE: str = f"http://{JADX_HOST}:{JADX_PORT}"
```

### Function: `set_jadx_host(host: str) -> None`

**Description**: Updates the JADX plugin host configuration.

**Parameters**:
- `host` (str): IP address or hostname of the JADX AI MCP plugin

### Function: `set_jadx_port(port: int) -> None`

**Description**: Updates the JADX plugin port configuration.

**Parameters**:
- `port` (int): TCP port where JADX AI MCP plugin listens

**Side Effects**: Updates global `JADX_PORT` and `JADX_HTTP_BASE`

**Example**:
```python
set_jadx_host("192.168.1.100")
set_jadx_port(8652)
# Now all requests go to http://192.168.1.100:8652
```

### Function: `health_ping() -> Union[str, Dict[str, Any]]`

**Description**: Checks if JADX plugin is reachable.

**Returns**:
- Success: `"OK"` string
- Failure: `{"error": "<error message>"}`

**Timeout**: 60 seconds

**Example**:
```python
result = health_ping()
if isinstance(result, str):
    print("Plugin is healthy")
else:
    print(f"Health check failed: {result['error']}")
```

### Function: `get_from_jadx(endpoint: str, params: Dict[str, Any] = {}) -> Union[str, Dict[str, Any]]`

**Description**: Generic async HTTP GET request to JADX plugin.

**Parameters**:
- `endpoint` (str): API endpoint path (e.g., "class-source", "manifest")
- `params` (dict): Query parameters for the request

**Returns**:
- Success: Parsed JSON dict or `{"response": text}` if not JSON
- Failure: `{"error": "<error message>"}`

**Security Feature**:
- Uses `trust_env=False` on the `httpx.AsyncClient` to prevent system proxy interference (e.g. proxying internal requests meant for `127.0.0.1`).

**Timeout**: 60 seconds

**Error Handling**:
- HTTP errors → Returns error dict with status code
- Connection errors → Returns error dict with exception message
- JSON decode errors → Returns text wrapped in dict

**Example**:
```python
# Get class source
result = await get_from_jadx("class-source", {"class_name": "com.example.MainActivity"})

if "error" not in result:
    print(result["source"])
else:
    print(f"Error: {result['error']}")
```

---

## Module: `src.PaginationUtils`

Reusable pagination framework for handling large datasets.

### Class: `PaginationUtils`

**Description**: Utility class for consistent pagination across all tools.

**Constants**:
```python
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 10000
MAX_OFFSET = 1000000
```

### Method: `validate_pagination_params(offset: int, count: int) -> tuple[int, int]`

**Description**: Validates and normalizes pagination parameters.

**Parameters**:
- `offset` (int): Requested starting offset (can be negative or excessive)
- `count` (int): Requested item count (can be negative or excessive)

**Returns**: `(validated_offset, validated_count)` tuple

**Validation Logic**:
- Clamps offset to [0, MAX_OFFSET]
- Clamps count to [0, MAX_PAGE_SIZE]

**Example**:
```python
# Input: Invalid values
offset, count = PaginationUtils.validate_pagination_params(-10, 50000)

# Output: (0, 10000)
# Negative offset becomes 0
# Excessive count clamped to MAX_PAGE_SIZE
```

### Method: `get_paginated_data(...) -> Union[Dict[str, Any], str]`

**Description**: Generic pagination handler for all JADX endpoints.

**Parameters**:
- `endpoint` (str): JADX API endpoint
- `offset` (int): Starting index (default: 0)
- `count` (int): Items to return (default: 0 = all)
- `additional_params` (dict): Extra query parameters
- `data_extractor` (Callable): Function to extract items from response
- `item_transformer` (Callable): Optional per-item transformation
- `fetch_function` (Callable): Async function to fetch data (typically `get_from_jadx`)

**Returns**: Standardized pagination response

**Error Handling (Early Return)**:
If the `fetch_function` returns an error dictionary (i.e. containing an `"error"` key), the pagination utility will immediately return the error object. This ensures API errors are properly propagated instead of swallowed into an empty list.

**Response Format**:
```python
{
    "type": "paginated-list",
    "items": [...],  # Extracted/transformed items
    "pagination": {
        "total": 1500,      # Total items available
        "offset": 100,      # Current offset
        "limit": 100,       # Items per page
        "count": 100,       # Items in this response
        "has_more": True,   # More items available?
        "next_offset": 200, # Next page offset
        "prev_offset": 0    # Previous page offset
    }
}
```

**Example**:
```python
result = await PaginationUtils.get_paginated_data(
    endpoint="all-classes",
    offset=0,
    count=50,
    data_extractor=lambda resp: resp.get("classes", []),
    fetch_function=get_from_jadx
)

print(f"Got {result['pagination']['count']} of {result['pagination']['total']} classes")
for class_name in result['items']:
    print(class_name)

if result['pagination']['has_more']:
    # Fetch next page
    next_result = await PaginationUtils.get_paginated_data(
        endpoint="all-classes",
        offset=result['pagination']['next_offset'],
        count=50,
        data_extractor=lambda resp: resp.get("classes", []),
        fetch_function=get_from_jadx
    )
```

---

## Module: `src.server.tools.class_tools`

Tools for analyzing decompiled Java classes.

### Function: `fetch_current_class() -> dict`

**MCP Tool**: `fetch_current_class`

**Description**: Fetches the currently selected class in JADX-GUI editor.

**Returns**:
```python
{
    "className": "com.example.MainActivity",
    "package": "com.example",
    "source": "public class MainActivity extends Activity { ... }"
}
```

**Use Cases**:
- Quick context gathering
- AI-assisted code review of selected class
- Starting point for deeper analysis

**Example Prompt**:
```
Fetch the currently selected class and perform a security audit
```

### Function: `get_class_source(class_name: str) -> dict`

**MCP Tool**: `get_class_source`

**Description**: Retrieves complete decompiled source for a specific class.

**Parameters**:
- `class_name` (str): Fully qualified class name

**Returns**:
```python
{
    "className": "com.example.utils.CryptoHelper",
    "source": "package com.example.utils;\n\npublic class CryptoHelper { ... }",
    "exists": True
}
```

**Error Response**:
```python
{
    "error": "CLASS_NOT_FOUND",
    "message": "Class com.example.Unknown not found"
}
```

**Example**:
```python
result = await get_class_source("com.example.MainActivity")
if result.get("exists"):
    print(result["source"])
```

### Function: `get_all_classes(offset: int = 0, count: int = 0) -> dict`

**MCP Tool**: `get_all_classes`

**Description**: Returns paginated list of all classes in the APK.

**Parameters**:
- `offset` (int): Starting index (default: 0)
- `count` (int): Number to return (0 = all, default: 0)

**Returns**: Paginated response with class names

**Performance Notes**:
- Small APKs (<1000 classes): Use count=0 to get all
- Large APKs (>1000 classes): Use pagination with count=100-500

**Example**:
```python
# Get first 200 classes
result = await get_all_classes(offset=0, count=200)

print(f"Total classes in APK: {result['pagination']['total']}")
for class_name in result['items']:
    print(class_name)

# Get next 200
if result['pagination']['has_more']:
    next_batch = await get_all_classes(
        offset=result['pagination']['next_offset'],
        count=200
    )
```

### Function: `get_smali_of_class(class_name: str) -> dict`

**MCP Tool**: `get_smali_of_class`

**Description**: Retrieves Smali (Dalvik bytecode) representation of a class.

**Parameters**:
- `class_name` (str): Fully qualified class name

**Returns**:
```python
{
    "className": "com.example.Native",
    "smali": ".class public Lcom/example/Native;\n.super Ljava/lang/Object;\n...",
    "format": "smali"
}
```

**Use Cases**:
- Low-level bytecode analysis
- Native method investigation
- Obfuscation pattern detection
- Instruction-level optimization analysis

**Example Prompt**:
```
Get the smali for NativeLib class and identify anti-debugging checks
```

---

## Module: `src.server.tools.search_tools`

Full-text search capabilities across decompiled code.

### Function: `search_classes_by_keyword(search_term: str, search_in: str = "all", package: str = "", offset: int = 0, count: int = 20) -> dict`

**MCP Tool**: `search_classes_by_keyword`

**Description**: Performs full-text search across all class source code with scope filters.

**Parameters**:
- `search_term` (str): Keyword to search for
- `search_in` (str): Search scope: "all", "code", "comments", or "strings" (default: "all")
- `package` (str): Limit search to specific package (default: "")
- `offset` (int): Pagination offset (default: 0)
- `count` (int): Results per page (default: 20)

**Returns**: Paginated search results

**Search Behavior**:
- Case-sensitive matching
- Searches in decompiled Java source
- Returns classes containing the term
- Includes match count per class

**Performance**:
- Broad terms ("a", "get") → Slow, many results
- Specific terms ("AES", "password") → Fast, focused results

**Example**:
```python
# Find all WebView usage
results = await search_classes_by_keyword("WebView", offset=0, count=50)

for item in results['items']:
    print(f"Found in: {item['className']}")
    print(f"Matches: {item['matches']}")
    print(f"Preview: {item['preview']}")
```

---

## Module: `src.server.tools.xrefs_tools`

Cross-reference analysis for tracking code usage.

### Function: `get_xrefs_to_method(class_name: str, method_name: str, offset: int = 0, count: int = 20) -> dict`

**MCP Tool**: `get_xrefs_to_method`

**Description**: Finds all locations where a method is invoked.

**Parameters**:
- `class_name` (str): Class containing the method
- `method_name` (str): Method name (can include signature)
- `offset` (int): Pagination offset (default: 0)
- `count` (int): Results per page (default: 20)

**Returns**:
```python
{
    "targetMethod": "encrypt",
    "targetClass": "com.example.crypto.AES",
    "references": [
        {
            "fromClass": "com.example.FileManager",
            "fromMethod": "void saveSecure(File)",
            "lineNumber": 120,
            "code": "String encrypted = aes.encrypt(data);"
        },
        # ... more references
    ],
    "pagination": { ... }
}
```

**Use Cases**:
- Data flow analysis
- Impact assessment for refactoring
- Vulnerability tracking
- Understanding code relationships

**Example Workflow**:
```python
# 1. Find suspicious crypto method
crypto_methods = await search_method_by_name("decrypt")

# 2. For each method, get xrefs
for method in crypto_methods['results']:
    xrefs = await get_xrefs_to_method(
        method['className'],
        method['methodName'],
        offset=0,
        count=100
    )

    # 3. Analyze each call site
    for ref in xrefs['references']:
        source = await get_class_source(ref['fromClass'])
        # Analyze if sensitive data is passed to decrypt
```

---

## Module: `src.server.tools.refactor_tools`

Code refactoring capabilities for improving readability.

### Function: `rename_class(class_name: str, new_name: str) -> dict`

**MCP Tool**: `rename_class`

**Description**: Renames a class and updates all references.

**Parameters**:
- `class_name` (str): Current fully qualified class name
- `new_name` (str): New class name (without package)

**Returns**:
```python
{
    "oldName": "com.example.a",
    "newName": "com.example.CryptoHelper",
    "success": True,
    "affectedFiles": 12  # Number of files updated
}
```

**Behavior**:
- Updates class declaration
- Updates all import statements
- Updates all instantiations
- Updates all references throughout codebase

**Best Practices**:
1. Start with leaf classes (no dependencies)
2. Use descriptive names based on functionality
3. Keep package structure intact
4. Rename systematically (not randomly)

**Example Workflow**:
```python
# Systematic deobfuscation
# 1. Identify obfuscated class
source = await get_class_source("com.example.a")

# 2. Analyze functionality
# (AI determines it's a crypto helper)

# 3. Rename
result = await rename_class("com.example.a", "CryptoHelper")

print(f"Updated {result['affectedFiles']} files")
```

---

## Module: `src.server.tools.debug_tools`

Runtime analysis during debugging sessions.

### Function: `debug_get_variables() -> dict`

**MCP Tool**: `debug_get_variables`

**Description**: Retrieves local and instance variables when debugger is paused.

**Requirements**:
- JADX debugger must be active
- Execution must be suspended at a breakpoint

**Returns**:
```python
{
    "locals": [
        {
            "name": "password",
            "type": "String",
            "value": "secret123"
        },
        {
            "name": "isValid",
            "type": "boolean",
            "value": "true"
        }
    ],
    "fields": [
        {
            "name": "mContext",
            "type": "Context",
            "value": "android.app.ContextImpl@abc123"
        }
    ]
}
```

**Use Cases**:
- Runtime security analysis
- Understanding execution flow
- Identifying sensitive data in memory
- Debugging complex logic

**Example Analysis**:
```python
# Set breakpoint at login method
# When hit, get variables
vars = await debug_get_variables()

# Check for security issues
for local in vars['locals']:
    if 'password' in local['name'].lower():
        if local['type'] == 'String':
            print("⚠️  Password stored as String (security risk)")
            print("   Recommendation: Use char[] and clear after use")
```

---

## Error Handling

All tools follow consistent error handling:

### Success Response
```python
{
    "success": True,
    "data": { ... },
    "metadata": {
        "timestamp": "2025-12-30T00:00:00Z",
        "tool": "get_class_source"
    }
}
```

### Error Response
```python
{
    "error": "CLASS_NOT_FOUND",
    "message": "Class com.example.Unknown not found",
    "details": "..."
}
```

### Common Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| `CLASS_NOT_FOUND` | Class doesn't exist | Verify class name is fully qualified |
| `METHOD_NOT_FOUND` | Method doesn't exist | Check method signature |
| `NO_APK_LOADED` | No APK in JADX | Load an APK file |
| `DEBUGGER_NOT_ACTIVE` | Debugger not running | Start JADX debugger |
| `CONNECTION_ERROR` | Can't reach plugin | Check plugin is running |
| `TIMEOUT` | Operation took >60s | Use pagination or smaller requests |

---

## Type Hints

All functions use Python type hints:

```python
from typing import Dict, List, Any, Union, Optional

async def get_class_source(class_name: str) -> Dict[str, Any]:
    ...

async def search_classes_by_keyword(
    search_term: str,
    offset: int = 0,
    count: int = 20
) -> Dict[str, Any]:
    ...
```

---

## Testing

Example test structure:

```python
import pytest
from src.server.tools import class_tools

@pytest.mark.asyncio
async def test_get_class_source():
    result = await class_tools.get_class_source("com.example.MainActivity")
    assert "source" in result
    assert result["className"] == "com.example.MainActivity"

@pytest.mark.asyncio  
async def test_class_not_found():
    result = await class_tools.get_class_source("com.example.NonExistent")
    assert "error" in result
    assert result["error"] == "CLASS_NOT_FOUND"
```

---

## Next Steps

- [Java Plugin Reference](java-api.md) - Plugin-side documentation
- [API Reference](api-reference.md) - Tool usage examples
- [Architecture](architecture.md) - System design details
