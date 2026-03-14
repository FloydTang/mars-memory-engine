"""
Mars Memory Engine - 分类行为差异化
每个记忆类别的冲突策略、操作权限定义
"""

# 冲突策略:
#   always_merge   — 同 agent 高相似度直接 replace，不问 LLM (profile)
#   merge_supported — 走完整冲突检测流程 (preference/entity/pattern)
#   append_only    — 跳过冲突检测，直接 insert；完全重复则 skip (event/case)

CATEGORY_BEHAVIORS = {
    "profile": {
        "conflict_strategy": "always_merge",
        "allow_supersede": False,
    },
    "preference": {
        "conflict_strategy": "merge_supported",
        "allow_supersede": True,
    },
    "entity": {
        "conflict_strategy": "merge_supported",
        "allow_supersede": True,
    },
    "event": {
        "conflict_strategy": "append_only",
        "allow_supersede": False,
    },
    "case": {
        "conflict_strategy": "append_only",
        "allow_supersede": False,
    },
    "pattern": {
        "conflict_strategy": "merge_supported",
        "allow_supersede": False,
    },
}

# 完全重复判定阈值 (cosine similarity)
EXACT_DUPLICATE_THRESHOLD = 0.95


def get_behavior(category: str) -> dict:
    """获取分类行为配置，未知分类按 pattern 处理"""
    return CATEGORY_BEHAVIORS.get(category, CATEGORY_BEHAVIORS["pattern"])
