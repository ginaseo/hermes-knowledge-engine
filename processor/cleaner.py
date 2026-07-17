import re
from pathlib import Path

from processor.log import get_logger
from processor.paths import VAULT

logger = get_logger(__name__)

_SYNC_CONFLICT_RE = re.compile(r"\.sync-conflict-\d{8}-\d{6}-[A-Za-z0-9]+")


class Cleaner:

    INVALID_PREFIX = ("?", " ", "湲", "臾")

    def process(self) -> None:
        logger.info("=" * 60)
        logger.info(" Vault Cleanup ")
        logger.info("=" * 60)

        removed = 0

        for folder in (VAULT / "wiki", VAULT / "projects", VAULT / "people"):
            if not folder.exists():
                continue
            for file in folder.rglob("*.md"):
                if self._remove_invalid(file) or self._remove_empty(file):
                    removed += 1

        removed += self._remove_sync_conflicts()

        logger.info(f"[CLEAN] Removed : {removed} file(s)")

    def _remove_sync_conflicts(self) -> int:
        """Syncthing leaves *.sync-conflict-*.* copies on concurrent edits.
        Only delete when the conflict copy is provably redundant: identical
        to the live file, or empty. Any other case (no live counterpart, or
        content that differs regardless of which is older) is a genuine
        concurrent-edit conflict -- mtime doesn't prove which side is right,
        so leave it and log for manual review instead of guessing."""
        removed = 0
        for file in VAULT.rglob("*sync-conflict*"):
            if not file.is_file() or ".git" in file.parts:
                continue

            live = Path(_SYNC_CONFLICT_RE.sub("", str(file)))

            if not live.is_file():
                logger.warning(f"[CLEAN] No live counterpart, needs review: {file}")
                continue

            conflict_bytes = file.read_bytes()
            if conflict_bytes.strip() and conflict_bytes != live.read_bytes():
                logger.warning(f"[CLEAN] Conflict copy differs from live, needs review: {file}")
                continue

            file.unlink()
            logger.info(f"[DELETE] {file.name} (sync-conflict)")
            removed += 1
        return removed

    def _remove_invalid(self, file: Path) -> bool:
        if any(file.stem.startswith(p) for p in self.INVALID_PREFIX):
            file.unlink()
            logger.info(f"[DELETE] {file.name}")
            return True
        return False

    def _remove_empty(self, file: Path) -> bool:
        if not file.read_text(encoding="utf-8").strip():
            file.unlink()
            logger.info(f"[DELETE] {file.name}")
            return True
        return False
