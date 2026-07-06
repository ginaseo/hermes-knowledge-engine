# Architecture

## Overview

Gina Agent is a sequential processor pipeline. Each stage reads from the previous
stage's output. Incremental state tracking ensures only changed files are reprocessed.

---

## Processor Pipeline

```
Input:  HermesVault/slack/          (raw Slack markdown exports)
          │
          ▼
        MarkdownProcessor            adds YAML front-matter, copies to knowledge/slack/
        WikiProcessor                copies to wiki/slack/
          │
          ▼ (reads knowledge/slack/)
        SummaryProcessor             calls LLM → knowledge/summary/
          │
          ├──────────────────────────────────────────────────┐
          ▼                          ▼                       ▼
        EntityProcessor            KeywordProcessor       RelatedProcessor
        knowledge/entity/          knowledge/keywords/    knowledge/related/
        projects/, people/, wiki/
          │
          ▼ (after entity + related)
        DescriptionFillProcessor   enriches wiki/{Technology,Organization,Concept}
                                    TODO stubs using matching summary + related text
          │
          ▼ (always runs)
        Cleaner                    removes invalid/empty stub files
        VaultIndexer               builds index/vault_index.json
        Validator                  checks UTF-8 + JSON integrity
```

Entity, Keyword, and Related processors are independent of each other and can
run concurrently with `--parallel`.

---

## ProcessingState

`processor/processing_state.py`

Each processor owns a named state file in `HermesVault/index/<name>_state.json`.
The state maps absolute file paths to their last-seen `mtime` (float).

```
{
  "/abs/path/to/file.md": 1718000000.123456
}
```

`is_modified(file)` returns `True` if the file's current `mtime` differs from the stored value.
`update(file)` records the current `mtime`. `save()` persists to disk.

`force=True` bypasses the check — `is_modified` always returns `True`.

---

## LLM Cache

`processor/llm/cache.py`

Responses are keyed by `SHA256(prompt)`. The cache file is loaded once at
`LLMClient.__init__` and written at most once per processor run (via `flush()`,
called from `LLMClient.__exit__`).

`put()` updates in-memory only. `flush()` merges with the on-disk file under a
threading lock, making it safe for parallel use.

---

## Vault Structure

```
HermesVault/
├── slack/                  raw Slack markdown input
├── knowledge/
│   ├── slack/              processed markdown (with front-matter)
│   ├── summary/            LLM-generated summaries
│   ├── entity/             extracted entity JSON
│   ├── keywords/           keyword lists
│   └── related/            related document links
├── projects/               auto-generated project stubs
├── people/                 auto-generated person stubs
├── wiki/                   auto-generated wiki stubs + slack copies
├── index/
│   ├── *_state.json        incremental state per processor
│   ├── vault_index.json    full document index for search
│   ├── job_history.json    job execution history (rolling 500)
│   └── evaluation_history.json  evaluation snapshots (rolling 365)
├── config/
│   └── schedule.yaml       daemon job schedule
├── benchmark/
│   └── questions.json      auto-generated retrieval benchmark questions
├── reports/
│   └── daily-learning.md   daily knowledge evaluation report
└── cache/
    └── llm_cache.json      LLM response cache
```

---

## Logging

`processor/log.py`

All output uses Python's `logging` module with a `%(message)s` format to preserve
the existing `[TAG] message` console appearance.

The `_SmartHandler` routes log records to a thread-local `StringIO` buffer when one
is active (set by `log.capture(fn)`). This enables parallel processors to accumulate
output independently, which the runner then flushes in original order — preventing
interleaved console output.

---

## Configuration

`processor/config.py`

Reads environment variables once at import time (via `load_dotenv()`). Exposes a
frozen `Config` dataclass as the module-level singleton `cfg`.

`cfg.validate_llm()` raises `EnvironmentError` with a clear message when
`HERMES_API_URL` or `HERMES_API_KEY` are absent. Called from `LLMClient.__init__`
so non-LLM processors can run without credentials.

---

## Daemon

`processor/daemon.py`

`run_daemon()` polls every 10 seconds. For each tick it checks whether any job's
`next_run` timestamp has elapsed. If the schedule file has been modified since last
load, it hot-reloads — preserving each job's `next_run` so no jobs are skipped or
double-triggered.

Each job is run via `_make_processor(name)` (importlib lookup in `_PROCESSOR_MAP`).
On failure, the job is retried up to `retry.count` times using `RetryPolicy.wait_for(attempt)`:
- `exponential`: `delay * 2^attempt`
- `linear`: `delay * (attempt + 1)`
- `fixed`: `delay`

Every execution (success or final failure) is recorded to `JobHistory`.

---

## Job History

`processor/history.py`

`JobRecord` dataclass fields: `name`, `start_time`, `finish_time`, `duration`,
`status` (`ok`/`fail`), `exception`, `retry_count`.

`JobHistory` loads `HermesVault/index/job_history.json` on init. `append()` adds a
record and trims to 500 most recent before writing. `last_success(name)` walks in
reverse to find the most recent `ok` entry.

---

## Knowledge Evaluation

`processor/evaluator.py`

Five phases, all computed locally without LLM calls:

1. **Stats** (`_scan_stats`) — file counts per vault folder
2. **Growth** (`_scan_growth`) — `mtime`-based new-file counts for 1d / 7d / 30d
3. **Quality** (`_scan_quality`) — stem intersection for coverage %; BFS on `[[wikilinks]]` for broken refs
4. **Graph** (`_build_graph`) — entity names as nodes, `[[links]]` in related files as edges; BFS for connected components
5. **Scoring** — `health = 100 − Σ(deductions)`, `learning = health × 0.7 + min(new_docs_7d × 5, 30)`

No external graph library — adjacency list + BFS implemented inline.

---

## Retrieval Benchmark

`processor/retrieval.py`

Keyword overlap scoring: `_score(question, doc) = |qkw ∩ dkw| / |qkw|`. Stop-word
filtered. Questions auto-generated from the top 3 entities per entity JSON file.

Metrics: Top-K accuracy (1/3/5), Recall, Precision, F1.

---

## Execution Flow

```
hermes [subcommand] [--force] [--parallel] [--watch[=N]]
       [--log-level=X] [--log-file=path] [--last=N] [targets...]

Subcommands: run (default), watch, validate, clean, benchmark,
             daemon, history, evaluate, benchmark-retrieval

ProcessorRunner.__init__
  └── extracts subcommand from argv[1] if known
  └── parses flags and targets
  └── calls log.setup(level, log_file)
  └── instantiates all processors

ProcessorRunner.run()
  ├── watch / --watch       → _watch() → loop: try _run_once() + sleep
  ├── validate              → Validator().process()
  ├── clean                 → Cleaner().process()
  ├── benchmark             → _benchmark() → processors + timing table
  ├── daemon                → daemon.run_daemon() [lazy import]
  ├── history               → JobHistory().display(n=last_n) [lazy import]
  ├── evaluate              → Evaluator().run() [lazy import]
  ├── benchmark-retrieval   → RetrievalBenchmark().run() [lazy import]
  └── run / default         → _run_once()

_run_once()
  ├── _run_sequential(pending)  (default)
  └── _run_parallel(pending)    (--parallel)
      └── entity/keyword/related → ThreadPoolExecutor
          └── each thread: log.capture(processor.process)
          └── results flushed to stdout in original order
```

---

## Architecture Status

**Status:** FROZEN
**Version:** v1.0
**Freeze Date:** 2026-07

### Current Architecture

- Hermes = Agent Runtime
- Gina = Knowledge Engine
- Obsidian = Source of Truth
- MCP = Integration Layer
- Knowledge Pipeline = Independent

### Design Principles

- Reuse Before Build
- YAGNI
- Keep Pipeline Independent
- MCP is the only integration point
- Obsidian is never synchronized into Hermes Memory
- Add abstractions only after a second implementation exists

### Gina MCP Server (Phase 1 target — not yet implemented)

```
Hermes Agent (Gateway/Scheduler/Memory/Skill/MCP client) — unmodified
        │  MCP (config.yaml mcp_servers entry only)
        ▼
Gina MCP Server
  ├── search()          keyword lookup over index/vault_index.json
  ├── build_context()   wiki doc + bounded Related Links expansion
  ├── health()           liveness/readiness, cheap
  └── evaluate()/briefing()  thin wrappers over existing Evaluator output
        │
Knowledge Pipeline (this repo, daemon.py) — unmodified, independent process
        │
   HermesVault (Obsidian, Source of Truth)
```

Any change that violates a Design Principle above (e.g. syncing Obsidian into
Hermes Memory, adding a second integration point besides MCP, introducing a
Retriever abstraction before a second implementation exists) is an
**architecture change** and needs its own review — not a routine feature add.
