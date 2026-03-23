---
name: memory-engine
description: "Mars Memory Engine - 持续学习与自我进化系统。整合 self-improving 逻辑，自动记录、归档、生成 Skills。触发场景：(1) 被用户纠正 (2) 命令失败 (3) 发现更好的方法 (4) 用户请求新能力 (5) 知识过时"
metadata:
  triggers:
    - correction
    - error
    - knowledge_gap
    - best_practice
    - feature_request
  files:
    - memory/ERRORS.md
    - memory/LEARNINGS.md
    - memory/FEATURE_REQUESTS.md
    - memory/topics/*.md
    - MEMORY.md
    - SOUL.md
    - AGENTS.md
    - TOOLS.md
---

# Memory Engine Skill - 持续学习与自我进化系统

> 整合 self-improving-agent 逻辑，让 Mars 具备持续学习和自我改进能力

## 版本识别与升级提示

如果 agent 之前安装或学习过旧版 Mars Memory Engine，在进入当前仓库时，必须先执行一次认知升级，不能继续沿用旧假设。

### 遇到以下仓库信号时，必须判定为“已升级版本”

- 仓库存在 `openclaw/adapter.py`
- README 明确写着 “Markdown as the source of truth”
- 仓库存在 `for-codex/README.md`
- 仓库存在 `for-codex/SKILL.md`
- 仓库存在 `for-codex/scripts/install_for_codex.sh`

### 升级后必须替换掉的旧认知

- 不要再把 LanceDB 当成主存储；Markdown 才是唯一事实源
- 不要绕过 `openclaw/adapter.py` 直接把 OpenClaw 接到存储层
- 不要因为旧版 `SKILL.md` 没变，就判断“无需更新”
- 不要把 Codex 兼容逻辑默认混在主 OpenClaw 流程里；应切换到 `for-codex/`

### 已安装旧版本的 agent 必做检查

1. 先重读仓库 `README.md`
2. 走 OpenClaw 路径时，先重读 `openclaw/adapter.py`
3. 走 Codex 路径时，先重读 `for-codex/README.md` 和 `for-codex/SKILL.md`
4. 如果记忆中的安装方式、架构描述、事实源定义与当前仓库冲突，以仓库当前文件为准

### 过期判断规则

如果 agent 出现以下任一说法，说明它仍在使用过期认知，必须先升级理解再继续：

- “LanceDB 是主记忆源”
- “只要旧版 SKILL.md 没变化，就说明仓库无需更新”
- “Codex 版本只是口头约定，没有独立安装入口”
- “OpenClaw 集成可以直接调用底层存储实现”

## 核心原则

**MEMORY.md 和 SOUL.md 保持精简**，只记录：
- 索引和导航
- 核心方向和原则
- 快速参考表格

**具体问题指向具体文档**，不重复记录。

---

## 晋升机制（关键！）

### 1. 直接晋升（立即执行）

当用户明确说"记到 XXX"时，立即执行：

| 用户指令 | 晋升目标 |
|----------|----------|
| "记到 SOUL" | `SOUL.md` |
| "记到 AGENTS" | `AGENTS.md` |
| "记到 TOOLS" | `TOOLS.md` |
| "记到 memory/topics/xxx" | `memory/topics/xxx.md` |

### 2. 自动晋升（根据内容类型）

系统自动判断晋升目标：

| 学习类型 | 晋升到 | 示例 |
|----------|--------|------|
| **行为规范** | `SOUL.md` | "不要在频道@子代理" |
| **工作流程** | `AGENTS.md` | "调用子代理用 spawn" |
| **工具配置** | `TOOLS.md` | "JINA_API_KEY 配置方法" |
| **频道管理** | `memory/topics/discord_management.md` | Discord 相关 |
| **系统配置** | `memory/topics/system_config.md` | Gateway/配置相关 |
| **开源相关** | `memory/topics/github_automation.md` | GitHub 相关 |

### 3. 优先级晋升

根据 Priority 自动决定：

| Priority | 晋升时机 |
|----------|----------|
| **critical** | 立即晋升到目标文档 |
| **high** | 24小时内晋升 |
| **medium** | 每周审查时晋升 |
| **low** | 手动确认后晋升 |

### 4. 重复问题晋升

同一问题出现 **3次** 时：
- 自动晋升到 SOUL.md 作为铁律
- 添加 `**铁律**` 标记

---

## 文件结构

```
memory/
├── ERRORS.md                    # 技术错误记录（临时）
├── LEARNINGS.md                 # 学习与纠正记录（临时）
├── FEATURE_REQUESTS.md          # 能力需求（临时）
├── topics/                     # 主题归档（长期）
│   ├── system_config.md        # 系统配置
│   ├── discord_management.md   # 频道管理
│   ├── github_automation.md   # GitHub自动化
│   └── ...
├── YYYY-MM-DD.md              # 日常日记
└── archive/                   # 归档（很少访问）

根目录：
├── MEMORY.md                   # 核心索引（精简！）
├── SOUL.md                     # 行为准则（精简！）
├── AGENTS.md                   # 工作流程
├── TOOLS.md                    # 工具配置
└── memory_engine/
    └── skills/                 # 生成的 Skills
```

---

## 记录格式

### LEARNINGS.md（临时存储）

```markdown
## [LRN-YYYYMMDD-XXX] 类别

**Logged**: ISO-8601 时间
**Priority**: low | medium | high | critical
**Status**: pending | promoted | archived
**Promote-To**: <目标文档>

### Summary
一行描述

### Details
完整上下文

### Suggested Action
具体改进建议
```

### ERRORS.md（临时存储）

```markdown
## [ERR-YYYYMMDD-XXX] 错误名称

**Logged**: ISO-8601 时间
**Priority**: high
**Status**: pending | resolved | wont_fix
**Promote-To**: <目标文档>

### Summary
错误简述

### Error
```
实际错误信息
```

### Resolution
- **Resolved**: YYYY-MM-DD
- **Notes**: 解决说明
```

---

## 晋升执行流程

```
用户纠正/发现问题
       │
       ▼
┌──────────────────┐
│ 1. 记录到临时文件  │ → memory/ERRORS.md 或 LEARNINGS.md
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ 2. 判断晋升目标    │
│ - 用户明确指定？   │ → 直接晋升
│ - Priority=critical?│ → 立即晋升
│ - 重复3次？      │ → 晋升为铁律
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ 3. 执行晋升       │
│ - 写入目标文档    │
│ - 更新索引       │
│ - 标记 Status    │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ 4. 同步到 GitHub │
└──────────────────┘
```

---

## 精简原则

### MEMORY.md（只放索引）

```markdown
# MEMORY.md - 核心记忆索引

## 快速导航
| 主题 | 位置 |
|------|------|
| 系统配置 | memory/topics/system_config.md |
| 频道管理 | memory/topics/discord_management.md |
| GitHub自动化 | memory/topics/github_automation.md |

## 学习系统
- ERRORS.md - 技术错误
- LEARNINGS.md - 学习记录
- FEATURE_REQUESTS.md - 能力需求

## 最近更新
- 2026-03-14: 晋升机制优化
```

### SOUL.md（只放核心准则）

```markdown
# SOUL.md - Mars 行为准则

## 核心原则
- 家庭优先
- 今日事今日毕

## 工作铁律（反复强调的）
- 调用子代理必须用 spawn
- 频道信息分层

## 晋升机制
- 具体问题 → memory/topics/*.md
- 工作流程 → AGENTS.md
- 工具配置 → TOOLS.md
```

---

## 用户沟通规范

### 正确指出问题的方式

```markdown
【记录这个】：<问题描述>
【晋升到】：<SOUL.md / AGENTS.md / TOOLS.md / memory/topics/xxx.md>
【原因】：<为什么重要>
```

示例：
```
【记录这个】：子代理调用必须用 sessions_spawn，不能在频道用 @ 
【晋升到】：SOUL.md
【原因】：已经犯了3次，必须强制执行
```

### 简化指令

- "记到 SOUL" → 晋升到 SOUL.md
- "记到 AGENTS" → 晋升到 AGENTS.md  
- "记到 TOOLS" → 晋升到 TOOLS.md
- "记到 discord" → 晋升到 memory/topics/discord_management.md
- "记到 system" → 晋升到 memory/topics/system_config.md
- **"记到相关的空间"** → 自动判断目标文档并晋升

---

## "记到相关的空间" 自动判断规则

当用户说"记到相关的空间"时，Mars 自动判断内容类型并晋升：

| 内容类型 | 关键词 | 目标文档 |
|----------|--------|----------|
| **频道管理** | 子代理、频道、@、Discord | `memory/topics/discord_management.md` |
| **行为规范** | 原则、铁律、永远、不要 | `SOUL.md` |
| **工作流程** | 调用、spawn、工作流、代理 | `AGENTS.md` |
| **工具配置** | API、配置、工具、环境变量 | `TOOLS.md` |
| **系统配置** | 系统、Gateway、OpenClaw | `memory/topics/system_config.md` |
| **GitHub** | 仓库、开源、GitHub | `memory/topics/github_automation.md` |

### 执行流程

```
用户说"记到相关的空间"
       │
       ▼
1. 判断内容类型（根据关键词）
       │
       ▼
2. 记录到 LEARNINGS.md
       │
       ▼
3. 晋升到目标文档
       │
       ▼
4. 同步到 GitHub（openclaw-config + mars-memory-engine）
```

### 判断示例

| 用户输入 | 判断结果 | 目标文档 |
|----------|----------|----------|
| "子代理要用 spawn 调用" | 频道管理 + 工作流程 | discord_management.md |
| "不要在频道 @ 我" | 行为规范 | SOUL.md |
| "API Key 要配置到环境变量" | 工具配置 | TOOLS.md |

---

## 自我提升承诺（Mars 必须遵守）

### 立即执行规则

当用户说"记到 XXX"时，**立即执行**：
1. 记录到 LEARNINGS.md
2. 晋升到目标文档
3. 同步到 GitHub

### 问题重复处理

当用户说"这个问题怎么又犯了"：
1. 立即记录，标记 critical
2. 检查是否已晋升过
3. 如果重复3次，自动晋升为铁律

### 每次晋升后

**必须**自动同步到：
- `openclaw-config` 仓库
- `mars-memory-engine` 开源仓库

---

## 自动审查

每日 `cron_memory_review.py` 执行：

1. **扫描** LEARNINGS.md 和 ERRORS.md
2. **识别** 待晋升的条目
3. **执行** 自动晋升（根据规则）
4. **精简** MEMORY.md 和 SOUL.md
5. **生成** 新 Skills

---

## GitHub 同步

| 仓库 | 内容 |
|------|------|
| `openclaw-config` | 完整 memory/ 和配置 |
| `mars-memory-engine` | 开源版本 |
| `bjjl-knowledge-base` | Mars日记/ |

---

*更新于 2026-03-14 | 晋升机制 v2.0*
