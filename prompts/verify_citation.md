# Task: Verify whether a single academic citation is real

You are given one citation and — optionally — evidence already collected from the Crossref, OpenAlex, and Semantic Scholar APIs. Your job is to decide whether the citation points to a real, existing paper, or is an AI hallucination.

## Decision rubric

- `valid`: a real paper exists whose title, author list, and year substantively match the citation. Small formatting differences are OK (punctuation, middle initials, "and" vs "&", etc.).
- `hallucinated`: no paper with this title/authors/year combination exists in any of the major academic databases AND a web search for the exact title does not produce the paper. This is the "AI made it up" verdict.
- `partially_valid`: a real paper exists whose metadata partially matches — e.g., correct authors and year but wrong title, or correct title but wrong authors. This often means the AI mashed two real papers together.
- `uncertain`: you don't have enough evidence to be confident either way. Use this sparingly; prefer `hallucinated` or `valid` when you have clear signal.

## What to return

Emit JSON conforming to the provided schema. Required fields:

- `verdict`: one of the four labels above
- `confidence`: 0.0–1.0
- `explanation`: 1-3 sentence reasoning in plain English
- `matched_identifier`: the canonical DOI or URL of the real paper if `valid` or `partially_valid`; null otherwise
- `mismatches`: a list of field-level discrepancies (e.g., `["year: claimed 2021, actual 2019"]`). Empty if perfect match.
- `search_attempts`: brief log of what you looked up. At minimum include: "reviewed API evidence", and if you performed web search, "web searched: <query>".

## Rules

1. **Trust the API evidence first.** If Channel-A evidence says `not_found` across all three databases, and nothing else contradicts that, return `hallucinated` with high confidence.
2. **Do NOT fabricate DOIs.** If no real paper is found, `matched_identifier` is null. Never invent a DOI that "looks right".
3. **Character-level title match is not required.** "Attention Is All You Need" and "Attention is all you need" are the same paper.
4. **A real DOI that doesn't resolve → `hallucinated`.** A DOI that resolves to a completely different paper → `partially_valid` or `hallucinated` depending on overlap.
5. **Emit only the JSON.** No prose before or after.

## Input

Below is the citation plus any API evidence already collected. Use it to make your judgment. If you have tools to do web search, use them for cases where the API evidence is ambiguous.

__INPUT_JSON__
