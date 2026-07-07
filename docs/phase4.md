# Phase 4 — Feature Design

Vault가 안정 궤도(파이프라인 100%, Slack RAG 확인)에 오른 뒤 다음 단계로 추가할
4개 기능의 설계. 모두 기존 `HermesVault/index/` 데이터(vault_index, evaluation_history,
job_history)와 `processor/evaluator.py`, `processor/retrieval.py`를 기반으로 확장한다.

---

## evaluate()

이미 `hermes evaluate`로 구현됨 (`processor/evaluator.py`). Phase 4에서는 MCP tool로 노출.

### 입력/출력 스펙
- **입력**: 없음 (vault 전체 스캔)
- **출력**:
  ```json
  {
    "stats": {"documents": 136, "entities": 42, "keywords": 88, "relations": 210},
    "growth": {"1d": 5, "7d": 23, "30d": 90},
    "quality": {"coverage_pct": 87.5, "missing_files": 3, "orphan_entities": 2, "broken_refs": 1},
    "graph": {"nodes": 178, "edges": 210, "density": 0.013, "components": 4, "isolated": 6},
    "health_score": 82,
    "learning_score": 79
  }
  ```

### 구현 우선순위
1순위 — 이미 CLI로 존재, MCP tool 등록만 남음 (`evaluate()` in `mcp/server.py`).

### 예상 토큰 소모량
0 (LLM 호출 없음, 순수 vault 스캔/집계).

---

## briefing()

매일 아침 vault의 최신 변화를 요약해 Slack에 자동 게시.

### 입력/출력 스펙
- **입력**: `date` (optional, default: 오늘), `channel` (optional, default: 메인 채널)
- **처리**: 최근 24h `knowledge/summary/`, `knowledge/entity/` diff → LLM 요약 프롬프트
- **출력**: Slack 메시지 (마크다운), 예:
  ```
  📋 오늘의 브리핑 (2026-07-07)
  - 신규 문서 5건, 신규 엔티티 2건
  - 주요 항목: [[프로젝트X]], [[채용공고Y]]
  - 놓친 것: entity Z가 3일째 orphan 상태
  ```

### 구현 우선순위
2순위 — `gina-enrich` systemd timer 패턴 재사용, `briefing_prompt.md` 신규 프롬프트 필요.

### 예상 토큰 소모량
요약 대상 문서당 ~500 토큰 입력, 브리핑 1건당 ~1,500 토큰 (일 1회 실행 기준 소액).

---

## recommend()

관심 종목/채용 공고를 entity 그래프 연결성 기반으로 추천.

### 입력/출력 스펙
- **입력**: `category` (`stock` | `job`), `top_k` (default: 5)
- **처리**: `project_alias.json` 카테고리 필터 → RelatedProcessor 그래프에서 연결 수/최신성 가중 랭킹
- **출력**:
  ```json
  {"recommendations": [{"entity": "종목A", "score": 0.91, "reason": "최근 7일 3회 언급, 연결 엔티티 5개"}]}
  ```

### 구현 우선순위
3순위 — LLM 불필요, `related/` JSON 그래프 순회만으로 구현 가능 (rule-based).

### 예상 토큰 소모량
0 (LLM 미사용, 그래프 스코어링 로직만).

---

## timeline()

날짜별 Knowledge 축적을 타임라인으로 조회.

### 입력/출력 스펙
- **입력**: `start_date`, `end_date` (optional, default: 최근 30일), `entity` (optional 필터)
- **처리**: `vault_index.json`의 각 문서 `created_at`/`updated_at` 기준 정렬
- **출력**:
  ```json
  {"timeline": [{"date": "2026-07-05", "documents": ["doc1", "doc2"], "entities": ["종목A"]}]}
  ```

### 구현 우선순위
4순위 — `evaluate()`의 growth 계산 로직 재사용, 정렬/필터만 추가.

### 예상 토큰 소모량
0 (LLM 미사용, 순수 인덱스 조회).

---

## 요약 우선순위

1. `evaluate()` — MCP 노출만 (즉시 가능)
2. `briefing()` — 프롬프트 1개 + systemd timer
3. `recommend()` — rule-based, LLM 불필요
4. `timeline()` — evaluate() 로직 재사용
