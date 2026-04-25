#!/usr/bin/env python3
"""Parse a codex --json event stream from stdin and emit the final assistant JSON."""
import json
import sys


def extract_final_text(lines):
    last_text = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        # 1) codex 0.124+ shape: {"type":"item.completed","item":{"type":"agent_message","text":"..."}}
        if ev.get("type") == "item.completed":
            item = ev.get("item") or {}
            if item.get("type") == "agent_message":
                t = item.get("text") or item.get("content")
                if t:
                    last_text = t
        # 2) older shape: {"type": "agent_message", "message": {"content": [{"text": "..."}]}}
        if ev.get("type") in ("agent_message", "message", "assistant_message"):
            msg = ev.get("message") or ev
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") in (None, "text", "output_text"):
                        t = part.get("text") or part.get("content")
                        if t:
                            last_text = t
            elif isinstance(content, str):
                last_text = content
            elif msg.get("text"):
                last_text = msg["text"]
        # 3) legacy shape: {"final_message": "..."}
        if ev.get("final_message"):
            last_text = ev["final_message"]
        # 4) fallback: anything with a "text" field on a completion event
        if ev.get("type") == "completion" and ev.get("text"):
            last_text = ev["text"]
    return last_text


def strip_code_fences(t):
    t = t.strip()
    fence = "`" * 3
    if t.startswith(fence):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith(fence):
            t = t.rsplit(fence, 1)[0]
        t = t.strip()
    return t


def main():
    last_text = extract_final_text(sys.stdin)
    if not last_text:
        sys.stderr.write("ERROR: could not locate final message in codex event stream\n")
        sys.exit(1)
    t = strip_code_fences(last_text)
    try:
        parsed = json.loads(t)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"ERROR: model output was not valid JSON: {e}\n")
        sys.stderr.write("--- raw model output ---\n")
        sys.stderr.write(t[:2000] + "\n")
        sys.exit(2)
    sys.stdout.write(json.dumps(parsed, ensure_ascii=False))


if __name__ == "__main__":
    main()
