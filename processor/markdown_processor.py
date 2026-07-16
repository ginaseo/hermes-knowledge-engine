from pathlib import Path

from processor.log import get_logger
from processor.processing_state import ProcessingState

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
KNOWLEDGE_ROOT = VAULT / "knowledge"

# (source name, provider class name, raw import dir) — add new ingest sources here.
SOURCES = [
    ("slack", "SlackProvider", VAULT / "slack"),
    ("claude-code", "ClaudeCodeProvider", VAULT / "claude-code"),
]
SOURCE_NAMES = [s[0] for s in SOURCES]  # shared with summary_processor / wiki_processor

logger = get_logger(__name__)


class MarkdownProcessor:

    def __init__(self):
        self.force = False

    def process(self) -> None:
        state = ProcessingState("markdown", force=self.force)
        generated = 0
        skipped = 0
        found_any = False

        for source_name, provider_name, raw_dir in SOURCES:
            files = list(raw_dir.rglob("*.md")) if raw_dir.exists() else []
            if not files:
                continue
            found_any = True

            knowledge_dir = KNOWLEDGE_ROOT / source_name
            knowledge_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                if not state.is_modified(file):
                    logger.info(f"[SKIP] {file.name}")
                    skipped += 1
                    continue

                content = file.read_text(encoding="utf-8")
                output = knowledge_dir / file.name
                output.write_text(
                    "---\n"
                    f"source: {source_name}\n"
                    f"provider: {provider_name}\n"
                    "status: processed\n"
                    f"original_file: {file.name}\n"
                    "---\n\n"
                    "# Summary\n\n"
                    "> TODO\n\n"
                    "# Original Content\n\n" + content,
                    encoding="utf-8",
                )
                state.update(file)
                generated += 1
                logger.info(f"[PROCESS] {output.name}")

        if not found_any:
            logger.info("[INFO] No markdown files.")
            return

        state.save()
        logger.info("")
        logger.info(f"Processed : {generated} file(s)")
        logger.info(f"Skipped  : {skipped} file(s)")
