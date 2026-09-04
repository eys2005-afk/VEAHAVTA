---
description: חקירת עומק בזמן אמת על הסשן הנוכחי — אילו כלים רצו, עם מה, ומה חזר
argument-hint: "[timeline|stats|commands|files|errors|step N|grep PATTERN|prompts]"
allowed-tools: Bash(python3 .claude/skills/session-audit/session_audit.py:*), Read
---

Investigate this session in depth, right now, using the recorded transcript —
not your memory of it.

Requested focus: **$ARGUMENTS** (empty means: the full timeline plus stats).

Run `.claude/skills/session-audit/session_audit.py` with the mode that matches
the focus above (see `.claude/skills/session-audit/SKILL.md` for the mode table),
then report in Hebrew, לשון זכר, flowing text without bullets or bold:

1. What was asked, and how many tool calls it took.
2. The timeline: each step with its tool, its real arguments, and its result.
3. Anything that failed or was retried, with the actual error text.
4. Files touched and commands run, exactly as recorded.
5. Where the record is silent (e.g. reasoning text is not stored) — say so
   plainly rather than filling the gap from memory.

If a specific step matters, show it in full with `--step N`.
