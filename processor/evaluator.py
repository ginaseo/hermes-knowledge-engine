"""Knowledge evaluation — statistics, quality, health, learning score, graph metrics."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from processor.log import get_logger

logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
EVAL_HISTORY_FILE = VAULT / "index" / "evaluation_history.json"
REPORTS_DIR = VAULT / "reports"

_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass
class KnowledgeStats:
    documents: int = 0
    summaries: int = 0
    entities: int = 0
    keywords: int = 0
    relations: int = 0
    projects: int = 0
    people: int = 0
    wiki_pages: int = 0
    timestamp: str = ""


@dataclass
class QualityMetrics:
    entity_coverage: float = 0.0  # % summaries with entity file
    keyword_coverage: float = 0.0  # % summaries with keyword file
    relation_coverage: float = 0.0  # % summaries with related file
    summary_coverage: float = 0.0  # % raw docs with summary
    missing_summaries: int = 0
    missing_keywords: int = 0
    missing_relations: int = 0
    orphan_entities: int = 0  # entity files with no matching summary
    broken_references: int = 0  # [[links]] pointing to non-existent docs
    duplicate_entity_names: int = 0


@dataclass
class GraphMetrics:
    total_nodes: int = 0
    total_edges: int = 0
    density: float = 0.0
    connected_components: int = 0
    average_degree: float = 0.0
    largest_cluster: int = 0
    isolated_nodes: int = 0
    duplicated_entities: int = 0
    disconnected_projects: int = 0


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _count(path: Path, pattern: str) -> int:
    return len(list(path.rglob(pattern))) if path.exists() else 0


def _count_since(path: Path, pattern: str, days: int) -> int:
    """Count files modified within the last N days."""
    if not path.exists():
        return 0
    cutoff = datetime.now().timestamp() - days * 86400
    return sum(1 for f in path.rglob(pattern) if f.stat().st_mtime >= cutoff)


# ------------------------------------------------------------------
# Evaluator
# ------------------------------------------------------------------


class Evaluator:

    def run(self) -> None:
        logger.info("=" * 60)
        logger.info(" Hermes Knowledge Evaluation")
        logger.info("=" * 60)

        stats = self._scan_stats()
        quality = self._scan_quality()
        graph = self._build_graph()
        growth = self._scan_growth()
        health, deductions = self._compute_health(stats, quality)
        history = self._load_history()
        prev_score = history[-1]["learning_score"] if history else None
        learning = self._compute_learning(health, growth)

        self._display(stats, quality, graph, growth, health, deductions, learning, prev_score)
        self._save_history(history, stats, health, learning)
        self._write_daily_report(stats, quality, health, learning, prev_score, growth)

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _scan_stats(self) -> KnowledgeStats:
        return KnowledgeStats(
            documents=_count(VAULT / "slack", "*.md"),
            summaries=_count(VAULT / "knowledge" / "summary", "*.md"),
            entities=_count(VAULT / "knowledge" / "entity", "*.json"),
            keywords=_count(VAULT / "knowledge" / "keywords", "*.md"),
            relations=_count(VAULT / "knowledge" / "related", "*.md"),
            projects=_count(VAULT / "projects", "*.md"),
            people=_count(VAULT / "people", "*.md"),
            wiki_pages=_count(VAULT / "wiki", "*.md"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _scan_growth(self) -> dict:
        return {
            "today": {
                "documents": _count_since(VAULT / "slack", "*.md", 1),
                "summaries": _count_since(VAULT / "knowledge" / "summary", "*.md", 1),
                "entities": _count_since(VAULT / "knowledge" / "entity", "*.json", 1),
            },
            "7d": {
                "documents": _count_since(VAULT / "slack", "*.md", 7),
                "summaries": _count_since(VAULT / "knowledge" / "summary", "*.md", 7),
                "entities": _count_since(VAULT / "knowledge" / "entity", "*.json", 7),
            },
            "30d": {
                "documents": _count_since(VAULT / "slack", "*.md", 30),
                "summaries": _count_since(VAULT / "knowledge" / "summary", "*.md", 30),
                "entities": _count_since(VAULT / "knowledge" / "entity", "*.json", 30),
            },
        }

    def _scan_quality(self) -> QualityMetrics:
        q = QualityMetrics()

        summary_dir = VAULT / "knowledge" / "summary"
        entity_dir = VAULT / "knowledge" / "entity"
        keyword_dir = VAULT / "knowledge" / "keywords"
        related_dir = VAULT / "knowledge" / "related"
        slack_dir = VAULT / "knowledge" / "slack"

        def _stems(d: Path, pat: str) -> set[str]:
            return {f.stem for f in d.glob(pat)} if d.exists() else set()

        summary_stems = _stems(summary_dir, "*.md")
        entity_stems = _stems(entity_dir, "*.json")
        keyword_stems = _stems(keyword_dir, "*.md")
        related_stems = _stems(related_dir, "*.md")
        slack_stems = _stems(slack_dir, "*.md")

        # Normalize all to base stem for cross-directory comparison
        # e.g. "foo-summary" → "foo", "foo-entity" → "foo", "foo-keywords" → "foo"
        summary_base = {s.removesuffix("-summary") for s in summary_stems}
        entity_base = {s.removesuffix("-entity") for s in entity_stems}
        keyword_base = {s.removesuffix("-keywords") for s in keyword_stems}
        related_base = {s.removesuffix("-related") for s in related_stems}

        if summary_base:
            n = len(summary_base)
            q.entity_coverage = len(summary_base & entity_base) / n * 100
            q.keyword_coverage = len(summary_base & keyword_base) / n * 100
            q.relation_coverage = len(summary_base & related_base) / n * 100
            q.missing_keywords = len(summary_base - keyword_base)
            q.missing_relations = len(summary_base - related_base)
            q.orphan_entities = len(entity_base - summary_base)

        if slack_stems:
            q.summary_coverage = len(slack_stems & summary_base) / len(slack_stems) * 100
            q.missing_summaries = len(slack_stems - summary_base)
        else:
            q.summary_coverage = 100.0

        # Broken references: [[links]] in related files pointing to non-existent docs
        wiki_stems = _stems(VAULT / "wiki", "*.md")
        project_stems = _stems(VAULT / "projects", "*.md")
        people_stems = _stems(VAULT / "people", "*.md")
        existing = summary_base | slack_stems | wiki_stems | project_stems | people_stems
        if related_dir.exists():
            for rf in related_dir.glob("*.md"):
                try:
                    text = rf.read_text(encoding="utf-8")
                    for link in _WIKILINK.findall(text):
                        stem = Path(link).stem if "." in link else link.strip()
                        if stem and stem not in existing:
                            q.broken_references += 1
                except Exception as e:
                    logger.debug(f"[EVAL] skip corrupt file: {rf.name} ({e})")

        # Duplicate entity names
        seen: dict[str, int] = {}
        if entity_dir.exists():
            for ef in entity_dir.glob("*.json"):
                try:
                    data = json.loads(ef.read_text(encoding="utf-8"))
                    for e in data if isinstance(data, list) else data.get("entities", []):
                        name = (e.get("name") or "").strip().lower()
                        if name:
                            seen[name] = seen.get(name, 0) + 1
                except Exception as e:
                    logger.debug(f"[EVAL] skip corrupt file: {ef.name} ({e})")
        q.duplicate_entity_names = sum(1 for c in seen.values() if c > 1)

        return q

    def _build_graph(self) -> GraphMetrics:
        g = GraphMetrics()
        entity_dir = VAULT / "knowledge" / "entity"
        related_dir = VAULT / "knowledge" / "related"

        # Nodes = unique entity names across all entity JSON files
        entity_names: set[str] = set()
        name_counts: dict[str, int] = {}
        if entity_dir.exists():
            for ef in entity_dir.glob("*.json"):
                try:
                    data = json.loads(ef.read_text(encoding="utf-8"))
                    for e in data if isinstance(data, list) else data.get("entities", []):
                        n = (e.get("name") or "").strip()
                        if n:
                            entity_names.add(n)
                            nl = n.lower()
                            name_counts[nl] = name_counts.get(nl, 0) + 1
                except Exception as e:
                    logger.debug(f"[EVAL] skip corrupt file: {ef.name} ({e})")

        g.total_nodes = len(entity_names)
        g.duplicated_entities = sum(1 for c in name_counts.values() if c > 1)

        # Edges = document-document connections from related files
        adj: dict[str, set[str]] = {}
        if related_dir.exists():
            for rf in related_dir.glob("*.md"):
                src = rf.stem
                try:
                    text = rf.read_text(encoding="utf-8")
                except Exception as e:
                    logger.debug(f"[EVAL] skip corrupt file: {rf.name} ({e})")
                    continue
                links = _WIKILINK.findall(text)
                if links:
                    adj.setdefault(src, set())
                    for link in links:
                        tgt = link.strip()
                        if tgt and tgt != src:
                            adj[src].add(tgt)
                            adj.setdefault(tgt, set())

        edge_count = sum(len(v) for v in adj.values())
        g.total_edges = edge_count // 2

        n_docs = len(adj)
        if n_docs > 1:
            g.density = round(2 * g.total_edges / (n_docs * (n_docs - 1)), 4)
        g.average_degree = round(2 * g.total_edges / n_docs, 2) if n_docs > 0 else 0.0

        # Connected components via BFS
        visited: set[str] = set()
        components: list[int] = []
        for start in adj:
            if start in visited:
                continue
            queue = [start]
            size = 0
            while queue:
                node = queue.pop()
                if node in visited:
                    continue
                visited.add(node)
                size += 1
                for nb in adj.get(node, set()):
                    if nb not in visited:
                        queue.append(nb)
            components.append(size)

        g.connected_components = len(components)
        g.largest_cluster = max(components, default=0)
        g.isolated_nodes = sum(1 for c in components if c == 1)

        # Disconnected projects: project stubs not mentioned in any entity file
        project_dir = VAULT / "projects"
        if project_dir.exists() and entity_names:
            entity_lower = {e.lower() for e in entity_names}
            for pf in project_dir.glob("*.md"):
                if pf.stem.lower() not in entity_lower:
                    g.disconnected_projects += 1

        return g

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_health(
        self, stats: KnowledgeStats, quality: QualityMetrics
    ) -> tuple[float, list[str]]:
        score = 100.0
        deductions: list[str] = []

        def deduct(amount: float, reason: str) -> None:
            nonlocal score
            score -= amount
            deductions.append(f"{reason} (-{amount:.1f})")

        if stats.summaries > 0:
            if quality.entity_coverage < 80:
                deduct(
                    (80 - quality.entity_coverage) * 0.15,
                    f"Entity coverage {quality.entity_coverage:.0f}%",
                )
            if quality.keyword_coverage < 80:
                deduct(
                    (80 - quality.keyword_coverage) * 0.10,
                    f"Keyword coverage {quality.keyword_coverage:.0f}%",
                )
            if quality.relation_coverage < 80:
                deduct(
                    (80 - quality.relation_coverage) * 0.08,
                    f"Relation coverage {quality.relation_coverage:.0f}%",
                )

        if stats.documents > 0 and quality.summary_coverage < 80:
            deduct(
                (80 - quality.summary_coverage) * 0.20,
                f"Summary coverage {quality.summary_coverage:.0f}%",
            )

        if quality.orphan_entities > 0:
            deduct(
                min(quality.orphan_entities * 0.5, 10.0),
                f"{quality.orphan_entities} orphan entity file(s)",
            )

        if quality.broken_references > 0:
            deduct(
                min(quality.broken_references * 1.0, 10.0),
                f"{quality.broken_references} broken reference(s)",
            )

        if quality.duplicate_entity_names > 0:
            deduct(
                min(quality.duplicate_entity_names * 0.3, 5.0),
                f"{quality.duplicate_entity_names} duplicate entity name(s)",
            )

        return round(max(0.0, score), 1), deductions

    def _compute_learning(self, health: float, growth: dict) -> float:
        # Growth contribution: new docs in last 7d * 5, capped at 30 pts
        new_docs_7d = growth["7d"].get("documents", 0)
        growth_pts = min(new_docs_7d * 5, 30)
        score = health * 0.7 + growth_pts
        return round(min(100.0, score), 1)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _load_history(self) -> list[dict]:
        if not EVAL_HISTORY_FILE.exists():
            return []
        try:
            return json.loads(EVAL_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"[EVAL] skip corrupt history: {EVAL_HISTORY_FILE.name} ({e})")
            return []

    def _save_history(
        self, history: list[dict], stats: KnowledgeStats, health: float, learning: float
    ) -> None:
        EVAL_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        history.append(
            {
                "timestamp": stats.timestamp,
                "health_score": health,
                "learning_score": learning,
                "stats": asdict(stats),
            }
        )
        if len(history) > 365:
            history = history[-365:]
        EVAL_HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _display(
        self,
        stats: KnowledgeStats,
        quality: QualityMetrics,
        graph: GraphMetrics,
        growth: dict,
        health: float,
        deductions: list[str],
        learning: float,
        prev_score: float | None,
    ) -> None:
        logger.info("")
        logger.info("## Knowledge Statistics")
        logger.info(f"  Documents  : {stats.documents}")
        logger.info(f"  Summaries  : {stats.summaries}")
        logger.info(f"  Entities   : {stats.entities}")
        logger.info(f"  Keywords   : {stats.keywords}")
        logger.info(f"  Relations  : {stats.relations}")
        logger.info(f"  Projects   : {stats.projects}")
        logger.info(f"  People     : {stats.people}")
        logger.info(f"  Wiki Pages : {stats.wiki_pages}")

        logger.info("")
        logger.info("## Knowledge Growth")
        for period, label in [("today", "Today"), ("7d", "Last 7 Days"), ("30d", "Last 30 Days")]:
            d = growth[period]
            logger.info(
                f"  {label:<14}: +{d['documents']} docs"
                f"  +{d['summaries']} summaries  +{d['entities']} entities"
            )

        logger.info("")
        logger.info("## Knowledge Quality")
        logger.info(f"  Entity Coverage   : {quality.entity_coverage:.1f}%")
        logger.info(f"  Keyword Coverage  : {quality.keyword_coverage:.1f}%")
        logger.info(f"  Relation Coverage : {quality.relation_coverage:.1f}%")
        logger.info(f"  Summary Coverage  : {quality.summary_coverage:.1f}%")
        logger.info(f"  Missing Summaries : {quality.missing_summaries}")
        logger.info(f"  Missing Keywords  : {quality.missing_keywords}")
        logger.info(f"  Missing Relations : {quality.missing_relations}")
        logger.info(f"  Orphan Entities   : {quality.orphan_entities}")
        logger.info(f"  Broken References : {quality.broken_references}")
        logger.info(f"  Duplicate Entities: {quality.duplicate_entity_names}")

        logger.info("")
        logger.info("## Knowledge Graph")
        logger.info(f"  Total Nodes          : {graph.total_nodes}")
        logger.info(f"  Total Edges          : {graph.total_edges}")
        logger.info(f"  Graph Density        : {graph.density:.4f}")
        logger.info(f"  Connected Components : {graph.connected_components}")
        logger.info(f"  Average Degree       : {graph.average_degree:.2f}")
        logger.info(f"  Largest Cluster      : {graph.largest_cluster}")
        logger.info(f"  Isolated Nodes       : {graph.isolated_nodes}")
        logger.info(f"  Duplicated Entities  : {graph.duplicated_entities}")
        logger.info(f"  Disconnected Projects: {graph.disconnected_projects}")

        logger.info("")
        logger.info("## Knowledge Health")
        logger.info(f"  {health} / 100")
        if deductions:
            for d in deductions:
                logger.info(f"  - {d}")
        else:
            logger.info("  No deductions.")

        logger.info("")
        logger.info("## Learning Score")
        logger.info(f"  Current : {learning}")
        if prev_score is not None:
            delta = round(learning - prev_score, 1)
            sign = "+" if delta >= 0 else ""
            logger.info(f"  Previous: {prev_score}")
            logger.info(f"  Change  : {sign}{delta}")
        else:
            logger.info("  Previous: (first evaluation)")

        logger.info("")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Daily Report
    # ------------------------------------------------------------------

    def _write_daily_report(
        self,
        stats: KnowledgeStats,
        quality: QualityMetrics,
        health: float,
        learning: float,
        prev_score: float | None,
        growth: dict,
    ) -> None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")

        delta_str = ""
        if prev_score is not None:
            delta = round(learning - prev_score, 1)
            sign = "+" if delta >= 0 else ""
            delta_str = f" ({sign}{delta})"

        lines = [
            f"# Daily Learning Report — {today}",
            "",
            "## Knowledge Statistics",
            f"- Documents: {stats.documents}",
            f"- Summaries: {stats.summaries}",
            f"- Entities: {stats.entities}",
            f"- Keywords: {stats.keywords}",
            f"- Relations: {stats.relations}",
            f"- Projects: {stats.projects}",
            f"- People: {stats.people}",
            f"- Wiki Pages: {stats.wiki_pages}",
            "",
            "## Growth",
            (
                f"- Today: +{growth['today']['documents']} docs,"
                f" +{growth['today']['summaries']} summaries,"
                f" +{growth['today']['entities']} entities"
            ),
            (
                f"- Last 7 Days: +{growth['7d']['documents']} docs,"
                f" +{growth['7d']['summaries']} summaries"
            ),
            f"- Last 30 Days: +{growth['30d']['documents']} docs",
            "",
            "## Quality",
            f"- Entity Coverage: {quality.entity_coverage:.1f}%",
            f"- Keyword Coverage: {quality.keyword_coverage:.1f}%",
            f"- Relation Coverage: {quality.relation_coverage:.1f}%",
            f"- Summary Coverage: {quality.summary_coverage:.1f}%",
            "",
            "## Knowledge Health",
            f"**{health} / 100**",
            "",
            "## Learning Score",
            f"**{learning}{delta_str}**",
            "",
            f"*Generated: {stats.timestamp}*",
        ]

        report_file = REPORTS_DIR / "daily-learning.md"
        report_file.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"[EVALUATE] Report: {report_file}")
