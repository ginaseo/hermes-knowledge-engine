# Ingest 소스

## Slack

`SlackProvider`는 설정된 채널을 폴링해서 원본 메시지를 `HermesVault/slack/`에 저장합니다.
채널 ID는 `.env`의 `SLACK_CHANNEL_IDS`로 설정합니다 (커밋되지 않음).

## Claude Code 세션

`ClaudeCodeProvider` (`ingest/providers/claude_code.py`)는 Claude Code의
`SessionEnd` 훅을 통해 방금 끝난 세션의 트랜스크립트를
`HermesVault/claude-code/<year>/<month>/<date>-<session-id-8자리>.md`로 가져옵니다.
매 실행은 `HermesVault/index/claude_code_state.json`(세션 ID + 트랜스크립트 mtime
기준)으로 중복 방지되어, 이미 가져왔고 변경 없는 세션은 건너뜁니다.

Claude Code 설정에서 `SessionEnd` 훅으로 등록하고, 훅의 stdin JSON
(`transcript_path`, `session_id`, `cwd`)을 다음으로 흘려보내면 됩니다:

```bash
python ingest/providers/claude_code.py
```

한번 vault에 들어오면 Slack 메시지와 동일하게 `MarkdownProcessor →
SummaryProcessor → EntityProcessor/WikiProcessor` 파이프라인을 그대로
탑니다 — 별도 처리 경로 없음.

## 새 소스 추가하기

1. `ingest/providers/` 아래에 원본 `.md` 파일을 `HermesVault/<source>/`에
   써주는 provider 추가
2. `processor/markdown_processor.py`의 `SOURCES` 리스트에
   `(source_name, provider_name, raw_dir)`를 등록 — `summary_processor.py`,
   `wiki_processor.py`는 공유되는 `SOURCE_NAMES`를 통해 자동으로 인식함
