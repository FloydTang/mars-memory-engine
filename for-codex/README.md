# Mars Memory Engine for Codex

Maintained by 半斤九两科技.

This is the Codex-adapted variant of Mars Memory Engine. It keeps the durable learning workflow from the main project while intentionally dropping OpenClaw-specific runtime concerns.

## Goals

- Capture corrections, failures, and reusable patterns in Markdown.
- Promote durable lessons into stable operating docs.
- Keep `MEMORY.md` index-like and lightweight.
- Distill large topic histories into reusable skills later.

## Included Files

- `SKILL.md` — Codex skill behavior and triggers
- `templates/` — starter Markdown files for a Codex memory workspace
- `scripts/install_for_codex.sh` — installs the skill into `~/.codex/skills/`

## What This Version Does

- Logs failures into `memory/ERRORS.md`
- Logs corrections and lessons into `memory/LEARNINGS.md`
- Promotes durable items into:
  - `SOUL.md`
  - `AGENTS.md`
  - `TOOLS.md`
  - `memory/topics/*.md`
- Escalates repeated problems into rules

## What This Version Does Not Do

- No LanceDB
- No embeddings
- No OpenClaw plugin interface
- No guild/private/shared isolation

## Install

```bash
./for-codex/scripts/install_for_codex.sh
```

This installs the skill package into:

```text
~/.codex/skills/mars-memory-engine-for-codex
```

## Suggested Workspace Layout

```text
codex-memory/
├── MEMORY.md
├── SOUL.md
├── AGENTS.md
├── TOOLS.md
└── memory/
    ├── ERRORS.md
    ├── LEARNINGS.md
    ├── FEATURE_REQUESTS.md
    ├── topics/
    └── archive/
```
