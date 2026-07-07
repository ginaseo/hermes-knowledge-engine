import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "HermesVault" / "cache"
CACHE_FILE = CACHE_DIR / "llm_cache.json"

_flush_lock = threading.Lock()


class LLMCache:

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache: dict[str, str] = {}
        if CACHE_FILE.exists():
            self.cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        self._dirty = False

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def get(self, prompt: str) -> str | None:
        return self.cache.get(self._key(prompt))

    def put(self, prompt: str, response: str) -> None:
        self.cache[self._key(prompt)] = response
        self._dirty = True

    def flush(self) -> None:
        """Flush dirty entries to disk. Merges with on-disk state for thread safety."""
        if not self._dirty:
            return
        with _flush_lock:
            if CACHE_FILE.exists():
                existing = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                existing.update(self.cache)
                data = existing
            else:
                data = self.cache
            fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, CACHE_FILE)
        self._dirty = False
