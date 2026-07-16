from pathlib import Path

from processor.log import get_logger
from processor.markdown_processor import SOURCE_NAMES
from processor.processing_state import ProcessingState

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
KNOWLEDGE_ROOT = VAULT / "knowledge"
WIKI_ROOT = VAULT / "wiki"

logger = get_logger(__name__)


class WikiProcessor:

    def __init__(self):
        self.force = False

    def process(self) -> None:
        state = ProcessingState("wiki", force=self.force)
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
            logger.info("Generated : 0 wiki file(s)")
            logger.info(f"Skipped  : {len(files)} wiki file(s)")
            return

        generated = 0
        skipped = 0

        for file in files:
            if not state.is_modified(file):
                logger.info(f"[SKIP] {file.name}")
                skipped += 1
                continue

            source = file.parent.name
            output_dir = WIKI_ROOT / source
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / file.name
            output.write_text(file.read_text(encoding="utf-8"), encoding="utf-8")
            state.update(file)
            generated += 1
            logger.info(f"[WIKI] {output.name}")

        state.save()
        logger.info("")
        logger.info(f"Generated : {generated} wiki file(s)")
        logger.info(f"Skipped  : {skipped} wiki file(s)")
