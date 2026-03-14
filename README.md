# Mars Memory Engine v3

> Discord 多代理系统的记忆引擎 — LanceDB + 本地 Embedding

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

**Mars Memory Engine** 是为 Discord 多代理系统（OpenClaw）设计的长期记忆引擎。基于 LanceDB 向量数据库 + 本地 BGE-M3 Embedding，实现多代理记忆隔离、智能分类、冲突检测、时间版本管理和知识蒸馏。

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **多代理隔离** | 每条记忆绑定 agent_id + guild_id，检索自动隔离 private/shared |
| **噪音过滤** | 写入侧拦截问候语、表情、系统标记等无意义内容 |
| **自适应检索** | 查询侧自动跳过命令、问候、短查询；记忆意图词强制检索 |
| **L0/L1/L2 三层记忆** | L0 一句话摘要、L1 结构化概览、L2 完整内容（规则生成，零 LLM 成本） |
| **Temporal Versioning** | preference/entity 类别支持 supersede 链，旧记忆标记 invalidated_at 而非删除 |
| **Weibull 衰减** | 拉伸指数衰减 + 访问强化（最大 3x）+ 分类别差异化半衰期和衰减地板 |
| **6 分类系统** | profile / preference / entity / event / case / pattern，规则+LLM 混合分类 |
| **分类行为差异化** | profile=always_merge, event/case=append_only, 其余=merge_supported |
| **冲突检测** | 同 Agent cosine>0.85 自动替换，跨 Agent 可选 LLM 判断 UPDATE/SUPPLEMENT |
| **3 层晋升/降级** | Peripheral → Working → Core，基于 composite score + access_count + importance |
| **Knowledge Distiller** | 主题文件 >10KB 且 >20 条时自动蒸馏为 Skill 配置 |
| **混合检索** | Vector + BM25 + RRF 融合 + Length Norm + Recency Boost + Hardmin 截断 |
| **Embedding 缓存** | LRU 256 条 / 30min TTL，线程安全 |
| **DM 保护** | DM 频道记忆强制 private scope |

---

## 架构

```
┌──────────────────────────────────────────────────────────┐
│                     调用方 (Discord Bot / Skill)           │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│              protocols/memory_gateway.py                  │
│  MemoryGateway — 统一写入/检索入口                          │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌────────────┐  │
│  │噪音过滤  │ │自动分类   │ │分类行为    │ │冲突检测     │  │
│  │noise_   │ │classifier│ │category_  │ │cosine +    │  │
│  │filter   │ │规则+LLM  │ │behaviors  │ │LLM 判断    │  │
│  └─────────┘ └──────────┘ └───────────┘ └────────────┘  │
│  ┌────────────────┐ ┌──────────────────────────────────┐ │
│  │L0/L1/L2 生成   │ │Temporal Versioning (supersede链) │ │
│  └────────────────┘ └──────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────┐ │
│  │自适应检索 adaptive_retrieval — 查询侧噪音跳过         │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│              core/lancedb_store.py                        │
│  LanceDBMemoryStore — 向量存储引擎                         │
│  ┌──────────────────┐ ┌──────────────────┐               │
│  │search_hybrid     │ │promote_memory    │               │
│  │Vector+BM25+RRF   │ │晋升/降级逻辑      │               │
│  │+Weibull+LenNorm  │ │composite score   │               │
│  │+Recency+Hardmin  │ │                  │               │
│  └──────────────────┘ └──────────────────┘               │
│  ┌──────────────────────────────────────────────────────┐ │
│  │EmbeddingProvider — 本地 bge-m3 优先，Jina API 回退    │ │
│  │LRU 缓存 256 条 / 30min TTL                           │ │
│  └──────────────────────────────────────────────────────┘ │
│                         │                                 │
│                    LanceDB (本地)                          │
│              tables: memories / topics / access_log       │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│            skills/knowledge_distiller.py                  │
│  Knowledge Distiller — 主题 >10KB+>20条 → Skill 蒸馏      │
└──────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/FloydTang/mars-memory-engine.git
cd mars-memory-engine
pip install -r requirements.txt
```

主要依赖：
- `lancedb` — 向量数据库
- `sentence-transformers` + `torch` — 本地 BGE-M3 Embedding
- `pyarrow`, `numpy`

### 2. 环境变量（可选）

本地 Embedding 无需 API Key。如使用 LLM 分类或冲突判断：

```bash
export LLM_API_KEY="your_api_key"
export LLM_BASE_URL="https://your-llm-endpoint"
export LLM_MODEL="kimi-k2.5"  # 默认值
```

### 3. 使用示例

```python
import asyncio
from protocols.memory_gateway import MemoryGateway

gateway = MemoryGateway()

async def demo():
    # 写入记忆
    result = await gateway.write_memory(
        content="用户 Mars 喜欢用 Python 写自动化脚本",
        agent_id="agent-alpha",
        guild_id="guild-123",
        topic="user_preference",
    )
    print(result)
    # → {"id": "...", "conflict": False, "action": "insert", ...}

    # 检索记忆
    results = gateway.search(
        query="Mars 的编程偏好是什么？",
        agent_id="agent-alpha",
        guild_id="guild-123",
    )
    for r in results:
        print(f"[{r['category']}] {r['content'][:80]}")

asyncio.run(demo())
```

噪音内容会被自动过滤：

```python
result = await gateway.write_memory(
    content="ok",
    agent_id="agent-alpha", guild_id="guild-123",
)
# → {"action": "filtered", "reason": "affirmation"}
```

---

## 文件结构

```
mars-memory-engine/
├── core/
│   ├── lancedb_store.py          # LanceDB 存储引擎、MemoryEntry Schema、
│   │                             # 混合检索、Weibull 衰减、晋升/降级、
│   │                             # L0/L1/L2 生成、Embedding 缓存
│   ├── classifier.py             # 规则+LLM 混合分类器 (6 分类)
│   ├── noise_filter.py           # 写入侧噪音过滤
│   ├── adaptive_retrieval.py     # 查询侧自适应检索跳过
│   └── category_behaviors.py     # 分类行为差异化配置
├── protocols/
│   └── memory_gateway.py         # 多代理记忆网关 (统一写入/检索入口)
├── skills/
│   └── knowledge_distiller.py    # 知识蒸馏 → Skill 配置生成
├── migration/
│   ├── migrate_memory.py         # Markdown → LanceDB 数据迁移
│   └── migrate_v3_fields.py      # v2 → v3 字段迁移脚本
├── topics/
│   └── auto_archiver.py          # 主题聚类与自动归档
├── tests/
│   └── test_integration_v3.py    # v3 集成测试 (10 个测试)
├── cron_memory_review.py         # 每日定时审查
├── memory_query.py               # CLI 检索工具
├── setup.sh                      # 初始化脚本
├── requirements.txt
└── README.md
```

---

## Weibull 衰减参数

每个分类有独立的衰减曲线：

| 分类 | 半衰期(天) | β (形状) | 衰减地板 | 说明 |
|------|-----------|----------|---------|------|
| profile | 365 | 0.8 | 0.9 | 亚指数慢衰，几乎不遗忘 |
| preference | 180 | 1.0 | 0.7 | 标准指数衰减 |
| entity | 90 | 1.0 | 0.7 | 标准指数衰减 |
| pattern | 120 | 1.0 | 0.6 | 标准指数衰减 |
| case | 30 | 1.2 | 0.5 | 超指数快衰 |
| event | 14 | 1.3 | 0.5 | 超指数快衰，事件性记忆 |

访问强化：`log1p(access_count)` 延长有效半衰期，最大 3 倍。

---

## 从旧版迁移 (v2 → v3)

使用 `migration/migrate_v3_fields.py` 迁移已有数据：

```bash
# 先预览，不修改数据
python migration/migrate_v3_fields.py --dry-run

# 执行迁移
python migration/migrate_v3_fields.py
```

迁移内容：
- 为每条旧记忆生成 L0/L1/L2 三层摘要
- 初始化 Temporal Versioning 字段（invalidated_at, supersedes, superseded_by, fact_key）
- 重建 LanceDB 表以包含新字段

---

## 测试

```bash
python -m pytest tests/test_integration_v3.py -v
```

10 个集成测试，使用 FakeEmbeddingProvider，无需真实模型或 API。

---

## 许可证

MIT License

---

## 联系

- 项目维护：[@FloydTang](https://github.com/FloydTang)
- 作者：Mars (半斤九两科技)

**Version**: 3.0
**Last Updated**: 2026-03-15
