import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from slack_sdk import WebClient
from ingest.base import BaseProvider

ROOT = Path(__file__).resolve().parents[2]
VAULT = ROOT / "HermesVault"
STATE_FILE = VAULT / "index" / "slack_state.json"
load_dotenv(ROOT / ".env")


class SlackProvider(BaseProvider):
    def __init__(self):
        self.client = None
        self.token = os.getenv("SLACK_BOT_TOKEN")
        ids = os.getenv("SLACK_CHANNEL_IDS") or os.getenv("SLACK_CHANNEL_ID", "")
        self.channels = [c.strip() for c in ids.split(",") if c.strip()]
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

    def process(self):
        self.run()

    def connect(self):
        self.client = WebClient(token=self.token)
        print("[Slack] Connected")

    def fetch(self):
        results = {}
        for ch in self.channels:
            try:
                oldest = self.state.get(ch, "0")
                resp = self.client.conversations_history(
                    channel=ch,
                    limit=100,
                    oldest=oldest,
                )
                messages = resp["messages"]
                if messages:
                    results[ch] = messages
            except Exception as e:
                print(f"[Slack] Failed to fetch {ch}: {e}")
        return results or None

    def save(self, data):
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        date = now.strftime("%Y-%m-%d")

        for ch, messages in data.items():
            vault = VAULT / "slack" / year / month
            vault.mkdir(parents=True, exist_ok=True)
            filename = vault / f"{date}-{ch}.md"

            # 기존 파일 있으면 append, 없으면 새로 생성
            existing = ""
            if filename.exists():
                existing = filename.read_text(encoding="utf-8")

            # 이미 저장된 timestamp 추출
            import re
            saved_ts = set(re.findall(r"Timestamp: ([\d.]+)", existing))

            new_messages = [m for m in messages if m.get("ts", "") not in saved_ts]
            if not new_messages:
                print(f"[Slack] No new messages in {ch}")
                continue

            start_idx = existing.count("## Message ")
            with open(filename, "a" if existing else "w", encoding="utf-8", newline="\n") as f:
                if not existing:
                    f.write(f"# Slack Import — {ch}\n\n")
                    f.write(f"Date: {date}\n\n")
                    f.write("---\n\n")
                for idx, msg in enumerate(reversed(new_messages), start=start_idx + 1):
                    text = msg.get("text", "").strip()
                    ts = msg.get("ts", "")
                    f.write(f"## Message {idx}\n\n")
                    f.write(f"Timestamp: {ts}\n\n")
                    f.write(text)
                    f.write("\n\n")
                    f.write("---\n\n")

            print(f"[Slack] Saved {filename.name} (+{len(new_messages)} messages)")

            # 가장 최신 timestamp 저장
            latest_ts = max(m.get("ts", "0") for m in messages)
            self.state[ch] = latest_ts

        self._save_state()
