---
name: mars-memory-engine-for-codex
description: Codex-adapted memory workflow. Capture corrections, errors, and repeatable patterns in Markdown, then promote durable lessons into SOUL.md, AGENTS.md, TOOLS.md, or topic files.
metadata:
  triggers:
    - correction
    - error
    - repeated_mistake
    - workflow_learning
    - explicit_memory_request
  files:
    - MEMORY.md
    - SOUL.md
    - AGENTS.md
    - TOOLS.md
    - memory/ERRORS.md
    - memory/LEARNINGS.md
    - memory/FEATURE_REQUESTS.md
    - memory/topics/*.md
---

# Mars Memory Engine for Codex

## Purpose

Use this skill when Codex should preserve durable lessons from collaboration, especially after:

- the user corrects the agent
- a command fails and the fix is reusable
- the same mistake happens multiple times
- a workflow or tool setup should become standard
- the user explicitly asks to remember something

## Core Workflow

1. Write the event to a temporary capture file:
   - `memory/ERRORS.md` for failures
   - `memory/LEARNINGS.md` for corrections and reusable lessons
   - `memory/FEATURE_REQUESTS.md` for requested capabilities
2. Decide whether the lesson should remain temporary or be promoted.
3. Promote durable guidance into:
   - `SOUL.md` for behavioral rules
   - `AGENTS.md` for workflow rules
   - `TOOLS.md` for environment or tool setup
   - `memory/topics/*.md` for domain-specific knowledge
4. If the same issue appears three times, escalate it to a durable rule.
5. Keep `MEMORY.md` as a compact index, not a dumping ground.

## Promotion Defaults

- Explicit user request: promote immediately.
- Critical or repeated mistake: promote immediately.
- Workflow improvement: usually promote to `AGENTS.md`.
- Tool configuration: usually promote to `TOOLS.md`.
- Domain knowledge: promote to `memory/topics/<topic>.md`.

## Record Formats

### `memory/ERRORS.md`

```markdown
## [ERR-YYYYMMDD-001] Short Name

**Logged**: ISO-8601 time
**Priority**: high
**Status**: pending
**Promote-To**: TOOLS.md

### Summary
Short description

### Error
Condensed failure details

### Resolution
What fixed it
```

### `memory/LEARNINGS.md`

```markdown
## [LRN-YYYYMMDD-001] Topic

**Logged**: ISO-8601 time
**Priority**: medium
**Status**: pending
**Promote-To**: AGENTS.md

### Summary
Short lesson

### Details
Context and correction

### Suggested Action
Future default behavior
```

## Non-Goals

- Do not introduce a primary database in v1.
- Do not replace Markdown with vector search.
- Do not add OpenClaw-only concepts to this variant.

## Future Expansion

If retrieval is needed later, add a derived index from Markdown rather than changing the source of truth.
