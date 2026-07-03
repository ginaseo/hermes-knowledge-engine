import json
import re
from pathlib import Path

from processor.llm.client import LLMClient
from processor.log import get_logger
from processor.processing_state import ProcessingState

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
SUMMARY = VAULT / "knowledge" / "summary"
ENTITY = VAULT / "knowledge" / "entity"
RELATED = VAULT / "knowledge" / "related"
WIKI = VAULT / "wiki"
PROMPT = ROOT / "processor" / "prompts" / "description_fill_prompt.txt"
PROJECT_ALIAS_FILE = ROOT / "processor" / "prompts" / "project_alias.json"
SOURCES_FILE = VAULT / "index" / "description_fill_sources.json"

_TARGET_TYPES = {"Technology", "Organization", "Concept"}
_TYPE_RE = re.compile(r"^---\s*\ntype:\s*(.+?)\s*\n")
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

logger = get_logger(__name__)


class DescriptionFillProcessor:
    """Enriches wiki/{Technology,Organization,Concept} TODO stubs (created by
    EntityProcessor) into full docs, grounded in knowledge/summary and
    knowledge/related text. Only touches a stub when a source file it hasn't
    seen yet mentions that entity — reappearing entities get merged into the
    existing content, not overwritten from scratch.
    """

    def __init__(self):
        self.force = False

    def process(self) -> None:
        entity_files = list(ENTITY.glob("*-entity.json"))

        if not entity_files:
            logger.info("[INFO] No entity files.")
            return

        state = ProcessingState("description_fill", force=self.force)
        if not any(state.is_modified(f) for f in entity_files):
            logger.info("[SKIP] No entity changes.")
            return

        targets = [f for f in WIKI.glob("*.md") if self._stub_type(f) in _TARGET_TYPES]

        if not targets:
            logger.info("[INFO] No wiki stubs to enrich.")
            for f in entity_files:
                state.update(f)
            state.save()
            return

        alias = (
            json.loads(PROJECT_ALIAS_FILE.read_text(encoding="utf-8"))
            if PROJECT_ALIAS_FILE.exists()
            else {}
        )
        source_index = self._build_source_index(entity_files, alias)
        sources_done = self._load_sources_done()
        prompt_template = PROMPT.read_text(encoding="utf-8")
        generated = 0

        with LLMClient() as client:
            for stub in targets:
                name = stub.stem
                mentions = source_index.get(name.lower(), set())
                done = set(sources_done.get(name.lower(), []))
                new_sources = sorted(mentions - done)

                if not new_sources:
                    logger.info(f"[SKIP] {stub.name}")
                    continue

                source_text = self._collect_source_text(new_sources)
                if not source_text.strip():
                    logger.info(f"[SKIP] {stub.name} (no source text)")
                    continue

                existing = stub.read_text(encoding="utf-8")
                entity_type = self._stub_type(stub) or "Concept"
                prompt = (
                    prompt_template.replace("{entity_name}", name)
                    .replace("{entity_type}", entity_type)
                    .replace("{existing}", existing)
                    .replace("{source}", source_text)
                )

                try:
                    result = client.ask(prompt)
                    fields = json.loads(result)
                except Exception as e:
                    logger.error(f"[FAIL] {stub.name}")
                    logger.error(str(e))
                    continue

                links = self._extract_links(existing) | self._extract_links(source_text)
                stub.write_text(self._render(name, entity_type, fields, links), encoding="utf-8")

                sources_done[name.lower()] = sorted(done | set(new_sources))
                generated += 1
                logger.info(f"[ENRICH] {stub.name}")

        self._save_sources_done(sources_done)
        for f in entity_files:
            state.update(f)
        state.save()

        logger.info("")
        logger.info(f"Description Filled : {generated} file(s)")

    def _stub_type(self, file: Path) -> str | None:
        match = _TYPE_RE.match(file.read_text(encoding="utf-8"))
        return match.group(1) if match else None

    def _build_source_index(
        self, entity_files: list[Path], alias: dict[str, str]
    ) -> dict[str, set[str]]:
        index: dict[str, set[str]] = {}

        for entity_file in entity_files:
            base = entity_file.stem
            if base.endswith("-entity"):
                base = base[: -len("-entity")]

            try:
                entities = json.loads(entity_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue

            for entity in entities:
                if entity.get("type", "").strip() not in _TARGET_TYPES:
                    continue
                name = entity.get("name", "").strip()
                if not name:
                    continue
                if name.lower().endswith(".md"):
                    name = name[:-3]
                name = " ".join(name.split())
                name = alias.get(name, name)
                index.setdefault(name.lower(), set()).add(base)

        return index

    def _collect_source_text(self, stems: list[str]) -> str:
        parts = []
        for stem in stems:
            summary_file = SUMMARY / f"{stem}-summary.md"
            related_file = RELATED / f"{stem}-related.md"
            if summary_file.exists():
                parts.append(summary_file.read_text(encoding="utf-8"))
            if related_file.exists():
                parts.append(related_file.read_text(encoding="utf-8"))
        return "\n\n---\n\n".join(parts)

    def _extract_links(self, text: str) -> set[str]:
        return set(_LINK_RE.findall(text))

    def _render(self, name: str, entity_type: str, fields: dict, links: set[str]) -> str:
        description = str(fields.get("description") or "").strip() or "TODO"
        summary = str(fields.get("summary") or "").strip()
        related_entities = fields.get("related_entities") or []
        tags = fields.get("tags") or []

        related_block = "\n".join(f"- {r}" for r in related_entities) or "- (없음)"
        links_block = "\n".join(f"- [[{link}]]" for link in sorted(links)) or "- (없음)"
        tags_block = " ".join(f"#{t}" for t in tags) or "(없음)"

        return (
            f"---\ntype: {entity_type}\ncreated: auto\nupdated: auto\n---\n\n"
            f"# {name}\n\n"
            f"## Description\n\n{description}\n\n"
            f"## 핵심 내용 요약\n\n{summary}\n\n"
            f"## 관련 기술/기업/프로젝트\n\n{related_block}\n\n"
            f"## Related Links\n\n{links_block}\n\n"
            f"## Tags\n\n{tags_block}\n"
        )

    def _load_sources_done(self) -> dict[str, list[str]]:
        if SOURCES_FILE.exists():
            return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        return {}

    def _save_sources_done(self, data: dict[str, list[str]]) -> None:
        SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
        SOURCES_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
