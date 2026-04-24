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
  5. Render report + optionally patch document         (render_report.py)

Never calls `codex resume`. Every Codex invocation is one-shot.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROMPTS = SKILL_ROOT / "prompts"
SCHEMAS = SKILL_ROOT / "schemas"

# --- dependency check ---

REQUIRED = {
    "pdfplumber": "pdfplumber",
    "docx": "python-docx",
    "requests": "requests",
    "rapidfuzz": "rapidfuzz",
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
        [sys.executable, str(SCRIPT_DIR / "parse_doc.py"), str(input_path), "--out", str(parse_out)],
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

def step3_verify_one(cit: dict, work_dir: Path, *, codex_available: bool) -> dict:
    # Channel A: deterministic API lookup
    api_out = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "api_verify.py"), "--citation-json", json.dumps(cit)],
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
        in_file = work_dir / f"stage3_input_{cit['id']}.json"
        in_file.write_text(json.dumps(stage3_input, ensure_ascii=False), encoding="utf-8")
        try:
            channel_b = _codex_atom(
                PROMPTS / "verify_citation.md",
                SCHEMAS / "verdict.schema.json",
                in_file,
                label=f"verify-{cit['id']}",
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
    reverify = step3_verify_one(winner_as_citation, work_dir, codex_available=codex_available)
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


# --- codex invocation ---

def _is_codex_available() -> bool:
    from shutil import which
    return which("codex") is not None


def _codex_atom(prompt: Path, schema: Path, input_file: Path, label: str) -> dict:
    """Call scripts/codex_atom.sh and return parsed JSON."""
    result = subprocess.run(
        [str(SCRIPT_DIR / "codex_atom.sh"), str(prompt), str(schema), str(input_file)],
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

    sys.stderr.write(f"[1/5] parsing document: {input_path.name}\n")
    parsed = step1_parse_doc(input_path, work_dir)
    if parsed.get("warnings"):
        for w in parsed["warnings"]:
            sys.stderr.write(f"    warning: {w}\n")

    sys.stderr.write("[2/5] atomizing citations\n")
    atomized = step2_atomize_citations(parsed, work_dir, codex_available=codex_available)
    citations = atomized.get("citations", [])
    if args.limit:
        citations = citations[: args.limit]
    (out_dir / "citations.json").write_text(json.dumps(atomized, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stderr.write(f"    {len(citations)} citations parsed\n")
    if not citations:
        sys.stderr.write("    no citations to verify — done.\n")
        return 0

    sys.stderr.write(f"[3/5] verifying {len(citations)} citations (parallel={args.parallel})\n")
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
        sys.stderr.write(f"[4/5] finding replacements for {len(hallucinated)} hallucinated citations\n")
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

    sys.stderr.write("[5/5] rendering report\n")
    render = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "render_report.py"),
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
