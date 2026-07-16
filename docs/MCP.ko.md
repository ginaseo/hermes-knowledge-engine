# MCP 서버

vault를 [MCP](https://modelcontextprotocol.io) 서버로 노출해서, MCP 클라이언트
(Hermes, Claude Desktop, Cursor, VS Code, ChatGPT 등) 어디서든 별도 동기화나
복사 없이 Hermes의 지식을 검색·조회할 수 있게 합니다.

## 서버 시작

```bash
pip install .
hermes-mcp
# 또는
python -m processor.mcp.server
```

흐름: `Hermes → MCP → search() → build_context() → LLM`

## 도구 목록

| 도구 | 입력 | 비고 |
|------|-------|-------|
| `search(query, top_k=5)` | 자유 텍스트 쿼리 | vault 인덱스 대상 키워드 검색 |
| `build_context(id, max_related=3, max_tokens=2000)` | search()에서 나온 id | Related Links를 따라가며 max_tokens에서 잘라냄 |
| `health()` | 없음 | vault 접근 가능 여부 + uptime |
| `evaluate()` | 없음 | vault 통계, 품질, health/learning 점수 |
| `briefing(date="")` | 날짜 `YYYY-MM-DD` | 최근 vault 변경사항 요약 |
| `recommend(category="stock", top_k=5)` | `stock` \| `job`, 개수 | 그래프 연결성 기준 엔티티 랭킹 |
| `timeline(start_date="", end_date="", entity="", days=30)` | 날짜 범위, 선택적 엔티티 필터 | 시간순 지식 축적 현황 |

## Hermes에 등록하기

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  hermes_wiki:
    command: "hermes-mcp"
```

재시작 없이 리로드: `/reload-mcp`

### 검증된 등록 예시 (운영 환경)

실제 운영에서 쓰는 방식 — Hermes Gateway의 CWD와 무관하게 stdio 실행 시
`processor.mcp.server`가 확실히 resolve되도록 올바른 `PYTHONPATH`로 서버를
등록합니다:

```bash
hermes mcp add hermes-wiki \
  --command python \
  --env PYTHONPATH=<repo가 마운트된 컨테이너 내부 경로> \
  --args -m processor.mcp.server
```

> `PYTHONPATH`는 호스트 자체 경로가 아니라 `hermes-gateway` 컨테이너 내부의
> bind-mount 경로여야 합니다. 컨테이너 이미지(`nousresearch/hermes-agent`)가
> 자체적으로 쓰는 표준 경로(예: 자체 `cli.py`, `agent/` 등이 있는 위치)와
> 겹치지 않는, 충돌 없는 별도 경로를 골라야 vendor 설치를 가리지 않습니다.

## 알려진 문제: ModuleNotFoundError

**원인**: Hermes Gateway가 프로젝트 디렉터리를 CWD로 두지 않고 stdio MCP
서버를 실행함.
**해결**: 위와 동일 (`--env PYTHONPATH=<컨테이너 내부 경로>`).

## Slack 질의 예시

Slack에서 질문하면 Hermes → MCP → `search()` → `build_context()` → LLM 순서로
라우팅됩니다:

```
User: 오늘 주식 브리핑 요약해줘
Bot:  [RAG 응답 — 주식 모닝 브리핑 채널의 최신 요약/엔티티를 검색해 컨텍스트로 구성 후 답변]
```

## Vault 규모

현재 `vault_index.json`: 문서 136개 이상 (summary, entity, keyword, related,
wiki 포함).

## 에러 계약

`{"error": {"code", "message", "retryable"}}`
코드: `NOT_FOUND | INVALID_ARGUMENT | TIMEOUT | VAULT_UNAVAILABLE | CORRUPT_FILE | INTERNAL`

- `search()` — 2초 예산
- `build_context()` — 5초 hard / 3초 soft 예산

전체 설계는 [ARCHITECTURE.ko.md](ARCHITECTURE.ko.md) 참고.
