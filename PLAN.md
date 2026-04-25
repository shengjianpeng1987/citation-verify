# citation-verify — Development & Publication Plan

**Owner:** Sheng Jianpeng, Nanjing University of Aeronautics and Astronautics
**Collaborators:** Claude (Cowork / planning + review), Claude Code (implementation)
**Target venue:** Journal of Open Source Software (JOSS)
**Current phase:** Phase 1

---

## Execution rules (read first)

1. **Do not work ahead of the current phase.** Finish the current phase's exit criteria, report back, wait for sign-off, then advance. Seeing a later phase described here is not permission to start it.
2. **Git operations are delegated to Claude Code.** Commit, push to `main`, branch management — all yours. Single-author repo, no PR ceremony. **Three gates remain with the user** (because they are public and irreversible): (a) creating the `v1.0.0` release tag (triggers Zenodo DOI minting), (b) flipping the repo from private to public, (c) the JOSS submission itself. Do not perform those three without explicit user confirmation in chat.
3. **Do not modify locked decisions in Phase 0** without raising it back to the user.
4. **Schema changes** bump `schema_version` in `corrections.schema.json` per semver (patch = clarification, minor = additive non-breaking, major = breaking). `orchestrator_version` tracks the code producing the schema and is independent.
5. **When a design question arises mid-phase, stop and ask** rather than guessing. The 5-question pushback on Stage 4b schema is the model — that was the right behavior.

---

## Phase 0 — Locked decisions

These are fixed. Do not renegotiate without user sign-off.

- **Repo:** `github.com/shengjianpeng1987/citation-verify`. Private through Phase 4; flipped public at start of Phase 5.
- **License:** Apache-2.0. Root-level `LICENSE` (full text) + `NOTICE` (one-line copyright).
- **Python:** 3.10+.
- **Package layout:** `src/citation_verify/` as the canonical import path; `skill/` subdirectory holds `SKILL.md` + thin script wrappers that import from `src/`. There is one codebase, not two.
- **Author:** Sheng Jianpeng (NUAA). Single author on JOSS paper. AI contribution acknowledged in paper's Acknowledgements section; not listed as co-author (per JOSS policy).
- **Release model:** semver; `VERSION` file at repo root is source of truth; `CHANGELOG.md` in Keep-a-Changelog format.

---

## Phase 1 — Stage 4b finalization + repo skeleton

### Claude Code tasks
- Implement Stage 4b per the schema already drafted at `schemas/corrections.schema.json` and the conventions in `SKILL.md` invariants 6 and 7.
- Apply the 5 schema decisions from the pushback round:
  1. `canonical_record.year` and `canonical_record.venue` are nullable (`["string", "null"]` / `["integer", "null"]`) to accommodate Crossref preprints/datasets.
  2. `url` is intentionally absent from `field_diff_entry.field` enum (URL is derivative of DOI, not separately verifiable).
  3. `unresolvable.reason` stays free-form for now but **must start with a snake_case tag followed by `: `** (e.g. `"channel_b_only_no_a_match: Codex returned a candidate but no Channel A source confirmed it"`) to make later enum migration mechanical.
  4. `correction.requires_human_review` defaults to `false` when omitted; the 4b prompt should only set `true` when there is genuine risk (ambiguity, multiple plausible canonical records, domain-sensitive claims).
  5. Top-level `meta` block is **required** with fields:
     - `schema_version` (string, semver of corrections.schema.json)
     - `orchestrator_version` (string, read from `VERSION` file at runtime)
     - `generated_at` (string, ISO-8601 UTC)
     - `input_doc_sha256` (string, hex)
     - `input_doc_filename` (string, basename only, no path)
     - `codex_model` (string, actual model ID used)
     - `api_sources_enabled` (array of strings from `["crossref", "openalex", "semantic_scholar"]`)
- Ensure `canonical_record.source` enum contains only Channel A sources (`"crossref" | "openalex" | "semantic_scholar"`). Never `"channel_b_web"`.
- Do NOT modify the semantics of the existing four buckets (valid / partially_valid / uncertain / hallucinated) from Stage 3. Stage 4b consumes those buckets, it does not re-classify.

### Cowork/Claude tasks
- Write the skeleton files into the current skill directory as additions (not a restructure): `LICENSE` (Apache-2.0 full text), `NOTICE` (one-line copyright), `CHANGELOG.md` (empty stub in Keep-a-Changelog format), `VERSION` (`0.1.0`), `pyproject.toml` skeleton. These are plain file writes; no git operations from Cowork.

### Claude Code bootstrap tasks (runs first, before 4b work)
- If repo is not yet git-initialized: `git init`, set default branch to `main`, `git add` everything, initial commit.
- Create the private GitHub remote: `gh repo create shengjianpeng1987/citation-verify --private --source=. --remote=origin`. Confirm the repo name with the user once before running — we do not want to clobber an existing repo with that name.
- Push initial commit to `origin/main`.
- Private repo creation is authorized (reversible, not outward-facing). Do NOT run `gh repo edit --visibility public` — that's a user gate in Phase 5.
- All subsequent Phase 1 commits push to `main` directly. No feature branches.

### Target repo skeleton
```
citation-verify/
├── LICENSE
├── NOTICE
├── README.md                    (Phase 3)
├── CHANGELOG.md
├── CONTRIBUTING.md              (Phase 3)
├── CITATION.cff                 (Phase 3)
├── VERSION
├── PLAN.md                      (this file)
├── pyproject.toml
├── .github/workflows/           (Phase 2)
│   ├── tests.yml
│   └── lint.yml
├── src/citation_verify/
│   ├── __init__.py
│   ├── orchestrate.py
│   ├── api_verify.py
│   ├── codex_verify.py
│   ├── reconcile.py
│   ├── docx_patch.py
│   └── schemas/
│       └── corrections.schema.json
├── skill/
│   ├── SKILL.md
│   └── scripts/                 (thin wrappers → src/)
├── tests/                       (Phase 2)
│   ├── test_parser.py
│   ├── test_reconcile.py
│   ├── test_schema.py
│   ├── fixtures/
│   └── snapshots/
├── examples/
│   └── nasal_methylation/       (Phase 1 seed, expand Phase 2)
│       ├── README.md
│       ├── input.docx
│       ├── run.sh
│       └── expected_output/
└── paper/                       (Phase 4)
    ├── paper.md
    ├── paper.bib
    └── figures/
        ├── architecture.svg
        └── worked_example.svg
```

### Exit criteria
- Stage 4b runs end-to-end on the nasal methylation docx; outputs `corrections.json` that validates against `corrections.schema.json`; `meta` block fully populated.
- Repo skeleton exists on GitHub, private, with Phase 0 locked decisions reflected in `LICENSE`/`pyproject.toml`/`VERSION`.
- No commits or tags beyond what the user explicitly approves.

---

## Phase 2 — Second case + test suite

### Status
Prep complete: #1 raw Channel A scores (`d155f9b`), #3 schema 0.2.0 + `valid_citation_ids` + shape-drift guard (`202561d`), #2 `requires_human_review` backstop (`511fdf7`), VERSION + orchestrator_version bumped to 0.2.0 (`707527c`). Three release-gate tests green: `test_skill_doc_parity.py`, `test_schema_shape_drift.py`, `test_review_override.py`. Snapshot harness work pending — see `### Claude Code tasks`.

### Prerequisites (first harness pass)
Pre-0.2.0 outputs at `/tmp/phase2-e2e/` and `/Users/shengjianpeng/Documents/citation verify/eif4enif1-phase2/run-output-formal/` are 0.1.0 schema instances missing `meta.valid_citation_ids` — they will not validate against the current `corrections.schema.json` and must not be frozen as fixtures. Refresh both before recording snapshots:
- Re-run the nasal methylation case (`/Users/shengjianpeng/Documents/rrbs/过敏性鼻炎甲基化技术选型.docx`) through the current orchestrator.
- Re-run the EIF4ENIF1 case (`/Users/shengjianpeng/Documents/citation verify/eif4enif1-phase2/EIF4ENIF1_LACE-seq_正式方案.docx`) the same way.
- Persist refreshed outputs as the canonical baseline under `tests/snapshots/<case>/`. Do not freeze any prep-era artifact.

### Trigger
User provides the second validation document (English or Chinese; user selects). Cowork/Claude runs it through the pipeline, not Claude Code.

### Claude Code tasks
- Write integration tests consuming both cases (nasal methylation + the second case) as snapshot tests in `tests/`.
- Mock all outbound network calls: Crossref / OpenAlex / Semantic Scholar responses stored as JSON fixtures in `tests/fixtures/api/`; Codex responses stored as JSON fixtures in `tests/fixtures/codex/`.
- Add `.github/workflows/tests.yml` (pytest + coverage on push/PR) and `.github/workflows/lint.yml` (ruff + mypy, non-blocking initially).
- Coverage target: `src/citation_verify/parser.py`, `src/citation_verify/reconcile.py`, schema validation paths — each >70%.

### Exit criteria
- `pytest tests/` passes locally in under 3 seconds (no network).
- CI green on the push of Phase 2 work.
- Both cases' snapshot outputs committed; subsequent schema or logic changes that alter outputs must be accompanied by deliberate snapshot updates in the same PR.

---

## Phase 3 — Documentation

### Cowork/Claude tasks
- Write `README.md`. Structure:
  - One-sentence pitch + badges placeholder
  - **Why** (3–4 sentences: LLM-assisted writing → citation hallucination risk → gap in existing tools)
  - **Install** (pip, from source)
  - **Quickstart** (single command that runs `examples/nasal_methylation/`)
  - **How it works** (4 paragraphs: parse / dual-channel / reconcile / Stage 4b)
  - **Citation** (JOSS + Zenodo DOI, filled in Phase 5)
  - **Contributing** (pointer to `CONTRIBUTING.md`)
  - **License**
- `README.md` is distinct from `SKILL.md`. SKILL.md is the Claude-agent operator manual; README.md is the human developer + JOSS reviewer entrypoint. Do not merge them.

### Claude Code tasks
- Write `CONTRIBUTING.md`: dev setup, how to run tests, schema-change bumping rules, PR checklist (tests pass, schema changes documented, CHANGELOG entry added).
- Write `CITATION.cff` in CFF 1.2 format. Fields: `authors` (Sheng Jianpeng, NUAA), `title`, `version` (from VERSION), `license` (Apache-2.0), `repository-code`, `type: software`.
- Fill out `pyproject.toml`: classifiers (`Development Status`, `Intended Audience :: Science/Research`, `License :: OSI Approved :: Apache Software License`, `Topic :: Scientific/Engineering`), keywords (`citations`, `hallucination`, `verification`, `bibliography`, `LLM`), optional extras (`[test]`, `[dev]`).
- `docx_patch.py` — deferred from Phase 1 (formerly an unimplemented `--apply-replacements` promise in SKILL.md). Acceptance:
  - (a) At least 1 Phase 3 case has non-empty `replacements[]` with a `confirmed_replacement` landing as `canonical_record`.
  - (b) Implementation consumes `replacements[]` only; never touches `corrections[]` (field_diff requires human review).
  - (c) `--apply-replacements` flag wired into `argparse` + `verify.sh`.
  - (d) Output `<input>.patched.docx` differs in sha256 from the original input, but all non-citation paragraphs are byte-identical.
  - (e) Idempotent — running the same `corrections.json` twice produces sha256-identical output.
  - (f) The SKILL.md Stage 5 paragraph removed when this was deferred is restored in the same commit that completes (a)–(e).
- `render_report.py --format docx` — deferred from Phase 1 (formerly an unimplemented `--format docx` promise in SKILL.md). Acceptance:
  - (a) `--format` argument added to `render_report.py` argparse with choices `{markdown, docx}`, default `markdown`.
  - (b) DOCX output reuses `python-docx` (already in `REQUIRED`) so no new system-level dependency (no pandoc).
  - (c) DOCX content layout mirrors the current Markdown report: At-a-glance table + per-citation dual-channel detail blocks.
  - (d) `tests/` adds a smoke test asserting the generated `.docx` is a valid OOXML zip and contains at least one table.
  - (e) On completion, the two SKILL.md lines removed when this was deferred (the Stage 5 DOCX/PDF bullet and the `report.docx` Output-layout line) are restored in the same commit.
- Channel A scoring recalibration — deferred from Phase 2 review of the EIF4ENIF1 case, where all 5 partials reported `author_overlap=0.95` while raw values were 0.0–0.4 because the DOI-exact-match override floors both similarity scores. `d155f9b` (Phase 2 prep #1) exposed the raw values for transparency; this deliverable makes them the verdict's input. Acceptance:
  - (a) Replace `_author_overlap` (currently `|A∩B|/|A|`, asymmetric — biased toward citation-side coverage when the citation lists only first-author + et al.) with symmetric Jaccard (`|A∩B|/|A∪B|`); update `AUTHOR_OVERLAP_VALID` and any partial threshold accordingly.
  - (b) Remove the DOI-exact-match score floor inside `_score_match`. Replace it with an explicit branch in the verdict classifier that consumes the existing `doi_exact_match` boolean as a structural signal, not a similarity-score override. Raw similarity values stop being mutated anywhere in the pipeline.
  - (c) Re-tune classification thresholds against both Phase 2 cases (nasal methylation + EIF4ENIF1). Acceptance: ≥80% of pre-recalibration `valid` verdicts remain `valid` (no silent mass downgrades). Every flip — in either direction — is documented in the recalibration commit with a one-line per-citation justification.
  - (d) Phase 4 `paper/paper.md` Limitations section gains a one-paragraph note covering the metric switch, the structural (rather than score-floored) DOI signal, and the residual limitation (Channel A still verifies existence + identifier match, not textual claim-to-source fidelity — that remains Channel B's job).
  - (e) Phase 2 snapshot fixtures are deliberately re-baselined in the same commit; baseline diffs require user sign-off before the commit is considered complete (this is a Phase 3 user gate parallel to the Phase 5 release gates, not auto-applied).

### Exit criteria
- A zero-context reader can follow README's Quickstart and run `examples/nasal_methylation/run.sh` successfully within 10 minutes of `git clone`.
- CITATION.cff parses (test with `cffconvert` or `pip install cffconvert && cffconvert --validate`).
- `docx_patch.py` deliverable acceptance criteria (a)–(f) all met.
- `render_report.py --format docx` deliverable acceptance criteria (a)–(e) all met.
- Channel A scoring recalibration deliverable acceptance criteria (a)–(e) all met.

---

## Phase 4 — paper.md + figures

### Cowork/Claude tasks
- Draft `paper/paper.md` (800–1000 words, JOSS hard practical limit). Five sections:
  1. **Summary** (~120 words) — what citation-verify does in neutral technical language.
  2. **Statement of need** (~250 words, two paragraphs). Paragraph 1: problem — LLM-assisted writing has made citation hallucination a new academic integrity risk, particularly in biomedical reviews where AI drafting is common. Existing solutions split into (a) DOI-lookup tools (scite.ai, Semantic Scholar paper validation) that verify existence but not claim-to-source fidelity, and (b) LLM self-check approaches shown to be unreliable. Paragraph 2: gap — no published workflow explicitly partitions deterministic API adjudication and exploratory LLM probing, joined by a reverse-validation invariant preventing LLM outputs from becoming canonical records without API confirmation.
  3. **Architecture** (~300 words) — reference Figure 1; name the invariant; describe Stage 4b corrections/replacements split.
  4. **Worked example** (~200 words) — reference Figure 2; **narrate the real DOI-substitution incident from the nasal methylation review case**: an LLM-assisted citation rewrite introduced a plausible-but-incorrect DOI (off-by-three digits, pointing to an unrelated preprint on a different subject); dual-channel re-verification surfaced the mismatch, Stage 4b produced a correction object with the right Crossref record. Use the real data. Neutral tone — do not name the specific tool that produced the wrong DOI.
  5. **Limitations** (~80 words) — English-dominant citation coverage; external API dependency; user must provide Codex CLI access.
- Draft both figures as SVG (so they're diffable and reviewers can see changes):
  - **Figure 1 (architecture):** horizontal 5-column layout: input docx → parse → (Channel A ∥ Channel B) → reconcile into 4 buckets → Stage 4b (corrections/replacements) → patched docx. Channel A in blue (deterministic), Channel B in orange (exploratory). Label the reconcile box with the invariant `canonical_record.source ∈ {crossref, openalex, semantic_scholar}`.
  - **Figure 2 (worked example):** three-panel layout using the real nasal-review data: (left) original citation text with the incorrect DOI highlighted; (middle) Channel A response ∥ Channel B response side-by-side; (right) the Stage 4b correction JSON that was actually produced. No synthetic data.
- Write `paper/paper.bib`. Required citations: Athaluri 2023 (Cureus, ChatGPT fake citations), Walters & Wilder 2023 (JASIST), Agrawal et al. 2024 (ACL, LLM hallucination detection), scite.ai method paper, Crossref API paper (Hendricks et al. 2020), OpenAlex (Priem et al. 2022 arXiv), Semantic Scholar Graph API (Kinney et al. 2023). Add 2–4 domain-relevant citations on LLM use in biomedical literature.

### Exit criteria
- `paper/paper.md` + `paper.bib` + two SVG figures in place.
- Local Pandoc renders PDF without errors using the JOSS Open Journals template (test command documented in paper/README).

---

## Phase 5 — Freeze, Zenodo, JOSS submission

### Claude Code tasks
- Clean up `CHANGELOG.md` with full 0.x → 1.0.0 history.
- Set `VERSION` to `1.0.0`, commit, push to `main`.
- Draft the annotated tag message for `v1.0.0` (release notes summary). **Do not run `git tag` yourself** — this is a user-gated step because the tag push triggers Zenodo DOI minting.
- Verify Zenodo-GitHub integration is enabled in repo settings (user does the OAuth step; Claude Code confirms via public API once enabled).

### Cowork/Claude tasks
- Final review pass on `paper/paper.md`, focused on Statement of Need phrasing. This is the single most common JOSS revision-request target. Rewrite until it reads like academic positioning, not a product pitch.

### User tasks (cannot be delegated)
- Flip repo public.
- Push git tag `v1.0.0`.
- Confirm Zenodo webhook fired and DOI was minted.
- Submit to `joss.theoj.org/papers/new`: repo URL + Zenodo DOI + editor suggestion (look at JOSS active editors, pick one in bioinformatics or digital health).

### Exit criteria
- JOSS submission confirmation email received.
- Review issue opened in `shengjianpeng1987/citation-verify` by the JOSS bot.

---

## Phase 6 — JOSS review loop

Reviewers check their public checklist in the GitHub issue. We respond per-comment: push fixes, update the issue, reviewer re-checks. Typical concerns: incomplete tests, unclear README sections, Statement of Need revisions, platform-specific install notes.

### Exit criteria
- JOSS accept decision + paper DOI minted + Zenodo DOI updated to point at the accepted version.

---

## Open questions (log here as they arise)

_None currently. Previous 5 pushback questions on Stage 4b schema resolved in Phase 1 spec above._

---

## Changelog of this PLAN

- **v1** — Initial plan. Phase 0 locked, Phase 1 specified in full, Phases 2–6 outlined.
