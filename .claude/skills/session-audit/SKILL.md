---
name: session-audit
description: >-
  Deep, real-time investigation of what is happening in the current Claude Code
  session — every tool call with its real arguments, every result, every error,
  timings and volumes. Use when the user asks what you actually did, which tools
  ran, which files you touched, which commands you executed, why something took
  so long, or wants to audit/verify a session; also for "חקירת עומק", "מה עשית
  בפועל", "אילו כלים הרצת", "תראה לי את הסשן". Works on mobile, desktop, web and
  CLI.
---

# Session audit — חקירת עומק על הסשן

Claude Code writes the live session to a JSONL transcript **while it runs**, so
this works mid-session, not only afterwards.

## Where the transcript is

```
~/.claude/projects/<url-encoded-cwd>/<session-id>.jsonl
```

The live session id is in `$CLAUDE_CODE_SESSION_ID`. The script resolves it
automatically; it falls back to the most recently written transcript.

## How to run it

From the repo root:

```bash
python3 .claude/skills/session-audit/session_audit.py            # timeline
python3 .claude/skills/session-audit/session_audit.py --stats    # overview
```

Pick the mode that answers the question actually asked:

| The user asks | Run |
|---|---|
| "what did you do?" / "מה עשית" | *(no flag)* — the timeline |
| "show me step 7 in full" | `--step 7` |
| "which commands did you run?" | `--commands` |
| "which files did you touch?" | `--files` |
| "what failed?" | `--errors` |
| "did you ever look at X?" | `--grep X` |
| "how long did it take?" / "how much output?" | `--stats` |
| "what did I ask?" | `--prompts` |
| "only the recent part" | `--last 20` |
| another session, on desktop | `--list`, then `--session <id>` |

`--json` emits the whole timeline machine-readably if it needs further processing.

## Reporting rules

Report what the transcript says, not what you remember — memory of the session
and the recorded facts can diverge, and the transcript is the evidence.

- Quote real step numbers, real timestamps and real arguments.
- If the user is chasing a specific claim, run `--grep` and show the matching
  step rather than asserting it from recollection.
- Follow the repo's "איך להסביר את העבודה" convention in CLAUDE.md: name the
  tool, the exact arguments, and where each fact came from.

## Known limit — verified, do not overstate

`thinking` blocks are present in the transcript but their **text is empty**;
only a per-block cryptographic signature is stored. The reasoning itself is
**not** recoverable after the fact. `--thinking` says so explicitly instead of
printing nothing. Everything the reasoning produced — the tool calls, arguments,
results — is fully recoverable.

On web/mobile the container is recreated per session, so `--list` normally shows
only the current session. On desktop/CLI the directory persists across sessions.
