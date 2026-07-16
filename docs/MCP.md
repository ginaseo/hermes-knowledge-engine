# MCP Server

Exposes the vault as an [MCP](https://modelcontextprotocol.io) server so any MCP
client (Hermes, Claude Desktop, Cursor, VS Code, ChatGPT) can search and read
Hermes's knowledge without syncing or copying it anywhere.

## Starting the Server

```bash
pip install .
hermes-mcp
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
| `evaluate()` | none | vault stats, quality, health/learning scores |
| `briefing(date="")` | date `YYYY-MM-DD` | summarizes recent vault changes |
| `recommend(category="stock", top_k=5)` | `stock` \| `job`, count | ranks entities by graph connectivity |
| `timeline(start_date="", end_date="", entity="", days=30)` | date range, optional entity filter | chronological knowledge accumulation |

## Registering with Hermes

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  hermes_wiki:
    command: "hermes-mcp"
```

Reload without restarting: `/reload-mcp`

### Verified Registration (EC2)

Actually used in production — registers the server with the correct `PYTHONPATH`
so stdio launch resolves `processor.mcp.server` regardless of Hermes Gateway's CWD:

```bash
hermes mcp add hermes-wiki \
  --command python \
  --env PYTHONPATH=/opt/knowledge-engine \
  --args -m processor.mcp.server
```

> `/opt/...` is a path inside the `hermes-gateway` Docker container (bind-mounted
> from `/home/ubuntu/hermes-knowledge-engine` via `hermes-docker/docker-compose.yml`),
> not the EC2 host's own `/opt`. **Do not use `/opt/hermes`** — that path already
> exists inside the `nousresearch/hermes-agent` image itself (its own `cli.py`,
> `agent/`, etc.); mounting this repo there would shadow the vendor's install.
> `/opt/knowledge-engine` is the collision-free destination actually verified on EC2.

## Known Issue: ModuleNotFoundError

**Cause**: Hermes Gateway launches stdio MCP servers without project directory as CWD.
**Solution**: same as above (`--env PYTHONPATH=/opt/knowledge-engine`).

## Slack Query Example

Asking in Slack routes through Hermes → MCP → `search()` → `build_context()` → LLM:

```
User: 오늘 주식 브리핑 요약해줘
Bot:  [RAG 응답 — 주식 모닝 브리핑 채널의 최신 요약/엔티티를 검색해 컨텍스트로 구성 후 답변]
```

## Vault Scale

Current `vault_index.json`: 136+ documents (summary, entity, keyword, related, wiki 포함).

## Error Contract

`{"error": {"code", "message", "retryable"}}`
Codes: `NOT_FOUND | INVALID_ARGUMENT | TIMEOUT | VAULT_UNAVAILABLE | CORRUPT_FILE | INTERNAL`

- `search()` — 2s budget
- `build_context()` — 5s hard / 3s soft budget

See `ARCHITECTURE.md` for full design details.
