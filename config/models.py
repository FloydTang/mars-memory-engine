"""
Mars Memory Engine - 模型配置中心
统一管理所有模块的模型引用，避免硬编码分散在各文件中。
"""

# 分类/路由任务 — 快速、低成本
MODEL_CLASSIFY = "yunwu/claude-haiku-4-5-20251001"

# 记忆操作（归档、整理、去噪）— 平衡质量与成本
MODEL_MEMORY_OPS = "yunwu/claude-sonnet-4-6"

# 知识蒸馏（Skill 生成）— 需要较好的理解力
MODEL_DISTILL = "yunwu/claude-sonnet-4-6"

# 主决策/复杂推理 — 最强模型
MODEL_MAIN = "yunwu/claude-opus-4-6"
