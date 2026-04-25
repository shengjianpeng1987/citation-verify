"""pytest fixtures wiring the snapshot replay runner into orchestrate.subprocess.

Used by tests that exercise the full pipeline against pre-recorded fixtures.
The standalone test files (test_skill_doc_parity, test_schema_shape_drift,
test_review_override) do not depend on these fixtures.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(TESTS_DIR))

from _runner import make_subprocess_run  # noqa: E402


@pytest.fixture
def replay_subprocess(monkeypatch):
    """Return a function that, when called with a case name, monkey-patches
    `citation_verify.orchestrate.subprocess.run` to route api_verify.py /
    codex_atom.sh invocations through pre-recorded fixtures under
    tests/fixtures/<case>/.

    Also patches `_is_codex_available` to return True. Reason: on a host
    where the `codex` CLI is not on PATH (every CI runner — Codex CLI is
    not pip-installable), orchestrate.py would normally short-circuit to
    a regex-based fallback parser in Stage 2 and to `verdict="skipped"`
    in Stage 3, which produces completely different cit dicts and verdicts
    than the hand-crafted / recorded fixtures encode. Replay mode
    explicitly mocks every subprocess call that *would* have invoked
    codex, so the binary's absence is irrelevant to test correctness —
    we just need the orchestrator to *believe* codex is available so it
    dispatches down the codex path.

    Usage in a test:
        def test_foo(replay_subprocess):
            replay_subprocess("nasal_methylation")
            from citation_verify import orchestrate
            # ... call orchestrate.main(); subprocess.run is now intercepted
    """
    from citation_verify import orchestrate  # local import: src/ on sys.path

    def _activate(case: str) -> None:
        monkeypatch.setattr(orchestrate.subprocess, "run", make_subprocess_run(case, "replay"))
        monkeypatch.setattr(orchestrate, "_is_codex_available", lambda: True)

    return _activate
