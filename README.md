# Mars Memory Engine 🧠⚡

> 让 AI 真正拥有长期记忆 | 基于 LanceDB + Jina Embeddings v3

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

**Mars Memory Engine** 是半斤九两科技自主研发的 AI 长期记忆管理系统，专为 AI 代理（Agent）设计，实现智能记忆存储、语义检索和知识蒸馏。

---

## ✨ 特性

| 特性 | 说明 |
|------|------|
| **混合检索** | Vector + BM25 + RRF Fusion，多策略融合搜索 |
| **6 分类系统** | profile / preference / entity / event / case / pattern |
| **3 层记忆晋升** | Peripheral → Working → Core |
| **自动归档** | MEMORY.md 超阈值自动触发主题聚类 |
| **知识蒸馏** | 主题文件超阈值自动生成 Skill 配置 |
| **时间衰减** | Weibull 模型 + 访问频率加权 |

---

## 🎯 价值与意义

### 解决什么问题？

**传统 AI 的痛点**：
- 依赖上下文窗口，历史记忆易丢失
- 知识分散在各文档，难以关联
- 人工整理知识库费时费力

**Mars Memory Engine 的答案**：
- 持久化向量存储，语义检索召回率 > 90%
- 6 分类自动归类，主题化聚类管理
- 自动归档 + 知识蒸馏 → 一键生成可复用 Skill

### 适用场景

- 🤖 AI 代理/智能体的长期记忆系统
- 📚 个人知识库智能管理
- 🔍 企业内部文档语义搜索
- 🧠 AI 应用的上下文记忆管理

---

## 🚀 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/FloydTang/mars-memory-engine.git
cd mars-memory-engine
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
export JINA_API_KEY="your_jina_api_key"
# 可选：用于 LLM 增强
export OPENAI_API_KEY="your_openai_api_key"
```

### 3. 初始化

```bash
# 一键初始化
bash setup.sh

# 或手动执行
python migration/migrate_memory.py --reset
python topics/auto_archiver.py --force
```

### 4. 使用

```python
from core.lancedb_store import get_memory_store, get_embedder

store = get_memory_store()
embedder = get_embedder()

# 语义检索
query = "Discord 配置问题"
embedding = embedder.embed([query], task="retrieval.query")[0]

results = store.search_hybrid(
    query=query,
    embedding=embedding,
    topic="discord_management",
    limit=5
)

for r in results:
    print(f"[{r['topic']}] {r['content'][:100]}...")
```

---

## 📂 项目结构

```
mars-memory-engine/
├── core/
│   └── lancedb_store.py          # LanceDB 核心存储 (混合检索)
├── migration/
│   └── migrate_memory.py          # Markdown → LanceDB 数据迁移
├── topics/
│   └── auto_archiver.py           # 主题聚类与自动归档
├── skills/
│   └── knowledge_distiller.py     # 知识蒸馏与 Skill 生成
├── protocols/
│   └── memory_gateway.py          # 记忆网关 (可选)
├── cron_memory_review.py          # 每日定时审查入口
├── setup.sh                       # 一键初始化脚本
├── memory_query.py                # CLI 检索工具
└── README.md                      # 本文档
```

---

## ⚙️ 配置参数

### 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `JINA_API_KEY` | Jina AI API Key (生成向量) | ✅ |
| `OPENAI_API_KEY` | OpenAI API Key (LLM 增强，可选) | ❌ |

### 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `EMBEDDING_DIM` | 1024 | Jina v3 向量维度 |
| `MEMORY_THRESHOLD` | 2000 | MEMORY.md 归档阈值 (tokens) |
| `TOPIC_FILE_THRESHOLD` | 10KB | 知识蒸馏阈值 |

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可证

MIT License

---

## 🏆 致谢

- [LanceDB](https://lancedb.com/) - 高性能向量数据库
- [Jina AI](https://jina.ai/) - 优秀的 Embedding 模型

---

## 📞 联系

- 项目维护：[@FloydTang](https://github.com/FloydTang)
- 作者：Mars (半斤九两科技)

---

*让 AI 真正拥有长期记忆 — Mars Memory Engine*

**Version**: 1.0  
**Last Updated**: 2026-03-13

---

## Self-Improving 整合 (2026-03-14)

Memory Engine 整合了 self-improving skill 的学习逻辑：

### 触发场景
- 用户纠正 → 记录到 `memory/LEARNINGS.md`
- 命令失败 → 记录到 `memory/ERRORS.md`
- 发现更好方法 → 记录到 `memory/LEARNINGS.md` (best_practice)
- 用户请求新能力 → 记录到 `memory/FEATURE_REQUESTS.md`

### 文件对应
| self-improving | Mars Memory Engine |
|----------------|---------------------|
| corrections.md | memory/LEARNINGS.md |
| errors | memory/ERRORS.md |
| feature requests | memory/FEATURE_REQUESTS.md |

### 自动审查
每日通过 `cron_memory_review.py` 自动审查和归档。

---

## 晋升机制 v2.0 (2026-03-14)

### 自动判断规则

当用户说"记到相关的空间"时，自动判断内容类型：

| 内容类型 | 关键词 | 目标文档 |
|----------|--------|----------|
| 频道管理 | 子代理、频道、@、Discord | memory/topics/discord_management.md |
| 行为规范 | 原则、铁律、永远、不要 | SOUL.md |
| 工作流程 | 调用、spawn、工作流、代理 | AGENTS.md |
| 工具配置 | API、配置、工具、环境变量 | TOOLS.md |
| 系统配置 | 系统、Gateway、OpenClaw | memory/topics/system_config.md |
| GitHub | 仓库、开源、GitHub | memory/topics/github_automation.md |

### 沟通指令

| 指令 | 动作 |
|------|------|
| "记到相关的空间" | 自动判断 + 晋升 + GitHub同步 |
| "记到 SOUL" | 晋升到 SOUL.md |
| "记到 discord" | 晋升到 discord_management.md |
