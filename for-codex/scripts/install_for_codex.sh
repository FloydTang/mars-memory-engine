#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="${HOME}/.codex/skills/mars-memory-engine-for-codex"

mkdir -p "${HOME}/.codex/skills"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

cp -R "$PACKAGE_DIR"/. "$TARGET_DIR"/
find "$TARGET_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} +

echo "Installed Mars Memory Engine for Codex to: $TARGET_DIR"
