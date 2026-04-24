#!/usr/bin/env python3
"""
api_verify.py — Deterministic citation verification against Crossref, OpenAlex, and Semantic Scholar.

This is "Channel A" in the skill's two-channel consensus model. It runs fast, cheap
lookups with no LLM involved. The separate Codex "Channel B" runs in parallel; the
orchestrator reconciles the two.

Usage (CLI):
    python3 api_verify.py --citation-json '{"authors":["Smith, J"],"title":"...","year":2021,"doi":null}'
    python3 api_verify.py --citation-file citation.json
    # Batch mode: one JSON citation per line on stdin, one verdict per line on stdout
    cat citations.jsonl | python3 api_verify.py --batch

Output JSON shape:
    {
      "verdict": "valid" | "partially_valid" | "not_found" | "error",
      "confidence": 0.0-1.0,
      "matched_source": "crossref" | "openalex" | "semantic_scholar" | null,
      "matched_record": { ... best match metadata ... } | null,
      "title_similarity": 0.0-1.0,
      "author_overlap": 0.0-1.0,
      "year_match": bool,
      "reasons": ["...human-readable explanations..."]
    }
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

try:
    import requests
except ImportError:
    sys.stderr.write("ERROR: requests not installed. Run: pip install requests\n")
    sys.exit(2)

try:
    from rapidfuzz import fuzz
except ImportError:
    sys.stderr.write("ERROR: rapidfuzz not installed. Run: pip install rapidfuzz\n")
    sys.exit(2)


def _title_looks_usable(title: str | None) -> bool:
    """A parsed title is usable only if it looks like a real title.
    Reject empty strings, punctuation-leading fragments like ';10:3095' from a bad
    Vancouver-regex split, or tiny 1-2 word leftovers like '-05-21' or '）'.
    """
    if not title:
        return False
    s = title.strip()
    if not s:
        return False
    if s[0] in ";,:-)）(（":
        return False
    # Count alphabetic words of length >= 2 — real titles have a few.
    import re as _re
    words = [w for w in _re.findall(r"[A-Za-z\u4e00-\u9fff]{2,}", s)]
    if len(words) < 3:
        return False
    return True


# --- Tunable thresholds ---
TITLE_VALID_THRESHOLD = 0.85     # fuzz ratio >= this → strong title match
TITLE_PARTIAL_THRESHOLD = 0.70   # 0.70–0.85 → partial match
AUTHOR_OVERLAP_VALID = 0.5       # fraction of authors overlapping → strong
YEAR_TOLERANCE = 1               # accept ±1 year drift (preprint vs publication)

USER_AGENT = "citation-verify-skill/0.1 (mailto:user@example.com)"
CROSSREF_URL = "https://api.crossref.org/works"
OPENALEX_URL = "https://api.openalex.org/works"
S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")


# -------------- similarity helpers --------------

def _normalize_title(t: str) -> str:
    return " ".join(t.lower().split())


def _title_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(_normalize_title(a), _normalize_title(b)) / 100.0


def _author_family_names(authors: list) -> set[str]:
    """Normalize a list of author strings to a set of lowercased family names."""
    out = set()
    for a in authors or []:
        if isinstance(a, dict):
            fam = a.get("family") or a.get("last") or a.get("name", "")
        else:
            fam = str(a)
        # "Smith, John A" -> "smith"; "John A. Smith" -> "smith"
        if "," in fam:
            fam = fam.split(",", 1)[0]
        else:
            fam = fam.strip().split()[-1] if fam.strip() else ""
        fam = fam.lower().strip(" .-'")
        if fam:
            out.add(fam)
    return out


def _author_overlap(claimed: list, found: list) -> float:
    a = _author_family_names(claimed)
    b = _author_family_names(found)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), 1)


# -------------- API queries --------------

def _crossref_search(citation: dict) -> dict | None:
    """Crossref bibliographic search. Returns best-match record or None on no result."""
    doi = citation.get("doi")
    if doi:
        # Direct DOI lookup — fastest and most authoritative
        r = requests.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        if r.status_code == 200:
            msg = r.json().get("message", {})
            return _crossref_to_record(msg)
        if r.status_code == 404:
            return {"_not_found_for_doi": doi}
    # Fallback: bibliographic query. Build the best query we can from the
    # structured fields; if title looks like junk (missing or starts with
    # punctuation like ";10:3095" from a bad Vancouver-style regex parse), fall
    # back to the raw citation text — Crossref's query.bibliographic handles
    # full-text citations well.
    title = citation.get("title") or ""
    if _title_looks_usable(title):
        query = title
        if citation.get("authors"):
            first = _first_author_family(citation["authors"])
            if first:
                query = f"{first} {query}"
    else:
        query = citation.get("raw_text") or ""
    if not query.strip():
        return None
    r = requests.get(
        CROSSREF_URL,
        params={"query.bibliographic": query, "rows": 5},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    if r.status_code != 200:
        return None
    items = r.json().get("message", {}).get("items", [])
    if not items:
        return None
    return _crossref_to_record(items[0])


def _crossref_to_record(msg: dict) -> dict:
    title = (msg.get("title") or [""])[0]
    authors = [
        {"family": a.get("family", ""), "given": a.get("given", "")}
        for a in msg.get("author", [])
    ]
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        if msg.get(key, {}).get("date-parts"):
            year = msg[key]["date-parts"][0][0]
            break
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "venue": (msg.get("container-title") or [""])[0],
        "doi": msg.get("DOI"),
        "url": msg.get("URL"),
    }


def _openalex_search(citation: dict) -> dict | None:
    doi = citation.get("doi")
    if doi:
        r = requests.get(
            f"https://api.openalex.org/works/https://doi.org/{doi}",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        if r.status_code == 200:
            return _openalex_to_record(r.json())
    title = citation.get("title") or ""
    query = title if _title_looks_usable(title) else (citation.get("raw_text") or "")
    if not query.strip():
        return None
    r = requests.get(
        OPENALEX_URL,
        params={"search": query, "per_page": 5},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    if not results:
        return None
    return _openalex_to_record(results[0])


def _openalex_to_record(w: dict) -> dict:
    authors = [
        {"family": (a.get("author", {}).get("display_name") or "").split()[-1],
         "given": " ".join((a.get("author", {}).get("display_name") or "").split()[:-1])}
        for a in w.get("authorships", [])
    ]
    return {
        "title": w.get("title") or w.get("display_name") or "",
        "authors": authors,
        "year": w.get("publication_year"),
        "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
        "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
        "url": w.get("id"),
    }


def _s2_search(citation: dict) -> dict | None:
    title = citation.get("title") or ""
    query = title if _title_looks_usable(title) else (citation.get("raw_text") or "")
    # Semantic Scholar search has a hard cap around 300 chars for the query param.
    if len(query) > 280:
        query = query[:280]
    if not query.strip():
        return None
    headers = {"User-Agent": USER_AGENT}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY
    r = requests.get(
        S2_URL,
        params={
            "query": query,
            "limit": 5,
            "fields": "title,authors,year,venue,externalIds,url",
        },
        headers=headers,
        timeout=15,
    )
    if r.status_code != 200:
        return None
    data = r.json().get("data", [])
    if not data:
        return None
    return _s2_to_record(data[0])


def _s2_to_record(p: dict) -> dict:
    authors = [
        {"family": (a.get("name") or "").split()[-1],
         "given": " ".join((a.get("name") or "").split()[:-1])}
        for a in (p.get("authors") or [])
    ]
    doi = (p.get("externalIds") or {}).get("DOI")
    return {
        "title": p.get("title") or "",
        "authors": authors,
        "year": p.get("year"),
        "venue": p.get("venue") or "",
        "doi": doi,
        "url": p.get("url"),
    }


def _first_author_family(authors: list) -> str:
    for a in authors or []:
        if isinstance(a, dict):
            fam = a.get("family") or a.get("last") or a.get("name", "")
        else:
            fam = str(a)
        if "," in fam:
            fam = fam.split(",", 1)[0]
        else:
            fam = fam.strip().split()[-1] if fam.strip() else ""
        if fam:
            return fam
    return ""


# -------------- reconciliation --------------

def _score_match(citation: dict, record: dict) -> tuple[float, float, bool]:
    title_sim = _title_sim(citation.get("title") or "", record.get("title") or "")
    author_ov = _author_overlap(citation.get("authors") or [], record.get("authors") or [])
    year_match = False
    cy = citation.get("year")
    ry = record.get("year")
    if cy and ry:
        try:
            year_match = abs(int(cy) - int(ry)) <= YEAR_TOLERANCE
        except (TypeError, ValueError):
            year_match = False

    # DOI-exact-match override. When the citation has a DOI and the returned record
    # carries the same DOI, we found the paper by direct identifier lookup — the
    # query didn't depend on title/author similarity. Treat as strong evidence so a
    # citation with null title (e.g. from the regex fallback parser) still gets a
    # valid verdict instead of being dragged down by title_sim=0.
    cd = (citation.get("doi") or "").lower().strip()
    rd = (record.get("doi") or "").lower().strip()
    if cd and rd and cd == rd:
        if title_sim < 0.95:
            title_sim = 0.95
        if author_ov < 0.95:
            author_ov = 0.95
    return title_sim, author_ov, year_match


def verify_one(citation: dict) -> dict:
    """Run Crossref → OpenAlex → Semantic Scholar and return a consensus verdict."""
    reasons: list[str] = []
    best_verdict = "not_found"
    best_confidence = 0.0
    best_source = None
    best_record = None
    best_title_sim = 0.0
    best_author_ov = 0.0
    best_year_match = False

    for source_name, fn in (
        ("crossref", _crossref_search),
        ("openalex", _openalex_search),
        ("semantic_scholar", _s2_search),
    ):
        try:
            rec = fn(citation)
        except requests.RequestException as e:
            reasons.append(f"{source_name}: network error ({e})")
            continue
        if not rec:
            reasons.append(f"{source_name}: no results")
            continue
        if rec.get("_not_found_for_doi"):
            reasons.append(f"{source_name}: DOI {rec['_not_found_for_doi']} does not resolve")
            continue

        title_sim, author_ov, year_match = _score_match(citation, rec)

        # Build a composite confidence
        conf = 0.6 * title_sim + 0.3 * author_ov + 0.1 * (1.0 if year_match else 0.0)

        # Classify
        if title_sim >= TITLE_VALID_THRESHOLD and author_ov >= AUTHOR_OVERLAP_VALID:
            verdict = "valid"
        elif title_sim >= TITLE_PARTIAL_THRESHOLD or (title_sim >= 0.6 and author_ov >= AUTHOR_OVERLAP_VALID):
            verdict = "partially_valid"
        else:
            verdict = "not_found"
            reasons.append(
                f"{source_name}: best candidate title_sim={title_sim:.2f}, "
                f"author_overlap={author_ov:.2f} — too weak to call a match"
            )

        reasons.append(
            f"{source_name}: {verdict} "
            f"(title_sim={title_sim:.2f}, author_overlap={author_ov:.2f}, year_match={year_match})"
        )

        # Take the strongest evidence across sources
        rank = {"valid": 3, "partially_valid": 2, "not_found": 1, "error": 0}
        if rank[verdict] > rank[best_verdict] or (
            rank[verdict] == rank[best_verdict] and conf > best_confidence
        ):
            best_verdict = verdict
            best_confidence = conf
            best_source = source_name
            best_record = rec
            best_title_sim = title_sim
            best_author_ov = author_ov
            best_year_match = year_match

        # Early exit on strong valid — no need to hit remaining APIs
        if best_verdict == "valid" and best_confidence >= 0.9:
            break

    return {
        "verdict": best_verdict,
        "confidence": round(best_confidence, 3),
        "matched_source": best_source,
        "matched_record": best_record if best_record and not best_record.get("_not_found_for_doi") else None,
        "title_similarity": round(best_title_sim, 3),
        "author_overlap": round(best_author_ov, 3),
        "year_match": best_year_match,
        "reasons": reasons,
    }


# -------------- CLI --------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--citation-json", help="Single citation as inline JSON")
    g.add_argument("--citation-file", help="Single citation as a JSON file")
    g.add_argument("--batch", action="store_true", help="Read one JSON citation per line from stdin")
    args = ap.parse_args()

    if args.batch:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                cit = json.loads(line)
            except json.JSONDecodeError as e:
                sys.stdout.write(json.dumps({"verdict": "error", "reasons": [f"bad json: {e}"]}) + "\n")
                continue
            sys.stdout.write(json.dumps(verify_one(cit), ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return 0

    if args.citation_json:
        cit = json.loads(args.citation_json)
    elif args.citation_file:
        cit = json.loads(open(args.citation_file).read())
    else:
        sys.stderr.write("ERROR: need one of --citation-json, --citation-file, or --batch\n")
        return 1

    sys.stdout.write(json.dumps(verify_one(cit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
