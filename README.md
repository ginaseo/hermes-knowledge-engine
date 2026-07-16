# Hermes Knowledge Engine

**🇰🇷 [한국어](README.ko.md)**

A personal knowledge pipeline that turns your Slack conversations and Claude Code
sessions into a self-organizing, searchable Obsidian vault — automatically summarized,
linked, and cross-referenced by an LLM.

Point it at a Slack workspace and/or your Claude Code sessions, and it keeps a living
wiki of projects, people, and concepts up to date on its own — no manual note-taking.

---

## Features

- **Multi-source ingest** — Slack channels and Claude Code session transcripts today;
  new sources plug in with one small provider
- **Automatic knowledge graph** — entities (projects, people, concepts), keywords, and
  cross-links extracted and maintained by an LLM
- **Self-updating wiki** — Markdown pages generated and kept current as new
  conversations come in
- **Incremental processing** — only reprocesses what changed
- **LLM response cache** — avoids redundant API calls
- **Watch & daemon modes** — runs continuously on a schedule, unattended
- **Knowledge evaluation** — health/learning scores, coverage gaps, retrieval
  benchmarking
- **MCP server** — query your vault directly from Claude (search, context building,
  health checks)

---

## Quick Start

```bash
# 1. Clone and set up a virtual environment
git clone https://github.com/ginaseo/hermes-knowledge-engine.git
cd hermes-knowledge-engine
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# 2. Install (exposes the `hermes` CLI command)
pip install .

# 3. Configure environment variables
cp .env.example .env
# Set HERMES_API_URL / HERMES_API_KEY (LLM endpoint) and, if using Slack, SLACK_BOT_TOKEN / SLACK_CHANNEL_IDS

# 4. Run the pipeline
hermes run
```

See [INSTALL.md](docs/INSTALL.md) for full setup, environment variables, and dev setup.

### Common Commands

```bash
hermes                      # full pipeline
hermes watch                # poll for changes every 30s
hermes daemon               # continuously scheduled job runner
hermes evaluate             # knowledge stats, quality, health & learning scores
hermes validate             # validate vault integrity
hermes --help               # everything else
```

---

## Learn More

- [INSTALL.md](docs/INSTALL.md) — full installation, configuration, and dev setup
- [docs/pipeline.md](docs/pipeline.md) — processor pipeline, folder structure, caching/incremental details
- [docs/ingest-sources.md](docs/ingest-sources.md) — Slack & Claude Code providers, adding a new source
- [docs/operations.md](docs/operations.md) — daemon mode, evaluation, retrieval benchmark, deployment notes
- [docs/vault-sync.md](docs/vault-sync.md) — mirroring the vault across machines with Syncthing
- [MCP.md](docs/MCP.md) — MCP server setup and tools
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design
