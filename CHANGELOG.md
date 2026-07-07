# Changelog
## v1.2.1 (2026-07-07)

### Added

**Phase 4 MCP Tools**
- `processor/evaluator.py`
  - Added `evaluate()` MCP tool for vault quality analysis and health score
- `processor/briefing.py`
  - Added `briefing()` MCP tool for daily knowledge briefing
- `processor/recommend.py`
  - Added `recommend()` MCP tool for stock/job recommendations using the knowledge graph
- `processor/timeline.py`
  - Added `timeline()` MCP tool for chronological knowledge history

### Changed

- `processor/mcp/server.py`
  - Registered Phase 4 MCP tools:
    - `evaluate()`
    - `briefing()`
    - `recommend()`
    - `timeline()`
  - Moved `main()` to the bottom of the file so every `@mcp.tool()` decorator is registered before `mcp.run()`
- `processor/llm/client.py`
  - Replaced hard-coded model (`hermes-agent`) with configurable LLM model for OpenAI-compatible APIs
- `.env`
  - Added OpenAI-compatible API configuration
  - Added DeepSeek API configuration
  - Added Slack multi-channel configuration

### Fixed

- Fixed MCP tool discovery issue where only three tools (`search`, `build_context`, `health`) were exposed because `mcp.run()` executed before remaining tools were registered.
- Fixed SummaryProcessor failing due to missing LLM environment variables.
- Fixed invalid model configuration causing `404 model_not_found`.
- Fixed OpenAI quota issue by migrating the pipeline to DeepSeek API.
- Fixed Hermes Gateway integration so all Phase 4 tools are discoverable.

### Verified

**Knowledge Pipeline**
- ✅ Slack → Markdown
- ✅ Markdown → Summary
- ✅ Summary → Entity
- ✅ Entity → Keyword
- ✅ Keyword → Related
- ✅ Wiki Generation
- ✅ Vault Index
- ✅ Validator

**Hermes Gateway**
- ✅ Gateway connected
- ✅ MCP connected
- ✅ `hermes mcp test gina` passed
- ✅ 7 MCP tools discovered

**Available MCP Tools**
1. `search()`
2. `build_context()`
3. `health()`
4. `evaluate()`
5. `briefing()`
6. `recommend()`
7. `timeline()`

**LLM**
- ✅ DeepSeek API integration
- ✅ OpenAI-compatible endpoint
- ✅ Summary generation working

### Result

The Gina Knowledge Engine now provides a complete end-to-end knowledge pipeline:

```
Slack / KRX / Future Providers
            │
         Ingest
            │
      Markdown Processor
            │
 Summary → Entity → Keyword → Related
            │
         Wiki Builder
            │
       Vault Indexer
            │
        HermesVault
            │
        Gina MCP Server
            │
Hermes Gateway (7 MCP Tools)
            │
Dashboard / CLI / AI Agent
```

Phase 4 is complete.

Remaining roadmap:
- Phase 5 Production
- Scheduler / Systemd automation
- Continuous knowledge accumulation
- Long-term RAG quality improvements

---

## v1.2.0 (2026-07-06)

### Added

**Gina MCP server** (Phase 1)
- `processor/mcp/server.py` — `search()`, `build_context()`, `health()` tools over stdio
- Path-traversal guard, timeout handling, tool registration
- `pyproject.toml` — `gina-mcp` CLI entry point
- `tests/test_mcp_server.py` — 7 tests (search/build_context/health, empty search, invalid id, path traversal, vault-missing, timeout)

**Description fill processor**
- `processor/description_fill_processor.py` — enriches wiki TODO stubs with LLM-generated descriptions
- `processor/prompts/description_fill_prompt.txt`
- `project_alias.json` — normalizes name variants (e.g. "장애 대응") to prevent duplicate stubs
- `tests/test_description_fill_processor.py` — 8 tests

**Ingestion providers**
- `ingest/providers/krx.py` — `KRXProvider` reads daily KOSPI200/briefing JSON, converts to markdown, dedupes by date
- `ingest/providers/slack.py` — `SLACK_CHANNEL_IDS` (comma-separated) support, falls back to `SLACK_CHANNEL_ID` for backward compat; each channel saved as separate dated markdown

### Changed
- `processor/retrieval.py` — Korean character support (`[가-힣]+`), fixed entity stem suffix (`-entity` not `-summary`), filters generic entities from benchmark questions
- `processor/related_processor.py` — injects existing doc list into prompt to prevent hallucinated `[[wikilinks]]`
- Summary prompt — removed Slack-specific wording, uses generic `{markdown}` placeholder
- `processor/evaluator.py` — replaced Unicode minus with ASCII in log output (cp949 console compat)
- Broken reference check — now includes `wiki/projects` and `wiki/people`
- Project renamed `gina-agent` → `gina-knowledge-engine` (repo URL, package name)
- Total: **129 tests**

### Fixed
- `requirements.txt` — `mcp` dependency was missing despite being declared in `pyproject.toml`

---

## v1.1.0 (2026-06-28)

### Added

**Daemon mode** (`hermes daemon`)
- `processor/daemon.py` — polling scheduler (10s tick), schedule.yaml hot-reload
- Reads `HermesVault/config/schedule.yaml`; creates default on first run
- Per-job exponential/linear/fixed retry with configurable count and delay
- Interval formats: `30s`, `5m`, `2h`, `1d`, `hour`, `day`, `sunday`
- `_make_processor()` — importlib-based factory; validates against `_PROCESSOR_MAP`
- Graceful `KeyboardInterrupt` shutdown

**Job history** (`hermes history`)
- `processor/history.py` — `JobRecord` dataclass + `JobHistory` persistence
- Rolling 500-record JSON in `HermesVault/index/job_history.json`
- `--last=N` flag to control how many records are displayed (default: 20)
- `last_success(name)` — returns finish timestamp of most recent successful run

**Knowledge evaluation** (`hermes evaluate`)
- `processor/evaluator.py` — full knowledge quality analysis
- Knowledge Statistics: documents, summaries, entities, keywords, relations, projects, people, wiki pages
- Knowledge Growth: mtime-based new-file counts for today / 7d / 30d
- Knowledge Quality: entity/keyword/relation/summary coverage %, orphan entities, broken references, duplicate entity names
- Graph Metrics: nodes, edges, density, connected components, isolated nodes (BFS, no external library)
- Health Score 0–100 with per-deduction breakdown
- Learning Score 0–100: `health × 0.7 + min(new_docs_7d × 5, 30)`
- Evaluation history: rolling 365-entry JSON in `HermesVault/index/evaluation_history.json`
- Daily learning report written to `HermesVault/reports/daily-learning.md`

**Retrieval benchmark** (`hermes benchmark-retrieval`)
- `processor/retrieval.py` — keyword overlap retrieval evaluator
- Stop-word filtered tokenization
- Auto-generates questions from entity JSON files → `HermesVault/benchmark/questions.json`
- Reports Top-1 / Top-3 / Top-5 accuracy, Recall, Precision, F1 Score

**Tests**
- `tests/test_history.py` — 5 tests (empty display, append, rolling window, last_success)
- `tests/test_daemon.py` — 13 tests (_parse_interval variants, RetryPolicy backoff variants)
- `tests/test_evaluator.py` — 7 tests (_count, health score, deductions, learning score)
- `tests/test_retrieval.py` — 8 tests (_keywords, _score, _search)
- `tests/test_runner.py` — 6 new tests (daemon/history/evaluate/benchmark-retrieval subcommands, --last)
- Total: **112 tests**

### Changed
- `processor/runner.py` — 4 new subcommands dispatched via lazy imports
- `pyproject.toml` — added `pyyaml>=6.0` to `[project.dependencies]`
- `requirements.txt` — added `pyyaml>=6.0`

---

## v1.0.0 (2026-06-27)

### Added

**CLI subcommands**
- `hermes run` / `python -m processor.runner run` — explicit run subcommand
- `hermes watch` — watch subcommand (equivalent to `--watch` flag)
- `hermes validate` — run Validator only
- `hermes clean` — run Cleaner only
- `hermes benchmark` — run full pipeline with per-processor timing table

**Logging**
- `--log-level=DEBUG|INFO|WARNING|ERROR` — configurable log level per run
- `--log-file=path` — write logs to rotating file (10 MB, 5 backups)
- `processor/log.py` — `setup()` now accepts `level` and `log_file` params

**Configuration**
- `processor/config.py` — centralized env config; reads `HERMES_API_URL`, `HERMES_API_KEY`, `HERMES_VAULT`, `LOG_LEVEL`
- `cfg.validate_llm()` — fail-fast on missing LLM credentials (called in `LLMClient.__init__`)

**Packaging**
- `pyproject.toml` — full `[build-system]` and `[project]` sections; `pip install .` supported
- `hermes` CLI entry point via `project.scripts`
- `main()` function in `processor/runner.py`

**Tests**
- 13 new tests covering subcommands, `--log-level`, `--log-file`, `benchmark`, `validate`, `clean`
- Total: **73 tests**

### Changed
- `LLMClient` — reads credentials from `processor.config.cfg` instead of calling `load_dotenv()` + `os.getenv()` directly
- `VaultIndexer` — removed dependency on `processor/runtime.py`; `self.force = False` directly
- `Validator.validate_summary()` — warns if summary folder is missing instead of crashing
- `_watch()` — exceptions in the run body are caught and logged; watch loop continues

### Fixed
- `Validator.validate_summary()` crashed with `FileNotFoundError` if summary folder did not exist
- `_watch()` would abort the loop if `_run_once()` raised an unhandled exception

### Removed
- `processor/runtime.py` — only contained `FORCE = False`; replaced with `self.force = False` in VaultIndexer

---

## v0.9.0 (2026-06-27) — pre-release

### Added
- `processor/log.py` — centralized logging with thread-local capture for parallel output buffering
- `--parallel` flag — runs entity/keyword/related concurrently; output flushed in order
- `--watch[=N]` flag — polls pipeline every N seconds (default: 30); graceful Ctrl+C shutdown
- `ProcessingState` for `EntityProcessor`, `KeywordProcessor`, `RelatedProcessor` — `--force` now works for all processors
- Incremental `Validator` — `validate_utf8` and `validate_entity` skip unchanged files
- `LLMCache.flush()` — batches disk writes; called once per processor run via context manager
- `LLMCache` thread-safe merge on flush — safe for parallel processor runs
- `LLMClient` context manager (`__enter__` / `__exit__`) — automatic cache flush
- Early-return SKIP path for all processors — `LLMClient` not created when all files are up to date
- `tests/` — 60 pytest tests covering ProcessingState, LLMCache, all LLM processors, runner
- `.github/workflows/ci.yml` — CI runs Ruff, Black, Pytest on every push and PR
- `requirements.txt`, `requirements-dev.txt`
- `README.md`, `INSTALL.md`, `ARCHITECTURE.md`

### Changed
- All `print()` calls replaced with `logging` — same console output format (`%(message)s`)
- `_SmartHandler` routes log output to per-thread capture buffers during parallel execution
- `EntityProcessor`, `KeywordProcessor`, `RelatedProcessor` — added `__init__` with `self.force`
- `VaultIndexer` — `SEARCH_FOLDERS` promoted to module-level constant; `st_mtime` called once per file
- `Cleaner._remove_invalid` — loop replaced with `any()`
- `MarkdownProcessor`, `WikiProcessor` — early-return SKIP path added
- `EntityProcessor` — extracted `_write_entity_stubs` and `_resolve_project_name` as methods; `_ENTITY_FOLDER` dict

### Fixed
- `--force` had no effect on `EntityProcessor`, `KeywordProcessor`, `RelatedProcessor`
- `LLMCache.put()` wrote to disk on every API call — now deferred to `flush()`
- Parallel processor output was interleaved — now buffered per thread, flushed in order

---

## v0.x (internal)

Development only. No changelog.
