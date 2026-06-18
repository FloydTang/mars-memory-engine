# Mars Memory Engine

Maintained for the OpenClaw upgrade by 半斤九两科技.

> OpenClaw plugin-oriented memory engine with Markdown as the source of truth.

Mars Memory Engine now treats OpenClaw workspace memory files as canonical:

- `MEMORY.md`
- `memory/YYYY-MM-DD.md`
- `memory/topics/*.md`

LanceDB remains useful, but only as a derived layer for indexing, retrieval, ranking, and lifecycle scoring.

## What Changed

- Markdown is the only source of truth.
- LanceDB is rebuilt from workspace files and never replaces them.
- `openclaw/adapter.py` provides the OpenClaw-facing integration layer.
- Search results now trace back to source file and source section.
- Access statistics are updated on retrieval and stored in `access_log`.
- Fact keys now prefer stable anchors from section names and explicit metadata, instead of coarse `category:topic`.

## Architecture

```text
OpenClaw Host / Plugin Hook
        |
        v
openclaw.adapter.OpenClawMemoryAdapter
  - ingest_markdown_memory()
  - search_memory()
  - promote_memory()
  - rebuild_index()
        |
        v
Workspace Markdown (source of truth)
  - MEMORY.md
  - memory/*.md
  - memory/topics/*.md
        |
        v
protocols.memory_gateway.MemoryGateway
  - classification
  - noise filtering
  - conflict detection
  - temporal versioning
        |
        v
core.lancedb_store.LanceDBMemoryStore
  - derived index only
  - hybrid retrieval
  - access logging
  - scoring / tiers
```

## OpenClaw Adapter API

```python
from openclaw.adapter import (
    MarkdownMemoryEntry,
    OpenClawMemoryAdapter,
    WorkspaceContext,
)

adapter = OpenClawMemoryAdapter("/path/to/workspace")
ctx = WorkspaceContext(
    workspace_path="/path/to/workspace",
    agent_id="agent-main",
    guild_id="guild-123",
    session_scope="shared",
)

adapter.ingest_markdown_memory(
    MarkdownMemoryEntry(
        title="Webhook 配置",
        content="Discord 的 webhook URL 配置在 openclaw.json 里。",
        topic="discord",
        category="pattern",
    ),
    ctx,
)

results = adapter.search_memory("Discord 配置在哪里？", ctx)
```

Search responses always include:

- `memory_ref`
- `source_file`
- `source_section`
- `category`
- `tier`
- `summary_l1`
- `raw_excerpt`
- `score`
- `is_history`

## Derived Index Rebuild

```bash
python3 migration/migrate_memory.py --workspace /path/to/workspace --reset
```

This command scans workspace Markdown and rebuilds the derived LanceDB index.

## Setup

```bash
git clone https://github.com/FloydTang/mars-memory-engine.git
cd mars-memory-engine
pip install -r requirements.txt
./setup.sh /path/to/openclaw/workspace plugin
```

Arguments:

1. `workspace_path`
2. `mode`: `plugin` or `index-only`
3. optional `db_path`

## Upgrade Existing Agents

If an agent has already installed or learned an older Mars Memory Engine workflow, it should treat the current repository state as authoritative and refresh its assumptions before continuing.

Old assumptions that are now outdated:

- LanceDB is not the source of truth anymore.
- OpenClaw integrations should not call storage internals directly.
- Memory sync is no longer centered on a single generated `SKILL.md`.
- Codex support now lives in a dedicated `for-codex/` package instead of being implied by the main OpenClaw flow.

Current rules that upgraded agents must follow:

- Workspace Markdown is canonical: `MEMORY.md`, `memory/YYYY-MM-DD.md`, `memory/topics/*.md`
- LanceDB is derived state only and can be rebuilt from Markdown.
- OpenClaw hosts should integrate through `openclaw/adapter.py`.
- Codex installs should use `for-codex/SKILL.md` and `for-codex/scripts/install_for_codex.sh`.
- When repository behavior conflicts with remembered habits, trust the repository files on `main` and discard the stale habit.

Fast upgrade checklist for existing agents:

1. Re-read this `README.md`.
2. Re-read `openclaw/adapter.py` integration entrypoints before using the OpenClaw path.
3. Re-read `for-codex/README.md` and `for-codex/SKILL.md` before using the Codex path.
4. Stop treating old local prompts, generated snippets, or cached summaries as authoritative if they predate the OpenClaw adapter refactor or the `for-codex/` package.

Signs an agent is still running with stale understanding:

- It says LanceDB is the primary memory store.
- It ignores `openclaw/adapter.py` and reaches into lower layers directly.
- It claims no update is needed because an old `SKILL.md` did not change.
- It does not recognize `for-codex/` as a first-class install target.

## Codex Variant

The repository also ships a Codex-oriented skill package in [`for-codex/`](./for-codex/).

This variant is intentionally lightweight:

- Markdown-only persistence
- correction and error capture
- promotion into `SOUL.md`, `AGENTS.md`, `TOOLS.md`, and topic files
- no LanceDB or OpenClaw runtime coupling

## Repo Layout

```text
core/         reusable retrieval, scoring, and memory logic
openclaw/     plugin-facing adapter and workspace integration
protocols/    existing gateway-level orchestration
migration/    rebuild derived index from Markdown source files
skills/       knowledge distillation and generated prompts
tests/        integration coverage
```

## Notes

- Markdown corruption should never be a consequence of index rebuild failure.
- Rebuilding the index is safe because the database is derived from workspace files.
- OpenClaw-facing integrations should call the adapter layer, not talk to LanceDB directly.

---

<!-- jiuliang-about-start -->

## 关于半斤九两 / About EVEN BETTER

半斤九两科技（EVEN BETTER）专注“外贸 + AI”的真实落地。我们希望帮助外贸企业把产品、客户、渠道和团队流程，沉淀成客户看得懂、渠道跑得动、团队留得下的系统。

我们主要提供：

- 外贸 AI 落地方法：围绕 Build / Traffic / Team，判断企业该先建资产、放流量，还是建系统。
- 企业表达与内容增长：把产品、案例、FAQ、老板经验和信任证据，整理成海外客户看得懂的内容资产。
- 主动开发流程：从客户画像、线索搜索、客户背调到开发信和跟进复盘，跑出可复用闭环。
- 团队 AI 工作流：把经验写进 AGENTS.md、SOP、模板库、检查清单和可复用 Skill。

更多内容可以查看我们整理的 [《外贸人 Codex 蓝皮书》](https://github.com/FloydTang/waimaoren-codex-bluebook)。

### 找到我们

- 官网：[tang92.com](https://tang92.com)
- 公众号：半斤九两
- GitHub：[@FloydTang](https://github.com/FloydTang)

扫码关注公众号，领取后续模板、案例和更新；也可以通过公众号后台留言联系九两。

<p>
  <img src="https://raw.githubusercontent.com/FloydTang/waimaoren-codex-bluebook/main/assets/wechat-qr.png" alt="半斤九两公众号二维码" width="180">
</p>

<!-- jiuliang-about-end -->
