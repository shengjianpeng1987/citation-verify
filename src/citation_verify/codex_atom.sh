#!/usr/bin/env bash
# codex_atom.sh — Invoke `codex exec` atomically: ephemeral, schema-constrained, JSON output.
#
# Why this wrapper exists:
#   Every atomic task in the citation-verify skill must be a fresh one-shot run of codex.
#   NO `codex resume`. NO session reuse. Atomization is the whole point — it lets us
#   parallelize safely, keep contexts clean, and fail one task without poisoning the rest.
#
# Usage:
#   codex_atom.sh <prompt_file> <schema_file> [input_json_file]
#
# - <prompt_file>: path to a markdown/text prompt template. The template may contain
#                  the literal placeholder __INPUT_JSON__; if present and input_json_file
#                  is given, that placeholder is replaced with the file's contents.
# - <schema_file>: path to a JSON schema file that the final output must conform to.
#                  Passed to codex via --output-schema.
# - [input_json_file]: optional. If provided, its contents are spliced into the prompt.
#                      If not provided, the prompt is used as-is.
#
# Environment variables:
#   CODEX_MODEL        Override default model (optional).
#   CODEX_TIMEOUT      Kill codex after this many seconds (default 120).
#   CITATION_VERIFY_DEBUG=1  Echo the final command and prompt to stderr.
#
# Output:
#   On success: the model's final message, parsed as JSON, to stdout.
#   On failure: non-zero exit code, error message to stderr.

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: codex_atom.sh <prompt_file> <schema_file> [input_json_file]" >&2
    exit 64
fi

PROMPT_FILE="$1"
SCHEMA_FILE="$2"
INPUT_FILE="${3:-}"

if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "ERROR: prompt file not found: $PROMPT_FILE" >&2
    exit 66
fi
if [[ ! -f "$SCHEMA_FILE" ]]; then
    echo "ERROR: schema file not found: $SCHEMA_FILE" >&2
    exit 66
fi

if ! command -v codex >/dev/null 2>&1; then
    echo "ERROR: codex CLI not found on PATH. Install codex first: https://developers.openai.com/codex/cli" >&2
    exit 69
fi

TIMEOUT="${CODEX_TIMEOUT:-120}"

# Build the final prompt by splicing input_json into the template if requested.
PROMPT_CONTENT="$(cat "$PROMPT_FILE")"
if [[ -n "$INPUT_FILE" ]]; then
    if [[ ! -f "$INPUT_FILE" ]]; then
        echo "ERROR: input json file not found: $INPUT_FILE" >&2
        exit 66
    fi
    INPUT_CONTENT="$(cat "$INPUT_FILE")"
    # Export BEFORE the python subprocess so it can see the vars.
    export PROMPT_CONTENT INPUT_CONTENT
    # Use python to do a safe literal replace — avoids sed's trouble with special chars.
    PROMPT_CONTENT="$(python3 - <<'PYEOF'
import os, sys
prompt = os.environ["PROMPT_CONTENT"]
inp    = os.environ["INPUT_CONTENT"]
if "__INPUT_JSON__" in prompt:
    sys.stdout.write(prompt.replace("__INPUT_JSON__", inp))
else:
    sys.stdout.write(prompt + "\n\n## Input\n\n```json\n" + inp + "\n```\n")
PYEOF
)"
    export PROMPT_CONTENT
fi

# Assemble codex command. Global flags go AFTER the subcommand (per codex 2026 CLI changes).
CODEX_ARGS=(
    exec
    --ephemeral                    # do not persist rollout files
    --json                         # newline-delimited JSON events
    --sandbox read-only            # this skill never needs write access
    --skip-git-repo-check          # don't require the skill folder to be a git repo
    --output-schema "$SCHEMA_FILE" # enforce structured output
)
if [[ -n "${CODEX_MODEL:-}" ]]; then
    CODEX_ARGS+=(--model "$CODEX_MODEL")
fi
CODEX_ARGS+=(-)  # read prompt from stdin

if [[ "${CITATION_VERIFY_DEBUG:-0}" = "1" ]]; then
    echo "--- codex command: codex ${CODEX_ARGS[*]}" >&2
    echo "--- prompt (first 500 chars):" >&2
    echo "${PROMPT_CONTENT:0:500}" >&2
    echo "--- end prompt preview" >&2
fi

# Run codex with the prompt piped into stdin, capture stdout (JSON events), and extract the final message.
# --json emits one JSON event per line; the final message event has type "message" or "agent_message".
# Capture stderr to a temp file so failures surface with context instead of being silently swallowed.
CODEX_STDERR="$(mktemp -t codex_atom_stderr.XXXXXX)"
trap 'rm -f "$CODEX_STDERR"' EXIT
RAW_EVENTS=$(printf '%s' "$PROMPT_CONTENT" | timeout "$TIMEOUT" codex "${CODEX_ARGS[@]}" 2>"$CODEX_STDERR") || {
    rc=$?
    echo "ERROR: codex exec failed (exit $rc)." >&2
    if [[ -s "$CODEX_STDERR" ]]; then
        echo "--- codex stderr ---" >&2
        sed -n '1,60p' "$CODEX_STDERR" >&2
        echo "--- end codex stderr ---" >&2
    else
        echo "(codex produced no stderr output)" >&2
    fi
    # codex emits error events on stdout as JSON; surface them too.
    if [[ -n "$RAW_EVENTS" ]]; then
        echo "--- codex event stream (last 40 lines) ---" >&2
        printf '%s\n' "$RAW_EVENTS" | tail -40 >&2
        echo "--- end event stream ---" >&2
    fi
    echo "Re-run with CITATION_VERIFY_DEBUG=1 to see the full prompt." >&2
    exit "$rc"
}

# Always save the raw event stream to a tmp file — makes parsing failures diagnosable.
EVENTS_DUMP="$(mktemp -t codex_atom_events.XXXXXX).jsonl"
printf '%s\n' "$RAW_EVENTS" > "$EVENTS_DUMP"

# Parse the event stream via the companion python script (separate file to dodge
# bash's heredoc-in-$(...) tokenizer quirks with embedded backticks).
PARSER="$(dirname "$0")/_parse_codex_events.py"
set +e
FINAL_JSON="$(python3 "$PARSER" < "$EVENTS_DUMP")"
PARSE_RC=$?
set -e
if [[ $PARSE_RC -ne 0 ]]; then
    echo "--- codex event stream saved to: $EVENTS_DUMP" >&2
    echo "    first 20 lines:" >&2
    sed -n '1,20p' "$EVENTS_DUMP" >&2
    echo "    ..." >&2
    echo "    last 10 lines:" >&2
    tail -10 "$EVENTS_DUMP" >&2
    exit "$PARSE_RC"
fi
# success — clean up the dump unless debug is on
if [[ "${CITATION_VERIFY_DEBUG:-0}" != "1" ]]; then
    rm -f "$EVENTS_DUMP"
fi
printf '%s\n' "$FINAL_JSON"
