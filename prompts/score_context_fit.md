# Task: Score how well a candidate paper fits the original claim's context

You are given:
- `original_context`: the passage from the user's document where the citation was placed
- `original_claim`: the specific claim or statement the citation was meant to support (extracted from `original_context`)
- `candidate`: a candidate replacement paper (title, authors, year, venue, DOI, one-line summary, abstract if available)

Your job is to judge, on a 0–10 scale, how well this candidate supports the original claim.

## Scoring rubric

- **9-10** — Direct, strong support: the candidate paper explicitly studies or proves the claim being made. Replacing the hallucinated citation with this paper would be seamless; a human reviewer would not raise an eyebrow.
- **7-8** — Relevant support: the candidate establishes the same finding or phenomenon but maybe in a different population / system / with slightly different methods. Still a legitimate citation for the claim.
- **5-6** — Tangentially relevant: the paper is in the same area and mentions the topic, but doesn't substantively support *this specific claim*. A reviewer might ask "why this paper?".
- **3-4** — Wrong subfield or wrong angle: keyword match but doesn't support the claim. Should not be used as replacement.
- **0-2** — Unrelated: replacing with this paper would be clearly inappropriate.

## Output

Emit JSON:
- `fit_score`: integer 0-10
- `rationale`: 2-4 sentence explanation of the score, citing what the candidate actually shows vs what the original claim needed
- `supports_claim`: boolean — `true` if fit_score >= 7
- `confidence`: 0.0-1.0 — how confident you are in this judgment given the information available
- `concerns`: list of short strings — any red flags (e.g., "candidate abstract unavailable, judgment based on title only", "candidate is from 2003 while the claim may require more recent evidence")

## Rules

1. **Be conservative.** If the abstract is not available and you're judging from title+venue alone, lower your `confidence` and note it in `concerns`.
2. **Do not reward generic similarity.** Papers in the same field but on a different question should score 5 or below.
3. **Time sensitivity matters.** If the claim involves "recent" findings, older candidate papers should score lower unless they're foundational.
4. **Emit only the JSON.**

## Input

The original context, claim, and candidate appear below.

__INPUT_JSON__
