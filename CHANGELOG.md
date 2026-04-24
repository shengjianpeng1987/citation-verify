# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Stage 4b: `corrections.json` output separating `corrections[]` / `replacements[]` / `unresolvable[]`.
- `schemas/corrections.schema.json` with required top-level `meta` block (schema_version, orchestrator_version, generated_at, input_doc_sha256, input_doc_filename, codex_model, api_sources_enabled).
- SKILL.md invariants #6 (`canonical_record.source` must be from Channel A: crossref / openalex / semantic_scholar — never `channel_b_web`) and #7 (Stage 4b consumes Stage 3 verdict buckets without re-classifying).
- `PLAN.md` — development and JOSS publication plan.
- Apache-2.0 `LICENSE` and `NOTICE`.
- `pyproject.toml` skeleton; `VERSION` file.

### Changed
- Vancouver-format citation parser added to fallback path; junk-title guard (`_title_looks_usable`) prevents empty/punctuation-leading/<3-word titles from becoming API search queries.

## [0.1.0] — Unreleased

Initial pre-release. Not yet published; no git tag.

[Unreleased]: https://github.com/shengjianpeng1987/citation-verify/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/shengjianpeng1987/citation-verify/releases/tag/v0.1.0
