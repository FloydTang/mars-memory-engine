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
    - memory_engine/skills/*.json
---

# Memory Engine Skill - 持续学习与自我进化系统

> 整合 self-improving-agent 逻辑，让 Mars 具备持续学习和自我改进能力

## 概述

Memory Engine 是 Mars 的核心学习系统，具备以下能力：
- **自动记录**：错误、纠正、知识更新
- **智能归档**：根据主题分类存储
- **技能生成**：从学习中提取可复用的 Skills
- **持续进化**：通过每日审查不断优化

## 快速参考

| 场景 | 动作 |
|------|------|
| 命令/操作失败 | 记录到 `memory/ERRORS.md` |
| 用户纠正你 | 记录到 `memory/LEARNINGS.md`，category: `correction` |
| 用户想要不存在的能力 | 记录到 `memory/FEATURE_REQUESTS.md` |
| API/外部工具失败 | 记录到 `memory/ERRORS.md`，包含集成详情 |
| 知识过时/错误 | 记录到 `memory/LEARNINGS.md`，category: `knowledge_gap` |
| 发现更好的方法 | 记录到 `memory/LEARNINGS.md`，category: `best_practice` |
| 重要学习 | 晋升到 `SOUL.md` / `AGENTS.md` / `TOOLS.md` |

## 文件结构

```
memory/
├── ERRORS.md              # 技术错误记录
├── LEARNINGS.md          # 学习与纠正记录
├── FEATURE_REQUESTS.md   # 能力需求
├── topics/               # 主题归档
│   ├── system_config.md
│   ├── discord_management.md
│   └── ...
├── YYYY-MM-DD.md        # 日常日记
└── memory_engine/
    └── skills/           # 生成的 Skills
        ├── skill_xxx.json
        └── ...
```

## 记录格式

### 错误记录 (ERRORS.md)

```markdown
## [ERR-YYYYMMDD-XXX] 错误名称

**Logged**: ISO-8601 时间
**Priority**: high
**Status**: pending | resolved | wont_fix

### Summary
错误简述

### Error
```
实际错误信息
```

### Context
- 操作/命令
- 使用的参数
- 环境细节

### Resolution (resolved 时填写)
- **Resolved**: YYYY-MM-DD
- **Notes**: 解决说明
```

### 学习记录 (LEARNINGS.md)

```markdown
## [LRN-YYYYMMDD-XXX] 类别

**Logged**: ISO-8601 时间
**Priority**: low | medium | high | critical
**Status**: pending | promoted

### Summary
一行描述

### Details
完整上下文

### Suggested Action
具体改进建议

### Metadata
- Source: correction | knowledge_gap | best_practice
- Tags: tag1, tag2
```

### 能力需求 (FEATURE_REQUESTS.md)

```markdown
## [FEAT-YYYYMMDD-XXX] 能力名称

**Logged**: ISO-8601 时间
**Priority**: medium
**Status**: pending | implemented

### Requested Capability
用户想要的能力

### User Context
用户为什么需要

### Complexity Estimate
simple | medium | complex
```

## 晋升路径

| 学习类型 | 晋升到 |
|----------|--------|
| 行为模式 | SOUL.md |
| 工作流程 | AGENTS.md |
| 工具技巧 | TOOLS.md |
| 系统配置 | memory/topics/system_config.md |
| 频道管理 | memory/topics/discord_management.md |

## 每日审查流程

每日自动执行 `cron_memory_review.py`：

1. **扫描记忆**：读取最近的 memory 文件
2. **主题归档**：根据内容分类到 topics/
3. **生成 Skills**：从高频模式提取可复用逻辑
4. **重构索引**：保持 MEMORY.md 精简

## 同步到 GitHub

自动同步到两个仓库：

| 仓库 | 路径 | 用途 |
|------|------|------|
| `openclaw-config` | `memory/` | Mars 配置备份 |
| `bjjl-knowledge-base` | `Mars日记/` | 九两 Obsidian 查看 |

## 触发方式

在对话中触发学习记录：
- 用户说 "不是这样的"、"应该是..."
- 命令执行失败
- 发现更好的解决方案
- 用户请求 "能不能做..."

## 示例

**用户纠正**：
```
用户：子代理要用 spawn 调用，不是 @

→ 记录到 LEARNINGS.md
→ 晋升到 SOUL.md 规范
→ 同步到 GitHub
```

**错误发生**：
```
命令：git push
错误：Permission denied

→ 记录到 ERRORS.md
→ 解决后标记 resolved
→ 晋升到 TOOLS.md
```

---

*整合自 self-improving-agent | 更新于 2026-03-14*
