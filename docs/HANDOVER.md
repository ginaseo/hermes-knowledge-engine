# 🎯 Project Goal (최종 목표)

## 최종 목표

Hermes Agent와 Obsidian(HermesVault)을 연동하는 **개인 AI Knowledge Engine** 구축.

Slack, GitHub, Obsidian 등에 축적되는 지식을 자동으로 수집·가공·검색하여 Hermes Agent가 MCP Tool을 통해 필요한 정보를 즉시 검색하고 활용할 수 있는 환경을 만드는 것이 목표이다.

---

# 🗺 현재 진행 상황

## 완료

* ✅ EC2 인프라 (Ubuntu 24.04, Docker Compose)
* ✅ Hermes Gateway / Dashboard
* ✅ Hermes MCP 연결
* ✅ Obsidian Vault 연결
* ✅ Slack Bot 연결 (3개 채널: 메인, 주식 브리핑, 채용 브리핑)
* ✅ SlackProvider (5분마다 timestamp 기반 증분 수집, 중복 수집 방지)
* ✅ 전체 프로세서 파이프라인 완성
  * MarkdownProcessor / WikiProcessor / SummaryProcessor
  * EntityProcessor (슬래시 문자 처리 포함) / KeywordProcessor / RelatedProcessor
  * DescriptionFillProcessor / VaultIndexer / Validator
* ✅ 프롬프트 파일 분리 (summary / entity / keyword / related / description_fill)
* ✅ project_alias.json 주식/채용 alias 추가
* ✅ systemd 자동화 3개 (hermes-knowledge 5분, hermes-slack 5분, hermes-enrich KST 03:00)
* ✅ Slack RAG 응답 확인
* ✅ CI (ruff + black) 통과
* ✅ Phase 4 MCP Tools (evaluate, briefing, recommend, timeline) — 설계: [docs/phase4.md](docs/phase4.md)
* ✅ CI/CD: GitHub Actions CI → CD를 workflow_run으로 연동, CI 성공 시에만 EC2 SSH 자동 배포 (git pull + systemctl restart), 배포 concurrency group으로 중복 SSH 방지
* ✅ gina → hermes 프로젝트/서버 리소스 전면 rename 완료 (systemd 유닛, MCP 서버 id, /opt 마운트 경로 충돌 해결)

---

# ⚙️ 인프라

## EC2
* AWS EC2, Ubuntu 24.04
* /home/ubuntu/hermes-knowledge-engine

## Docker
* hermes-gateway (:8642)
* hermes-dashboard (:9119)

## systemd 서비스

| 서비스 | 동작 | 간격 |
|--------|------|------|
| hermes-slack.timer | Slack 메시지 수집 | 5분 |
| hermes-knowledge.service | 전체 파이프라인 | 5분 |
| hermes-enrich.timer | DescriptionFillProcessor | 매일 KST 03:00 |

## LLM

현재: Cerebras (gpt-oss-120b) — 무료, 느림

HERMES_API_URL=https://api.cerebras.ai/v1
HERMES_API_KEY=발급받은_Cerebras_키
HERMES_MODEL=gpt-oss-120b

대안:
* Groq: https://api.groq.com/openai/v1 (무료 100,000 토큰/일)
* Gemini: https://generativelanguage.googleapis.com/v1beta/openai (무료 1,500회/일)
* OpenRouter: https://openrouter.ai/api/v1 (무료 50회/일, $10 충전시 1000회)
* OpenAI: https://api.openai.com/v1 (유료, gpt-4o-mini 권장)

Cerebras 느릴 때 Groq으로 전환. Groq 일일 토큰 한도 100,000 주의.

## Slack 채널
Channel IDs는 .env에 저장 (SLACK_CHANNEL_IDS)
* 메인 채널
* 주식 모닝 브리핑
* 백엔드 채용 브리핑

---

# 📋 남은 태스크

## 개발 중
* Slack RAG 응답 품질 재테스트
* DescriptionFillProcessor 전체 처리 완료

## Phase 5 CI/CD (진행 중)
* GitHub Actions 자동 배포 (CI→CD 연동, EC2 SSH restart) 완료
* Docker Image 분리 — 미착수

---

# Known Issues

## summary_state.json 타입 오류
항상 echo '{}' 로 초기화 ([]로 초기화하면 TypeError 발생)

## MCP Server ModuleNotFoundError
hermes mcp add hermes-wiki --command python --env PYTHONPATH=/opt/knowledge-engine --args -m processor.mcp.server
# /opt/hermes 쓰지 말 것 — nousresearch/hermes-agent 이미지 자체 내장 경로라 vendor 설치 덮어씀

## Cerebras 느릴 때
응답 지연 발생 시 Groq으로 전환 (단, 일일 토큰 한도 100,000)

---

# 📈 전체 진행률

Architecture        100%
Knowledge Engine    100%
Slack Provider      100%
Pipeline            100%
systemd 자동화       100%
Slack RAG 응답      100%
Phase 4 MCP Tools   100%
LLM 안정화           70%
CI/CD                70%
Production            0%
