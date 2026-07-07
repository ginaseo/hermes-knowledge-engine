from pathlib import Path

from processor.llm.client import LLMClient
from processor.log import get_logger
from processor.processing_state import ProcessingState

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
SUMMARY = VAULT / "knowledge" / "summary"
RELATED = VAULT / "knowledge" / "related"
PROMPT = ROOT / "processor" / "prompts" / "related_prompt.txt"

logger = get_logger(__name__)


class RelatedProcessor:

    def __init__(self):
        self.force = False

    def process(self) -> None:
        RELATED.mkdir(parents=True, exist_ok=True)

        state = ProcessingState("related", force=self.force)
        files = list(SUMMARY.glob("*.md"))

        if not files:
            logger.info("[INFO] No summary files.")
            return

        if not any(state.is_modified(f) for f in files):
            for file in files:
                logger.info(f"[SKIP] {file.name}")
            logger.info("")
            logger.info("Related Generated : 0 file(s)")
            return

        generated = 0
        prompt_template = PROMPT.read_text(encoding="utf-8")

        # Collect existing vault documents for grounding
        existing_docs: list[str] = []
        for folder in ("wiki", "projects", "people"):
            d = VAULT / folder
            if d.exists():
                existing_docs += [f.stem for f in d.glob("*.md")]
        existing_docs += [f.stem for f in SUMMARY.glob("*.md")]
        doc_list = "\n".join(f"- {d}" for d in sorted(set(existing_docs)))

        with LLMClient() as client:
            for file in files:
                if not state.is_modified(file):
                    logger.info(f"[SKIP] {file.name}")
                    continue

                logger.info(f"[RELATED] {file.name}")
                summary = file.read_text(encoding="utf-8")
                prompt = prompt_template.replace("{doc_list}", doc_list).replace(
                    "{summary}", summary
                )

                try:
                    related = client.ask(prompt)
                except Exception as e:
                    logger.error(f"[FAIL] LLM : {file.name}")
                    logger.error(str(e))
                    continue

                output = RELATED / file.name.replace("-summary.md", "-related.md")
                output.write_text(related.strip(), encoding="utf-8")
                logger.info(f"[SAVE] {output.name}")
                state.update(file)
                generated += 1

        state.save()
        logger.info("")
        logger.info(f"Related Generated : {generated} file(s)")
