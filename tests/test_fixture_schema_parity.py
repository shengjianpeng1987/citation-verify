#!/usr/bin/env python3
"""Validate every committed codex fixture against its active schema.

Each fixture under `tests/fixtures/codex/<case>/` is the recorded or
hand-crafted stdout of a `codex exec --output-schema <schema>` call.
At Codex runtime the schema is enforced; in test replay no runtime check
exists, so this test stands in as the guard.

If `schemas/<schema>.json` changes (field added/removed/typed differently)
and a fixture isn't updated, this test goes red — preventing the
"fixture passes against old schema, breaks against new schema" drift.

Mapping by fixture filename pattern:

    stage2_input.json                                → citations.schema.json
    stage3_input_<id>.json
    stage3_input_<id>_reverify.json                  → verdict.schema.json
    stage4a_input_<id>.json                          → alternatives.schema.json
    stage4b_input_<id>_<rank>.json   (with rank)     → fit_score.schema.json
    stage4b_input_<id>.json          (no rank)       → correction_diff.schema.json

Filename patterns mirror the input-file names the orchestrator writes to
its `_work/` directory before invoking `codex_atom.sh`.

Run:
    .venv/bin/pytest tests/test_fixture_schema_parity.py -v

Or under standalone Python (no pytest dependency for the dispatcher):
    .venv/bin/python3 tests/test_fixture_schema_parity.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterator

import jsonschema

REPO = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO / "schemas"
CODEX_FIXTURES = REPO / "tests" / "fixtures" / "codex"


def _schema_for(name: str) -> Path | None:
    """Resolve which schema applies to a codex fixture by filename pattern.
    Returns None for unrecognized patterns — caller should treat that as a
    test failure (forces extending this function rather than silently
    skipping)."""
    if name == "stage2_input.json":
        return SCHEMAS_DIR / "citations.schema.json"
    if re.match(r"^stage3_input_\d+(?:_reverify)?\.json$", name):
        return SCHEMAS_DIR / "verdict.schema.json"
    if re.match(r"^stage4a_input_\d+\.json$", name):
        return SCHEMAS_DIR / "alternatives.schema.json"
    if re.match(r"^stage4b_input_\d+_\d+\.json$", name):  # rank suffix
        return SCHEMAS_DIR / "fit_score.schema.json"
    if re.match(r"^stage4b_input_\d+\.json$", name):  # no rank suffix
        return SCHEMAS_DIR / "correction_diff.schema.json"
    return None


def _iter_codex_fixtures() -> Iterator[tuple[str, Path]]:
    if not CODEX_FIXTURES.exists():
        return
    for case_dir in sorted(CODEX_FIXTURES.iterdir()):
        if not case_dir.is_dir():
            continue
        for fixture in sorted(case_dir.iterdir()):
            if fixture.suffix == ".json":
                yield case_dir.name, fixture


def _validate_fixture(case: str, fixture: Path) -> None:
    schema_path = _schema_for(fixture.name)
    if schema_path is None:
        raise AssertionError(
            f"unrecognized codex fixture filename: {fixture}\n"
            f"Extend _schema_for() in tests/test_fixture_schema_parity.py with the "
            f"new pattern → schema mapping."
        )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    instance = json.loads(fixture.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as e:
        raise AssertionError(
            f"\nfixture {case}/{fixture.name} failed {schema_path.name} validation:\n"
            f"  path: {list(e.absolute_path)}\n"
            f"  error: {e.message}"
        ) from None


# pytest discovery — parametrized so each fixture is a distinct test id
try:
    import pytest
except ImportError:
    pytest = None  # type: ignore[assignment]

if pytest is not None:
    @pytest.mark.parametrize(
        "case,fixture",
        [
            pytest.param(case, fix, id=f"{case}/{fix.name}")
            for case, fix in _iter_codex_fixtures()
        ],
    )
    def test_codex_fixture_validates_against_schema(case: str, fixture: Path) -> None:
        _validate_fixture(case, fixture)


if __name__ == "__main__":
    n = 0
    for case, fixture in _iter_codex_fixtures():
        _validate_fixture(case, fixture)
        n += 1
    print(f"PASS: {n} codex fixtures validate against their schemas.")
