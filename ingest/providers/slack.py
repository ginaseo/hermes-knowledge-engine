import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from slack_sdk import WebClient

from ingest.base import BaseProvider

# 프로젝트 루트
ROOT = Path(__file__).resolve().parents[2]

# HermesVault 위치
VAULT = ROOT / "HermesVault"

# .env 로드
load_dotenv(ROOT / ".env")


class SlackProvider(BaseProvider):

    def __init__(self):

        self.client = None

        self.token = os.getenv("SLACK_BOT_TOKEN")
        self.channel = os.getenv("SLACK_CHANNEL_ID")

    def process(self):
        self.run()

    def connect(self):

        self.client = WebClient(token=self.token)

        print("[Slack] Connected")

    def fetch(self):

        response = self.client.conversations_history(channel=self.channel, limit=5)

        return response["messages"]

    def save(self, data):

        now = datetime.now()

        year = now.strftime("%Y")
        month = now.strftime("%m")
        date = now.strftime("%Y-%m-%d")

        vault = VAULT / "slack" / year / month
        vault.mkdir(parents=True, exist_ok=True)

        filename = vault / f"{date}-hermes.md"

        print("=" * 80)
        print("[DEBUG] Saving Slack Messages")
        print("=" * 80)

        with open(filename, "w", encoding="utf-8", newline="\n") as f:

            f.write("# Slack Import\n\n")
            f.write(f"Date: {date}\n\n")
            f.write("---\n\n")

            for idx, msg in enumerate(reversed(data), start=1):

                text = msg.get("text", "").strip()
                ts = msg.get("ts", "")

                # ---------- DEBUG ----------
                print(f"\n[Message {idx}]")

                print("\nrepr(text)")
                print(repr(text))

                print("\ntext")
                print(text)

                print("\nUnicode Code Points")
                print(" ".join(hex(ord(ch)) for ch in text[:50]))

                print("-" * 80)
                # ---------------------------

                f.write(f"## Message {idx}\n\n")
                f.write(f"Timestamp: {ts}\n\n")
                f.write(text)
                f.write("\n\n")
                f.write("---\n\n")

        print("=" * 80)
        print("[SAVE]", filename)
        print("=" * 80)


if __name__ == "__main__":

    SlackProvider().run()
