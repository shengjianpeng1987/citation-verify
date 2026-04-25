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
- `api_verify.py` now surfaces three new diagnostic fields on every Channel A verdict: `title_similarity_raw`, `author_overlap_raw`, and `doi_exact_match`. The post-DOI-override values (`title_similarity`, `author_overlap`) remain the inputs to verdict classification and confidence scoring; raw values are advisory and audit-friendly. Phase 2 review of the EIF4ENIF1 case showed all 5 partials reporting overlap=0.95 while raw values were 0.0–0.4 — surfaced now to make the asymmetry visible without changing verdict semantics.

## [0.1.0] — Unreleased

Initial pre-release. Not yet published; no git tag.

[Unreleased]: https://github.com/shengjianpeng1987/citation-verify/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/shengjianpeng1987/citation-verify/releases/tag/v0.1.0
