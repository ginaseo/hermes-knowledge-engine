import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from processor import retrieval
from processor.log import get_logger
from processor.vault_indexer import _SEARCH_FOLDERS

ROOT = Path(__file__).resolve().parents[2]
VAULT = ROOT / "HermesVault"

SEARCH_TIMEOUT = 2.0
BUILD_CONTEXT_SOFT_TIMEOUT = 3.0
BUILD_CONTEXT_HARD_TIMEOUT = 5.0
RELATED_SNIPPET_CHARS = 500

_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_START_TIME = time.monotonic()

logger = get_logger(__name__)
mcp = FastMCP("gina-wiki")
_executor = ThreadPoolExecutor(max_workers=4)


def _error(code: str, message: str, retryable: bool) -> None:
    payload = {"error": {"code": code, "message": message, "retryable": retryable}}
    raise ToolError(json.dumps(payload, ensure_ascii=False))


def _log(tool: str, started: float, status: str, query_len: int) -> None:
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    logger.info(f"[MCP] tool={tool} elapsed={elapsed_ms}ms status={status} query_len={query_len}")


def _run_with_timeout(fn, timeout: float, message: str):
    future = _executor.submit(fn)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        _error("TIMEOUT", message, True)


def _load_index() -> list[dict]:
    if not VAULT.exists():
        _error("VAULT_UNAVAILABLE", "HermesVault not accessible", True)
    if not retrieval.INDEX_FILE.exists():
        return []
    try:
        return json.loads(retrieval.INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        _error("CORRUPT_FILE", "vault_index.json is corrupt", False)


def _resolve_doc_path(doc_id: str) -> Path:
    """doc_id must be a vault_index.json path (e.g. 'wiki/Kafka.md') — reject anything else."""
    parts = Path(doc_id).parts
    if not parts or parts[0] not in _SEARCH_FOLDERS or ".." in parts or not doc_id.endswith(".md"):
        _error("INVALID_ARGUMENT", f"invalid id: {doc_id}", False)
    return VAULT / doc_id


@mcp.tool()
def search(query: str, top_k: int = 5) -> dict:
    """Search Gina Agent's Obsidian knowledge base (wiki/projects/people) for matching documents."""
    started = time.monotonic()

    if not query or not query.strip():
        _log("search", started, "INVALID_ARGUMENT", 0)
        _error("INVALID_ARGUMENT", "query must not be empty", False)

    top_k = max(1, min(20, top_k))

    def _do():
        index = _load_index()
        hits = retrieval._search(query, index, top_k=top_k)
        return [
            {
                "id": doc["path"],
                "title": doc["title"],
                "type": doc.get("folder", ""),
                "score": round(retrieval._score(query, doc), 4),
            }
            for doc in hits
        ]

    results = _run_with_timeout(_do, SEARCH_TIMEOUT, "search() exceeded 2s budget")
    _log("search", started, "ok", len(query))
    return {
        "schema_version": "1.0",
        "query": query,
        "total": len(results),
        "results": results,
    }


@mcp.tool()
def build_context(id: str, max_related: int = 3, max_tokens: int = 2000) -> dict:
    """Assemble minimal LLM-ready context for a doc: its body plus bounded Related Links."""
    started = time.monotonic()
    max_related = max(0, min(10, max_related))
    max_tokens = max(200, min(8000, max_tokens))

    def _do():
        if not VAULT.exists():
            _error("VAULT_UNAVAILABLE", "HermesVault not accessible", True)

        path = _resolve_doc_path(id)
        if not path.exists():
            _error("NOT_FOUND", f"no document at {id}", False)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            _error("CORRUPT_FILE", f"{id} is not valid UTF-8", False)

        sources = [id]
        parts = [content]
        truncated = False

        index = _load_index()
        by_stem = {Path(doc["path"]).stem.lower(): doc for doc in index}

        links = list(dict.fromkeys(_LINK_RE.findall(content)))[:max_related]
        for name in links:
            if time.monotonic() - started > BUILD_CONTEXT_SOFT_TIMEOUT:
                truncated = True
                break
            doc = by_stem.get(name.lower())
            if not doc:
                continue
            try:
                related_text = (VAULT / doc["path"]).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            parts.append(f"## Related: {name}\n\n{related_text[:RELATED_SNIPPET_CHARS]}")
            sources.append(doc["path"])

        context = "\n\n---\n\n".join(parts)
        char_budget = max_tokens * 4
        if len(context) > char_budget:
            context = context[:char_budget]
            truncated = True

        return context, sources, truncated

    context, sources, truncated = _run_with_timeout(
        _do, BUILD_CONTEXT_HARD_TIMEOUT, "build_context() exceeded 5s budget"
    )
    _log("build_context", started, "ok", len(id))
    return {
        "schema_version": "1.0",
        "id": id,
        "context": context,
        "sources": sources,
        "truncated": truncated,
    }


@mcp.tool()
def health() -> dict:
    """Report whether the Gina MCP server and its Obsidian vault are reachable."""
    started = time.monotonic()
    vault_accessible = VAULT.exists() and VAULT.is_dir()
    status = "ok" if vault_accessible else "degraded"
    _log("health", started, status, 0)
    return {
        "schema_version": "1.0",
        "status": status,
        "vault_accessible": vault_accessible,
        "uptime_s": round(time.monotonic() - _START_TIME, 1),
    }



@mcp.tool()
def evaluate() -> dict:
    """Return vault statistics, quality metrics, health score, and learning score."""
    started = time.monotonic()
    try:
        from processor.evaluator import Evaluator

        e = Evaluator()
        stats = e._scan_stats()
        quality = e._scan_quality()
        graph = e._build_graph()
        growth = e._scan_growth()
        health, _ = e._compute_health(stats, quality)
        learning = e._compute_learning(health, growth)
        result = {
            "stats": {
                "documents": stats.documents,
                "summaries": stats.summaries,
                "entities": stats.entities,
                "keywords": stats.keywords,
                "relations": stats.relations,
                "wiki_pages": stats.wiki_pages,
            },
            "growth": growth,
            "quality": {
                "coverage_pct": quality.coverage_pct,
                "missing_files": quality.missing_files,
                "orphan_entities": quality.orphan_entities,
                "broken_refs": quality.broken_refs,
            },
            "graph": {
                "nodes": graph.nodes,
                "edges": graph.edges,
                "density": graph.density,
                "components": graph.components,
                "isolated": graph.isolated,
            },
            "health_score": health,
            "learning_score": learning,
        }
        _log("evaluate", started, "ok", 0)
        return result
    except Exception as e:
        _error("INTERNAL", str(e), True)


@mcp.tool()
def briefing(date: str = "", channel: str = "") -> dict:
    """Generate a daily briefing from recent vault changes and post to Slack.

    Args:
        date: Target date in YYYY-MM-DD format (default: today)
        channel: Slack channel ID (default: main channel from env)
    """
    started = time.monotonic()
    try:
        from processor.briefing import BriefingProcessor

        result = BriefingProcessor().run(date=date or None, channel=channel or None)
        _log("briefing", started, "ok", 0)
        return result
    except Exception as e:
        _error("INTERNAL", str(e), True)


@mcp.tool()
def recommend(category: str = "stock", top_k: int = 5) -> dict:
    """Recommend stocks or job postings based on entity graph connectivity.

    Args:
        category: 'stock' | 'job'
        top_k: Number of recommendations (default: 5)
    """
    started = time.monotonic()
    try:
        from processor.recommend import RecommendProcessor

        result = RecommendProcessor().run(category=category, top_k=top_k)
        _log("recommend", started, "ok", len(category))
        return result
    except Exception as e:
        _error("INTERNAL", str(e), True)


@mcp.tool()
def timeline(
    start_date: str = "",
    end_date: str = "",
    entity: str = "",
    days: int = 30,
) -> dict:
    """Return a date-based timeline of knowledge accumulation.

    Args:
        start_date: Start date in YYYY-MM-DD format (default: days ago)
        end_date: End date in YYYY-MM-DD format (default: today)
        entity: Filter by entity name (optional)
        days: Number of days to look back if start_date not specified (default: 30)
    """
    started = time.monotonic()
    try:
        from processor.timeline import TimelineProcessor

        result = TimelineProcessor().run(
            start_date=start_date or None,
            end_date=end_date or None,
            entity=entity or None,
            days=days,
        )
        _log("timeline", started, "ok", len(entity))
        return result
    except Exception as e:
        _error("INTERNAL", str(e), True)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
