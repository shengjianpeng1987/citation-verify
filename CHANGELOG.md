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
- Phase 2 snapshot harness:
  - `tests/_runner.py` — capture/replay subprocess interceptor for `api_verify.py` and `codex_atom.sh`. Fixture paths keyed by citation id (api) or input file basename (codex). `normalize_meta()` handles `generated_at` and `codex_model` for diffable snapshots.
  - `tests/_record_fixtures.py` — one-shot CLI to run the orchestrator in record mode and persist the snapshot baseline.
  - `tests/conftest.py` — pytest `replay_subprocess(case)` fixture mounting the replay-mode interceptor on `orchestrate.subprocess.run`.
  - `tests/test_runner_unit.py` — 6 unit tests locking fixture-path resolution and meta-normalization behaviour.
  - `tests/test_pipeline_snapshots.py` — full-pipeline replay tests for both cases (nasal_methylation, eif4enif1). Run in <1 s with no network. Skip if input docx is absent locally.
  - `tests/fixtures/api/<case>/citation_<id>.json` — recorded Channel A outputs (10 nasal + 20 EIF4ENIF1).
  - `tests/fixtures/codex/<case>/<input_basename>.json` — recorded Codex atomic outputs (15 nasal + 26 EIF4ENIF1).
  - `tests/snapshots/<case>/{corrections,verdicts,replacements}.json` — meta-normalized baseline outputs.
- CI workflows: `.github/workflows/tests.yml` runs `pytest tests/` on Python 3.10 / 3.11 / 3.12 with coverage measurement (`pytest-cov`, threshold currently `--cov-fail-under=0` to establish a baseline). `.github/workflows/lint.yml` runs `ruff` and `mypy` non-blocking (PLAN Phase 2 phrasing).

### Changed
- **Layout migration: `scripts/` → `src/citation_verify/`.** Phase 0's canonical-import-path lock is now reality. Six files moved under git-mv (history preserved): `orchestrate.py`, `api_verify.py`, `parse_doc.py`, `render_report.py`, `_parse_codex_events.py`, `codex_atom.sh`. New `src/citation_verify/__init__.py`. `orchestrate.py` path constants renamed (`SCRIPT_DIR` → `PACKAGE_DIR`, `SKILL_ROOT` → `REPO_ROOT`) and `REPO_ROOT` walks one extra level up. `verify.sh`, `pyproject.toml` `[tool.setuptools.packages.find]`, conftest's `sys.path`, the recorder, and the package-style imports in `test_review_override.py` / `test_pipeline_snapshots.py` all updated to match. SKILL.md path mentions follow. Snapshot tests are byte-identical pre/post migration (output is independent of source-file location), confirming this was a pure mechanical refactor.

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
