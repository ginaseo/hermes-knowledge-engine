# 아키텍처

## 개요

Hermes Agent는 순차적인 프로세서 파이프라인입니다. 각 단계는 이전 단계의
출력을 읽습니다. 증분 상태 추적 덕분에 변경된 파일만 재처리됩니다.

---

## 프로세서 파이프라인

```
Input:  HermesVault/slack/          (원본 Slack markdown export)
          │
          ▼
        MarkdownProcessor            YAML front-matter 추가, knowledge/slack/로 복사
        WikiProcessor                wiki/slack/로 복사
          │
          ▼ (knowledge/slack/ 읽음)
        SummaryProcessor             LLM 호출 → knowledge/summary/
          │
          ├──────────────────────────────────────────────────┐
          ▼                          ▼                       ▼
        EntityProcessor            KeywordProcessor       RelatedProcessor
        knowledge/entity/          knowledge/keywords/    knowledge/related/
        projects/, people/, wiki/
          │
          ▼ (entity + related 이후)
        DescriptionFillProcessor   매칭되는 summary + related 텍스트로
                                    wiki/{Technology,Organization,Concept}의
                                    TODO 스텁을 보강
          │
          ▼ (항상 실행)
        Cleaner                    잘못되거나 빈 스텁 파일 제거
        VaultIndexer               index/vault_index.json 생성
        Validator                  UTF-8 + JSON 무결성 검사
```

Entity, Keyword, Related 프로세서는 서로 독립적이라 `--parallel`로 동시
실행할 수 있습니다.

---

## ProcessingState

`processor/processing_state.py`

각 프로세서는 `HermesVault/index/<name>_state.json`에 자신의 이름이 붙은
상태 파일을 소유합니다. 상태는 절대 파일 경로를 마지막으로 본 `mtime`
(float)에 매핑합니다.

```
{
  "/abs/path/to/file.md": 1718000000.123456
}
```

`is_modified(file)`은 파일의 현재 `mtime`이 저장된 값과 다르면 `True`를
반환합니다. `update(file)`은 현재 `mtime`을 기록합니다. `save()`는 디스크에
저장합니다.

`force=True`면 이 체크를 무시하고 `is_modified`가 항상 `True`를 반환합니다.

---

## LLM 캐시

`processor/llm/cache.py`

응답은 `SHA256(prompt)`로 키가 매겨집니다. 캐시 파일은 `LLMClient.__init__`
에서 한 번만 로드되고, 프로세서 실행당 최대 한 번(`LLMClient.__exit__`에서
호출되는 `flush()`를 통해) 기록됩니다.

`put()`은 메모리에만 반영됩니다. `flush()`는 스레드 락 하에 디스크 파일과
병합되므로 병렬 사용에도 안전합니다.

---

## Vault 구조

```
HermesVault/
├── slack/                  원본 Slack markdown 입력
├── knowledge/
│   ├── slack/              처리된 markdown (front-matter 포함)
│   ├── summary/            LLM이 생성한 요약
│   ├── entity/             추출된 엔티티 JSON
│   ├── keywords/           키워드 목록
│   └── related/            관련 문서 링크
├── projects/                자동 생성된 프로젝트 스텁
├── people/                  자동 생성된 인물 스텁
├── wiki/                    자동 생성된 위키 스텁 + slack 사본
├── index/
│   ├── *_state.json        프로세서별 증분 상태
│   ├── vault_index.json    검색용 전체 문서 인덱스
│   ├── job_history.json    작업 실행 이력 (최근 500개)
│   └── evaluation_history.json  평가 스냅샷 (최근 365개)
├── config/
│   └── schedule.yaml       daemon 작업 스케줄
├── benchmark/
│   └── questions.json      자동 생성된 검색 벤치마크 질문
├── reports/
│   └── daily-learning.md   일일 지식 평가 리포트
└── cache/
    └── llm_cache.json      LLM 응답 캐시
```

---

## 로깅

`processor/log.py`

모든 출력은 기존 `[TAG] message` 콘솔 표시 형태를 유지하기 위해
`%(message)s` 포맷의 Python `logging` 모듈을 사용합니다.

`_SmartHandler`는 (`log.capture(fn)`으로 활성화된 경우) 로그 레코드를
thread-local `StringIO` 버퍼로 라우팅합니다. 이 덕분에 병렬 프로세서들이
각자 독립적으로 출력을 쌓을 수 있고, runner가 이를 원래 순서대로 flush해서
콘솔 출력이 섞이지 않습니다.

---

## 설정

`processor/config.py`

import 시점에 (`load_dotenv()`를 통해) 환경 변수를 한 번 읽습니다.
모듈 레벨 싱글턴 `cfg`로 불변(frozen) `Config` dataclass를 노출합니다.

`cfg.validate_llm()`은 `HERMES_API_URL`이나 `HERMES_API_KEY`가 없으면
명확한 메시지와 함께 `EnvironmentError`를 발생시킵니다. `LLMClient.__init__`
에서 호출되므로 LLM을 쓰지 않는 프로세서는 자격 증명 없이 실행할 수
있습니다.

---

## Daemon

`processor/daemon.py`

`run_daemon()`은 10초마다 폴링합니다. 매 tick마다 각 작업의 `next_run`
타임스탬프가 지났는지 확인합니다. 스케줄 파일이 마지막 로드 이후
수정됐으면 hot-reload하되, 각 작업의 `next_run`은 보존해서 작업이
건너뛰이거나 중복 실행되지 않게 합니다.

각 작업은 `_make_processor(name)` (`_PROCESSOR_MAP`에서 importlib로 조회)로
실행됩니다. 실패하면 `RetryPolicy.wait_for(attempt)`를 사용해 최대
`retry.count`번 재시도합니다:
- `exponential`: `delay * 2^attempt`
- `linear`: `delay * (attempt + 1)`
- `fixed`: `delay`

모든 실행(성공이든 최종 실패든)은 `JobHistory`에 기록됩니다.

---

## 작업 이력

`processor/history.py`

`JobRecord` dataclass 필드: `name`, `start_time`, `finish_time`, `duration`,
`status` (`ok`/`fail`), `exception`, `retry_count`.

`JobHistory`는 초기화 시 `HermesVault/index/job_history.json`을 로드합니다.
`append()`는 레코드를 추가하고 기록 전 최근 500개로 정리합니다.
`last_success(name)`는 역순으로 훑어 가장 최근 `ok` 항목을 찾습니다.

---

## 지식 평가

`processor/evaluator.py`

LLM 호출 없이 로컬에서 계산되는 5단계:

1. **통계** (`_scan_stats`) — vault 폴더별 파일 개수
2. **성장** (`_scan_growth`) — `mtime` 기준 1일/7일/30일 신규 파일 수
3. **품질** (`_scan_quality`) — 커버리지 %를 위한 stem 교집합; 깨진 참조를
   위한 `[[wikilinks]]` BFS
4. **그래프** (`_build_graph`) — 엔티티 이름을 노드로, related 파일의
   `[[links]]`를 엣지로; 연결 컴포넌트 계산에 BFS 사용
5. **점수화** — `health = 100 − Σ(감점)`,
   `learning = health × 0.7 + min(new_docs_7d × 5, 30)`

외부 그래프 라이브러리 없이 인접 리스트 + BFS를 직접 구현했습니다.

---

## 검색 벤치마크

`processor/retrieval.py`

키워드 중복 기반 점수화: `_score(question, doc) = |qkw ∩ dkw| / |qkw|`.
불용어 필터링 적용. 질문은 각 엔티티 JSON 파일당 상위 3개 엔티티에서
자동 생성됩니다.

지표: Top-K 정확도 (1/3/5), Recall, Precision, F1.

---

## 실행 흐름

```
hermes [subcommand] [--force] [--parallel] [--watch[=N]]
       [--log-level=X] [--log-file=path] [--last=N] [targets...]

서브커맨드: run (기본), watch, validate, clean, benchmark,
           daemon, history, evaluate, benchmark-retrieval

ProcessorRunner.__init__
  └── argv[1]이 알려진 서브커맨드면 추출
  └── 플래그와 target 파싱
  └── log.setup(level, log_file) 호출
  └── 모든 프로세서 인스턴스화

ProcessorRunner.run()
  ├── watch / --watch       → _watch() → 루프: _run_once() 시도 + sleep
  ├── validate              → Validator().process()
  ├── clean                 → Cleaner().process()
  ├── benchmark             → _benchmark() → 프로세서 + 타이밍 테이블
  ├── daemon                → daemon.run_daemon() [lazy import]
  ├── history               → JobHistory().display(n=last_n) [lazy import]
  ├── evaluate              → Evaluator().run() [lazy import]
  ├── benchmark-retrieval   → RetrievalBenchmark().run() [lazy import]
  └── run / 기본             → _run_once()

_run_once()
  ├── _run_sequential(pending)  (기본)
  └── _run_parallel(pending)    (--parallel)
      └── entity/keyword/related → ThreadPoolExecutor
          └── 각 스레드: log.capture(processor.process)
          └── 결과를 원래 순서대로 stdout에 flush
```

---

## 아키텍처 상태

**상태:** FROZEN
**버전:** v1.0
**동결일:** 2026-07

### 현재 아키텍처

- External Agent = Agent Runtime
- Hermes = Knowledge Engine
- Obsidian = Source of Truth
- MCP = Integration Layer
- Knowledge Pipeline = Independent

### 설계 원칙

- 새로 만들기 전에 재사용
- YAGNI
- Pipeline은 독립성 유지
- MCP가 유일한 통합 지점
- Obsidian은 절대 External Agent Memory로 동기화하지 않음
- 두 번째 구현이 나온 뒤에만 추상화 추가

### Hermes MCP 서버 (Phase 1 목표 — 아직 미구현)

```
External Agent (Gateway/Scheduler/Memory/Skill/MCP client) — 수정 없음
        │  MCP (config.yaml mcp_servers 항목만)
        ▼
Hermes MCP Server
  ├── search()          index/vault_index.json 대상 키워드 조회
  ├── build_context()   위키 문서 + 제한된 Related Links 확장
  ├── health()           liveness/readiness, 저비용
  └── evaluate()/briefing()  기존 Evaluator 출력의 얇은 wrapper
        │
Knowledge Pipeline (이 repo, daemon.py) — 수정 없음, 독립 프로세스
        │
   HermesVault (Obsidian, Source of Truth)
```

위 설계 원칙 중 하나라도 어기는 변경(예: Obsidian을 External Agent
Memory로 동기화, MCP 외 두 번째 통합 지점 추가, 두 번째 구현이 나오기 전에
Retriever 추상화 도입)은 **아키텍처 변경**이며 일반적인 기능 추가가 아닌
별도 리뷰가 필요합니다.
