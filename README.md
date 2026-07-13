# Hermes Knowledge Engine

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
git clone https://github.com/ginaseo/hermes-knowledge-engine.git
cd hermes-knowledge-engine
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
| `HERMES_MODEL` | Yes | LLM model name (e.g. `llama-3.3-70b-versatile`) |
| `SLACK_BOT_TOKEN` | Yes | Slack Bot Token (`xoxb-...`) |
| `SLACK_CHANNEL_IDS` | Yes | Comma-separated Slack channel IDs |
| `HERMES_VAULT` | No | Path to vault directory (default: `./HermesVault`) |
| `LOG_LEVEL` | No | Logging level: `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |

Set these in a `.env` file in the project root.

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
hermes-knowledge-engine/
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

## MCP Server

See [MCP.md](MCP.md) for setup, tools, and Hermes integration details.

---

## Deployment (EC2)

Currently running on AWS EC2 (Ubuntu 24.04).

### Infrastructure
- **EC2**: AWS EC2, Ubuntu 24.04
- **Docker**: hermes-gateway (:8642), hermes-dashboard (:9119)
- **Vault**: `/home/ubuntu/gina-knowledge-engine/HermesVault`
- **LLM**: OpenAI-compatible API (Gemini / OpenRouter / OpenAI)
- **Automation**: systemd services

### systemd Services
| Service | Description |
|---------|-------------|
| `gina-knowledge` | Pipeline watch mode (every 30s) |
| `gina-slack` | Slack message collector (every 5min) |

```bash
sudo systemctl status gina-knowledge
sudo systemctl status gina-slack
sudo journalctl -u gina-knowledge -f
```

### Slack Channels
| Channel | Description |
|------------|-------------|
| Main channel | General updates |
| Stock briefing | Daily stock morning briefing |
| Job briefing | Backend job postings briefing |

> Channel IDs are stored in `.env` (not committed).

---

## Roadmap

- GitHub ingest provider (issues/PRs → vault) — planned, not started
- Claude ingest provider — planned, not started
