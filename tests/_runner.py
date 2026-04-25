"""Capture/replay infrastructure for Phase 2 snapshot tests.

The orchestrator drives every Channel A and Codex call via subprocess.run.
For deterministic, no-network tests we intercept those subprocess.run
invocations and route them through fixture files under tests/fixtures/.

Two modes:

- **record**: pass through to real subprocess.run, then save the stdout
  of api_verify.py / codex_atom.sh calls to a fixture file. Other
  subprocess calls (parse_doc.py, render_report.py) pass through
  untouched and are not captured (deterministic given inputs).

- **replay**: do NOT call real subprocess for api_verify.py /
  codex_atom.sh. Instead, look up the fixture for the call and return
  a CompletedProcess with that content as stdout. Missing fixture →
  loud FileNotFoundError so the test fails informatively.

Fixture naming:

- api_verify.py invocations are keyed by the citation_id parsed out of
  the `--citation-json` argv value. Path:
  `tests/fixtures/api/<case>/citation_<id>.json`.

- codex_atom.sh invocations are keyed by the basename of the input
  JSON file. Path:
  `tests/fixtures/codex/<case>/<input_basename>.json`.

This module is imported by `conftest.py` (pytest fixtures) and
`_record_fixtures.py` (CLI driver). It does not import pytest itself,
so it can be exercised standalone.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, Literal

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SNAPSHOTS_DIR = TESTS_DIR / "snapshots"

Mode = Literal["record", "replay"]


# --- fixture path resolution ---

def api_fixture_path(case: str, citation_json: str) -> Path:
    """Resolve the fixture path for one api_verify.py invocation."""
    try:
        cit = json.loads(citation_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"api_verify.py was passed un-parseable --citation-json: {e}")
    cid = cit.get("id")
    if not isinstance(cid, int):
        raise RuntimeError(f"api_verify.py citation has no integer id: {cit}")
    return FIXTURES_DIR / "api" / case / f"citation_{cid}.json"


def codex_fixture_path(case: str, input_file: Path) -> Path:
    """Resolve the fixture path for one codex_atom.sh invocation."""
    return FIXTURES_DIR / "codex" / case / input_file.name


# --- subprocess interceptor ---

def make_subprocess_run(case: str, mode: Mode) -> Callable:
    """Return a callable that replaces orchestrate.subprocess.run.

    `case` namespaces the fixtures (e.g. 'nasal_methylation', 'eif4enif1').
    `mode` is 'record' (passthrough + save) or 'replay' (fixture-only).
    """
    real_run = subprocess.run

    def _run(cmd, *args, **kwargs):
        cmd_list = list(cmd) if isinstance(cmd, (list, tuple)) else [cmd]
        cmd_str = " ".join(str(c) for c in cmd_list)

        if "api_verify.py" in cmd_str:
            return _handle_api_verify(cmd_list, kwargs, case, mode, real_run)
        if "codex_atom.sh" in cmd_str:
            return _handle_codex_atom(cmd_list, kwargs, case, mode, real_run)
        return real_run(cmd, *args, **kwargs)

    return _run


def _handle_api_verify(cmd_list, kwargs, case, mode, real_run):
    try:
        idx = cmd_list.index("--citation-json")
    except ValueError:
        raise RuntimeError(
            "api_verify.py invocation missing --citation-json; the runner only "
            "supports the orchestrator's standard call shape."
        )
    citation_json = cmd_list[idx + 1]
    fixture = api_fixture_path(case, citation_json)

    if mode == "replay":
        if not fixture.exists():
            raise FileNotFoundError(
                f"missing api fixture: {fixture}. "
                f"Run `python3 tests/_record_fixtures.py --case {case} ...` first."
            )
        return subprocess.CompletedProcess(
            args=cmd_list,
            returncode=0,
            stdout=fixture.read_text(encoding="utf-8"),
            stderr="",
        )

    # record mode: real call, save stdout, return as-is
    result = real_run(cmd_list, **kwargs)
    if result.returncode == 0 and result.stdout:
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(result.stdout, encoding="utf-8")
    return result


def _handle_codex_atom(cmd_list, kwargs, case, mode, real_run):
    if len(cmd_list) < 4:
        raise RuntimeError(
            f"codex_atom.sh invocation has too few arguments: {cmd_list}"
        )
    input_file = Path(cmd_list[3])
    fixture = codex_fixture_path(case, input_file)

    if mode == "replay":
        if not fixture.exists():
            raise FileNotFoundError(
                f"missing codex fixture: {fixture}. "
                f"Run `python3 tests/_record_fixtures.py --case {case} ...` first."
            )
        return subprocess.CompletedProcess(
            args=cmd_list,
            returncode=0,
            stdout=fixture.read_text(encoding="utf-8"),
            stderr="",
        )

    result = real_run(cmd_list, **kwargs)
    if result.returncode == 0 and result.stdout:
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(result.stdout, encoding="utf-8")
    return result


# --- meta normalization (used by replay tests when diffing snapshots) ---

NORMALIZED_GENERATED_AT = "1970-01-01T00:00:00Z"
NORMALIZED_CODEX_MODEL = "<recorded-model>"


def normalize_meta(corrections_obj: dict) -> dict:
    """Return a deep-copy of `corrections_obj` with volatile meta fields
    replaced by stable placeholders. `generated_at` and `codex_model` are
    the only volatile fields — sha256, filename, schema_version, and
    api_sources_enabled all stay strict so a real drift surfaces."""
    out = json.loads(json.dumps(corrections_obj))
    meta = out.get("meta", {})
    if "generated_at" in meta:
        meta["generated_at"] = NORMALIZED_GENERATED_AT
    if "codex_model" in meta:
        meta["codex_model"] = NORMALIZED_CODEX_MODEL
    return out
