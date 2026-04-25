#!/usr/bin/env bash
# verify.sh — one-command launcher for the citation-verify skill.
#
# First run: auto-creates a .venv/ inside this folder, installs deps, checks codex.
# Every run:  activates the venv and forwards everything to src/citation_verify/orchestrate.py.
#
# Usage:
#   ./verify.sh <input.pdf|input.docx> [orchestrator-flags...]
#   ./verify.sh --setup              # run setup only, don't process anything
#   ./verify.sh --doctor             # diagnose install problems
#   ./verify.sh --help               # show this help and orchestrator help
#
# You don't need to `source` anything — the script handles the venv internally.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HERE/.venv"
REQS="$HERE/requirements.txt"
ORCH="$HERE/src/citation_verify/orchestrate.py"
READY_MARKER="$VENV/.deps-installed"

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info()  { color "36" "[verify.sh] $1"; }
ok()    { color "32" "[verify.sh] $1"; }
warn()  { color "33" "[verify.sh] $1"; }
err()   { color "31" "[verify.sh] $1" >&2; }

# ---------- python discovery ----------
find_python() {
    for cand in python3 python3.12 python3.11 python3.10 python3.9 python; do
        if command -v "$cand" >/dev/null 2>&1; then
            v=$("$cand" -c 'import sys; print(sys.version_info[0]*10+sys.version_info[1])' 2>/dev/null || echo 0)
            if [[ "$v" -ge 39 ]]; then
                echo "$cand"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_BIN="$(find_python || true)"

if [[ -z "$PYTHON_BIN" ]]; then
    err "No Python 3.9+ found on PATH."
    err "Install Python via Homebrew (brew install python) then re-run this script."
    exit 1
fi

# ---------- setup ----------
ensure_venv() {
    # Detect a stale venv whose shebang points to a python that no longer exists
    # (e.g. venv was created under a different path / on a different machine).
    if [[ -d "$VENV" ]]; then
        if [[ ! -x "$VENV/bin/python" && ! -x "$VENV/bin/python3" ]]; then
            warn "existing .venv/ looks broken (no working python inside). Rebuilding."
            rm -rf "$VENV"
        elif ! "$VENV/bin/python" -c 'import sys' >/dev/null 2>&1; then
            warn "existing .venv/ python can't execute (stale path?). Rebuilding."
            rm -rf "$VENV"
        fi
    fi
    if [[ ! -d "$VENV" ]]; then
        info "creating virtual env at .venv/"
        "$PYTHON_BIN" -m venv "$VENV"
    fi
}

ensure_deps() {
    ensure_venv
    # If requirements.txt newer than marker, reinstall.
    if [[ -f "$READY_MARKER" && "$READY_MARKER" -nt "$REQS" ]]; then
        return
    fi
    # Verify venv has pip; on some Linux distros venv ships without ensurepip.
    if [[ ! -x "$VENV/bin/pip" ]]; then
        err "venv was created but has no pip binary."
        err "On Debian/Ubuntu: sudo apt install python3-venv"
        err "On macOS with Homebrew Python, this should never happen — please report."
        exit 1
    fi
    info "installing Python dependencies (first run, ~20 seconds)"
    # Use the venv's pip directly — no activation needed.
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$REQS"
    touch "$READY_MARKER"
    ok "dependencies installed"
}

check_codex() {
    if command -v codex >/dev/null 2>&1; then
        ok "codex CLI found: $(codex --version 2>&1 | head -1)"
    else
        warn "codex CLI not found. The skill will work in --api-only mode (reduced accuracy)."
        warn "Install codex from: https://developers.openai.com/codex/cli"
    fi
}

check_s2_key() {
    if [[ -n "${SEMANTIC_SCHOLAR_API_KEY:-}" ]]; then
        ok "SEMANTIC_SCHOLAR_API_KEY is set (5x faster Channel A lookups)"
    else
        info "SEMANTIC_SCHOLAR_API_KEY not set (optional; free at semanticscholar.org/product/api)"
    fi
}

doctor() {
    echo ""
    color "1;36" "=== citation-verify doctor ==="
    echo ""
    info "python: $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"
    info "venv:   $VENV $([[ -d "$VENV" ]] && echo '(exists)' || echo '(missing)')"
    info "deps:   $([[ -f "$READY_MARKER" ]] && echo 'installed' || echo 'NOT installed — run --setup')"
    check_codex
    check_s2_key
    echo ""
    info "skill root: $HERE"
    info "orchestrator: $ORCH"
    if [[ -f "$READY_MARKER" ]]; then
        info "testing imports..."
        "$VENV/bin/python" -c "import pdfplumber, docx, requests, rapidfuzz; print('all imports OK')" \
            && ok "dependency sanity check passed" \
            || err "dependency sanity check FAILED — try --setup to reinstall"
    fi
    echo ""
}

# ---------- dispatch ----------
if [[ $# -eq 0 ]]; then
    err "no arguments. Try: ./verify.sh path/to/paper.pdf"
    err "or:                ./verify.sh --setup | --doctor | --help"
    exit 64
fi

case "${1:-}" in
    --setup)
        ensure_deps
        check_codex
        check_s2_key
        ok "setup complete. Now run: ./verify.sh path/to/paper.pdf"
        exit 0
        ;;
    --doctor)
        doctor
        exit 0
        ;;
    --help|-h)
        head -14 "$0" | grep -v '^#!'
        echo ""
        if [[ -f "$READY_MARKER" ]]; then
            "$VENV/bin/python" "$ORCH" --help
        fi
        exit 0
        ;;
esac

# Regular run: make sure env is ready, then forward to orchestrator.
ensure_deps
exec "$VENV/bin/python" "$ORCH" "$@"
