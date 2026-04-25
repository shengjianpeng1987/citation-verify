#!/usr/bin/env python3
"""Build hand-crafted fixtures for tests/fixtures/{api,codex}/synthetic_mixed/.

This script is the source-of-truth for synthetic_mixed's fixture content.
Unlike Phase 2 fixtures (recorded from real Codex/API runs), synthetic_mixed
fixtures are deliberately authored — the synthetic docx is OUR contract for
what the orchestrator should do, not Codex's discovery of an answer.

Why a builder script and not 20 hand-written JSON files:

- Every fixture's source is self-evident in one Python file: which citation,
  which canonical record, which Stage 4 path.
- Re-running the script reproduces byte-identical fixtures (modulo dict key
  ordering, controlled by `sort_keys=True` on writes).
- Future fixture changes happen in one place, with the schema invariants
  visible alongside.

After running, the deliverable has:
- 7 Channel A (api) fixtures: 6 citations + 1 re-verify of the Stage-4 winner.
- 9 Codex fixtures: 1 stage2 (atomize), 6 stage3 verify Channel B,
  1 stage3 reverify, 2 stage4a find_alternatives (one for #5 with a winner,
  one for #6 returning empty), 1 stage4b score_context_fit (for #5's winner),
  2 stage4b build_correction (for #3 and #4).

Run:
    .venv/bin/python3 tests/_build_synthetic_mixed_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_API = TESTS_DIR / "fixtures" / "api" / "synthetic_mixed"
FIXTURES_CODEX = TESTS_DIR / "fixtures" / "codex" / "synthetic_mixed"


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _write_json(path: Path, obj: dict | list) -> None:
    """Write a JSON file mirroring the on-disk shape that real Codex/API runs
    produced for Phase 2 fixtures: compact for codex (single line), pretty for
    api (multi-line) — matching the historical recordings so fixture diffs
    stay readable side-by-side with Phase 2."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if "/api/" in str(path):
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(obj, ensure_ascii=False)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


# -------------------- citations as Stage 2 would atomize them --------------------

# These are the exact dict structures the orchestrator would feed into Stage 3.
# Order mirrors the docx; raw_text matches the docx paragraphs verbatim so
# the in-text-context extractor in step4 can find them.

CITATIONS = [
    {
        "id": 1,
        "authors": [
            {"family": "Jinek", "given": "M"},
            {"family": "Chylinski", "given": "K"},
            {"family": "Fonfara", "given": "I"},
            {"family": "Hauer", "given": "M"},
            {"family": "Doudna", "given": "JA"},
            {"family": "Charpentier", "given": "E"},
        ],
        "title": "A programmable dual-RNA-guided DNA endonuclease in adaptive bacterial immunity",
        "year": 2012,
        "venue": "Science",
        "doi": None,
        "url": None,
        "raw_text": (
            "1. Jinek M, Chylinski K, Fonfara I, Hauer M, Doudna JA, Charpentier E. "
            "A programmable dual-RNA-guided DNA endonuclease in adaptive bacterial "
            "immunity. Science. 2012;337(6096):816-821."
        ),
    },
    {
        "id": 2,
        "authors": [
            {"family": "Takahashi", "given": "K"},
            {"family": "Yamanaka", "given": "S"},
        ],
        "title": "Induction of pluripotent stem cells from mouse embryonic and adult fibroblast cultures by defined factors",
        "year": 2006,
        "venue": "Cell",
        "doi": None,
        "url": None,
        "raw_text": (
            "2. Takahashi K, Yamanaka S. Induction of pluripotent stem cells from "
            "mouse embryonic and adult fibroblast cultures by defined factors. "
            "Cell. 2006;126(4):663-676."
        ),
    },
    {
        "id": 3,
        "authors": [
            {"family": "Smith", "given": "P"},
            {"family": "Jones", "given": "K"},
        ],
        "title": "RNA-guided human genome engineering via Cas9",
        "year": 2013,
        "venue": "Science",
        "doi": None,
        "url": None,
        "raw_text": (
            "3. Smith P, Jones K. RNA-guided human genome engineering via Cas9. "
            "Science. 2013;339(6121):823-826."
        ),
    },
    {
        "id": 4,
        "authors": [
            {"family": "Patel", "given": "R"},
            {"family": "Kumar", "given": "S"},
        ],
        "title": "Genetic screens in human cells using the CRISPR-Cas9 system",
        "year": 2014,
        "venue": "Science",
        "doi": None,
        "url": None,
        "raw_text": (
            "4. Patel R, Kumar S. Genetic screens in human cells using the "
            "CRISPR-Cas9 system. Science. 2014;343(6166):80-84."
        ),
    },
    {
        "id": 5,
        "authors": [
            {"family": "Lee", "given": "J"},
            {"family": "Wang", "given": "K"},
        ],
        "title": "Universal off-target prediction model for CRISPR-Cas9 systems",
        "year": 2020,
        "venue": "Nature Biotechnology",
        "doi": "10.1038/nbt.fakefake2020",
        "url": None,
        "raw_text": (
            "5. Lee J, Wang K. Universal off-target prediction model for "
            "CRISPR-Cas9 systems. Nature Biotechnology. 2020;38:1234-1242. "
            "doi:10.1038/nbt.fakefake2020"
        ),
    },
    {
        "id": 6,
        "authors": [{"family": "Anonymous", "given": ""}],
        "title": "A novel framework for citation hallucination detection in academic literature",
        "year": 2024,
        "venue": "Nature Methods",
        "doi": "10.1038/nmeth.fakefake2024",
        "url": None,
        "raw_text": (
            "6. Anonymous. A novel framework for citation hallucination detection "
            "in academic literature. Nature Methods. 2024;21:9999-10001. "
            "doi:10.1038/nmeth.fakefake2024"
        ),
    },
]


# -------------------- canonical records (real Crossref data, paste-from-curl) --------------------

CANONICAL_JINEK_2012 = {
    "title": "A Programmable Dual-RNA–Guided DNA Endonuclease in Adaptive Bacterial Immunity",
    "authors": [
        {"family": "Jinek", "given": "M."},
        {"family": "Chylinski", "given": "K."},
        {"family": "Fonfara", "given": "I."},
        {"family": "Hauer", "given": "M."},
        {"family": "Doudna", "given": "J. A."},
        {"family": "Charpentier", "given": "E."},
    ],
    "year": 2012,
    "venue": "Science",
    "doi": "10.1126/science.1225829",
    "url": "https://doi.org/10.1126/science.1225829",
}

CANONICAL_TAKAHASHI_2006 = {
    "title": "Induction of Pluripotent Stem Cells from Mouse Embryonic and Adult Fibroblast Cultures by Defined Factors",
    "authors": [
        {"family": "Takahashi", "given": "Kazutoshi"},
        {"family": "Yamanaka", "given": "Shinya"},
    ],
    "year": 2006,
    "venue": "Cell",
    "doi": "10.1016/j.cell.2006.07.024",
    "url": "https://doi.org/10.1016/j.cell.2006.07.024",
}

CANONICAL_MALI_2013 = {
    "title": "RNA-Guided Human Genome Engineering via Cas9",
    "authors": [
        {"family": "Mali", "given": "Prashant"},
        {"family": "Yang", "given": "Luhan"},
        {"family": "Esvelt", "given": "Kevin M."},
        {"family": "Aach", "given": "John"},
        {"family": "Guell", "given": "Marc"},
        {"family": "DiCarlo", "given": "James E."},
        {"family": "Norville", "given": "Julie E."},
        {"family": "Church", "given": "George M."},
    ],
    "year": 2013,
    "venue": "Science",
    "doi": "10.1126/science.1232033",
    "url": "https://doi.org/10.1126/science.1232033",
}

CANONICAL_WANG_2014 = {
    "title": "Genetic Screens in Human Cells Using the CRISPR-Cas9 System",
    "authors": [
        {"family": "Wang", "given": "Tim"},
        {"family": "Wei", "given": "Jenny J."},
        {"family": "Sabatini", "given": "David M."},
        {"family": "Lander", "given": "Eric S."},
    ],
    "year": 2014,
    "venue": "Science",
    "doi": "10.1126/science.1246981",
    "url": "https://doi.org/10.1126/science.1246981",
}

CANONICAL_DOENCH_2016 = {
    "title": "Optimized sgRNA design to maximize activity and minimize off-target effects of CRISPR-Cas9",
    "authors": [
        {"family": "Doench", "given": "John G"},
        {"family": "Fusi", "given": "Nicolo"},
        {"family": "Sullender", "given": "Meagan"},
        {"family": "Hegde", "given": "Mudra"},
        {"family": "Vaimberg", "given": "Emma W"},
        {"family": "Donovan", "given": "Katherine F"},
        {"family": "Smith", "given": "Ian"},
        {"family": "Tothova", "given": "Zuzana"},
        {"family": "Wilen", "given": "Craig"},
        {"family": "Orchard", "given": "Robert"},
        {"family": "Virgin", "given": "Herbert W"},
        {"family": "Listgarten", "given": "Jennifer"},
        {"family": "Root", "given": "David E"},
    ],
    "year": 2016,
    "venue": "Nature Biotechnology",
    "doi": "10.1038/nbt.3437",
    "url": "https://doi.org/10.1038/nbt.3437",
}


# -------------------- builders --------------------

def api_response_valid(canonical: dict, *, source: str = "crossref") -> dict:
    """Channel A response for a clean valid match (all similarity = 1.0)."""
    return {
        "verdict": "valid",
        "confidence": 1.0,
        "matched_source": source,
        "matched_record": canonical,
        "title_similarity": 1.0,
        "author_overlap": 1.0,
        "year_match": True,
        "title_similarity_raw": 1.0,
        "author_overlap_raw": 1.0,
        "doi_exact_match": False,
        "reasons": [
            f"{source}: valid (title_sim=1.00 raw=1.00, author_overlap=1.00 raw=1.00, "
            f"year_match=True, doi_exact_match=False)"
        ],
    }


def api_response_partially_valid_author_drift(canonical: dict, *, source: str = "crossref") -> dict:
    """Channel A response for a partially-valid match driven by author drift.
    Title matches exactly (drift is in author byline), so title_sim ~ 1.0 but
    author_overlap = 0.0 → verdict = partially_valid."""
    return {
        "verdict": "partially_valid",
        "confidence": 0.7,
        "matched_source": source,
        "matched_record": canonical,
        "title_similarity": 1.0,
        "author_overlap": 0.0,
        "year_match": True,
        "title_similarity_raw": 1.0,
        "author_overlap_raw": 0.0,
        "doi_exact_match": False,
        "reasons": [
            f"{source}: partially_valid (title_sim=1.00 raw=1.00, author_overlap=0.00 raw=0.00, "
            f"year_match=True, doi_exact_match=False)"
        ],
    }


def api_response_not_found(extra_reasons: list[str] | None = None) -> dict:
    """Channel A response when no source has a usable match."""
    return {
        "verdict": "not_found",
        "confidence": 0.0,
        "matched_source": None,
        "matched_record": None,
        "title_similarity": 0.0,
        "author_overlap": 0.0,
        "year_match": False,
        "title_similarity_raw": 0.0,
        "author_overlap_raw": 0.0,
        "doi_exact_match": False,
        "reasons": extra_reasons or [
            "crossref: no results",
            "openalex: no results",
            "semantic_scholar: no results",
        ],
    }


def channel_b_response(verdict: str, explanation: str, matched_identifier: str | None,
                       mismatches: list[str], search_attempts: list[str]) -> dict:
    return {
        "verdict": verdict,
        "confidence": 1.0 if verdict == "valid" else 0.95 if verdict == "partially_valid" else 0.95,
        "explanation": explanation,
        "matched_identifier": matched_identifier,
        "mismatches": mismatches,
        "search_attempts": search_attempts,
    }


def find_alternatives_response(candidates: list[dict], note: str | None) -> dict:
    return {"candidates": candidates, "note": note}


def score_context_fit_response(fit_score: int, rationale: str, *, supports_claim: bool,
                               confidence: float, concerns: list[str]) -> dict:
    return {
        "fit_score": fit_score,
        "rationale": rationale,
        "supports_claim": supports_claim,
        "confidence": confidence,
        "concerns": concerns,
    }


def build_correction_response(field_diff: list[dict], confidence: float,
                              requires_human_review: bool) -> dict:
    return {
        "field_diff": field_diff,
        "confidence": confidence,
        "requires_human_review": requires_human_review,
    }


# -------------------- compose all fixtures --------------------

def main() -> int:
    FIXTURES_API.mkdir(parents=True, exist_ok=True)
    FIXTURES_CODEX.mkdir(parents=True, exist_ok=True)

    # --------- api fixtures ---------

    api_responses = {
        1: api_response_valid(CANONICAL_JINEK_2012),
        2: api_response_valid(CANONICAL_TAKAHASHI_2006),
        3: api_response_partially_valid_author_drift(CANONICAL_MALI_2013),
        4: api_response_partially_valid_author_drift(CANONICAL_WANG_2014),
        5: api_response_not_found([
            "crossref: DOI 10.1038/nbt.fakefake2020 does not resolve",
            "openalex: no results",
            "semantic_scholar: no results",
        ]),
        6: api_response_not_found([
            "crossref: DOI 10.1038/nmeth.fakefake2024 does not resolve",
            "openalex: no results",
            "semantic_scholar: no results",
        ]),
    }
    for cit in CITATIONS:
        cid = cit["id"]
        citation_json = json.dumps(cit)
        fixture_path = FIXTURES_API / f"citation_{cid}_{_short_hash(citation_json)}.json"
        _write_json(fixture_path, api_responses[cid])
        print(f"api    {fixture_path.name}")

    # Re-verify of citation #5's winner (Doench 2016).
    # The orchestrator constructs winner_as_citation from the find_alternatives
    # top candidate. We must mirror that construction exactly so the api hash
    # matches what the replay-mode interceptor will compute.
    winner_as_citation = {
        "id": 5,
        "authors": CANONICAL_DOENCH_2016["authors"],
        "title": CANONICAL_DOENCH_2016["title"],
        "year": CANONICAL_DOENCH_2016["year"],
        "venue": CANONICAL_DOENCH_2016["venue"],
        "doi": CANONICAL_DOENCH_2016["doi"],
        "url": CANONICAL_DOENCH_2016["url"],
        "raw_text": f"{CANONICAL_DOENCH_2016['title']} ({CANONICAL_DOENCH_2016['year']})",
    }
    winner_json = json.dumps(winner_as_citation)
    winner_fixture = FIXTURES_API / f"citation_5_{_short_hash(winner_json)}.json"
    _write_json(winner_fixture, api_response_valid(CANONICAL_DOENCH_2016))
    print(f"api    {winner_fixture.name}  (#5 reverify of winner)")

    # --------- codex fixtures ---------

    # Stage 2: atomize the bibliography text. The output is the citations list
    # exactly as Stage 3 will iterate. (The input file content depends on
    # parse_doc.py's actual extraction, which doesn't affect fixture lookup —
    # only the input filename matters for fixture-path resolution.)
    _write_json(
        FIXTURES_CODEX / "stage2_input.json",
        {"citations": CITATIONS},
    )
    print("codex  stage2_input.json")

    # Stage 3 verify: Channel B's verdict per citation.
    channel_b_responses = {
        1: channel_b_response(
            "valid",
            "Crossref returned an exact match for title, author sequence, year, and venue. "
            "The canonical DOI is 10.1126/science.1225829.",
            "10.1126/science.1225829",
            [],
            ["reviewed API evidence"],
        ),
        2: channel_b_response(
            "valid",
            "Crossref returned the canonical Takahashi & Yamanaka 2006 record. Title, "
            "authors, year, and venue all match.",
            "10.1016/j.cell.2006.07.024",
            [],
            ["reviewed API evidence"],
        ),
        3: channel_b_response(
            "partially_valid",
            "A real 2013 Science paper titled 'RNA-Guided Human Genome Engineering via "
            "Cas9' exists at this exact venue, year, and page range, but the byline is "
            "Mali, Yang, Esvelt et al., not Smith and Jones. The citation conflates "
            "real metadata with a fabricated author list.",
            "10.1126/science.1232033",
            ["authors: claimed Smith P, Jones K; actual lead author Prashant Mali with "
             "8 authors total"],
            ["reviewed API evidence"],
        ),
        4: channel_b_response(
            "partially_valid",
            "A real 2014 Science paper titled 'Genetic Screens in Human Cells Using the "
            "CRISPR-Cas9 System' exists at this exact venue, year, volume, issue, and "
            "page range, but the byline is Wang, Wei, Sabatini, Lander, not Patel and "
            "Kumar. Author attribution drift on otherwise correct metadata.",
            "10.1126/science.1246981",
            ["authors: claimed Patel R, Kumar S; actual authors Tim Wang, Jenny J. Wei, "
             "David M. Sabatini, Eric S. Lander"],
            ["reviewed API evidence"],
        ),
        5: channel_b_response(
            "hallucinated",
            "The supplied DOI (10.1038/nbt.fakefake2020) is non-resolving and the "
            "API evidence found no record. A web search for the exact title and the "
            "claimed author pair returned no Nature Biotechnology paper matching "
            "this citation. The paper appears fabricated.",
            None,
            [],
            ["reviewed API evidence", "web searched: \"Universal off-target prediction "
             "model for CRISPR-Cas9 systems\" Lee Wang"],
        ),
        6: channel_b_response(
            "hallucinated",
            "The supplied DOI (10.1038/nmeth.fakefake2024) does not resolve, and the "
            "claimed title 'A novel framework for citation hallucination detection in "
            "academic literature' does not appear in any indexed Nature Methods 2024 "
            "issue. Web searches returned no matching paper. The citation is fabricated.",
            None,
            [],
            ["reviewed API evidence", "web searched: \"citation hallucination detection\" "
             "\"Nature Methods\" 2024"],
        ),
    }
    for cid, resp in channel_b_responses.items():
        path = FIXTURES_CODEX / f"stage3_input_{cid}.json"
        _write_json(path, resp)
        print(f"codex  {path.name}")

    # Stage 3 reverify: the winner of Stage 4 for citation #5 (Doench 2016).
    _write_json(
        FIXTURES_CODEX / "stage3_input_5_reverify.json",
        channel_b_response(
            "valid",
            "Channel A confirmed an exact Crossref match for the candidate "
            "(Doench et al. 2016, Nat Biotechnol, DOI 10.1038/nbt.3437). The "
            "winner's metadata aligns with the original citation's claim about "
            "off-target prediction, so the replacement is sound.",
            "10.1038/nbt.3437",
            [],
            ["reviewed API evidence"],
        ),
    )
    print("codex  stage3_input_5_reverify.json")

    # Stage 4a find_alternatives for #5 — returns one strong candidate.
    doench_candidate = {
        "rank": 1,
        "title": CANONICAL_DOENCH_2016["title"],
        "authors": CANONICAL_DOENCH_2016["authors"],
        "year": CANONICAL_DOENCH_2016["year"],
        "venue": CANONICAL_DOENCH_2016["venue"],
        "doi": CANONICAL_DOENCH_2016["doi"],
        "url": CANONICAL_DOENCH_2016["url"],
        "one_line_summary": (
            "A widely-cited Nature Biotechnology paper (Doench et al. 2016) that "
            "introduces an optimized sgRNA scoring model for CRISPR-Cas9, with "
            "explicit off-target activity prediction."
        ),
        "relevance_note": (
            "The fabricated citation claims a 'universal off-target prediction model' "
            "for CRISPR-Cas9; this real paper provides exactly that — sgRNA design "
            "rules optimized to minimize off-target effects. Topic, venue, and method "
            "match the claim."
        ),
    }
    _write_json(
        FIXTURES_CODEX / "stage4a_input_5.json",
        find_alternatives_response([doench_candidate], None),
    )
    print("codex  stage4a_input_5.json")

    # Stage 4a find_alternatives for #6 — returns no candidates.
    _write_json(
        FIXTURES_CODEX / "stage4a_input_6.json",
        find_alternatives_response(
            [],
            "No published paper matches the claimed title 'A novel framework for "
            "citation hallucination detection in academic literature' in Nature "
            "Methods 2024. The topic exists in adjacent venues but no candidate "
            "is close enough on title, venue, and year to recommend.",
        ),
    )
    print("codex  stage4a_input_6.json")

    # Stage 4b score_context_fit for #5's only candidate.
    _write_json(
        FIXTURES_CODEX / "stage4b_input_5_1.json",
        score_context_fit_response(
            8,
            "The original (fabricated) citation claims a CRISPR-Cas9 off-target "
            "prediction model. Doench et al. 2016 is the canonical paper for that "
            "exact claim — sgRNA design rules with off-target minimization are the "
            "paper's headline contribution. The fit is direct and well-supported.",
            supports_claim=True,
            confidence=0.92,
            concerns=[
                "The fabricated citation specified Nature Biotechnology 2020; the real "
                "Doench paper is Nature Biotechnology 2016 — same venue, four years "
                "earlier. Author should confirm the year shift is acceptable for the "
                "claim being supported.",
            ],
        ),
    )
    print("codex  stage4b_input_5_1.json")

    # Stage 4b build_correction for #3 (author drift over Mali 2013).
    _write_json(
        FIXTURES_CODEX / "stage4b_input_3.json",
        build_correction_response(
            [
                {
                    "field": "authors",
                    "original": "Smith P, Jones K",
                    "corrected": (
                        "Mali Prashant, Yang Luhan, Esvelt Kevin M., Aach John, "
                        "Guell Marc, DiCarlo James E., Norville Julie E., "
                        "Church George M."
                    ),
                    "severity": "high",
                },
            ],
            0.95,
            True,
        ),
    )
    print("codex  stage4b_input_3.json")

    # Stage 4b build_correction for #4 (author drift over Wang 2014).
    _write_json(
        FIXTURES_CODEX / "stage4b_input_4.json",
        build_correction_response(
            [
                {
                    "field": "authors",
                    "original": "Patel R, Kumar S",
                    "corrected": (
                        "Wang Tim, Wei Jenny J., Sabatini David M., Lander Eric S."
                    ),
                    "severity": "high",
                },
            ],
            0.95,
            True,
        ),
    )
    print("codex  stage4b_input_4.json")

    print()
    print(f"wrote {len(list(FIXTURES_API.iterdir()))} api fixtures")
    print(f"wrote {len(list(FIXTURES_CODEX.iterdir()))} codex fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
