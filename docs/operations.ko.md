# 운영

## Daemon 모드

`hermes daemon`은 `HermesVault/config/schedule.yaml`을 읽어서 프로세서를
설정된 주기로 실행합니다. 파일이 없으면 기본 스케줄이 생성됩니다.
스케줄 파일은 변경 시 hot-reload되고, 작업은 설정된 backoff로 재시도됩니다.
모든 실행은 `HermesVault/index/job_history.json`에 기록됩니다.

```yaml
# HermesVault/config/schedule.yaml
jobs:
  summary:
    every: 10m
  entity:
    every: 10m
  index:
    every: hour
  cleaner:
    every: day

retry:
  count: 3
  delay: 30s
  backoff: exponential  # 또는 linear, fixed
```

주기 형식: `30s`, `5m`, `2h`, `1d`, `hour`, `day`, `sunday`

## 지식 평가

`hermes evaluate`는 vault를 스캔해서 다음을 출력합니다:
- **지식 통계** — 문서/요약/엔티티/키워드/관계/프로젝트/인물/위키 개수
- **지식 성장** — 최근 1/7/30일 신규 항목 수
- **지식 품질** — 커버리지 비율, 누락 파일, 고아 엔티티, 깨진 참조
- **그래프 지표** — 노드, 엣지, density, 연결 컴포넌트, 고립 노드
- **Health 점수** (0–100) — 품질 갭에 대한 가중 감점
- **Learning 점수** (0–100) — health × 0.7 + 성장 보너스 (최대 100)

결과는 `HermesVault/index/evaluation_history.json`에 저장되고, 일일 리포트는
`HermesVault/reports/daily-learning.md`에 기록됩니다.

## 검색 벤치마크

`hermes benchmark-retrieval`은 키워드 기반 검색 품질을 평가합니다:
- 질문이 없으면 엔티티 JSON 파일에서 자동 생성
- Top-1 / Top-3 / Top-5 정확도, Recall, Precision, F1 Score 보고

## 배포

파이프라인은 작은 상시 가동 호스트(예: 클라우드 VM)에서 무인으로 돌아가도록
설계돼 있습니다:

- 게이트웨이/API 프로세스와 대시보드 프로세스, 각각 자체 포트 사용
- `hermes watch` (또는 `hermes daemon`)를 장기 실행 서비스로 구동
  (systemd unit, supervisor, 컨테이너 재시작 정책 등 환경에 맞게)
- 각 ingest 소스별로(예: Slack 수집기) 자체 주기로 도는 별도 스케줄 작업

실제 호스트, 포트, 파일시스템 경로는 환경마다 다르며 보안상 여기 문서화하지
않습니다 — 본인 배포 환경에 맞게 `.env` / 프로세스 매니저 설정 파일에서
구성하세요.
