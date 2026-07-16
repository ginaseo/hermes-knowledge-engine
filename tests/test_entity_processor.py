"""Tests for EntityProcessor — entity stub creation, alias, dedup."""

import json
from unittest.mock import MagicMock, patch

import pytest

import processor.entity_processor as ep_module
import processor.processing_state as ps_module
from processor.entity_processor import EntityProcessor


@pytest.fixture(autouse=True)
def patch_paths(vault, monkeypatch, tmp_path):
    prompt_file = tmp_path / "entity_prompt.txt"
    prompt_file.write_text("Extract entities: {summary}", encoding="utf-8")

    alias_file = tmp_path / "project_alias.json"
    alias_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ep_module, "SUMMARY", vault / "knowledge" / "summary")
    monkeypatch.setattr(ep_module, "ENTITY", vault / "knowledge" / "entity")
    monkeypatch.setattr(ep_module, "PROJECTS", vault / "projects")
    monkeypatch.setattr(ep_module, "PEOPLE", vault / "people")
    monkeypatch.setattr(ep_module, "WIKI", vault / "wiki")
    monkeypatch.setattr(ep_module, "PROMPT", prompt_file)
    monkeypatch.setattr(ep_module, "PROJECT_ALIAS_FILE", alias_file)
    monkeypatch.setattr(
        ep_module,
        "_ENTITY_FOLDER",
        {
            "Project": vault / "projects",
            "Person": vault / "people",
        },
    )
    monkeypatch.setattr(ps_module, "STATE_DIR", vault / "index")


def _mock_client(entities: list):
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.ask.return_value = json.dumps(entities)
    return mock


def test_no_files(caplog):
    EntityProcessor().process()
    assert "No summary files" in caplog.text


def test_all_skip_no_llm(vault):
    src = vault / "knowledge" / "summary" / "x-summary.md"
    src.write_text("body", encoding="utf-8")

    with patch("processor.entity_processor.LLMClient", return_value=_mock_client([])):
        EntityProcessor().process()

    with patch("processor.entity_processor.LLMClient") as MockCls:
        EntityProcessor().process()  # Second run — no change
        MockCls.assert_not_called()


def test_creates_entity_json(vault):
    src = vault / "knowledge" / "summary" / "a-summary.md"
    src.write_text("summary text", encoding="utf-8")

    entities = [{"type": "Project", "name": "Alpha"}]
    with patch("processor.entity_processor.LLMClient", return_value=_mock_client(entities)):
        EntityProcessor().process()

    entity_file = vault / "knowledge" / "entity" / "a-entity.json"
    assert entity_file.exists()
    data = json.loads(entity_file.read_text(encoding="utf-8"))
    assert data == entities


def test_creates_project_stub(vault):
    src = vault / "knowledge" / "summary" / "b-summary.md"
    src.write_text("text", encoding="utf-8")

    entities = [{"type": "Project", "name": "Hermes"}]
    with patch("processor.entity_processor.LLMClient", return_value=_mock_client(entities)):
        EntityProcessor().process()

    stub = vault / "projects" / "Hermes.md"
    assert stub.exists()
    assert "type: Project" in stub.read_text(encoding="utf-8")


def test_creates_person_stub(vault):
    src = vault / "knowledge" / "summary" / "c-summary.md"
    src.write_text("text", encoding="utf-8")

    entities = [{"type": "Person", "name": "Alice"}]
    with patch("processor.entity_processor.LLMClient", return_value=_mock_client(entities)):
        EntityProcessor().process()

    stub = vault / "people" / "Alice.md"
    assert stub.exists()


def test_deduplicates_entities(vault):
    src = vault / "knowledge" / "summary" / "d-summary.md"
    src.write_text("text", encoding="utf-8")

    entities = [
        {"type": "Project", "name": "Beta"},
        {"type": "Project", "name": "Beta"},  # duplicate
    ]
    with patch("processor.entity_processor.LLMClient", return_value=_mock_client(entities)):
        EntityProcessor().process()

    assert (vault / "projects" / "Beta.md").exists()
    # Only one file created, not two
    assert len(list((vault / "projects").glob("*.md"))) == 1


def test_dedup_ignores_case_across_runs(vault):
    """Same entity re-extracted with different casing must not spawn a duplicate stub.

    Regression: on case-sensitive filesystems, `Path.exists()` missed an
    already-written "Architecture.md" when the next run's entity name came
    back as "architecture", creating a second stub.
    """
    src1 = vault / "knowledge" / "summary" / "g1-summary.md"
    src1.write_text("text", encoding="utf-8")
    entities1 = [{"type": "Concept", "name": "Architecture"}]
    with patch("processor.entity_processor.LLMClient", return_value=_mock_client(entities1)):
        EntityProcessor().process()

    src2 = vault / "knowledge" / "summary" / "g2-summary.md"
    src2.write_text("text", encoding="utf-8")
    entities2 = [{"type": "Concept", "name": "architecture"}]
    with patch("processor.entity_processor.LLMClient", return_value=_mock_client(entities2)):
        EntityProcessor().process()

    matches = list((vault / "wiki").glob("[Aa]rchitecture.md"))
    assert len(matches) == 1


def test_skips_empty_name(vault):
    src = vault / "knowledge" / "summary" / "e-summary.md"
    src.write_text("text", encoding="utf-8")

    entities = [{"type": "Project", "name": ""}]
    with patch("processor.entity_processor.LLMClient", return_value=_mock_client(entities)):
        EntityProcessor().process()

    assert list((vault / "projects").glob("*.md")) == []


def test_invalid_json_continues(vault, caplog):
    src = vault / "knowledge" / "summary" / "f-summary.md"
    src.write_text("text", encoding="utf-8")

    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.ask.return_value = "not valid json {"

    with patch("processor.entity_processor.LLMClient", return_value=mock):
        EntityProcessor().process()  # Must not raise

    assert "Invalid JSON" in caplog.text
