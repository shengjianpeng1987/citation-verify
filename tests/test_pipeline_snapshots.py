#!/usr/bin/env python3
"""Phase 2 snapshot replay tests.

For each recorded case, run the full orchestrator with `subprocess.run`
intercepted by `replay_subprocess` (no Channel A network calls, no Codex
calls), then assert byte-identity between the produced output files and
the snapshots committed under tests/snapshots/<case>/.

corrections.json undergoes meta normalization (generated_at,
codex_model) before diffing — see `_runner.normalize_meta`.
verdicts.json and replacements.json are diffed strictly: identical
fixtures + deterministic reconciliation must produce identical outputs.

These tests SKIP if the input docx is not on the local filesystem (the
docx files are not committed to the repo — they are real research
documents). On a contributor's machine without the originals, only the
unit-level guard tests (skill_doc_parity, schema_shape_drift,
review_override, runner_unit) run.

Run:
    .venv/bin/pytest tests/test_pipeline_snapshots.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# conftest.py has already inserted scripts/ and tests/ into sys.path.
from _runner import SNAPSHOTS_DIR, normalize_meta  # noqa: E402

CASES = [
    pytest.param(
        "nasal_methylation",
        "/Users/shengjianpeng/Documents/rrbs/过敏性鼻炎甲基化技术选型.docx",
        id="nasal_methylation",
    ),
    pytest.param(
        "eif4enif1",
        "/Users/shengjianpeng/Documents/citation verify/eif4enif1-phase2/EIF4ENIF1_LACE-seq_正式方案.docx",
        id="eif4enif1",
    ),
]


@pytest.mark.parametrize("case,input_path", CASES)
def test_pipeline_snapshot(case, input_path, replay_subprocess, tmp_path):
    if not Path(input_path).exists():
        pytest.skip(f"input docx not present: {input_path}")

    replay_subprocess(case)

    import orchestrate

    saved_argv = sys.argv[:]
    try:
        sys.argv = [
            "orchestrate.py", input_path,
            "--output-dir", str(tmp_path),
            "--parallel", "4",
        ]
        rc = orchestrate.main()
    finally:
        sys.argv = saved_argv

    assert rc == 0, f"orchestrator returned {rc}"

    snap_dir = SNAPSHOTS_DIR / case
    assert snap_dir.exists(), f"snapshot dir missing: {snap_dir}"

    for name in ("corrections.json", "verdicts.json", "replacements.json"):
        produced_path = tmp_path / name
        snap_path = snap_dir / name
        assert produced_path.exists(), f"orchestrator did not emit {name}"
        assert snap_path.exists(), f"snapshot missing: {snap_path}"

        produced = json.loads(produced_path.read_text(encoding="utf-8"))
        if name == "corrections.json":
            produced = normalize_meta(produced)
        expected = json.loads(snap_path.read_text(encoding="utf-8"))

        assert produced == expected, (
            f"\n{case}/{name} drifted from snapshot.\n"
            f"  snapshot: {snap_path}\n"
            f"  produced: {produced_path}\n"
            "If the change is intentional, re-record:\n"
            f"  .venv/bin/python3 tests/_record_fixtures.py --case {case} "
            f"--input {input_path!r} --persist-snapshot"
        )
