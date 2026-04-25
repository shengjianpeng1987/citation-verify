#!/usr/bin/env python3
"""Unit tests for tests/_runner.py — capture/replay path utilities.

These tests do NOT exercise the orchestrator or any subprocess. They lock
the runner's fixture-path resolution and meta normalization so the
infrastructure is correct before fixtures are recorded against it (Phase 2 H2).

Run standalone:
    .venv/bin/python3 tests/test_runner_unit.py

Or under pytest:
    .venv/bin/pytest tests/test_runner_unit.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _runner import (
    NORMALIZED_CODEX_MODEL,
    NORMALIZED_GENERATED_AT,
    api_fixture_path,
    codex_fixture_path,
    normalize_meta,
)


def test_api_fixture_path_uses_citation_id() -> None:
    cit = {"id": 7, "title": "X", "authors": [], "year": 2020,
           "venue": None, "doi": None, "url": None, "raw_text": "X"}
    p = api_fixture_path("nasal_methylation", json.dumps(cit))
    assert p.name == "citation_7.json"
    assert p.parent.name == "nasal_methylation"
    assert p.parent.parent.name == "api"


def test_api_fixture_path_rejects_missing_id() -> None:
    bad = json.dumps({"title": "X"})  # no id
    try:
        api_fixture_path("c", bad)
    except RuntimeError as e:
        assert "no integer id" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_api_fixture_path_rejects_bad_json() -> None:
    try:
        api_fixture_path("c", "{not valid json")
    except RuntimeError as e:
        assert "un-parseable" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_codex_fixture_path_uses_input_basename() -> None:
    p = codex_fixture_path("eif4enif1", Path("/some/where/_work/stage4b_input_3.json"))
    assert p.name == "stage4b_input_3.json"
    assert p.parent.name == "eif4enif1"
    assert p.parent.parent.name == "codex"


def test_normalize_meta_replaces_volatile_fields() -> None:
    obj = {
        "meta": {
            "schema_version": "0.2.0",
            "orchestrator_version": "0.2.0",
            "generated_at": "2026-04-25T12:34:56Z",
            "input_doc_sha256": "abcd" * 16,
            "input_doc_filename": "test.docx",
            "codex_model": "gpt-5.4",
            "api_sources_enabled": ["crossref", "openalex", "semantic_scholar"],
            "valid_citation_ids": [1, 2, 3],
        },
        "corrections": [], "replacements": [], "unresolvable": [],
    }
    norm = normalize_meta(obj)

    # Volatile → placeholder
    assert norm["meta"]["generated_at"] == NORMALIZED_GENERATED_AT
    assert norm["meta"]["codex_model"] == NORMALIZED_CODEX_MODEL

    # Stable → unchanged
    assert norm["meta"]["schema_version"] == "0.2.0"
    assert norm["meta"]["orchestrator_version"] == "0.2.0"
    assert norm["meta"]["input_doc_sha256"] == "abcd" * 16
    assert norm["meta"]["input_doc_filename"] == "test.docx"
    assert norm["meta"]["api_sources_enabled"] == ["crossref", "openalex", "semantic_scholar"]
    assert norm["meta"]["valid_citation_ids"] == [1, 2, 3]

    # Original not mutated (deep-copy)
    assert obj["meta"]["generated_at"] == "2026-04-25T12:34:56Z"
    assert obj["meta"]["codex_model"] == "gpt-5.4"


def test_normalize_meta_handles_missing_fields() -> None:
    # Should not crash on partial meta — Phase 4b error paths can produce
    # sparse meta if a run aborts. Normalize only what's present.
    obj = {"meta": {"schema_version": "0.2.0"}}
    norm = normalize_meta(obj)
    assert norm["meta"] == {"schema_version": "0.2.0"}


if __name__ == "__main__":
    test_api_fixture_path_uses_citation_id()
    test_api_fixture_path_rejects_missing_id()
    test_api_fixture_path_rejects_bad_json()
    test_codex_fixture_path_uses_input_basename()
    test_normalize_meta_replaces_volatile_fields()
    test_normalize_meta_handles_missing_fields()
    print("PASS: all 6 runner-unit cases.")
