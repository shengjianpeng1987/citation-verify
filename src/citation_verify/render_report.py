#!/usr/bin/env python3
"""
render_report.py — Turn verdicts.json + replacements.json into a human-readable report.

Outputs Markdown by default. Future extensions: --format docx (via python-docx).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


STATUS_EMOJI = {
    "valid": "OK",
    "partially_valid": "PARTIAL",
    "hallucinated": "FAKE",
    "uncertain": "?",
    "skipped": "-",
    "error": "ERR",
}


def _fmt_authors(authors: list) -> str:
    if not authors:
        return "(no authors)"
    parts = []
    for a in authors[:4]:
        if isinstance(a, dict):
            fam = a.get("family", "")
            giv = a.get("given", "")
            parts.append((fam + ", " + giv).strip(", "))
        else:
            parts.append(str(a))
    out = "; ".join(parts)
    if len(authors) > 4:
        out += f" et al. (+{len(authors)-4})"
    return out


def _fmt_citation(cit: dict) -> str:
    title = cit.get("title") or "(no title)"
    year = cit.get("year") or "?"
    venue = cit.get("venue") or ""
    doi = cit.get("doi")
    line = f"{_fmt_authors(cit.get('authors') or [])}. ({year}). *{title}*."
    if venue:
        line += f" {venue}."
    if doi:
        line += f" doi:{doi}"
    return line


def render(verdicts: list, replacements: list, source: str) -> str:
    rep_by_id = {r["citation_id"]: r for r in replacements}

    lines = []
    lines.append(f"# Citation verification report")
    lines.append("")
    lines.append(f"**Source:** `{source}`")
    lines.append(f"**Total citations checked:** {len(verdicts)}")
    counts = {}
    for v in verdicts:
        counts[v["final_label"]] = counts.get(v["final_label"], 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    lines.append(f"**Summary:** {summary}")
    lines.append("")

    # Summary table
    lines.append("## At a glance")
    lines.append("")
    lines.append("| # | Label | Citation (abbreviated) | Replacement |")
    lines.append("|---|-------|------------------------|-------------|")
    for v in verdicts:
        cit = v["citation"]
        label = v["final_label"]
        emoji = STATUS_EMOJI.get(label, "?")
        short = (cit.get("title") or cit.get("raw_text") or "")[:80].replace("|", r"\|")
        rep = rep_by_id.get(v["citation_id"])
        rep_text = "—"
        if rep:
            if rep.get("status") == "confirmed_replacement":
                win = rep["winner"]["candidate"]
                rep_text = f"[{STATUS_EMOJI['valid']}] {(win.get('title') or '')[:60]}"
            elif rep.get("status") == "no_suitable_replacement":
                rep_text = "none suitable"
            else:
                rep_text = rep.get("status", "—")
        lines.append(f"| {v['citation_id']} | {emoji} {label} | {short} | {rep_text} |")
    lines.append("")

    # Per-citation details
    lines.append("## Per-citation detail")
    lines.append("")
    for v in verdicts:
        cit = v["citation"]
        label = v["final_label"]
        lines.append(f"### [#{v['citation_id']}] {STATUS_EMOJI.get(label,'?')} {label}")
        lines.append("")
        lines.append(f"**Original:** {_fmt_citation(cit)}")
        lines.append("")
        lines.append("**Raw bibliography text:**")
        lines.append("")
        lines.append(f"> {cit.get('raw_text', '')}")
        lines.append("")
        # Channel A detail
        a = v.get("channel_a", {})
        lines.append(f"**Channel A (Crossref/OpenAlex/Semantic Scholar):** `{a.get('verdict','?')}` — confidence {a.get('confidence', 0)}")
        if a.get("matched_source"):
            lines.append(f"- Matched via: **{a['matched_source']}**")
        if a.get("matched_record"):
            mr = a["matched_record"]
            lines.append(f"- Match: {_fmt_citation(mr)}")
        if a.get("reasons"):
            for r in a["reasons"]:
                lines.append(f"- {r}")
        lines.append("")
        # Channel B detail
        b = v.get("channel_b", {})
        lines.append(f"**Channel B (Codex atomic verify):** `{b.get('verdict','?')}` — confidence {b.get('confidence', '?')}")
        if b.get("explanation"):
            lines.append(f"- {b['explanation']}")
        if b.get("mismatches"):
            for m in b["mismatches"]:
                lines.append(f"- mismatch: {m}")
        lines.append("")

        # Replacement
        rep = rep_by_id.get(v["citation_id"])
        if rep:
            lines.append("**Replacement search:**")
            status = rep.get("status", "—")
            lines.append(f"- Status: `{status}`")
            if status == "confirmed_replacement":
                win = rep["winner"]
                c = win["candidate"]
                fit = win["fit"]
                lines.append(f"- **Winner:** {_fmt_citation(c)}")
                lines.append(f"- Fit score: **{fit.get('fit_score')}/10** — {fit.get('rationale', '')}")
                lines.append(f"- Why: {c.get('relevance_note', '')}")
            elif status == "no_suitable_replacement":
                lines.append(f"- Reason: {rep.get('reason', '')}")
                for c in rep.get("candidates_considered", [])[:3]:
                    lines.append(f"  - considered: {c['candidate'].get('title')} (fit={c['fit'].get('fit_score')})")
            else:
                lines.append(f"- Reason: {rep.get('reason', '')}")
        lines.append("")

    # Action items
    lines.append("## Action items")
    lines.append("")
    hallucinated_with_fix = [v for v in verdicts if v["final_label"] == "hallucinated"
                             and rep_by_id.get(v["citation_id"], {}).get("status") == "confirmed_replacement"]
    hallucinated_without_fix = [v for v in verdicts if v["final_label"] == "hallucinated"
                                and rep_by_id.get(v["citation_id"], {}).get("status") != "confirmed_replacement"]
    uncertain = [v for v in verdicts if v["final_label"] == "uncertain"]

    if hallucinated_with_fix:
        lines.append(f"### {len(hallucinated_with_fix)} hallucinated citation(s) have a confirmed replacement — review and apply")
        for v in hallucinated_with_fix:
            rep = rep_by_id[v["citation_id"]]
            c = rep["winner"]["candidate"]
            lines.append(f"- [#{v['citation_id']}] replace with: {c.get('title')} (doi:{c.get('doi')})")
        lines.append("")
    if hallucinated_without_fix:
        lines.append(f"### {len(hallucinated_without_fix)} hallucinated citation(s) — no suitable replacement found")
        for v in hallucinated_without_fix:
            lines.append(f"- [#{v['citation_id']}] {v['citation'].get('title') or v['citation'].get('raw_text','')[:80]}")
        lines.append("")
    if uncertain:
        lines.append(f"### {len(uncertain)} uncertain citation(s) — channels disagree; human judgment needed")
        for v in uncertain:
            a = v["channel_a"].get("verdict", "?")
            b = v["channel_b"].get("verdict", "?")
            lines.append(f"- [#{v['citation_id']}] channel A: `{a}` vs channel B: `{b}` — {v['citation'].get('title') or ''}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--replacements", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", default=None, help="Output path (default stdout)")
    args = ap.parse_args()

    verdicts = json.loads(Path(args.verdicts).read_text(encoding="utf-8"))
    replacements = json.loads(Path(args.replacements).read_text(encoding="utf-8"))
    report = render(verdicts, replacements, args.source)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
