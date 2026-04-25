#!/usr/bin/env python3
"""Doc-vs-code drift guard for SKILL.md.

Mechanically scans SKILL.md for every CLI flag (`--xxx`) and every filename
in the `Output layout` fenced block, then asserts each one is implemented
somewhere a user can reach (orchestrate.py argparse for flags; orchestrate.py
file emissions for outputs).

Designed as a v1.0.0 release gate: if SKILL.md grows a new flag or output
file that the code does not emit, this test goes red.

Direction: SKILL.md → code. The reverse direction (code accepts a flag or
emits a file not yet documented) is allowed by this test — that is a
documentation TODO, not a broken promise to users.

Run standalone:
    .venv/bin/python3 tests/test_skill_doc_parity.py

Or under pytest (Phase 2+):
    .venv/bin/pytest tests/test_skill_doc_parity.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_MD = REPO / "SKILL.md"
ORCHESTRATE = REPO / "scripts" / "orchestrate.py"

CODEX_PASSTHROUGH_FLAGS = {
    "--ephemeral",
    "--json",
    "--output-schema",
    "--sandbox",
    "--skip-git-repo-check",
    "--model",
    "--version",
}

_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]+)")
_OUTPUT_BLOCK_RE = re.compile(r"```\s*\n<output-dir>/\n(.+?)```", re.S)
_TREE_LINE_RE = re.compile(r"[│├└─\s]+([\w<>.-]+\.\w+)\b")
_ARGPARSE_RE = re.compile(r'add_argument\(\s*"(--[a-z][a-z0-9-]+)"')
_EMIT_RE = re.compile(r'(?:out_dir|work_dir)\s*/\s*"([\w.-]+\.\w+)"')


def _flags_in_skill_md() -> set[str]:
    return set(_FLAG_RE.findall(SKILL_MD.read_text(encoding="utf-8")))


def _flags_in_orchestrator_argparse() -> set[str]:
    return set(_ARGPARSE_RE.findall(ORCHESTRATE.read_text(encoding="utf-8")))


def _output_files_in_skill_md() -> set[str]:
    m = _OUTPUT_BLOCK_RE.search(SKILL_MD.read_text(encoding="utf-8"))
    if not m:
        return set()
    files: set[str] = set()
    for line in m.group(1).splitlines():
        fn = _TREE_LINE_RE.match(line)
        if fn:
            files.add(fn.group(1))
    return {f for f in files if not (f.startswith("<") and ">" in f)}


def _output_files_emitted_by_orchestrator() -> set[str]:
    return set(_EMIT_RE.findall(ORCHESTRATE.read_text(encoding="utf-8")))


def test_skill_md_flags_are_implemented() -> None:
    skill = _flags_in_skill_md()
    orch = _flags_in_orchestrator_argparse()
    user_facing = skill - CODEX_PASSTHROUGH_FLAGS
    missing = user_facing - orch
    assert not missing, (
        f"SKILL.md mentions user-facing flags not in orchestrate.py argparse: "
        f"{sorted(missing)}. Either implement the flag, remove it from SKILL.md, "
        f"or — if the flag documents an external CLI — add it to "
        f"CODEX_PASSTHROUGH_FLAGS in {Path(__file__).name}."
    )


def test_skill_md_output_files_are_emitted() -> None:
    skill = _output_files_in_skill_md()
    emitted = _output_files_emitted_by_orchestrator()
    missing = skill - emitted
    assert not missing, (
        f"SKILL.md Output layout claims files not written by orchestrate.py: "
        f"{sorted(missing)}. Either implement the emission or remove from SKILL.md."
    )


if __name__ == "__main__":
    test_skill_md_flags_are_implemented()
    test_skill_md_output_files_are_emitted()
    print("PASS: SKILL.md ↔ code parity verified.")
