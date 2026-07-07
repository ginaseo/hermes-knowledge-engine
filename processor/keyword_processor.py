from pathlib import Path

from processor.llm.client import LLMClient
from processor.log import get_logger
from processor.processing_state import ProcessingState

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
SUMMARY = VAULT / "knowledge" / "summary"
KEYWORD = VAULT / "knowledge" / "keywords"
PROMPT = ROOT / "processor" / "prompts" / "keyword_prompt.txt"

logger = get_logger(__name__)


class KeywordProcessor:

    def __init__(self):
        self.force = False

    def process(self) -> None:
        KEYWORD.mkdir(parents=True, exist_ok=True)

        files = list(SUMMARY.glob("*.md"))
        if not files:
            logger.info("[INFO] No summary files.")
            return

        state = ProcessingState("keyword", force=self.force)

        if not any(state.is_modified(f) for f in files):
            for file in files:
                logger.info(f"[SKIP] {file.name}")
            logger.info("")
            logger.info("Keyword Generated : 0 file(s)")
            return

        generated = 0
        prompt_template = PROMPT.read_text(encoding="utf-8")

        with LLMClient() as client:
            for file in files:
                if not state.is_modified(file):
                    logger.info(f"[SKIP] {file.name}")
                    continue

                logger.info(f"[KEYWORD] {file.name}")
                summary = file.read_text(encoding="utf-8")
                prompt = prompt_template.replace("{summary}", summary)

                try:
                    keywords = client.ask(prompt)
                except Exception as e:
                    logger.error(f"[FAIL] LLM : {file.name}")
                    logger.error(str(e))
                    continue

                output = KEYWORD / file.name.replace("-summary.md", "-keywords.md")
                output.write_text(keywords, encoding="utf-8")
                logger.info(f"[SAVE] {output.name}")
                state.update(file)
                generated += 1

        state.save()
        logger.info("")
        logger.info(f"Keyword Generated : {generated} file(s)")
