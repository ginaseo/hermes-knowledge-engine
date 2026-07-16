import json
import re
from json import JSONDecodeError
from pathlib import Path

from processor.llm.client import LLMClient
from processor.log import get_logger
from processor.processing_state import ProcessingState

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
SUMMARY = VAULT / "knowledge" / "summary"
ENTITY = VAULT / "knowledge" / "entity"
PROJECTS = VAULT / "projects"
PEOPLE = VAULT / "people"
WIKI = VAULT / "wiki"
PROMPT = ROOT / "processor" / "prompts" / "entity_prompt.txt"
PROJECT_ALIAS_FILE = ROOT / "processor" / "prompts" / "project_alias.json"

_ENTITY_FOLDER: dict[str, Path] = {
    "Project": PROJECTS,
    "Person": PEOPLE,
}

logger = get_logger(__name__)


class EntityProcessor:

    def __init__(self):
        self.force = False

    def process(self) -> None:
        for d in (ENTITY, PROJECTS, PEOPLE, WIKI):
            d.mkdir(parents=True, exist_ok=True)

        state = ProcessingState("entity", force=self.force)
        summaries = list(SUMMARY.glob("*.md"))

        if not summaries:
            logger.info("[INFO] No summary files.")
            return

        if not any(state.is_modified(f) for f in summaries):
            for f in summaries:
                logger.info(f"[SKIP] {f.name}")
            logger.info("")
            logger.info("Entity Generated : 0 file(s)")
            return

        prompt_template = PROMPT.read_text(encoding="utf-8")
        project_alias: dict[str, str] = json.loads(PROJECT_ALIAS_FILE.read_text(encoding="utf-8"))
        existing_projects: dict[str, str] = {
            p.name.lower(): p.name for p in PROJECTS.iterdir() if p.is_dir()
        }
        generated = 0

        with LLMClient() as client:
            for summary_file in summaries:
                if not state.is_modified(summary_file):
                    logger.info(f"[SKIP] {summary_file.name}")
                    continue

                logger.info(f"[ENTITY] {summary_file.name}")
                prompt = prompt_template.replace(
                    "{summary}", summary_file.read_text(encoding="utf-8")
                )

                try:
                    result = client.ask(prompt)
                except Exception as e:
                    logger.error(f"[FAIL] LLM : {summary_file.name}")
                    logger.error(str(e))
                    continue

                try:
                    entities = json.loads(result)
                except JSONDecodeError:
                    logger.error(f"[FAIL] Invalid JSON : {summary_file.name}")
                    continue

                entity_output = ENTITY / summary_file.name.replace("-summary.md", "-entity.json")
                entity_output.write_text(
                    json.dumps(entities, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                self._write_entity_stubs(entities, project_alias, existing_projects)
                state.update(summary_file)
                generated += 1

        state.save()
        logger.info("")
        logger.info(f"Entity Generated : {generated} file(s)")

    def _resolve_project_name(
        self,
        name: str,
        existing_projects: dict[str, str],
    ) -> str:
        lower = name.lower()
        if lower in existing_projects:
            return existing_projects[lower]
        for project in existing_projects.values():
            if project.lower() in lower or lower in project.lower():
                return project
        return name

    def _write_entity_stubs(
        self,
        entities: list,
        project_alias: dict[str, str],
        existing_projects: dict[str, str],
    ) -> None:
        seen: set[tuple[str, str]] = set()
        folder_index: dict[Path, dict[str, str]] = {}

        for entity in entities:
            entity_type = entity.get("type", "").strip()
            name = entity.get("name", "").strip()

            if not name:
                continue

            if name.lower().endswith(".md"):
                name = name[:-3]

            name = " ".join(name.split())
            # 파일명에 사용할 수 없는 문자 제거
            name = re.sub(r'[/\\:*?"<>|]', "_", name).strip("_")
            if not name:
                continue
            name = project_alias.get(name, name)

            if entity_type == "Project":
                name = self._resolve_project_name(name, existing_projects)

            key = (entity_type.lower(), name.lower())
            if key in seen:
                continue
            seen.add(key)

            folder = _ENTITY_FOLDER.get(entity_type, WIKI)

            if (folder / name).is_dir():
                continue

            if folder not in folder_index:
                folder_index[folder] = {f.stem.lower(): f.name for f in folder.glob("*.md")}

            if name.lower() not in folder_index[folder]:
                md = folder / f"{name}.md"
                md.write_text(
                    f"---\ntype: {entity_type}\ncreated: auto\n---\n\n"
                    f"# {name}\n\n## Description\n\nTODO\n\n## Related\n\n",
                    encoding="utf-8",
                )
                folder_index[folder][name.lower()] = md.name
