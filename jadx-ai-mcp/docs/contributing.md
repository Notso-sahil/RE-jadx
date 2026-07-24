# Contributing Guide

We welcome contributions! Help us make Android reverse engineering smarter.

## Development Setup

### Prerequisites
- JDK 11+
- Python 3.10+
- Gradle
- Git

### 1. Java Plugin Development

```bash
# Clone repo
git clone https://github.com/zinja-coder/jadx-ai-mcp.git
cd jadx-ai-mcp

# Build plugin
./gradlew build

# Install locally
cp build/libs/jadx-ai-mcp-*.jar ~/.jadx/plugins/
```

### 2. Python Server Development

```bash
cd jadx-mcp-server

# Create venv
uv venv
source .venv/bin/activate

# Install editable
uv pip install -e .
```

---

## Testing

### Running Tests
```bash
# Java Tests
./gradlew test

# Python Tests
pytest tests/
```

### Manual Testing
1. Run JADX-GUI with local plugin.
2. Run Python server locally.
3. Use `mcp-inspector` or Claude Desktop to call tools.

---

## Coding Standards

### Java
- **Style**: Google Java Style
- **Indentation**: 4 spaces
- **Nullability**: Use `@Nullable` / `@NonNull`
- **Concurrency**: Respect JADX threading rules (EDT vs Workers)

### Python
- **Style**: PEP 8 (Black formatted)
- **Type Hints**: Required for all tool functions
- **Docstrings**: Google style

---
