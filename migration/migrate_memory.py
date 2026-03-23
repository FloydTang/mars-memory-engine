#!/usr/bin/env python3
"""
Markdown-first index rebuild entrypoint.

The OpenClaw workspace Markdown files remain the source of truth:
- MEMORY.md
- memory/YYYY-MM-DD.md
- memory/topics/*.md

This script rebuilds the derived LanceDB index from those files.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from openclaw.adapter import OpenClawMemoryAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild Mars Memory Engine index from Markdown.")
    parser.add_argument(
        "--workspace",
        default=os.getcwd(),
        help="OpenClaw workspace path that contains MEMORY.md and memory/.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional override for the derived LanceDB path.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the current derived index before rebuilding.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    db_path = args.db_path or str(workspace / ".mars-memory-engine" / "lancedb")

    if args.reset and Path(db_path).exists():
        shutil.rmtree(db_path)

    adapter = OpenClawMemoryAdapter(str(workspace), db_path=db_path)
    stats = adapter.rebuild_index(str(workspace))

    print("✅ Markdown source-of-truth index rebuilt")
    print(f"workspace: {workspace}")
    print(f"db_path: {db_path}")
    print(f"scanned_files: {stats['scanned_files']}")
    print(f"indexed_entries: {stats['indexed_entries']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
