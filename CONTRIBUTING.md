# Contributing to citation-verify

Thanks for your interest. The project is single-author (Sheng Jianpeng, NUAA) through the JOSS 2026 submission cycle. Issue reports are welcome at any time; pull requests will be reviewed once the JOSS review issue has opened, after which the contribution model becomes standard fork-and-PR.

## Development setup

Requires Python 3.10+ and (for live runs) the [Codex CLI](https://developers.openai.com/codex/cli) installed and authenticated.

```sh
git clone https://github.com/shengjianpeng1987/citation-verify
cd citation-verify
python3 -m venv .venv
source .venv/bin/activate    # or: .venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install -e ".[test,dev]"
```

After this, `pytest tests/` runs the full local suite (under one second on a clean machine). The orchestrator pipeline only works end-to-end if `codex` is on `PATH`; without it, the snapshot harness still runs because every Codex subprocess is mocked, but new documents cannot be verified.

## Running tests

```sh
.venv/bin/pytest tests/
.venv/bin/pytest tests/ --cov=src/citation_verify --cov-report=term   # with coverage
```

The suite has three layers:

| Layer | Tests | What goes red |
|---|---|---|
| Release-gate guards | `test_skill_doc_parity`, `test_schema_shape_drift`, `test_fixture_schema_parity`, `test_review_override`, `test_runner_unit` | Doc-vs-code drift, schema drift, fixture-vs-schema drift, deterministic-rule drift, fixture-path infrastructure regressions |
| Snapshot tests, synthetic | `test_pipeline_snapshot[synthetic_happy]`, `test_pipeline_snapshot[synthetic_mixed]` | Orchestrator's bucket / correction / replacement logic |
| Snapshot tests, real-research | `test_pipeline_snapshot[nasal_methylation]`, `test_pipeline_snapshot[eif4enif1]` | Real Codex/API behaviour against real research documents (skipped when input docx files are not present locally — they are not committed) |

CI runs the first two layers on Python 3.10 / 3.11 / 3.12. The third layer is local-only sanity. See `tests/fixtures/README.md` for the architectural distinction between the recorded and hand-crafted fixture corpora.

## Schema-change bumping rules

Per PLAN.md Execution rule 4, `schemas/corrections.schema.json` carries a `schema_version` string in its top-level description, and every `corrections.json` instance carries a matching `meta.schema_version`.

| Change | Bump |
|---|---|
| Clarification, comment-only, description edits | patch (`0.2.0` → `0.2.1`) |
| Additive non-breaking field (optional, not in `required`) | minor (`0.2.0` → `0.3.0`) |
| Removed field, type tightened, required-list expanded, or enum value removed | **major** (`0.2.0` → `1.0.0`) |

Pre-`1.0.0` the major-bump rule still applies but does not trigger the user-gated release tag.

After bumping the schema, in the **same commit**:

1. Update the `SCHEMA_VERSION` constant in `src/citation_verify/orchestrate.py`.
2. Update `tests/_build_synthetic_mixed_fixtures.py` if the bump cascades into hand-crafted fixtures.
3. Re-run `python3 tests/_build_synthetic_mixed_fixtures.py` and the synthetic-mixed snapshot replay to refresh baselines (see `tests/fixtures/README.md` for the procedure).
4. Verify `tests/test_schema_shape_drift.py` and `tests/test_fixture_schema_parity.py` are still green.
5. Add a `### Changed` entry to `CHANGELOG.md` `[Unreleased]` documenting the bump and what consumers must do to migrate.

## PR checklist

Before opening a PR:

- [ ] `.venv/bin/pytest tests/` passes locally.
- [ ] If SKILL.md gained a flag or output filename, `tests/test_skill_doc_parity.py` is green (the test scans SKILL.md and asserts implementation parity).
- [ ] If a schema changed, the bumping rules above were followed.
- [ ] `CHANGELOG.md` `[Unreleased]` has an entry for this PR.
- [ ] If the change adds or modifies a release-gate guard test, the test's docstring explains what drift it catches and how to update it intentionally.

## Adding a new fixture or case

The repository has two fixture corpora with different authorities. **Read `tests/fixtures/README.md` before adding either.** TL;DR:

- Real-research case (private docx): use `tests/_record_fixtures.py` to capture from a live Codex/API run. Costs Codex quota.
- Synthetic case (committed docx): hand-craft fixtures in a builder script à la `tests/_build_synthetic_mixed_fixtures.py`. Validate via `tests/test_fixture_schema_parity.py`. No Codex involved.

Then parametrize the new case into `tests/test_pipeline_snapshots.py`.

## AI usage in commits

This project is built with AI assistants in the loop (Claude Code / Cowork). Commits authored with AI assistance carry a `Co-Authored-By: Claude ...` trailer. Maintaining the trailer is part of the JOSS 2026 AI-disclosure norm — please preserve it when amending or rebasing AI-assisted work, and add a comparable trailer for any other AI tools that contributed substantively (model, version, role).

## Reporting bugs / requesting features

Open an issue at https://github.com/shengjianpeng1987/citation-verify/issues. For verification bugs include:

1. The input document (or a reduced reproduction).
2. The produced `corrections.json`, `verdicts.json`, and `report.md`.
3. The orchestrator's stderr log.
4. `codex --version` and the contents of `requirements.txt` lock state (e.g., `pip freeze | grep -E '(pdfplumber|python-docx|requests|rapidfuzz|jsonschema)'`).
