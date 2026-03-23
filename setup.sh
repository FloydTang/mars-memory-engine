#!/bin/bash
# Mars Memory Engine setup for Markdown-first OpenClaw workspaces

set -euo pipefail

WORKSPACE="${1:-$(pwd)}"
MODE="${2:-plugin}"
DB_PATH="${3:-$WORKSPACE/.mars-memory-engine/lancedb}"

echo "🚀 Mars Memory Engine - OpenClaw Setup"
echo "workspace: $WORKSPACE"
echo "mode: $MODE"
echo "db_path: $DB_PATH"

python3 -c "import lancedb, pyarrow, numpy" 2>/dev/null || {
  echo "Installing core dependencies..."
  pip install -r requirements.txt
}

mkdir -p "$WORKSPACE/memory/topics"
mkdir -p "$WORKSPACE/.mars-memory-engine"

python3 migration/migrate_memory.py --workspace "$WORKSPACE" --db-path "$DB_PATH" --reset

echo ""
echo "✅ Setup complete"
echo "Useful commands:"
echo "  Rebuild index: python3 migration/migrate_memory.py --workspace \"$WORKSPACE\" --db-path \"$DB_PATH\" --reset"
echo "  Daily review:  python3 cron_memory_review.py --workspace \"$WORKSPACE\""
echo "  Distill skills: python3 skills/knowledge_distiller.py --workspace \"$WORKSPACE\""
echo ""
if [ "$MODE" = "index-only" ]; then
  echo "Index-only mode selected. Markdown remains the sole source of truth."
else
  echo "Plugin mode selected. Use openclaw.adapter.OpenClawMemoryAdapter inside the host integration layer."
fi
