"""
BriefingProcessor — Phase 4

매일 아침 vault의 최신 변화를 요약해 반환.
LLM 불필요 — vault_index + summary 파일 기반.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
SUMMARY = VAULT / "knowledge" / "summary"
ENTITY = VAULT / "knowledge" / "entity"
INDEX_FILE = VAULT / "index" / "vault_index.json"


class BriefingProcessor:
    def run(
        self, date: str | None = None, channel: str | None = None
    ) -> dict:
        """
        Args:
            date: YYYY-MM-DD (default: today)
            channel: Slack channel ID (optional)
        Returns:
            {"date": str, "new_docs": int, "new_entities": int,
             "summaries": [...], "message": str}
        """
        now = datetime.now(timezone.utc)
        target = datetime.fromisoformat(date).replace(tzinfo=timezone.utc) if date else now
        start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        # 오늘 생성된 summary 파일 수집
        new_summaries = []
        for f in sorted(SUMMARY.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if start <= mtime < end:
                content = f.read_text(encoding="utf-8")
                # 핵심 내용 첫 3줄 추출
                lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
                preview = " ".join(lines[:3])[:200]
                new_summaries.append({
                    "file": f.stem,
                    "preview": preview,
                })

        # 오늘 생성된 entity 수 계산
        new_entities = sum(
            1 for f in ENTITY.glob("*.json")
            if start <= datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) < end
        )

        # vault 전체 문서 수
        total_docs = 0
        if INDEX_FILE.exists():
            docs = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            total_docs = len(docs)

        # 브리핑 메시지 생성
        date_str = target.strftime("%Y-%m-%d")
        lines = [
            f"📋 Knowledge Briefing — {date_str}",
            f"• 신규 문서: {len(new_summaries)}건 | 신규 엔티티: {new_entities}건 | 전체: {total_docs}건",
        ]
        for s in new_summaries[:5]:
            lines.append(f"  - {s['file']}: {s['preview'][:100]}")

        message = "\n".join(lines)

        return {
            "date": date_str,
            "new_docs": len(new_summaries),
            "new_entities": new_entities,
            "total_docs": total_docs,
            "summaries": new_summaries,
            "message": message,
            "channel": channel,
        }
