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
* ✅ Slack Bot 연결 (3개 채널)
* ✅ SlackProvider (5분마다 자동 수집, 증분 수집)
* ✅ MarkdownProcessor
* ✅ WikiProcessor
* ✅ SummaryProcessor
* ✅ EntityProcessor (슬래시 문자 처리 포함)
* ✅ KeywordProcessor
* ✅ RelatedProcessor
* ✅ VaultIndexer
* ✅ Validator
* ✅ systemd 자동화 (gina-knowledge, gina-slack, gina-enrich)
* ✅ Slack RAG 응답 확인

---

# ⚙️ 인프라

## EC2
* AWS EC2, Ubuntu 24.04
* /home/ubuntu/gina-knowledge-engine

## Docker
* hermes-gateway (:8642)
* hermes-dashboard (:9119)

## systemd 서비스

| 서비스 | 동작 | 간격 |
|--------|------|------|
| gina-slack.timer | Slack 메시지 수집 | 5분 |
| gina-knowledge.service | 전체 파이프라인 | 5분 |
| gina-enrich.timer | DescriptionFillProcessor | 매일 03:00 UTC |

## LLM

현재: Groq (무료 14400회/일)

HERMES_API_URL=https://api.groq.com/openai/v1
HERMES_API_KEY=발급받은_Groq_키
HERMES_MODEL=llama-3.3-70b-versatile

대안:
* Gemini: https://generativelanguage.googleapis.com/v1beta/openai (무료 1500회/일)
* OpenRouter: https://openrouter.ai/api/v1 (무료 50회/일, $10 충전시 1000회)
* OpenAI: https://api.openai.com/v1 (유료, gpt-4o-mini 권장)

## Slack 채널
Channel IDs는 .env에 저장 (SLACK_CHANNEL_IDS)
* 메인 채널
* 주식 모닝 브리핑
* 백엔드 채용 브리핑

---

# 📋 남은 태스크

## 개발 중
* DescriptionFillProcessor 빈 JSON 응답 FAIL 수정
* Slack 응답 품질 개선

## Phase 4 (예정)
* evaluate(), briefing(), recommend(), timeline()

## Phase 5 CI/CD (예정)
* Docker Image 분리, GitHub Actions, 자동 배포

---

# Known Issues

## summary_state.json 타입 오류
항상 echo '{}' 로 초기화 ([]로 초기화하면 TypeError 발생)

## MCP Server ModuleNotFoundError
hermes mcp add gina --command python --env PYTHONPATH=/opt/gina --args -m processor.mcp.server

## Groq Rate Limit
분당 30회 제한. watch 간격 5분으로 설정해서 완화. 429 발생 시 자동 retry 동작.

---

# 📈 전체 진행률

Architecture        100%
Knowledge Engine    100%
Slack Provider      100%
Pipeline            100%
systemd 자동화       100%
Slack RAG 응답      100%
LLM 안정화           70%
CI/CD                 0%
Production            0%
