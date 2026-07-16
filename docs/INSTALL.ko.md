# 설치 가이드

## 요구사항

- Python 3.13+
- OpenAI 호환 LLM 엔드포인트

## 방법 A — 패키지로 설치 (권장)

```bash
# 1. 저장소 클론
git clone https://github.com/ginaseo/hermes-knowledge-engine.git
cd hermes-knowledge-engine

# 2. 가상환경 생성
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# 3. 설치 (`hermes` CLI 명령 사용 가능해짐)
pip install .

# 4. 환경 변수 설정
cp .env.example .env
# .env 파일 열어서 HERMES_API_URL, HERMES_API_KEY 설정

# 5. 파이프라인 실행
hermes run
```

## 방법 B — 설치 없이 실행

```bash
pip install -r requirements.txt
python -m processor.runner
```

## 개발 환경 설정

```bash
pip install -r requirements-dev.txt

# 테스트 실행
pytest tests/ -v

# 린트
ruff check processor/ tests/

# 포맷 검사
black --check processor/ tests/
```

## 환경 변수

프로젝트 루트에 `.env` 파일 생성:

```dotenv
HERMES_API_URL=https://your-llm-endpoint/v1
HERMES_API_KEY=your-api-key

# 선택
HERMES_VAULT=./HermesVault   # vault 경로 커스터마이즈
LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR
```

`HERMES_API_URL`이나 `HERMES_API_KEY`가 없으면 첫 LLM 프로세서 시작 시 명확한
에러 메시지가 뜹니다. LLM을 안 쓰는 프로세서(markdown, wiki, cleaner 등)는
자격 증명 없이도 실행됩니다.

## Vault 구조

파이프라인은 프로젝트 루트의 `HermesVault/`를 읽고 씁니다.
최초 실행 전 입력 폴더를 만들어두세요:

```bash
mkdir -p HermesVault/slack
# Slack markdown export 파일을 HermesVault/slack/ 에 넣기
```
