"""
RecommendProcessor — Phase 4

관심 종목/채용 공고를 entity 그래프 연결성 기반으로 추천.
LLM 불필요 — related/ JSON 그래프 순회만으로 구현 (rule-based).
"""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "HermesVault"
ENTITY = VAULT / "knowledge" / "entity"
RELATED = VAULT / "knowledge" / "related"
WIKI = VAULT / "wiki"
CATEGORIES_FILE = ROOT / "processor" / "prompts" / "recommend_categories.json"


def _load_categories() -> dict[str, set[str]]:
    raw = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
    return {category: set(names) for category, names in raw.items()}


class RecommendProcessor:
    def run(self, category: str = "stock", top_k: int = 5) -> dict:
        """
        Args:
            category: 'stock' | 'job'
            top_k: 추천 개수
        Returns:
            {"recommendations": [{"entity": str, "score": float, "reason": str}]}
        """
        now = time.time()
        scores: dict[str, dict] = {}
        categories = _load_categories()
        allowed = categories.get(category, set())

        # entity 파일 순회
        for entity_file in ENTITY.glob("*-entity.json"):
            age_days = (now - entity_file.stat().st_mtime) / 86400
            recency_score = max(0.0, 1.0 - age_days / 7)  # 7일 이내일수록 높음

            try:
                entities = json.loads(entity_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            for entity in entities:
                name = entity.get("name", "").strip()
                if not name:
                    continue

                # 카테고리 필터
                if name not in allowed:
                    continue

                if name not in scores:
                    scores[name] = {"mention_count": 0, "recency": 0.0, "connections": 0}

                scores[name]["mention_count"] += 1
                scores[name]["recency"] = max(scores[name]["recency"], recency_score)

        # related 파일에서 연결 수 계산
        for related_file in RELATED.glob("*-related.md"):
            content = related_file.read_text(encoding="utf-8")
            for name in scores:
                if f"[[{name}]]" in content:
                    scores[name]["connections"] += 1

        # 점수 계산 (mention * 0.4 + recency * 0.4 + connections * 0.2)
        results = []
        for name, s in scores.items():
            score = (
                min(s["mention_count"] / 5, 1.0) * 0.4
                + s["recency"] * 0.4
                + min(s["connections"] / 10, 1.0) * 0.2
            )
            reason = f"최근 7일 {s['mention_count']}회 언급, 연결 엔티티 {s['connections']}개"
            results.append({"entity": name, "score": round(score, 3), "reason": reason})

        results.sort(key=lambda x: x["score"], reverse=True)
        return {"recommendations": results[:top_k]}
