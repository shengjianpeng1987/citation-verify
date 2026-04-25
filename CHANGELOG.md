# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Stage 4b: `corrections.json` output separating `corrections[]` / `replacements[]` / `unresolvable[]`.
- `schemas/corrections.schema.json` with required top-level `meta` block (schema_version, orchestrator_version, generated_at, input_doc_sha256, input_doc_filename, codex_model, api_sources_enabled, **valid_citation_ids** as of 0.2.0).
- SKILL.md invariants #6 (`canonical_record.source` must be from Channel A: crossref / openalex / semantic_scholar — never `channel_b_web`) and #7 (Stage 4b consumes Stage 3 verdict buckets without re-classifying).
- `PLAN.md` — development and JOSS publication plan.
- Apache-2.0 `LICENSE` and `NOTICE`.
- `pyproject.toml` skeleton; `VERSION` file.
- `tests/test_skill_doc_parity.py` — release gate: scans SKILL.md for `--xxx` flags and Output-layout files, asserts each resolves to an argparse `add_argument` or an emitted file.

### Changed
- Vancouver-format citation parser added to fallback path; junk-title guard (`_title_looks_usable`) prevents empty/punctuation-leading/<3-word titles from becoming API search queries.

## [0.2.0] — 2026-04-25

Phase 2 prep trilogy. Bumps `orchestrator_version` from 0.1.0 to 0.2.0 to match the schema bump in `corrections.schema.json`. No git tag yet — versioning here precedes the user-gated `v1.0.0` release.

### Added
- `tests/test_schema_shape_drift.py` — release gate: asserts `field_diff_entry` shape parity between `corrections.schema.json#/$defs` and the inline copy in `correction_diff.schema.json`. First run caught a real description-only drift (fixed in the same commit).
- `tests/test_review_override.py` — locks the deterministic backstop on `requires_human_review`: any `high`-severity diff in `{title, doi, year}` forces `True` regardless of Codex's per-call judgment.

### Changed
- **BREAKING (schema 0.1.0 → 0.2.0):** `corrections.schema.json` requires `meta.valid_citation_ids` (sorted unique array of citation IDs whose Stage 3 verdict was `valid`). Pre-0.2.0 instances without this field will now fail validation. Lets a corrections.json reader enumerate silent-valid citations without cross-referencing verdicts.json.
- `step4b_build_corrections` now ORs Codex's `requires_human_review` with a deterministic backstop (`_has_critical_high_diff`): any `high`-severity diff in `{title, doi, year}` flips the flag to `True` even if Codex returned `False`. Codex still drives the soft cases (multi-paper ambiguity, domain-sensitivity); this is purely a stricter floor to prevent a future model change from quietly under-flagging citation-integrity-critical drifts.
- `api_verify.py` now surfaces three new diagnostic fields on every Channel A verdict: `title_similarity_raw`, `author_overlap_raw`, and `doi_exact_match`. The post-DOI-override values (`title_similarity`, `author_overlap`) remain the inputs to verdict classification and confidence scoring; raw values are advisory and audit-friendly. Phase 2 review of the EIF4ENIF1 case showed all 5 partials reporting overlap=0.95 while raw values were 0.0–0.4 — surfaced now to make the asymmetry visible without changing verdict semantics.

## [0.1.0] — Unreleased

Initial pre-release. Not yet published; no git tag.

[Unreleased]: https://github.com/shengjianpeng1987/citation-verify/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/shengjianpeng1987/citation-verify/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/shengjianpeng1987/citation-verify/releases/tag/v0.1.0
