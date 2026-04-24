# Task: Parse a raw bibliography text into structured citations

You are given the raw text of the "References" / "Bibliography" section of an academic document. The entries may be numbered, author-year, or a mix. Some entries may span multiple lines. Your job is to extract each individual reference and return a structured JSON array.

## What to extract per citation

- `id`: a 1-indexed integer; entries ordered as they appear in the bibliography
- `authors`: list of `{family, given}` objects. If a work has many authors ("et al."), include every author name you can see — do NOT truncate.
- `title`: the title of the work
- `year`: publication year, integer, or null if you can't tell
- `venue`: journal / conference / publisher / book title
- `doi`: DOI string (without the `https://doi.org/` prefix) or null
- `url`: URL if one is present and no DOI; otherwise null
- `raw_text`: the original unedited text of that entry, with whitespace normalized to single spaces

## Rules

1. **Do not invent data.** If a field isn't in the source text, set it to null. Never guess a DOI or year.
2. **Do not merge entries.** Each numbered or author-block entry is one citation even if it looks suspiciously short.
3. **Strip citation numbers.** "[17]" or "17." at the start of an entry is not part of the title — drop it.
4. **DOI extraction.** Recognize DOIs in any of these forms: `doi:10.1000/xyz`, `https://doi.org/10.1000/xyz`, `10.1000/xyz` bare. Normalize to the bare `10.xxxx/...` form.
5. **Respect the output schema strictly.** Return ONLY the JSON — no prose, no code fences, no commentary.

## Heuristics for tricky cases

- Line breaks in the middle of a title are common in PDFs — merge them.
- "et al." with a year like "2023" usually means the authors list is incomplete in the source; include what's there and set `authors` to the listed names only.
- Book chapters with "In: <Editor> (ed.), <BookTitle>" — the book title is the venue.
- Preprints with arXiv numbers like "arXiv:2301.12345" — put "arXiv" as the venue and the arXiv id in the `url` field as `https://arxiv.org/abs/2301.12345`.

## Input

The raw references text will be supplied in the placeholder `__INPUT_JSON__` below, wrapped as `{"references_text": "..."}`. Parse the text inside.

__INPUT_JSON__
