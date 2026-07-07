# MCP Server

Exposes the vault as an [MCP](https://modelcontextprotocol.io) server so any MCP
client (Hermes, Claude Desktop, Cursor, VS Code, ChatGPT) can search and read
Gina's knowledge without syncing or copying it anywhere.

## Starting the Server

```bash
pip install .
gina-mcp
# or
python -m processor.mcp.server
```

Flow: `Hermes → MCP → search() → build_context() → LLM`

## Tools

| Tool | Input | Notes |
|------|-------|-------|
| `search(query, top_k=5)` | free-text query | keyword-based search against vault index |
| `build_context(id, max_related=3, max_tokens=2000)` | id from search() | follows Related Links, truncates at max_tokens |
| `health()` | none | vault reachability + uptime |

## Registering with Hermes

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  gina_wiki:
    command: "gina-mcp"
```

Reload without restarting: `/reload-mcp`

## Known Issue: ModuleNotFoundError

**Cause**: Hermes Gateway launches stdio MCP servers without project directory as CWD.
**Solution**:

```bash
hermes mcp add gina \
  --command python \
  --env PYTHONPATH=/opt/gina \
  --args -m processor.mcp.server
```

## Error Contract

`{"error": {"code", "message", "retryable"}}`
Codes: `NOT_FOUND | INVALID_ARGUMENT | TIMEOUT | VAULT_UNAVAILABLE | CORRUPT_FILE | INTERNAL`

- `search()` — 2s budget
- `build_context()` — 5s hard / 3s soft budget

See `ARCHITECTURE.md` for full design details.
