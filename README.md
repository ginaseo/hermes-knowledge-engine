# Gina Agent

A personal knowledge pipeline that automatically collects Slack messages and processes them into a structured Obsidian vault using an LLM.

---

## Features

- Incremental processing — skips unchanged files
- LLM response cache — avoids redundant API calls
- `--force` mode — reprocesses all files
- `--parallel` mode — runs entity/keyword/related concurrently
- `--watch` mode — polls for changes at a configurable interval
- Subcommands — `run`, `watch`, `validate`, `clean`, `benchmark`, `daemon`, `history`, `evaluate`, `benchmark-retrieval`
- Structured logging — optional file output with rotating handler
- Validator — incremental UTF-8 and JSON checks
- Cleaner — removes invalid or empty stub files

---

## Installation

```bash
# Clone and set up a virtual environment
git clone https://github.com/ginaseo/gina-knowledge-engine.git
cd gina-knowledge-engine
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# Install as a package (exposes the `hermes` CLI command)
pip install .

# Or install runtime deps only
pip install -r requirements.txt
```

See [INSTALL.md](INSTALL.md) for full setup instructions.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HERMES_API_URL` | Yes | Base URL of the LLM API (OpenAI-compatible) |
| `HERMES_API_KEY` | Yes | API key for authentication |
| `HERMES_VAULT` | No | Path to vault directory (default: `./HermesVault`) |
| `LOG_LEVEL` | No | Logging level: `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |

Set these in a `.env` file in the project root.

---

## Usage

### Via `hermes` CLI (after `pip install .`)

```bash
hermes                      # full pipeline
hermes run --force          # reprocess all files
hermes run summary entity   # specific processors only
hermes watch                # poll every 30s
hermes watch --watch=60     # poll every 60s
hermes validate             # run validation only
hermes clean                # run cleaner only
hermes benchmark            # run pipeline and report timing
hermes daemon               # start continuously scheduled job runner
hermes history              # show last 20 job executions
hermes history --last=50    # show last 50 job executions
hermes evaluate             # knowledge stats, quality, health & learning scores
hermes benchmark-retrieval  # evaluate search/retrieval quality
```

### Via `python -m processor.runner` (no install required)

```bash
python -m processor.runner                    # full pipeline
python -m processor.runner --force            # reprocess all
python -m processor.runner summary entity     # specific processors
python -m processor.runner --parallel         # parallel mode
python -m processor.runner --watch            # watch mode (30s)
python -m processor.runner --watch=60         # watch mode (60s)
python -m processor.runner benchmark          # benchmark
python -m processor.runner validate           # validate only
python -m processor.runner --log-level=debug  # verbose logging
python -m processor.runner --log-file=logs/hermes.log  # log to file
```

---

## Processor Pipeline

```
slack/ (raw)
  └─→ MarkdownProcessor  →  knowledge/slack/
  └─→ WikiProcessor      →  wiki/slack/

knowledge/slack/
  └─→ SummaryProcessor   →  knowledge/summary/

knowledge/summary/
  ├─→ EntityProcessor    →  knowledge/entity/ + projects/ + people/ + wiki/
  ├─→ KeywordProcessor   →  knowledge/keywords/
  └─→ RelatedProcessor   →  knowledge/related/

(always runs)
  ├─→ Cleaner            →  removes invalid/empty stubs
  ├─→ VaultIndexer       →  index/vault_index.json
  └─→ Validator          →  UTF-8 + JSON validation
```

---

## Folder Structure

```
gina-knowledge-engine/
├── processor/
│   ├── config.py               # Centralized env config + fail-fast validation
│   ├── log.py                  # Logging setup (thread-local capture)
│   ├── processing_state.py     # Incremental state tracking
│   ├── runner.py               # CLI entry point (hermes)
│   ├── daemon.py               # Scheduled job runner (hermes daemon)
│   ├── history.py              # Job execution history persistence
│   ├── evaluator.py            # Knowledge stats, quality, health & learning
│   ├── retrieval.py            # Retrieval benchmark + question generation
│   ├── llm/
│   │   ├── client.py           # OpenAI-compatible LLM client
│   │   └── cache.py            # SHA256-keyed response cache
│   ├── mcp/
│   │   └── server.py           # MCP server (search/build_context/health) for Hermes
│   ├── markdown_processor.py
│   ├── wiki_processor.py
│   ├── summary_processor.py
│   ├── entity_processor.py
│   ├── keyword_processor.py
│   ├── related_processor.py
│   ├── validator.py
│   ├── vault_indexer.py
│   └── cleaner.py
├── tests/
├── HermesVault/                # Output vault (gitignored)
│   ├── config/
│   │   └── schedule.yaml       # Daemon job schedule
│   ├── index/
│   │   ├── job_history.json    # Job execution history (rolling 500)
│   │   └── evaluation_history.json  # Evaluation history (rolling 365)
│   ├── benchmark/
│   │   └── questions.json      # Auto-generated retrieval benchmark questions
│   └── reports/
│       └── daily-learning.md   # Daily learning report
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

---

## Incremental Processing

Each processor tracks file modification times in `HermesVault/index/<name>_state.json`.
A file is only reprocessed when its `mtime` changes. Use `--force` to bypass this.

## LLM Cache

Responses are cached by SHA256 hash of the prompt in `HermesVault/cache/llm_cache.json`.
Cache is written to disk once per processor run (not on every API call).

## Parallel Mode

`--parallel` runs `entity`, `keyword`, and `related` concurrently using `ThreadPoolExecutor`.
Console output is buffered per thread and flushed in original order — no interleaving.

## Watch Mode

`--watch` (or `watch` subcommand) polls the pipeline on a fixed interval. If a run
fails with an unhandled exception, the error is logged and the watch loop continues.
Incremental processing ensures only changed files are processed on each tick.

## Fail-Fast Configuration

Missing `HERMES_API_URL` or `HERMES_API_KEY` raises a clear `EnvironmentError` when
the first LLM processor runs — not an obscure API error buried in a traceback.
Processors that don't call the LLM (markdown, wiki, cleaner, index, validator) run
without credentials.

## Daemon Mode

`hermes daemon` reads `HermesVault/config/schedule.yaml` and runs processors on their
configured intervals. If the file doesn't exist, a default schedule is created.
The schedule is hot-reloaded when the file changes. Jobs are retried with configurable
backoff. Every execution is recorded to `HermesVault/index/job_history.json`.

```yaml
# HermesVault/config/schedule.yaml
jobs:
  summary:
    every: 10m
  entity:
    every: 10m
  index:
    every: hour
  cleaner:
    every: day

retry:
  count: 3
  delay: 30s
  backoff: exponential  # or linear, fixed
```

Interval formats: `30s`, `5m`, `2h`, `1d`, `hour`, `day`, `sunday`

## Knowledge Evaluation

`hermes evaluate` scans the vault and prints:
- **Knowledge Statistics** — document, summary, entity, keyword, relation, project, people, wiki counts
- **Knowledge Growth** — new items in the last 1/7/30 days
- **Knowledge Quality** — coverage percentages, missing files, orphan entities, broken references
- **Graph Metrics** — nodes, edges, density, connected components, isolated nodes
- **Health Score** (0–100) — weighted deductions for quality gaps
- **Learning Score** (0–100) — health × 0.7 + growth bonus (capped at 100)

Results are saved to `HermesVault/index/evaluation_history.json` and a daily report is
written to `HermesVault/reports/daily-learning.md`.

## Retrieval Benchmark

`hermes benchmark-retrieval` evaluates the keyword-based search quality:
- Auto-generates questions from entity JSON files if none exist
- Reports Top-1 / Top-3 / Top-5 accuracy, Recall, Precision, F1 Score

---

## MCP Server (Phase 1 — Hermes integration)

Exposes the vault as an [MCP](https://modelcontextprotocol.io) server so any MCP
client (Hermes, Claude Desktop, Cursor, VS Code, ChatGPT) can search and read
Gina's knowledge without syncing or copying it anywhere. Read-only — the
Knowledge Pipeline above is unaffected and keeps running independently.

```bash
pip install .              # installs the `mcp` dependency too
gina-mcp                   # starts the stdio MCP server
# or
python -m processor.mcp.server
```

Flow: `Hermes → MCP → search() → build_context() → LLM`

```
search("Kafka")
  → [{"id": "wiki/Kafka.md", "title": "Kafka", "type": "wiki", "score": 0.8}, ...]

build_context("wiki/Kafka.md", max_related=3, max_tokens=2000)
  → { "context": "<wiki body + up to 3 Related Links excerpts>",
      "sources": ["wiki/Kafka.md", "wiki/Java.md", ...],
      "truncated": false }

health()
  → { "status": "ok", "vault_accessible": true, "uptime_s": 42.1 }
```

### Registering with Hermes

On the EC2 host running Hermes Agent, install this package (`pip install .`
inside the Hermes venv, or anywhere `gina-mcp` ends up on `PATH`), then add a
stdio entry to Hermes's own config — no new registration mechanism, this is
Hermes's standard MCP config format:

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  gina_wiki:
    command: "gina-mcp"
    # cwd/env only needed if HermesVault isn't next to gina-mcp on PATH
```

Reload without restarting Hermes: `/reload-mcp`. Hermes should then expose
`mcp_gina_wiki_search`, `mcp_gina_wiki_build_context`, `mcp_gina_wiki_health`
(Hermes's standard `mcp_<server>_<tool>` naming — verify the exact prefix in
your Hermes version's `hermes mcp list` or equivalent).

### Verifying the connection

Locally verified with the official `mcp` Python SDK acting as a generic MCP
client (the same protocol Hermes speaks — this is not Hermes-specific):

```bash
python -c "
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command='gina-mcp', args=[])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
asyncio.run(main())
"
```
Expect `['search', 'build_context', 'health']`. On the real EC2 box, confirm
the same three names show up through Hermes's own tool listing — that step
needs to be run against the actual Hermes instance, not something verifiable
from this repo.

### Example Skill: `/wiki`

Optional — lets a user type `/wiki Kafka` instead of relying on Hermes to
decide when to call the MCP tools on its own. Drop this at
`~/.hermes/skills/knowledge/wiki/SKILL.md` on the EC2 host (standard Hermes
Skill format, not a new mechanism):

```markdown
---
name: wiki
description: Search Gina Agent's Obsidian knowledge base and answer from it
metadata:
  hermes:
    requires_toolsets: [mcp]
---
# Wiki

## When to Use
The user asks about a project, technology, person, or concept that might be
documented in the Gina knowledge base (e.g. "Kafka가 뭐야?", "/wiki Kafka").

## Procedure
1. Call `mcp_gina_wiki_search` with the user's topic as `query`.
2. If `total` is 0, say nothing is documented yet — don't guess.
3. Otherwise call `mcp_gina_wiki_build_context` with the top result's `id`.
4. Answer using only the returned `context`. Mention `sources` if asked
   where the information came from.
```

### Example question flow

```
User: "Kafka가 뭐야?"
  → mcp_gina_wiki_search(query="Kafka")
      → {"total": 1, "results": [{"id": "wiki/Kafka.md", ...}]}
  → mcp_gina_wiki_build_context(id="wiki/Kafka.md")
      → {"context": "...", "sources": [...], "truncated": false}
  → Hermes LLM answers from `context`
```

### Tools

| Tool | Input | Notes |
|---|---|---|
| `search(query, top_k=5)` | free-text query | reuses `retrieval._search`/`_score` as-is, no new ranking logic |
| `build_context(id, max_related=3, max_tokens=2000)` | `id` from a `search()` result | follows `[[Related Links]]` up to `max_related`, truncates at `max_tokens*4` chars |
| `health()` | none | vault reachability + uptime, no content scan |

Errors follow a fixed contract: `{"error": {"code", "message", "retryable"}}` with
`code` in `NOT_FOUND | INVALID_ARGUMENT | TIMEOUT | VAULT_UNAVAILABLE | CORRUPT_FILE | INTERNAL`.
`search()` has a 2s budget, `build_context()` a 5s hard / 3s soft budget (returns
partial context with `truncated: true` past the soft budget instead of failing).

See `ARCHITECTURE.md` → "Architecture Status" for the frozen design this
implements, and why `evaluate()`/`briefing()` tools are deferred to Phase 2.
