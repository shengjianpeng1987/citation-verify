#!/usr/bin/env python3
"""Phase 2 fixture recorder.

One-shot script that runs the orchestrator on a real input docx with the
capture/replay runner in `record` mode. Saves api_verify.py and
codex_atom.sh outputs to `tests/fixtures/{api,codex}/<case>/`.
Optionally also persists the run's `corrections.json`, `verdicts.json`,
and `replacements.json` into `tests/snapshots/<case>/` (with meta
fields normalized) for the snapshot test to diff against.

Usage:
    python3 tests/_record_fixtures.py \\
        --case nasal_methylation \\
        --input "/Users/.../过敏性鼻炎甲基化技术选型.docx" \\
        --persist-snapshot

Quota note: this DOES make real Codex + Crossref/OpenAlex/S2 calls. Run
once per case, then commit the fixtures.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(TESTS_DIR))

from citation_verify import orchestrate  # noqa: E402  (path setup must precede import)
from _runner import (  # noqa: E402
    SNAPSHOTS_DIR,
    make_subprocess_run,
    normalize_meta,
)


def _persist_snapshot(case: str, out_dir: Path) -> None:
    snap = SNAPSHOTS_DIR / case
    snap.mkdir(parents=True, exist_ok=True)
    for name in ("corrections.json", "verdicts.json", "replacements.json"):
        src = out_dir / name
        if not src.exists():
            sys.stderr.write(f"  skip {name} (not produced)\n")
            continue
        data = json.loads(src.read_text(encoding="utf-8"))
        if name == "corrections.json":
            data = normalize_meta(data)
        (snap / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        sys.stderr.write(f"  snapshot: {snap / name}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True,
                    help="Case namespace under tests/fixtures/ and tests/snapshots/")
    ap.add_argument("--input", required=True, help="Path to input .docx")
    ap.add_argument("--output-dir", default=None,
                    help="Where the orchestrator writes (default: tempdir)")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--persist-snapshot", action="store_true",
                    help="Also save corrections.json / verdicts.json / replacements.json "
                         "into tests/snapshots/<case>/ with meta normalized.")
    args = ap.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else Path(tempfile.mkdtemp(prefix=f"record-{args.case}-"))
    out_dir.mkdir(parents=True, exist_ok=True)

    sys.stderr.write(f"[record] case={args.case}  input={args.input}  out={out_dir}\n")

    runner = make_subprocess_run(args.case, mode="record")
    saved_argv = sys.argv[:]
    try:
        sys.argv = [
            "orchestrate.py", args.input,
            "--output-dir", str(out_dir),
            "--parallel", str(args.parallel),
        ]
        with mock.patch.object(orchestrate.subprocess, "run", runner):
            rc = orchestrate.main()
    finally:
        sys.argv = saved_argv

    if rc != 0:
        sys.stderr.write(f"[record] orchestrator returned non-zero ({rc}) — fixtures may be partial\n")
        return rc

    if args.persist_snapshot:
        sys.stderr.write(f"[record] persisting snapshot into tests/snapshots/{args.case}/\n")
        _persist_snapshot(args.case, out_dir)

    sys.stderr.write(f"[record] done. Fixtures under tests/fixtures/{{api,codex}}/{args.case}/\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
