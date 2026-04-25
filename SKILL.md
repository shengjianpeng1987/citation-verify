---
name: citation-verify
description: Verify whether citations in an English academic document (Word/PDF) are real or AI-hallucinated, and — when a citation is fake — find a vetted real replacement through an atomized verify→find-alternative→re-verify loop. Use this skill whenever the user asks to check citations, references, or bibliographies, whenever they mention that an AI wrote citations they want to audit, whenever they upload a .docx or .pdf and ask about references, or whenever they say things like "did ChatGPT/Claude make these up", "核查引用", "查参考文献", "check if these papers are real". Even if the user only says "this paper has fake sources" or "audit my refs", use this skill. The skill runs verification against Crossref + OpenAlex + Semantic Scholar APIs AND uses `codex exec` for atomic LLM-driven verification, candidate search, and context-fit scoring. Every Codex call is one-shot and ephemeral — never use `codex resume`.
---

# citation-verify

## What this skill does

Given an English academic document (.docx or .pdf), verify every citation in the bibliography, find real replacements for any hallucinated ones (by searching the same academic databases and scoring them for context fit), and produce a report with before/after replacements plus evidence for every verdict.

The skill exists because LLMs fabricate ~14-95% of citations depending on domain (see the GhostCite study on 2.2M citations). The user already knows this — they want a production-grade audit, not a one-shot check.

## When to invoke

Use this skill whenever:
- The user uploads a Word/PDF and asks about its references, citations, or bibliography.
- The user says an AI produced a draft and wants to audit it.
- The user asks to "verify citations", "check references", "核查引用", "查参考文献", "这些文献是真的吗".
- The user mentions hallucinated references, fake DOIs, fabricated papers.

Do NOT use this skill for:
- Formatting citations into APA/MLA (that's a styling task, not verification).
- Citation management in reference managers (Zotero/Mendeley etc.).
- Verifying non-academic sources (news articles, webpages without DOIs).

## Architecture: atomic Codex calls

Every call to `codex` in this skill is **one-shot, ephemeral, no session reuse**. Never use `codex resume`. Every atomic task gets its own `codex exec` invocation with:
- `--ephemeral` so no session rollout is persisted
- `--json` so output is parseable
- `--output-schema <schema>` so the response conforms to a known shape
- `--sandbox read-only` because Codex is only reading web/APIs, never writing

This matters because:
1. Atomized tasks can run in parallel (one subprocess per citation).
2. Each task has a clean context — no contamination from earlier citations.
3. Failures are isolated — one bad citation doesn't poison the run.

The wrapper `scripts/codex_atom.sh` enforces these defaults. Call it like:
```
scripts/codex_atom.sh <prompt_file> <schema_file> <json_input>
```
It pipes `<json_input>` into the prompt template, calls Codex with the right flags, and returns the parsed JSON on stdout.

## The pipeline

For any user invocation, run the orchestrator:
```
python3 scripts/orchestrate.py <input.pdf|input.docx> [--output-dir <dir>] [--parallel N]
```

The orchestrator implements this flow:

**Stage 1 — Extract references text.** `scripts/parse_doc.py` pulls the "References" / "Bibliography" section from the file using pdfplumber (PDF) or python-docx (DOCX) and returns raw text.

**Stage 2 — Atomize citations.** One `codex exec` call (prompt: `prompts/parse_references.md`, schema: `schemas/citations.schema.json`) turns the raw text into a JSON list of structured citations: `{id, authors, title, year, venue, doi, raw_text}`. This is atomic but runs once, not per-citation.

**Stage 3 — Verify each citation (parallel, two channels).** For each citation, run two independent checks:
- **Channel A (deterministic API):** `scripts/api_verify.py` queries Crossref → OpenAlex → Semantic Scholar in that order. Returns a verdict (`valid` / `partially_valid` / `not_found`) plus the best-matching record.
- **Channel B (atomic Codex):** `codex_atom.sh prompts/verify_citation.md schemas/verdict.schema.json` — Codex is given the citation and the Channel-A evidence, and asked to give an independent judgment with explanation.

Reconcile the two:
- Both say `valid` with matching metadata → label `valid`.
- Both say `hallucinated` → label `hallucinated`.
- They disagree → label `uncertain` and show both channels' reasoning to the user. Do NOT auto-replace uncertain citations.

**Stage 4 — For each hallucinated citation, find a replacement (atomic loop).**

1. Read ~200 chars of original context around the in-text citation (from parse_doc output).
2. `codex_atom.sh prompts/find_alternatives.md schemas/alternatives.schema.json` — returns up to 5 candidates with DOI, title, authors, one-line summary.
3. For each candidate, in parallel: `codex_atom.sh prompts/score_context_fit.md schemas/fit_score.schema.json` — scores how well the candidate supports the claim in the original context (0-10 + rationale).
4. Take the top-scoring candidate with `fit_score >= 7`. If none meets that bar, mark as `no_suitable_replacement`.
5. Run Stage 3 on that winning candidate again. Only if the re-verification comes back `valid` AND the fit score was ≥7 do we mark it as a confirmed replacement.

**Stage 5 — Render the report.** `scripts/render_report.py` produces:
- A Markdown report (always) with per-citation verdicts, evidence links, and replacement rationale.

## Output layout

```
<output-dir>/
├── citations.json             # parsed structured citations
├── verdicts.json              # per-citation final labels + both channels' raw data
├── replacements.json          # Stage 4 raw replacement-search results (status + winner + candidates)
├── corrections.json           # Stage 4b structured output: corrections / replacements / unresolvable + meta block
└── report.md                  # human-readable report (always)
```

## Dependencies

Before invoking, ensure:
- Python 3.9+ with `pdfplumber`, `python-docx`, `requests`, `rapidfuzz` installed. The orchestrator checks and prints `pip install` command if missing.
- `codex` CLI installed and authenticated (`codex --version` should succeed).
- Optional but recommended: `SEMANTIC_SCHOLAR_API_KEY` env var (free, 1 minute to request) — speeds Channel A from 5s/citation to 1s/citation.

## Design invariants — do not violate

1. **Never `codex resume`.** Every Codex call is `codex exec --ephemeral`. Atomization is the whole point.
2. **Never auto-replace `uncertain` citations.** Only confirmed `hallucinated` with `fit_score >= 7` AND re-verification `valid` is eligible for replacement.
3. **Consensus before replacement.** Both Channel A and Channel B must agree on the fake label before hunting for a replacement. If they disagree, that's a signal to flag for the user, not to plow ahead.
4. **Keep original context.** When applying replacements, preserve the in-text citation marker style (numbered `[17]`, author-year `(Smith, 2023)`, etc.) — only the bibliography entry changes.
5. **Evidence over opinion.** Every verdict in the report carries a DOI/URL link to the matched record (or explicit "not found in Crossref / OpenAlex / Semantic Scholar"). No unsupported claims.
6. **`canonical_record.source` is always Channel A.** Any record that lands in `corrections[].canonical_record` or `replacements[].canonical_record` must come from Crossref, OpenAlex, or Semantic Scholar — the `source` enum in `schemas/corrections.schema.json` has no `channel_b_web` value. Channel B findings are candidate suggestions only: they must be round-tripped through Channel A to be promoted. If Channel A cannot confirm a Channel B candidate, the citation goes to `unresolvable[]`, not to corrections or replacements.
7. **Verdict buckets are fixed at Stage 3.** `partially_valid` → `corrections[]` (same paper, metadata fields diffed). `hallucinated` with confirmed replacement → `replacements[]` (different paper). `uncertain` that Stage 3 resolves through a Channel A round-trip → joins corrections or replacements based on whether the canonical DOI matches the original citation's DOI. Everything else → `unresolvable[]`. Stage 4b consumes the bucketing and fills in the structured output — it never re-classifies.

## Running a subset

If the user wants to test on a small subset first, pass `--limit N` to the orchestrator — it stops after N citations. Useful for debugging or cost control.

## Parallelism

Default `--parallel 4`. Each worker owns one citation at a time and drives it through Stages 3-4. Tune down if hitting Crossref rate limits (50 req/s polite pool) or Codex quota. Tune up on a fast machine with a Semantic Scholar key.

## When things go wrong

- `codex exec` fails with auth error → user needs `codex login` first.
- Crossref returns 429 → back off and retry; check `--parallel` isn't too high.
- A citation is in a language other than English → the skill is English-optimized; flag it as `out_of_scope` instead of processing. Do not guess.
- PDF has no clear "References" section → fall back to heuristic extraction (last 25% of document, look for numbered refs). Mark the run with a warning in the report.
