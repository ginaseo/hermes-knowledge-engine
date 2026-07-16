"""Claude Code session provider — imports the just-ended session's transcript
(path/id delivered via the SessionEnd hook's stdin JSON) into HermesVault as a
plain-text import, same shape as the Slack provider, for the existing
Markdown/Wiki/Summary/Entity pipeline to pick up."""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest.base import BaseProvider

ROOT = Path(__file__).resolve().parents[2]
VAULT = ROOT / "HermesVault"
STATE_FILE = VAULT / "index" / "claude_code_state.json"


class ClaudeCodeProvider(BaseProvider):

    def __init__(self, hook_input: dict):
        self.hook_input = hook_input
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_state(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def connect(self):
        pass  # local transcript file, nothing to connect to

    def fetch(self):
        transcript_path = self.hook_input.get("transcript_path")
        session_id = self.hook_input.get("session_id", "")
        if not transcript_path:
            return None

        path = Path(transcript_path)
        if not path.exists():
            return None

        mtime = path.stat().st_mtime
        if self.state.get(session_id) == mtime:
            return None  # already imported, unchanged since

        turns = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = entry.get("message")
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = self._extract_text(msg.get("content"))
                if text:
                    turns.append((role, text))

        if not turns:
            return None

        return {
            "session_id": session_id,
            "cwd": self.hook_input.get("cwd", ""),
            "turns": turns,
            "mtime": mtime,
        }

    @staticmethod
    def _extract_text(content) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "\n".join(p for p in parts if p).strip()
        return ""

    def save(self, data):
        now = datetime.now()
        year, month, date = now.strftime("%Y"), now.strftime("%m"), now.strftime("%Y-%m-%d")
        vault_dir = VAULT / "claude-code" / year / month
        vault_dir.mkdir(parents=True, exist_ok=True)

        session_id = data["session_id"]
        short_id = session_id[:8] if session_id else "unknown"
        filename = vault_dir / f"{date}-{short_id}.md"

        with open(filename, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# Claude Code Session — {short_id}\n\n")
            f.write(f"Date: {date}\n")
            f.write(f"Session ID: {session_id}\n")
            f.write(f"CWD: {data['cwd']}\n\n")
            f.write("---\n\n")
            for role, text in data["turns"]:
                label = "나 (Human)" if role == "user" else "Claude"
                f.write(f"### {label}\n\n{text}\n\n---\n\n")

        print(f"[ClaudeCode] Saved {filename.name} ({len(data['turns'])} turns)")

        self.state[session_id] = data["mtime"]
        self._save_state()


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        hook_input = {}
    ClaudeCodeProvider(hook_input).run()


if __name__ == "__main__":
    main()
