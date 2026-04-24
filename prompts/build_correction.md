# Task: Build a field-level correction for a partially-valid citation

You are given one parsed citation (what the writer wrote) and the canonical Channel A record it matches (the real paper, confirmed via Crossref/OpenAlex/Semantic Scholar). The verify stage already decided this is a real paper with metadata errors — not a hallucination and not a perfect match. Your job is to produce a structured diff telling the writer which fields to fix.

## Rules

1. **The paper's existence is settled.** Do not re-adjudicate whether the paper is real. Both channels already agreed it is.
2. **Never propose a canonical record of your own.** The `canonical_record` in the input is the ground truth for this task — it was confirmed by Channel A (Crossref / OpenAlex / Semantic Scholar). You may only describe field-level differences between it and the original citation. If the canonical record looks wrong, set `requires_human_review: true` and a low confidence — do NOT output fabricated replacement data.
3. **Do not invent values.** Only use field values from the two inputs. Never synthesize a DOI or a year.
4. **Emit only the JSON.** No prose before or after.

## Field comparison

For each of these fields, compare `original_citation.<field>` with `canonical_record.<field>`:

- `authors`: list of `{family, given}` objects. Compare the joined surname sequence. Order matters.
- `title`: strings. Ignore pure whitespace, punctuation, or case differences. Flag substantive wording changes.
- `year`: integers.
- `venue`: journal / proceedings name. Abbreviation vs full name ("JAMA" vs "The Journal of the American Medical Association") is a `low`-severity diff — still record it.
- `volume`, `issue`, `page`: strings. If the original citation didn't include these and canonical does, omit those fields from the diff (not an error, just missing detail in the original).
- `doi`: strings, lowercased for comparison. A DOI mismatch is always `high` severity.

Only include a `field_diff_entry` for fields that **actually differ**. Do not include matching fields.

## Severity grading

- `high`: the difference changes whether a reader retrieving the citation reaches the correct paper. DOI mismatch; title substantively wrong; all authors wrong.
- `medium`: year off by 1–2; volume/issue/page swapped or wrong numbers; first author correct but later authors wrong or missing; title word order reshuffled.
- `low`: journal abbreviation vs full name; middle initial dropped; single-character typo; page range missing the end number.

## requires_human_review

Set to `true` if any of:
- There is at least one `high` severity diff.
- There are three or more `medium` diffs.
- The canonical record's authors and title look like they might actually belong to two candidate papers (genuine ambiguity).
- The claim is in a domain-sensitive area (clinical guidelines, drug dosing, safety/mortality statistics).

Otherwise `false`.

## Output shape

Return JSON conforming to the attached schema:

```json
{
  "field_diff": [
    {"field": "year", "original": "2020", "corrected": "2019", "severity": "medium"},
    {"field": "venue", "original": "JAMA", "corrected": "JAMA: The Journal of the American Medical Association", "severity": "low"}
  ],
  "confidence": 0.92,
  "requires_human_review": false
}
```

- Render original/corrected field values as strings. For `authors`, render as "Family1 G1, Family2 G2, ...". For integers (year), render as digit string.
- `confidence` is your confidence that the canonical record really is the paper the writer intended to cite.

## Input

__INPUT_JSON__
