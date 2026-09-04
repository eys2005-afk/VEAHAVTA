#!/usr/bin/env python3
"""
session_audit.py — חקירת עומק בזמן אמת של סשן Claude Code.

Reads the LIVE transcript of the current (or any) Claude Code session and
reports exactly what happened: every tool call with its real arguments, every
result, every reasoning block, every error.

Works identically on mobile, desktop, web and CLI, because it reads the same
on-disk transcript format that Claude Code writes everywhere:
    ~/.claude/projects/<mangled-cwd>/<session-id>.jsonl

Usage (run from Bash inside a Claude Code session):
    python3 session_audit.py                 # timeline of the session so far
    python3 session_audit.py --last 20       # only the last 20 steps
    python3 session_audit.py --step 7        # full input+output of step 7
    python3 session_audit.py --commands      # every Bash command, verbatim
    python3 session_audit.py --files         # every file touched, by mode
    python3 session_audit.py --errors        # only failed tool calls
    python3 session_audit.py --thinking      # the reasoning blocks
    python3 session_audit.py --prompts       # what the user actually asked
    python3 session_audit.py --stats         # counts, timings, token-ish sizes
    python3 session_audit.py --list          # other sessions on this machine
    python3 session_audit.py --session <id>  # audit a different session
    python3 session_audit.py --grep PATTERN  # steps whose args/results match
    python3 session_audit.py --json          # machine-readable timeline
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- locating

def projects_root() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"


def all_transcripts() -> list[Path]:
    root = projects_root()
    if not root.is_dir():
        return []
    return sorted(root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def find_transcript(session_id: str | None) -> Path:
    """Locate the transcript. Prefer the explicit id, then the live session id,
    then the most recently written transcript."""
    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID")
    candidates = all_transcripts()
    if not candidates:
        sys.exit(f"no transcripts found under {projects_root()}")
    if sid:
        for p in candidates:
            if p.stem == sid:
                return p
        if session_id:  # user asked for a specific one and it is not there
            sys.exit(f"session {session_id} not found under {projects_root()}")
    return candidates[0]


# ---------------------------------------------------------------- parsing

def load(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # the last line can be half-written while the session is live
                continue
    return out


def blocks(rec: dict) -> list[dict]:
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def as_text(value) -> str:
    """tool_result content is sometimes a string, sometimes a list of blocks."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for b in value:
            if isinstance(b, dict):
                parts.append(b.get("text") or f"<{b.get('type', 'block')}>")
            else:
                parts.append(str(b))
        return "\n".join(parts)
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)[:100000]


def ts(rec: dict) -> datetime | None:
    raw = rec.get("timestamp")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class Step:
    """One tool call plus the result that came back for it."""

    __slots__ = ("n", "tool", "inp", "use_id", "started", "finished",
                 "result", "is_error", "sidechain")

    def __init__(self, n, tool, inp, use_id, started, sidechain):
        self.n = n
        self.tool = tool
        self.inp = inp or {}
        self.use_id = use_id
        self.started = started
        self.finished = None
        self.result = ""
        self.is_error = False
        self.sidechain = sidechain

    @property
    def duration(self) -> float | None:
        if self.started and self.finished:
            return (self.finished - self.started).total_seconds()
        return None


def build(records: list[dict]):
    steps: list[Step] = []
    by_id: dict[str, Step] = {}
    thinking: list[tuple[datetime | None, str, bool]] = []
    says: list[tuple[datetime | None, str]] = []
    prompts: list[tuple[datetime | None, str]] = []

    n = 0
    for rec in records:
        rtype = rec.get("type")
        side = bool(rec.get("isSidechain"))
        when = ts(rec)

        if rtype == "assistant":
            for b in blocks(rec):
                kind = b.get("type")
                if kind == "tool_use":
                    n += 1
                    st = Step(n, b.get("name", "?"), b.get("input"), b.get("id"), when, side)
                    steps.append(st)
                    if st.use_id:
                        by_id[st.use_id] = st
                elif kind == "thinking":
                    text = b.get("thinking") or b.get("text") or ""
                    thinking.append((when, text, side))
                elif kind == "text":
                    if b.get("text", "").strip():
                        says.append((when, b["text"]))

        elif rtype == "user":
            handled = False
            for b in blocks(rec):
                if b.get("type") == "tool_result":
                    handled = True
                    st = by_id.get(b.get("tool_use_id"))
                    if st is None:
                        continue
                    st.finished = when
                    st.is_error = bool(b.get("is_error"))
                    st.result = as_text(b.get("content"))
                    if not st.result and "toolUseResult" in rec:
                        st.result = as_text(rec["toolUseResult"])
            if not handled and not rec.get("isMeta"):
                text = "\n".join(b.get("text", "") for b in blocks(rec)).strip()
                if text:
                    prompts.append((when, text))

    return steps, thinking, says, prompts


# ---------------------------------------------------------------- rendering

FILE_TOOLS = {"Read", "Write", "Edit", "NotebookEdit", "MultiEdit"}


def summarise_input(step: Step, width: int = 96) -> str:
    i = step.inp
    t = step.tool

    def one_line(s):
        return " ".join(str(s).split())

    if t == "Bash":
        s = one_line(i.get("command", ""))
    elif t in FILE_TOOLS:
        s = str(i.get("file_path") or i.get("notebook_path") or "")
        if t == "Read" and i.get("offset"):
            s += f"  [from line {i['offset']}"
            s += f", {i['limit']} lines]" if i.get("limit") else "]"
    elif t == "Grep":
        s = f"/{i.get('pattern', '')}/"
        for key in ("path", "glob", "type"):
            if i.get(key):
                s += f"  {key}={i[key]}"
    elif t == "Glob":
        s = str(i.get("pattern", "")) + (f"  in {i['path']}" if i.get("path") else "")
    elif t in ("Agent", "Task"):
        s = f"[{i.get('subagent_type', 'agent')}] {one_line(i.get('description', ''))}"
    elif t == "Skill":
        s = str(i.get("skill", "")) + (f" {one_line(i.get('args', ''))}" if i.get("args") else "")
    elif t in ("WebFetch", "WebSearch"):
        s = str(i.get("url") or i.get("query") or "")
    elif t == "ToolSearch":
        s = str(i.get("query", ""))
    else:
        scalars = {k: v for k, v in i.items() if isinstance(v, (str, int, float, bool))}
        s = one_line(", ".join(f"{k}={v}" for k, v in list(scalars.items())[:4])) or one_line(json.dumps(i, ensure_ascii=False))

    return s if len(s) <= width else s[: width - 1] + "…"


def result_flag(step: Step) -> str:
    if step.finished is None:
        return "· running"
    if step.is_error:
        return "✗ ERROR"
    lines = step.result.count("\n") + 1 if step.result else 0
    return f"✓ {len(step.result)}c/{lines}L"


def clock(dt: datetime | None) -> str:
    return dt.strftime("%H:%M:%S") if dt else "--:--:--"


def print_timeline(steps: list[Step], last: int | None, show_result: bool):
    shown = steps[-last:] if last else steps
    if not shown:
        print("no tool calls recorded yet.")
        return
    print(f"{'#':>3}  {'time':<8} {'dur':>6}  {'tool':<22} {'result':<14} arguments")
    print("-" * 118)
    for s in shown:
        dur = f"{s.duration:.1f}s" if s.duration is not None else ""
        mark = "↳" if s.sidechain else " "
        print(f"{s.n:>3}{mark} {clock(s.started):<8} {dur:>6}  {s.tool:<22} {result_flag(s):<14} {summarise_input(s)}")
        if show_result and s.result:
            head = s.result.strip().splitlines()
            for line in head[:3]:
                print(f"          | {line[:104]}")
            if len(head) > 3:
                print(f"          | … +{len(head) - 3} more lines  (see --step {s.n})")


def print_step(steps: list[Step], num: int):
    match = [s for s in steps if s.n == num]
    if not match:
        sys.exit(f"no step {num} (session has {len(steps)} steps)")
    s = match[0]
    dur = f"{s.duration:.2f}s" if s.duration is not None else "still running"
    print(f"=== step {s.n} — {s.tool} — {clock(s.started)} — {dur}"
          f"{' — subagent' if s.sidechain else ''} ===\n")
    print("--- input ---")
    print(json.dumps(s.inp, ensure_ascii=False, indent=2))
    print(f"\n--- result {'(ERROR)' if s.is_error else ''} ---")
    print(s.result if s.result else "<empty>")


def print_commands(steps: list[Step]):
    hits = [s for s in steps if s.tool == "Bash"]
    if not hits:
        print("no Bash commands in this session.")
        return
    for s in hits:
        print(f"# step {s.n} — {clock(s.started)} — {result_flag(s)}"
              f" — {s.inp.get('description', '')}")
        print(s.inp.get("command", ""))
        print()


def print_files(steps: list[Step]):
    seen: dict[str, dict[str, list[int]]] = {}
    for s in steps:
        path = s.inp.get("file_path") or s.inp.get("notebook_path")
        if s.tool in FILE_TOOLS and path:
            seen.setdefault(path, {}).setdefault(s.tool, []).append(s.n)
    if not seen:
        print("no files touched through file tools in this session.")
        return
    print(f"{'mode':<26} file")
    print("-" * 90)
    for path in sorted(seen):
        modes = ", ".join(f"{tool}×{len(ns)}" for tool, ns in sorted(seen[path].items()))
        steps_str = ",".join(str(n) for ns in seen[path].values() for n in sorted(ns))
        print(f"{modes:<26} {path}")
        print(f"{'':<26} steps: {steps_str}")


def print_errors(steps: list[Step]):
    hits = [s for s in steps if s.is_error]
    if not hits:
        print("no failed tool calls in this session.")
        return
    for s in hits:
        print(f"=== step {s.n} — {s.tool} — {clock(s.started)} ===")
        print(f"args: {summarise_input(s, width=400)}")
        print(s.result.strip()[:2000])
        print()


def print_thinking(thinking, last):
    items = thinking[-last:] if last else thinking
    if not items:
        print("no reasoning blocks in this transcript "
              "(extended thinking was off for this session).")
        return
    with_text = [i for i in items if i[1].strip()]
    if not with_text:
        print(f"{len(items)} reasoning blocks are present, but their text is not stored "
              f"in this transcript — only a cryptographic signature per block.")
        print("On this surface the reasoning itself is not recoverable after the fact; "
              "the tool calls it produced are (run without --thinking).")
        return
    for when, text, side in with_text:
        print(f"=== {clock(when)}{' — subagent' if side else ''} ===")
        print(text.strip())
        print()


def print_prompts(prompts, says):
    if not prompts and not says:
        print("nothing recorded yet.")
        return
    for when, text in prompts:
        print(f"=== USER — {clock(when)} ===")
        print(text.strip()[:4000])
        print()
    for when, text in says:
        print(f"--- CLAUDE — {clock(when)} ---")
        print(text.strip()[:2000])
        print()


def print_stats(path: Path, steps, thinking, says, prompts):
    from collections import Counter
    counts = Counter(s.tool for s in steps)
    done = [s for s in steps if s.finished]
    errors = [s for s in steps if s.is_error]
    total_out = sum(len(s.result) for s in steps)
    spent = sum(s.duration or 0 for s in done)
    first = next((s.started for s in steps if s.started), None)
    last = next((s.finished for s in reversed(steps) if s.finished), None)

    print(f"transcript : {path}")
    print(f"size       : {path.stat().st_size:,} bytes")
    if first and last:
        print(f"span       : {clock(first)} → {clock(last)}  ({(last - first).total_seconds():.0f}s wall)")
    stored = sum(1 for t in thinking if t[1].strip())
    note = "" if stored == len(thinking) else f" ({stored} with readable text)"
    print(f"user turns : {len(prompts)}   claude replies: {len(says)}   "
          f"reasoning blocks: {len(thinking)}{note}")
    print(f"tool calls : {len(steps)}  (errors: {len(errors)}, still running: {len(steps) - len(done)})")
    print(f"tool time  : {spent:.1f}s   result volume: {total_out:,} chars (~{total_out // 4:,} tokens)")
    print()
    print(f"{'tool':<28} calls   result chars")
    print("-" * 56)
    for tool, c in counts.most_common():
        vol = sum(len(s.result) for s in steps if s.tool == tool)
        print(f"{tool:<28} {c:>5}   {vol:>12,}")


def print_grep(steps: list[Step], pattern: str):
    import re
    rx = re.compile(pattern, re.IGNORECASE)
    hits = 0
    for s in steps:
        blob = json.dumps(s.inp, ensure_ascii=False) + "\n" + s.result
        if not rx.search(blob):
            continue
        hits += 1
        print(f"=== step {s.n} — {s.tool} — {clock(s.started)} — {result_flag(s)} ===")
        print(f"args: {summarise_input(s, width=300)}")
        for line in blob.splitlines():
            if rx.search(line):
                print(f"  > {line.strip()[:160]}")
        print()
    if not hits:
        print(f"no step matched /{pattern}/")


def print_list():
    rows = all_transcripts()
    if not rows:
        print(f"no transcripts under {projects_root()}")
        return
    live = os.environ.get("CLAUDE_CODE_SESSION_ID")
    print(f"{'':1} {'modified':<17} {'size':>10}  session")
    for p in rows[:40]:
        mark = "*" if p.stem == live else " "
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{mark} {mtime:<17} {p.stat().st_size:>10,}  {p.stem}   ({p.parent.name})")
    print("\n* = this session")


def dump_json(steps: list[Step]):
    print(json.dumps([{
        "step": s.n,
        "tool": s.tool,
        "input": s.inp,
        "started": s.started.isoformat() if s.started else None,
        "duration_s": s.duration,
        "is_error": s.is_error,
        "sidechain": s.sidechain,
        "result": s.result,
    } for s in steps], ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Deep, real-time investigation of a Claude Code session.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", help="session id to audit (default: the live one)")
    ap.add_argument("--list", action="store_true", help="list sessions on this machine")
    ap.add_argument("--last", type=int, metavar="N", help="only the last N steps")
    ap.add_argument("--step", type=int, metavar="N", help="full input+output of step N")
    ap.add_argument("--commands", action="store_true", help="every Bash command, verbatim")
    ap.add_argument("--files", action="store_true", help="every file touched, by mode")
    ap.add_argument("--errors", action="store_true", help="only failed tool calls")
    ap.add_argument("--thinking", action="store_true", help="the reasoning blocks")
    ap.add_argument("--prompts", action="store_true", help="user turns and Claude's replies")
    ap.add_argument("--stats", action="store_true", help="counts, timings, volumes")
    ap.add_argument("--grep", metavar="PATTERN", help="steps whose args or results match")
    ap.add_argument("--results", action="store_true", help="preview results in the timeline")
    ap.add_argument("--json", action="store_true", help="machine-readable timeline")
    args = ap.parse_args()

    if args.list:
        print_list()
        return

    path = find_transcript(args.session)
    records = load(path)
    steps, thinking, says, prompts = build(records)

    if args.step is not None:
        print_step(steps, args.step)
    elif args.commands:
        print_commands(steps)
    elif args.files:
        print_files(steps)
    elif args.errors:
        print_errors(steps)
    elif args.thinking:
        print_thinking(thinking, args.last)
    elif args.prompts:
        print_prompts(prompts, says)
    elif args.stats:
        print_stats(path, steps, thinking, says, prompts)
    elif args.grep:
        print_grep(steps, args.grep)
    elif args.json:
        dump_json(steps)
    else:
        live = " (live)" if path.stem == os.environ.get("CLAUDE_CODE_SESSION_ID") else ""
        print(f"session {path.stem}{live} — {len(steps)} tool calls\n")
        print_timeline(steps, args.last, args.results)


if __name__ == "__main__":
    main()
