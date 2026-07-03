"""Tests for DescriptionFillProcessor — TODO stub enrichment and merge-on-reappearance."""

import json
from unittest.mock import MagicMock, patch

import pytest

import processor.description_fill_processor as dfp_module
import processor.processing_state as ps_module
from processor.description_fill_processor import DescriptionFillProcessor

TODO_STUB = (
    "---\ntype: Technology\ncreated: auto\n---\n\n"
    "# Kafka\n\n## Description\n\nTODO\n\n## Related\n\n"
)


@pytest.fixture(autouse=True)
def patch_paths(vault, monkeypatch, tmp_path):
    prompt_file = tmp_path / "description_fill_prompt.txt"
    prompt_file.write_text(
        "Entity: {entity_name} ({entity_type})\nExisting: {existing}\nSource: {source}",
        encoding="utf-8",
    )
    alias_file = tmp_path / "project_alias.json"
    alias_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(dfp_module, "SUMMARY", vault / "knowledge" / "summary")
    monkeypatch.setattr(dfp_module, "ENTITY", vault / "knowledge" / "entity")
    monkeypatch.setattr(dfp_module, "RELATED", vault / "knowledge" / "related")
    monkeypatch.setattr(dfp_module, "WIKI", vault / "wiki")
    monkeypatch.setattr(dfp_module, "PROMPT", prompt_file)
    monkeypatch.setattr(dfp_module, "PROJECT_ALIAS_FILE", alias_file)
    monkeypatch.setattr(dfp_module, "SOURCES_FILE", vault / "index" / "description_fill_sources.json")
    monkeypatch.setattr(ps_module, "STATE_DIR", vault / "index")


def _mock_client(response: str):
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.ask.return_value = response
    return mock


def _write_source(vault, stem: str, summary: str, related: str = "") -> None:
    (vault / "knowledge" / "summary" / f"{stem}-summary.md").write_text(summary, encoding="utf-8")
    (vault / "knowledge" / "entity" / f"{stem}-entity.json").write_text(
        json.dumps([{"type": "Technology", "name": "Kafka"}]), encoding="utf-8"
    )
    if related:
        (vault / "knowledge" / "related" / f"{stem}-related.md").write_text(related, encoding="utf-8")


def test_no_entity_files(caplog):
    DescriptionFillProcessor().process()
    assert "No entity files" in caplog.text


def test_fills_todo_stub(vault):
    _write_source(vault, "a", "Kafka summary text", "[[Streaming]]")
    (vault / "wiki" / "Kafka.md").write_text(TODO_STUB, encoding="utf-8")

    fields = json.dumps(
        {"description": "메시지 큐 시스템", "summary": "- 요약1", "related_entities": ["Streaming"], "tags": ["queue"]}
    )
    with patch("processor.description_fill_processor.LLMClient", return_value=_mock_client(fields)):
        DescriptionFillProcessor().process()

    content = (vault / "wiki" / "Kafka.md").read_text(encoding="utf-8")
    assert "TODO" not in content
    assert "메시지 큐 시스템" in content
    assert "[[Streaming]]" in content
    assert "#queue" in content


def test_second_run_no_new_source_skips(vault):
    _write_source(vault, "a", "Kafka summary text")
    (vault / "wiki" / "Kafka.md").write_text(TODO_STUB, encoding="utf-8")

    fields = json.dumps({"description": "d", "summary": "s", "related_entities": [], "tags": []})
    with patch("processor.description_fill_processor.LLMClient", return_value=_mock_client(fields)):
        DescriptionFillProcessor().process()

    with patch("processor.description_fill_processor.LLMClient") as MockCls:
        DescriptionFillProcessor().process()
        MockCls.assert_not_called()


def test_llm_failure_does_not_corrupt_existing_content(vault):
    _write_source(vault, "a", "Kafka summary text")
    (vault / "wiki" / "Kafka.md").write_text(TODO_STUB, encoding="utf-8")

    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.ask.side_effect = RuntimeError("LLM down")

    with patch("processor.description_fill_processor.LLMClient", return_value=mock):
        DescriptionFillProcessor().process()  # Must not raise

    assert (vault / "wiki" / "Kafka.md").read_text(encoding="utf-8") == TODO_STUB


def test_merge_new_source_updates_existing_doc(vault):
    _write_source(vault, "a", "Kafka summary text")
    (vault / "wiki" / "Kafka.md").write_text(TODO_STUB, encoding="utf-8")

    first = json.dumps({"description": "1차 설명", "summary": "s1", "related_entities": [], "tags": []})
    with patch("processor.description_fill_processor.LLMClient", return_value=_mock_client(first)):
        DescriptionFillProcessor().process()

    # New summary/entity file mentioning the same entity again
    _write_source(vault, "b", "Kafka more text")

    second = json.dumps({"description": "병합된 설명", "summary": "s2", "related_entities": [], "tags": []})
    with patch("processor.description_fill_processor.LLMClient", return_value=_mock_client(second)):
        DescriptionFillProcessor().process()

    content = (vault / "wiki" / "Kafka.md").read_text(encoding="utf-8")
    assert "병합된 설명" in content


def test_ignores_non_target_type(vault):
    _write_source(vault, "a", "text")
    (vault / "wiki" / "Other.md").write_text(
        "---\ntype: Project\ncreated: auto\n---\n\n# Other\n\n## Description\n\nTODO\n\n",
        encoding="utf-8",
    )

    with patch("processor.description_fill_processor.LLMClient") as MockCls:
        DescriptionFillProcessor().process()
        MockCls.assert_not_called()
