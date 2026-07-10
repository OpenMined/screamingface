#!/usr/bin/env python3
"""UserPromptSubmit hook — re-inject the ScreamingFace SDLC work-item gate on every prompt.

Advisory rules in CLAUDE.md don't self-enforce (they lose to the immediate task framing).
This hook re-states the non-negotiable gate each turn so "file the work item first" stays
salient. Non-blocking: it only injects context, never denies. Refs: OME-378.
"""
import json

GATE = (
    "[SDLC GATE — screamingface] If this turn starts a UNIT OF WORK: "
    "(1) file the Linear issue (OME-N, Engineering / 😱 ScreamingFace V1) AND create a "
    "docs/work ledger BEFORE writing any tracked path (docs/ .claude/ apps/ packages/ web/) "
    "— never defer with \"want me to file?\"; "
    "(2) invoke working-in-this-repo + task-management (+ the stack's sdlc-* skill for code); "
    "(3) order is spec → plan → code; (4) never commit to main. "
    "The scratchpad and the plan file are the ONLY exempt writes. "
    "Pure question / read-only turn? Ignore this line."
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": GATE,
    }
}))
