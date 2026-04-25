#!/usr/bin/env python3
"""
orchestrate.py — Main pipeline for the citation-verify skill.

Flow:
  1. Parse doc → references_text + full_text           (parse_doc.py)
  2. Atomize → structured citations list               (codex_atom.sh + parse_references prompt)
  3. For each citation, in parallel:
       a. Channel A: deterministic API lookup          (api_verify.py)
       b. Channel B: atomic codex verify call          (codex_atom.sh + verify_citation prompt)
       c. Reconcile → final label
  4. For each citation labeled hallucinated:
       a. Find up to 5 candidates                      (codex_atom.sh + find_alternatives)
       b. For each candidate, score context fit        (codex_atom.sh + score_context_fit)
       c. Take top candidate with fit_score>=7
       d. Re-verify the winner via Stage 3
       e. If re-verification passes → confirmed replacement
  4b. Build corrections.json (3-bucket structured output):
       partially_valid → corrections[]  (Codex diffs original vs canonical_record)
       hallucinated+confirmed_replacement → replacements[]
       uncertain / hallucinated-no-replacement → unresolvable[]
       Plus a required meta block (schema_version, sha256, codex_model, ...).
       Invariant: canonical_record.source is always a Channel A API; Channel B web
       findings must be round-tripped through A before landing in canonical_record.
  5. Render report + optionally patch document         (render_report.py)

Never calls `codex resume`. Every Codex invocation is one-shot.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent  # src/citation_verify
REPO_ROOT = PACKAGE_DIR.parent.parent          # repo root (above src/)
PROMPTS = REPO_ROOT / "prompts"
SCHEMAS = REPO_ROOT / "schemas"

# --- Stage 4b constants ---

SCHEMA_VERSION = "0.2.0"  # corrections.schema.json version. Bump per semver on schema change.
API_SOURCES_ENABLED = ["crossref", "openalex", "semantic_scholar"]

# Stage 4b: deterministic backstop on requires_human_review. Any high-severity
# diff in one of these citation-integrity-critical fields forces requires_human_review
# = True regardless of Codex's judgment. Codex's prompt drives broader / softer
# cases (ambiguity, domain-sensitivity) — this is purely a stricter backstop.
CRITICAL_REVIEW_FIELDS = frozenset({"title", "doi", "year"})

# --- dependency check ---

REQUIRED = {
    "pdfplumber": "pdfplumber",
    "docx": "python-docx",
    "requests": "requests",
    "rapidfuzz": "rapidfuzz",
    "jsonschema": "jsonschema",
}


def _check_python_deps() -> None:
    missing = []
    for modname, pkg in REQUIRED.items():
        try:
            __import__(modname)
        except ImportError:
            missing.append(pkg)
    if missing:
        sys.stderr.write(
            "ERROR: missing Python packages. Install them with:\n"
            f"    pip install {' '.join(missing)}\n"
        )
        sys.exit(2)


def _check_codex() -> None:
    # Don't hard-fail if codex is missing — user might be running --api-only.
    # The orchestrator checks again before any codex call.
    pass


# --- step 1: parse doc ---

def step1_parse_doc(input_path: Path, work_dir: Path) -> dict:
    parse_out = work_dir / "parsed.json"
    subprocess.run(
        [sys.executable, str(PACKAGE_DIR / "parse_doc.py"), str(input_path), "--out", str(parse_out)],
        check=True,
    )
    return json.loads(parse_out.read_text(encoding="utf-8"))


# --- step 2: atomize citations via codex ---

def step2_atomize_citations(parsed: dict, work_dir: Path, *, codex_available: bool) -> dict:
    if not parsed.get("references_text", "").strip():
        return {"citations": []}

    if not codex_available:
        # Fallback: regex-based entry splitting. Crude but lets the rest of the pipeline run.
        return _fallback_split_citations(parsed["references_text"])

    input_payload = {"references_text": parsed["references_text"]}
    input_file = work_dir / "stage2_input.json"
    input_file.write_text(json.dumps(input_payload, ensure_ascii=False), encoding="utf-8")

    out = _codex_atom(
        PROMPTS / "parse_references.md",
        SCHEMAS / "citations.schema.json",
        input_file,
        label="atomize-citations",
    )
    return out


def _fallback_split_citations(ref_text: str) -> dict:
    """Regex-based bibliography splitter. Used only when codex is unavailable."""
    # Strategy: split on lines beginning with "[N]" or "N." or blank-line + capital letter
    entries = []
    current: list[str] = []
    for line in ref_text.splitlines():
        stripped = line.strip()
        if re.match(r"^(\[\d+\]|\d+\.)\s", stripped):
            # start of a new entry — flush previous one
            if current:
                entries.append(" ".join(current).strip())
            current = [re.sub(r"^(\[\d+\]|\d+\.)\s", "", stripped)]
        else:
            if stripped:
                current.append(stripped)
            elif current:
                entries.append(" ".join(current).strip())
                current = []
    if current:
        entries.append(" ".join(current).strip())

    citations = []
    for i, raw in enumerate(entries, 1):
        parsed = _parse_vancouver(raw, i) or _parse_apa_like(raw, i)
        citations.append(parsed)
    return {"citations": citations}


def _extract_doi(raw: str) -> str | None:
    m = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", raw, re.I)
    return m.group(0).rstrip(".,;") if m else None


def _parse_authors_block(authors_str: str) -> list[dict]:
    """Parse a Vancouver authors block like 'Forno E, Acosta-Pérez E' or 'Ziller MJ et al'."""
    authors_str = re.sub(r",?\s*et al\.?$", "", authors_str.strip()).strip().rstrip(",.")
    if not authors_str:
        return []
    out: list[dict] = []
    for tok in re.split(r",\s*", authors_str):
        tok = tok.strip().rstrip(".")
        if not tok or tok.lower() in ("et al", "and"):
            continue
        # Form "Forno E" / "Campagna MP" / "Ziller MJ"
        parts = tok.rsplit(" ", 1)
        if len(parts) == 2 and re.match(r"^[A-Z]{1,4}$", parts[1]):
            out.append({"family": parts[0].strip(), "given": parts[1]})
        elif "," in tok:
            fam, giv = tok.split(",", 1)
            out.append({"family": fam.strip().strip(".,"),
                        "given": giv.strip().strip(".,")})
        else:
            out.append({"family": tok, "given": ""})
    return out


def _parse_vancouver(raw: str, i: int) -> dict | None:
    """Vancouver format: 'Authors. Title. Journal. Year;Volume(Issue):Pages.'
    Detection requires a `YYYY;` pattern (volume-page separator).
    """
    m_yr = re.search(r"\b(19|20)\d{2}\s*;", raw)
    if not m_yr:
        return None
    year = int(raw[m_yr.start():m_yr.start() + 4])

    # Split author block from the rest. Prefer "et al." terminator; fall back to a short
    # organization-name terminator (e.g., "Illumina.") if no "et al." is present.
    m_et_al = re.search(r"^(.+?)\s+et al\.\s+", raw)
    if m_et_al:
        authors_str = m_et_al.group(1) + " et al"
        remainder = raw[m_et_al.end():]
    else:
        m_org = re.match(r"^([A-Z][A-Za-z&\-]{1,30})\.\s+", raw)
        if m_org:
            authors_str = m_org.group(1)
            remainder = raw[m_org.end():]
        else:
            return None  # can't cleanly split authors — let APA parser try

    # From the remainder, strip off the "Year;Vol:Pages..." tail to get "Title. Journal"
    m_yr_rem = re.search(r"\b(19|20)\d{2}\s*;", remainder)
    if not m_yr_rem:
        return None
    tj = remainder[:m_yr_rem.start()].rstrip(" .")

    # Split tj on the LAST sentence-terminator ([.!?] + space) — everything before is title,
    # everything after is journal. Handles titles ending with '?' before the journal.
    last_split = None
    for m in re.finditer(r"[.!?]\s+", tj):
        last_split = m
    if last_split:
        title_out = tj[:last_split.start()].strip()
        venue_out = tj[last_split.end():].strip()
    else:
        title_out = tj.strip() or None
        venue_out = None

    return {
        "id": i,
        "authors": _parse_authors_block(authors_str),
        "title": title_out,
        "year": year,
        "venue": venue_out,
        "doi": _extract_doi(raw),
        "url": None,
        "raw_text": raw,
    }


def _parse_apa_like(raw: str, i: int) -> dict:
    """Generic fallback for APA-ish formats (Author (Year). Title. Venue.) or unparseable entries.
    Always returns a citation dict — never None — so every entry gets SOMETHING in the output.
    """
    year_match = re.search(r"\b(19|20)\d{2}\b", raw)
    doi_val = _extract_doi(raw)

    authors_out: list[dict] = []
    title_out: str | None = None
    venue_out: str | None = None
    if year_match:
        ys, ye = year_match.span()
        author_block = raw[:ys].rstrip(" .,()")
        after_year = raw[ye:].lstrip(" ).,")
        title_match = re.match(r"((?:[^.]|(?<=\b[A-Z])\.)+?\.)\s", after_year + " ")
        if title_match:
            title_out = title_match.group(1).rstrip(".").strip()
            tail = after_year[title_match.end():].strip()
            venue_match = re.match(r"([^.]+?)(?:\.|$)", tail)
            if venue_match:
                venue_out = venue_match.group(1).strip()
        author_tokens = [t.strip() for t in re.split(r",\s*(?=[A-Z][a-z]|[A-Z]\.(?:\s|$))", author_block) if t.strip()]
        for tok in author_tokens:
            if tok.lower() in ("et al", "et al.", "and"):
                continue
            if "," in tok:
                fam, giv = tok.split(",", 1)
            else:
                parts = tok.split()
                fam, giv = (parts[-1], " ".join(parts[:-1])) if parts else ("", "")
            authors_out.append({"family": fam.strip().strip(".,"),
                                "given": giv.strip().strip(".,")})

    return {
        "id": i,
        "authors": authors_out,
        "title": title_out,
        "year": int(year_match.group(0)) if year_match else None,
        "venue": venue_out,
        "doi": doi_val,
        "url": None,
        "raw_text": raw,
    }


# --- step 3: per-citation verify (channel A + B → consensus) ---

def step3_verify_one(cit: dict, work_dir: Path, *, codex_available: bool, label_suffix: str = "") -> dict:
    """Run Stage 3 (Channel A + Channel B) for one citation.

    `label_suffix` distinguishes calls that share the same citation_id but query
    different content — currently used by Stage 4's re-verify to prevent
    fixture-path collision with the initial verify call. Empty string for the
    initial verify; "_reverify" when re-verifying a Stage-4 winner candidate.
    """
    # Channel A: deterministic API lookup
    api_out = subprocess.run(
        [sys.executable, str(PACKAGE_DIR / "api_verify.py"), "--citation-json", json.dumps(cit)],
        capture_output=True,
        text=True,
        check=False,
    )
    if api_out.returncode != 0:
        channel_a = {"verdict": "error", "reasons": [api_out.stderr.strip() or "api_verify.py failed"]}
    else:
        try:
            channel_a = json.loads(api_out.stdout)
        except json.JSONDecodeError as e:
            channel_a = {"verdict": "error", "reasons": [f"bad api_verify output: {e}"]}

    # Channel B: Codex atomic verify
    if codex_available:
        stage3_input = {
            "citation": cit,
            "api_evidence": channel_a,
        }
        in_file = work_dir / f"stage3_input_{cit['id']}{label_suffix}.json"
        in_file.write_text(json.dumps(stage3_input, ensure_ascii=False), encoding="utf-8")
        try:
            channel_b = _codex_atom(
                PROMPTS / "verify_citation.md",
                SCHEMAS / "verdict.schema.json",
                in_file,
                label=f"verify-{cit['id']}{label_suffix}",
            )
        except subprocess.CalledProcessError as e:
            channel_b = {"verdict": "error", "reasons": [f"codex failed: {e}"]}
    else:
        channel_b = {"verdict": "skipped", "reasons": ["codex not available — API-only mode"]}

    final_label = _reconcile(channel_a, channel_b)
    return {
        "citation_id": cit["id"],
        "citation": cit,
        "channel_a": channel_a,
        "channel_b": channel_b,
        "final_label": final_label,
    }


def _reconcile(a: dict, b: dict) -> str:
    """
    Consensus rules:
      - both valid → valid
      - both hallucinated / not_found → hallucinated
      - one valid, one hallucinated → uncertain (flag for human)
      - anything involving partially_valid → partially_valid
      - skipped / error in one channel → take the other, but mark confidence down to uncertain if that's not clear
    """
    # Normalize channel A's "not_found" to the skill's "hallucinated" vocabulary at the reconciliation layer.
    a_v = a.get("verdict", "error")
    b_v = b.get("verdict", "error")

    # If codex was skipped (api-only mode), defer to A
    if b_v == "skipped":
        if a_v == "valid":
            return "valid"
        if a_v == "partially_valid":
            return "partially_valid"
        if a_v == "not_found":
            return "hallucinated"
        return "uncertain"

    # Translate A's vocabulary to B's
    a_trans = {"not_found": "hallucinated", "valid": "valid",
               "partially_valid": "partially_valid", "error": "error"}.get(a_v, "uncertain")
    b_trans = b_v if b_v in ("valid", "partially_valid", "hallucinated", "uncertain") else "uncertain"

    if a_trans == b_trans and a_trans in ("valid", "partially_valid", "hallucinated"):
        return a_trans
    if "partially_valid" in (a_trans, b_trans) and "hallucinated" not in (a_trans, b_trans):
        return "partially_valid"
    if a_trans == "valid" and b_trans == "hallucinated":
        return "uncertain"
    if a_trans == "hallucinated" and b_trans == "valid":
        return "uncertain"
    # Everything else: uncertain
    return "uncertain"


# --- step 4: for each hallucinated citation, find a replacement ---

def step4_find_replacement(
    verdict_record: dict,
    full_text: str,
    work_dir: Path,
    *,
    codex_available: bool,
) -> dict:
    if not codex_available:
        return {
            "status": "skipped",
            "reason": "codex not available — replacement search requires codex",
        }

    cit = verdict_record["citation"]
    context = _extract_in_text_context(full_text, cit)

    # Stage 4a: find candidates
    stage4a_input = {
        "hallucinated_citation": cit,
        "original_context": context,
    }
    in_file = work_dir / f"stage4a_input_{cit['id']}.json"
    in_file.write_text(json.dumps(stage4a_input, ensure_ascii=False), encoding="utf-8")
    try:
        alts = _codex_atom(
            PROMPTS / "find_alternatives.md",
            SCHEMAS / "alternatives.schema.json",
            in_file,
            label=f"find-alts-{cit['id']}",
        )
    except subprocess.CalledProcessError as e:
        return {"status": "error", "reason": f"find_alternatives failed: {e}"}

    candidates = alts.get("candidates", [])
    if not candidates:
        return {"status": "no_suitable_replacement", "reason": alts.get("note", "no candidates returned")}

    # Stage 4b: score each candidate in parallel
    fit_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {}
        for cand in candidates:
            input_payload = {
                "original_context": context,
                "original_claim": _extract_claim(context),
                "candidate": cand,
            }
            f = work_dir / f"stage4b_input_{cit['id']}_{cand['rank']}.json"
            f.write_text(json.dumps(input_payload, ensure_ascii=False), encoding="utf-8")
            futures[ex.submit(_codex_atom,
                              PROMPTS / "score_context_fit.md",
                              SCHEMAS / "fit_score.schema.json",
                              f,
                              f"score-{cit['id']}-{cand['rank']}")] = cand
        for fut in concurrent.futures.as_completed(futures):
            cand = futures[fut]
            try:
                score = fut.result()
            except subprocess.CalledProcessError:
                continue
            fit_results.append({"candidate": cand, "fit": score})

    if not fit_results:
        return {"status": "error", "reason": "all fit-score calls failed"}

    # Pick the top candidate with fit_score >= 7
    fit_results.sort(key=lambda r: r["fit"].get("fit_score", 0), reverse=True)
    top = fit_results[0]
    if top["fit"].get("fit_score", 0) < 7:
        return {
            "status": "no_suitable_replacement",
            "reason": f"best candidate fit_score={top['fit'].get('fit_score')} < 7",
            "candidates_considered": fit_results,
        }

    # Stage 4c: re-verify the winner
    winner_as_citation = {
        "id": cit["id"],
        "authors": top["candidate"]["authors"],
        "title": top["candidate"]["title"],
        "year": top["candidate"].get("year"),
        "venue": top["candidate"].get("venue"),
        "doi": top["candidate"].get("doi"),
        "url": top["candidate"].get("url"),
        "raw_text": f"{top['candidate']['title']} ({top['candidate'].get('year')})",
    }
    reverify = step3_verify_one(winner_as_citation, work_dir, codex_available=codex_available, label_suffix="_reverify")
    if reverify["final_label"] != "valid":
        return {
            "status": "re_verification_failed",
            "reason": f"winning candidate re-verified as '{reverify['final_label']}'",
            "winner": top,
            "reverification": reverify,
            "candidates_considered": fit_results,
        }

    return {
        "status": "confirmed_replacement",
        "winner": top,
        "reverification": reverify,
        "candidates_considered": fit_results,
    }


def _extract_in_text_context(full_text: str, cit: dict, radius: int = 250) -> str:
    """Find the in-text citation marker and return surrounding text (±radius chars)."""
    markers = []
    if cit.get("id"):
        # Numbered style: [N]
        markers.append(f"[{cit['id']}]")
    # Author-year style: try first author family + year
    authors = cit.get("authors") or []
    year = cit.get("year")
    if authors and year:
        fam = authors[0].get("family") if isinstance(authors[0], dict) else str(authors[0])
        if fam:
            markers.append(f"{fam}, {year}")
            markers.append(f"{fam} {year}")
            markers.append(f"{fam} et al., {year}")
            markers.append(f"{fam} et al. {year}")

    for m in markers:
        idx = full_text.find(m)
        if idx >= 0:
            start = max(0, idx - radius)
            end = min(len(full_text), idx + len(m) + radius)
            return full_text[start:end]
    # Not found → give the first 500 chars of the document as fallback context
    return full_text[:500]


def _extract_claim(context: str) -> str:
    """Trivially extract the sentence containing the citation marker. Good enough for the LLM."""
    # Find the last sentence in the context; usually the citation sits at the sentence end.
    sents = re.split(r"(?<=[.!?])\s+", context)
    return sents[-1] if sents else context


# --- step 4b: build Stage 4b corrections.json (3-bucket structured output) ---

def _read_orchestrator_version() -> str:
    """Read orchestrator_version from the repo-root VERSION file. On miss or malformed
    contents, emit a stderr warning and fall back to a hardcoded default — never fall
    back silently. Once Cowork's Phase 1 VERSION file is in place this warning path is
    diagnostic-only; it should fire in real runs only if someone deleted or corrupted
    the file."""
    vfile = REPO_ROOT / "VERSION"
    fallback = "0.1.0"
    if not vfile.exists():
        sys.stderr.write(
            f"[warn] VERSION file not found at {vfile}; "
            f"falling back to orchestrator_version={fallback!r}. "
            f"Restore the file to silence this warning.\n"
        )
        return fallback
    try:
        val = vfile.read_text(encoding="utf-8").strip()
    except OSError as e:
        sys.stderr.write(
            f"[warn] could not read {vfile} ({e}); "
            f"falling back to orchestrator_version={fallback!r}\n"
        )
        return fallback
    if not re.match(r"^\d+\.\d+\.\d+$", val):
        sys.stderr.write(
            f"[warn] {vfile} contents {val!r} do not match semver ^\\d+\\.\\d+\\.\\d+$; "
            f"falling back to orchestrator_version={fallback!r}\n"
        )
        return fallback
    return val


def _detect_codex_model() -> str:
    env = os.environ.get("CODEX_MODEL")
    if env:
        return env
    cfg = Path.home() / ".codex" / "config.toml"
    if cfg.exists():
        try:
            for line in cfg.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s.startswith("[") and s.endswith("]"):
                    break  # first section header ends top-level scope
                m = re.match(r'^model\s*=\s*"([^"]+)"', s)
                if m:
                    return m.group(1)
        except OSError:
            pass
    return "codex-default"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_raw_record_url(source: str, rec: dict) -> str:
    doi = (rec.get("doi") or "").strip()
    if source == "crossref" and doi:
        return f"https://api.crossref.org/works/{doi}"
    if source == "openalex":
        return rec.get("url") or (f"https://api.openalex.org/works/doi:{doi}" if doi else "")
    if source == "semantic_scholar":
        return rec.get("url") or (f"https://doi.org/{doi}" if doi else "")
    return rec.get("url") or ""


def _build_canonical_record(source: str | None, rec: dict | None) -> dict | None:
    """Construct a canonical_record dict conforming to corrections.schema.json.
    Returns None if the source is not a Channel A enum value, the record is missing,
    or required fields (doi, title) cannot be populated. Callers should route such
    citations to the unresolvable bucket — never fabricate a canonical record."""
    if source not in API_SOURCES_ENABLED:
        return None
    if not rec:
        return None
    doi = (rec.get("doi") or "").strip()
    title = (rec.get("title") or "").strip()
    if not doi or not title:
        return None
    raw_url = _build_raw_record_url(source, rec)
    if not raw_url:
        return None
    authors = [
        {"family": (a.get("family") or "").strip(), "given": (a.get("given") or "").strip()}
        for a in (rec.get("authors") or [])
    ]
    venue = rec.get("venue")
    venue = venue.strip() if isinstance(venue, str) and venue.strip() else None
    human_url = rec.get("url") or None
    return {
        "source": source,
        "raw_record_url": raw_url,
        "doi": doi,
        "title": title,
        "authors": authors,
        "year": rec.get("year"),
        "venue": venue,
        "volume": None,
        "issue": None,
        "page": None,
        "url": human_url,
    }


def _make_unresolvable(citation_id: int, reason: str, channel_a: dict, channel_b: dict) -> dict:
    """Build an unresolvable entry. reason MUST start with a snake_case tag + ': '."""
    if not re.match(r"^[a-z][a-z0-9_]*: .+", reason):
        reason = f"untagged: {reason}"
    ch_a_guess = None
    if channel_a:
        rec = channel_a.get("matched_record")
        if rec:
            ch_a_guess = {
                "matched_source": channel_a.get("matched_source"),
                "record": rec,
                "title_similarity": channel_a.get("title_similarity"),
                "author_overlap": channel_a.get("author_overlap"),
                "title_similarity_raw": channel_a.get("title_similarity_raw"),
                "author_overlap_raw": channel_a.get("author_overlap_raw"),
                "doi_exact_match": channel_a.get("doi_exact_match"),
            }
    ch_b_guess = None
    if channel_b:
        b_verdict = channel_b.get("verdict")
        b_expl = channel_b.get("explanation")
        b_ident = channel_b.get("matched_identifier")
        if b_verdict or b_expl or b_ident:
            ch_b_guess = {
                "verdict": b_verdict,
                "explanation": b_expl,
                "matched_identifier": b_ident,
                "mismatches": channel_b.get("mismatches", []),
            }
    return {
        "citation_id": citation_id,
        "reason": reason,
        "channel_a_best_guess": ch_a_guess,
        "channel_b_best_guess": ch_b_guess,
    }


def _has_critical_high_diff(field_diff: list[dict]) -> bool:
    """Return True if `field_diff` contains any high-severity entry on a
    citation-integrity-critical field (title / doi / year). Used as a
    deterministic backstop on requires_human_review so a model regression
    cannot let an obvious red-flag through."""
    for d in field_diff or []:
        if d.get("field") in CRITICAL_REVIEW_FIELDS and d.get("severity") == "high":
            return True
    return False


def _classify_uncertain(channel_a: dict, channel_b: dict) -> tuple[str, str]:
    """Return (tag, detail) for a Stage-3 uncertain verdict, ready for unresolvable.reason."""
    a_v = channel_a.get("verdict", "error") if channel_a else "error"
    b_v = channel_b.get("verdict", "error") if channel_b else "error"
    if b_v == "skipped":
        return "channel_b_skipped", "Channel B unavailable; Channel A alone insufficient for a confident verdict"
    if a_v == "error" or b_v == "error":
        return "channel_error", f"A={a_v} B={b_v}; see channel records for context"
    if a_v == "not_found" and b_v in ("valid", "partially_valid"):
        return "channel_b_only_no_a_match", "Channel B asserts a match but no Channel A source confirmed it"
    if a_v in ("valid", "partially_valid") and b_v == "hallucinated":
        return "channel_disagreement", "Channel A matched a record but Channel B rejected it as hallucinated"
    return "channel_disagreement", f"Channel A verdict={a_v}, Channel B verdict={b_v}"


def step4b_build_corrections(
    verdicts: list[dict],
    replacements_by_id: dict[int, dict],
    input_path: Path,
    work_dir: Path,
    *,
    codex_available: bool,
    max_workers: int = 4,
) -> dict:
    """Consume Stage 3 verdicts + Stage 4 replacements and emit the 3-bucket structured
    output (corrections / replacements / unresolvable) plus a meta block. Invariant #6:
    canonical_record.source is always one of Channel A's three APIs — if a Stage 3
    bucket can't yield one, the citation goes to unresolvable. Invariant #7: Stage 3's
    final_label is the source of truth for bucketing; 4b does not re-classify."""
    corrections: list[dict] = []
    replacements_out: list[dict] = []
    unresolvable: list[dict] = []
    correction_jobs: list[tuple[dict, dict, int]] = []

    for v in verdicts:
        label = v.get("final_label")
        cit = v.get("citation", {})
        cid = v.get("citation_id", cit.get("id"))
        channel_a = v.get("channel_a", {}) or {}
        channel_b = v.get("channel_b", {}) or {}

        if label == "valid":
            continue

        if label == "partially_valid":
            cr = _build_canonical_record(channel_a.get("matched_source"),
                                         channel_a.get("matched_record"))
            if cr is None:
                unresolvable.append(_make_unresolvable(
                    cid,
                    "channel_a_no_canonical_record: partially_valid but Channel A match was absent or missing required fields",
                    channel_a, channel_b))
                continue
            correction_jobs.append((cit, cr, cid))
            continue

        if label == "hallucinated":
            rep = replacements_by_id.get(cid)
            status = (rep or {}).get("status")
            if status == "confirmed_replacement":
                winner = rep["winner"]
                reverify = rep["reverification"]
                rev_a = reverify.get("channel_a", {}) or {}
                cr = _build_canonical_record(rev_a.get("matched_source"),
                                             rev_a.get("matched_record"))
                if cr is None:
                    unresolvable.append(_make_unresolvable(
                        cid,
                        "replacement_canonical_missing: re-verification passed but no Channel A canonical record captured",
                        channel_a, channel_b))
                    continue
                replacements_out.append({
                    "citation_id": cid,
                    "original_citation": cit,
                    "canonical_record": cr,
                    "fit_score": int(winner.get("fit", {}).get("fit_score", 0)),
                    "confidence": float(rev_a.get("confidence", 0.0)),
                })
                continue
            tag_map = {
                None: "no_replacement_attempted",
                "skipped": "replacement_search_skipped",
                "no_suitable_replacement": "no_suitable_replacement",
                "re_verification_failed": "replacement_reverify_failed",
                "error": "replacement_search_error",
            }
            tag = tag_map.get(status, "no_suitable_replacement")
            detail = (rep or {}).get("reason") or "no replacement found for hallucinated citation"
            unresolvable.append(_make_unresolvable(
                cid, f"{tag}: {detail}", channel_a, channel_b))
            continue

        if label == "uncertain":
            tag, detail = _classify_uncertain(channel_a, channel_b)
            unresolvable.append(_make_unresolvable(
                cid, f"{tag}: {detail}", channel_a, channel_b))
            continue

        unresolvable.append(_make_unresolvable(
            cid,
            f"unexpected_label: Stage 3 verdict '{label}' has no 4b handler",
            channel_a, channel_b))

    if correction_jobs:
        if not codex_available:
            for cit, cr, cid in correction_jobs:
                unresolvable.append(_make_unresolvable(
                    cid,
                    "codex_unavailable: correction diff requires Codex",
                    {"matched_source": cr["source"], "matched_record": cr}, {}))
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futs = {}
                for cit, cr, cid in correction_jobs:
                    payload = {"original_citation": cit, "canonical_record": cr}
                    p = work_dir / f"stage4b_input_{cid}.json"
                    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                    futs[ex.submit(_codex_atom,
                                   PROMPTS / "build_correction.md",
                                   SCHEMAS / "correction_diff.schema.json",
                                   p,
                                   f"build-correction-{cid}")] = (cit, cr, cid)
                for fut in concurrent.futures.as_completed(futs):
                    cit, cr, cid = futs[fut]
                    try:
                        diff_out = fut.result()
                    except Exception as e:
                        unresolvable.append(_make_unresolvable(
                            cid,
                            f"correction_build_failed: {e.__class__.__name__}: {e}",
                            {"matched_source": cr["source"], "matched_record": cr}, {}))
                        continue
                    field_diff = diff_out.get("field_diff", [])
                    codex_review = bool(diff_out.get("requires_human_review", False))
                    review = codex_review or _has_critical_high_diff(field_diff)
                    corrections.append({
                        "citation_id": cid,
                        "original_citation": cit,
                        "canonical_record": cr,
                        "field_diff": field_diff,
                        "confidence": float(diff_out.get("confidence", 0.0)),
                        "requires_human_review": review,
                    })

    corrections.sort(key=lambda x: x["citation_id"])
    replacements_out.sort(key=lambda x: x["citation_id"])
    unresolvable.sort(key=lambda x: x["citation_id"])

    valid_citation_ids = sorted({
        int(v["citation_id"])
        for v in verdicts
        if v.get("final_label") == "valid" and v.get("citation_id") is not None
    })
    meta = {
        "schema_version": SCHEMA_VERSION,
        "orchestrator_version": _read_orchestrator_version(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_doc_sha256": _sha256_file(input_path),
        "input_doc_filename": input_path.name,
        "codex_model": _detect_codex_model(),
        "api_sources_enabled": list(API_SOURCES_ENABLED),
        "valid_citation_ids": valid_citation_ids,
    }
    return {
        "meta": meta,
        "corrections": corrections,
        "replacements": replacements_out,
        "unresolvable": unresolvable,
    }


# --- codex invocation ---

def _is_codex_available() -> bool:
    from shutil import which
    return which("codex") is not None


def _codex_atom(prompt: Path, schema: Path, input_file: Path, label: str) -> dict:
    """Call src/citation_verify/codex_atom.sh and return parsed JSON."""
    result = subprocess.run(
        [str(PACKAGE_DIR / "codex_atom.sh"), str(prompt), str(schema), str(input_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(f"[codex_atom:{label}] failed: {result.stderr.strip()}\n")
        raise subprocess.CalledProcessError(result.returncode, "codex_atom.sh", output=result.stdout, stderr=result.stderr)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[codex_atom:{label}] bad json: {e}\n{result.stdout[:500]}\n")
        raise


# --- main ---

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="Path to .pdf or .docx")
    ap.add_argument("--output-dir", default=None, help="Where to write outputs (default: <input>.citation-verify/)")
    ap.add_argument("--parallel", type=int, default=4, help="Max parallel workers for verification (default 4)")
    ap.add_argument("--limit", type=int, default=None, help="Stop after N citations (debug)")
    ap.add_argument("--api-only", action="store_true", help="Skip all codex calls, use only API verification")
    ap.add_argument("--no-replace", action="store_true", help="Do not search for replacements for hallucinated citations")
    args = ap.parse_args()

    _check_python_deps()
    codex_available = not args.api_only and _is_codex_available()
    if args.api_only:
        sys.stderr.write("[info] --api-only: skipping all codex calls\n")
    elif not codex_available:
        sys.stderr.write("[warn] codex CLI not found. Running in API-only fallback mode.\n")

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        sys.stderr.write(f"ERROR: input not found: {input_path}\n")
        return 1

    out_dir = Path(args.output_dir) if args.output_dir else input_path.parent / f"{input_path.stem}.citation-verify"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / "_work"
    work_dir.mkdir(exist_ok=True)

    sys.stderr.write(f"[1/6] parsing document: {input_path.name}\n")
    parsed = step1_parse_doc(input_path, work_dir)
    if parsed.get("warnings"):
        for w in parsed["warnings"]:
            sys.stderr.write(f"    warning: {w}\n")

    sys.stderr.write("[2/6] atomizing citations\n")
    atomized = step2_atomize_citations(parsed, work_dir, codex_available=codex_available)
    citations = atomized.get("citations", [])
    if args.limit:
        citations = citations[: args.limit]
    (out_dir / "citations.json").write_text(json.dumps(atomized, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stderr.write(f"    {len(citations)} citations parsed\n")
    if not citations:
        sys.stderr.write("    no citations to verify — done.\n")
        return 0

    sys.stderr.write(f"[3/6] verifying {len(citations)} citations (parallel={args.parallel})\n")
    verdicts: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futures = {ex.submit(step3_verify_one, cit, work_dir, codex_available=codex_available): cit for cit in citations}
        for fut in concurrent.futures.as_completed(futures):
            v = fut.result()
            verdicts.append(v)
            sys.stderr.write(f"    [#{v['citation_id']}] {v['final_label']}\n")
    verdicts.sort(key=lambda r: r["citation_id"])
    (out_dir / "verdicts.json").write_text(json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8")

    replacements: list[dict] = []
    if not args.no_replace:
        hallucinated = [v for v in verdicts if v["final_label"] == "hallucinated"]
        sys.stderr.write(f"[4/6] finding replacements for {len(hallucinated)} hallucinated citations\n")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futures = {
                ex.submit(step4_find_replacement, v, parsed["full_text"], work_dir,
                          codex_available=codex_available): v
                for v in hallucinated
            }
            for fut in concurrent.futures.as_completed(futures):
                v = futures[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    r = {"status": "error", "reason": str(e)}
                replacements.append({"citation_id": v["citation_id"], **r})
                sys.stderr.write(f"    [#{v['citation_id']}] replacement: {r.get('status', 'error')}\n")
    replacements.sort(key=lambda r: r["citation_id"])
    (out_dir / "replacements.json").write_text(json.dumps(replacements, ensure_ascii=False, indent=2), encoding="utf-8")

    sys.stderr.write("[5/6] building Stage 4b corrections.json\n")
    replacements_by_id = {r["citation_id"]: r for r in replacements}
    corrections_obj = step4b_build_corrections(
        verdicts,
        replacements_by_id,
        input_path,
        work_dir,
        codex_available=codex_available,
        max_workers=args.parallel,
    )
    (out_dir / "corrections.json").write_text(
        json.dumps(corrections_obj, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sys.stderr.write(
        f"    corrections={len(corrections_obj['corrections'])} "
        f"replacements={len(corrections_obj['replacements'])} "
        f"unresolvable={len(corrections_obj['unresolvable'])}\n"
    )

    sys.stderr.write("[6/6] rendering report\n")
    render = subprocess.run(
        [sys.executable, str(PACKAGE_DIR / "render_report.py"),
         "--verdicts", str(out_dir / "verdicts.json"),
         "--replacements", str(out_dir / "replacements.json"),
         "--source", str(input_path),
         "--out", str(out_dir / "report.md")],
        capture_output=True, text=True, check=False,
    )
    if render.returncode != 0:
        sys.stderr.write(f"    render_report.py failed: {render.stderr}\n")
    else:
        sys.stderr.write(f"    wrote {out_dir / 'report.md'}\n")

    sys.stderr.write(f"\nDone. Outputs in: {out_dir}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
