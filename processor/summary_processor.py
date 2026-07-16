from pathlib import Path

from processor.llm.client import LLMClient
from processor.log import get_logger
from processor.markdown_processor import SOURCE_NAMES
from processor.processing_state import ProcessingState

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
KNOWLEDGE_ROOT = VAULT / "knowledge"
OUTPUT = VAULT / "knowledge" / "summary"
PROMPT = ROOT / "processor" / "prompts" / "summary_prompt.txt"

logger = get_logger(__name__)


class SummaryProcessor:

    def __init__(self):
        self.force = False

    def process(self) -> None:
        OUTPUT.mkdir(parents=True, exist_ok=True)

        state = ProcessingState("summary", force=self.force)
        files = [
            f
            for source in SOURCE_NAMES
            for f in (KNOWLEDGE_ROOT / source).glob("*.md")
        ]

        if not files:
            logger.info("[INFO] No markdown files.")
            return

        if not any(state.is_modified(f) for f in files):
            for file in files:
                logger.info(f"[SKIP] {file.name}")
            logger.info("")
            logger.info("Summary Generated : 0 file(s)")
            logger.info(f"Summary Skipped  : {len(files)} file(s)")
            return

        prompt_template = PROMPT.read_text(encoding="utf-8")
        generated = 0
        skipped = 0

        with LLMClient() as client:
            for file in files:
                if not state.is_modified(file):
                    logger.info(f"[SKIP] {file.name}")
                    skipped += 1
                    continue

                logger.info(f"[SUMMARY] {file.name}")
                prompt = prompt_template.replace("{markdown}", file.read_text(encoding="utf-8"))

                try:
                    summary = client.ask(prompt)
                except Exception as e:
                    logger.error(f"[FAIL] {file.name}")
                    logger.error(str(e))
                    continue

                output = OUTPUT / file.name.replace(".md", "-summary.md")
                output.write_text(summary.strip(), encoding="utf-8")
                logger.info(f"[SAVE] {output.name}")
                state.update(file)
                generated += 1

        state.save()
        logger.info("")
        logger.info(f"Summary Generated : {generated} file(s)")
        logger.info(f"Summary Skipped  : {skipped} file(s)")
