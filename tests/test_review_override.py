#!/usr/bin/env python3
"""Unit tests for the deterministic requires_human_review backstop.

Codex's build_correction prompt already aims to set requires_human_review=True
on any high-severity diff. The orchestrator wraps Codex's output with a stricter
hard rule: high-severity in {title, doi, year} forces True regardless. These
tests lock the rule's edges so a future prompt or model change cannot quietly
weaken it.

Run standalone:
    .venv/bin/python3 tests/test_review_override.py

Or under pytest (Phase 2+):
    .venv/bin/pytest tests/test_review_override.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from orchestrate import CRITICAL_REVIEW_FIELDS, _has_critical_high_diff


def _diff(field: str, severity: str) -> dict:
    return {"field": field, "original": "X", "corrected": "Y", "severity": severity}


def test_critical_review_fields_locked() -> None:
    """The set is the contract; widening or narrowing it is a deliberate decision
    that should fail this test until the test is updated."""
    assert CRITICAL_REVIEW_FIELDS == frozenset({"title", "doi", "year"}), (
        f"CRITICAL_REVIEW_FIELDS changed to {CRITICAL_REVIEW_FIELDS}. "
        "If intentional, update this test and document the rationale in CHANGELOG."
    )


def test_high_in_each_critical_field_triggers() -> None:
    for field in ("title", "doi", "year"):
        assert _has_critical_high_diff([_diff(field, "high")]), field


def test_high_in_non_critical_field_does_not_trigger() -> None:
    for field in ("authors", "venue", "volume", "issue", "page"):
        assert not _has_critical_high_diff([_diff(field, "high")]), field


def test_medium_and_low_in_critical_field_do_not_trigger() -> None:
    for field in ("title", "doi", "year"):
        for severity in ("medium", "low"):
            assert not _has_critical_high_diff([_diff(field, severity)]), (field, severity)


def test_mixed_diff_with_one_critical_high_triggers() -> None:
    diffs = [
        _diff("venue", "high"),
        _diff("authors", "high"),
        _diff("title", "high"),
    ]
    assert _has_critical_high_diff(diffs)


def test_empty_diff_does_not_trigger() -> None:
    assert not _has_critical_high_diff([])
    assert not _has_critical_high_diff(None)


def test_malformed_entry_does_not_crash() -> None:
    # Defensive: an entry missing field or severity should not raise — it just
    # doesn't trigger. Lets the function survive partial Codex output without
    # blocking the whole pipeline.
    assert not _has_critical_high_diff([{"severity": "high"}])
    assert not _has_critical_high_diff([{"field": "title"}])
    assert not _has_critical_high_diff([{}])


if __name__ == "__main__":
    test_critical_review_fields_locked()
    test_high_in_each_critical_field_triggers()
    test_high_in_non_critical_field_does_not_trigger()
    test_medium_and_low_in_critical_field_do_not_trigger()
    test_mixed_diff_with_one_critical_high_triggers()
    test_empty_diff_does_not_trigger()
    test_malformed_entry_does_not_crash()
    print("PASS: all 7 review-override cases.")
