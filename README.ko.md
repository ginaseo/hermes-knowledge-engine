# Hermes Knowledge Engine

**🇺🇸 [English](README.md)**

Slack 대화와 Claude Code 세션을 자동으로 요약·연결해서, 검색 가능한 Obsidian
지식 vault로 정리해주는 개인용 지식 파이프라인입니다.

Slack 워크스페이스와 Claude Code 세션을 연결해두면, 프로젝트·인물·개념에 대한
살아있는 위키를 알아서 최신 상태로 유지합니다 — 수동으로 노트를 정리할 필요가
없습니다.

---

## 주요 기능

- **멀티소스 수집** — 현재 Slack 채널과 Claude Code 세션 트랜스크립트 지원,
  작은 provider 하나만 추가하면 새 소스도 바로 연결
- **자동 지식 그래프** — 프로젝트·인물·개념 등 엔티티, 키워드, 상호 링크를
  LLM이 추출·관리
- **자동 갱신 위키** — 새 대화가 들어올 때마다 Markdown 페이지가 생성/갱신됨
- **증분 처리** — 변경된 파일만 재처리
- **LLM 응답 캐시** — 중복 API 호출 방지
- **Watch/Daemon 모드** — 스케줄에 따라 무인으로 계속 실행
- **지식 평가** — health/learning 점수, 커버리지 갭, 검색 성능 벤치마크
- **MCP 서버** — Claude에서 바로 vault 검색/컨텍스트 구성/헬스체크 가능

---

## 빠른 시작

```bash
# 1. 클론 후 가상환경 준비
git clone https://github.com/ginaseo/hermes-knowledge-engine.git
cd hermes-knowledge-engine
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# 2. 설치 (`hermes` CLI 명령 사용 가능해짐)
pip install .

# 3. 환경 변수 설정
cp .env.example .env
# HERMES_API_URL / HERMES_API_KEY (LLM 엔드포인트) 설정, Slack 쓸 경우 SLACK_BOT_TOKEN / SLACK_CHANNEL_IDS도 설정

# 4. 파이프라인 실행
hermes run
```

전체 설치, 환경 변수, 개발 환경 설정은 [INSTALL.ko.md](docs/INSTALL.ko.md) 참고.

### 자주 쓰는 명령어

```bash
hermes                      # 전체 파이프라인
hermes watch                # 30초마다 변경사항 폴링
hermes daemon               # 스케줄 기반 상시 실행
hermes evaluate             # 지식 통계, 품질, health/learning 점수
hermes validate             # vault 무결성 검증
hermes --help               # 그 외 전체 명령어
```

---

## 더 알아보기

- [INSTALL.ko.md](docs/INSTALL.ko.md) — 전체 설치, 설정, 개발 환경 세팅
- [docs/pipeline.ko.md](docs/pipeline.ko.md) — 프로세서 파이프라인, 폴더 구조, 캐싱/증분 처리 상세
- [docs/ingest-sources.ko.md](docs/ingest-sources.ko.md) — Slack & Claude Code provider, 새 소스 추가 방법
- [docs/operations.ko.md](docs/operations.ko.md) — daemon 모드, 평가, 검색 벤치마크, 배포 관련 참고사항
- [docs/vault-sync.ko.md](docs/vault-sync.ko.md) — Syncthing으로 여러 기기 간 vault 동기화
- [MCP.ko.md](docs/MCP.ko.md) — MCP 서버 설정 및 도구
- [ARCHITECTURE.ko.md](docs/ARCHITECTURE.ko.md) — 시스템 설계
