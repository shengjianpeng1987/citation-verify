# Task: Find real papers that could replace a hallucinated citation

You are given (a) a hallucinated citation — something an AI made up — and (b) the surrounding context from the original document showing what claim the citation was meant to support. Your job is to find up to 5 real, verifiable academic papers that could legitimately back up that claim.

## How to search

- Use the hallucinated citation's topic keywords and apparent subject domain to query academic search (OpenAlex, Semantic Scholar, Crossref, Google Scholar).
- Pay attention to the surrounding passage — if the claim is "X increases Y by Z%", find papers that directly establish that relationship.
- If the fake citation named specific authors, consider that the AI may have been *trying* to cite real work by those authors on an adjacent topic; look for their genuine publications in the same area.
- Prefer canonical / highly-cited papers when multiple candidates exist. In ambiguous cases, include diverse candidates (different methods / different samples) rather than 5 near-duplicates.

## What to return per candidate

Emit JSON with a `candidates` array. Each candidate:

- `rank`: 1-5 (1 = your best guess)
- `title`: real paper title
- `authors`: list of `{family, given}` objects (first 6 is enough, then "et al.")
- `year`: publication year (integer)
- `venue`: journal / conference / publisher
- `doi`: DOI (no `https://doi.org/` prefix); MUST be real
- `url`: canonical URL
- `one_line_summary`: what this paper says, in 1 sentence
- `relevance_note`: why this is a plausible replacement — how it supports the claim in the original passage

## Hard rules

1. **Every candidate must be a real paper you can verify.** If you're not confident a paper exists, do NOT include it. It is better to return 2 real candidates than 5 where 1 is hallucinated.
2. **DOIs must be real.** Before listing a DOI, verify it resolves (Crossref lookup is enough). If you cannot verify, set `doi` to null and put the canonical URL in `url` instead.
3. **Do not pad the list.** If only 2 good candidates exist, return 2.
4. **Emit only the JSON.** No prose before or after.
5. **Stay in-domain.** If the passage is about a specific subfield (e.g., transformer architectures for machine translation), do not suggest papers from a distant subfield just because keywords overlap.

## If no suitable replacement exists

If no real paper can support the claim, return:
```json
{"candidates": [], "note": "No suitable replacement found because: <short reason>"}
```

## Input

The hallucinated citation and surrounding context appear below.

__INPUT_JSON__
