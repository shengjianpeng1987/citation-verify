#!/usr/bin/env python3
"""Shape-drift guard for the field_diff_entry definition.

`field_diff_entry` lives in two schemas because the project deliberately
avoids cross-file `$ref` (codex `--output-schema` loads a single file at a
time):

  - schemas/corrections.schema.json#/$defs/field_diff_entry
      (canonical — bound on the full corrections.json output)
  - schemas/correction_diff.schema.json
      properties.field_diff.items (inline copy — what one Codex
      build_correction call must emit)

If those two shapes drift apart, Codex's atomic output can validate
against correction_diff.schema.json yet fail when wrapped into the full
corrections.json by orchestrate.py. This test catches that the moment it
happens.

Run standalone:
    .venv/bin/python3 tests/test_schema_shape_drift.py

Or under pytest (Phase 2+):
    .venv/bin/pytest tests/test_schema_shape_drift.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORRECTIONS_SCHEMA = REPO / "schemas" / "corrections.schema.json"
CORRECTION_DIFF_SCHEMA = REPO / "schemas" / "correction_diff.schema.json"


def test_field_diff_entry_shape_drift() -> None:
    canonical = json.loads(CORRECTIONS_SCHEMA.read_text(encoding="utf-8"))
    diff_owner = json.loads(CORRECTION_DIFF_SCHEMA.read_text(encoding="utf-8"))

    canonical_shape = canonical["$defs"]["field_diff_entry"]
    inline_shape = diff_owner["properties"]["field_diff"]["items"]

    assert inline_shape == canonical_shape, (
        "field_diff_entry shape drifted between schemas.\n\n"
        f"corrections.schema.json#/$defs/field_diff_entry:\n"
        f"{json.dumps(canonical_shape, indent=2, sort_keys=True)}\n\n"
        f"correction_diff.schema.json properties.field_diff.items:\n"
        f"{json.dumps(inline_shape, indent=2, sort_keys=True)}\n\n"
        "Either restore parity or, if the divergence is intentional, update "
        "this test with the new equivalence rule (and document why)."
    )


if __name__ == "__main__":
    test_field_diff_entry_shape_drift()
    print("PASS: field_diff_entry shape parity verified.")
