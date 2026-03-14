"""
Mars Memory Engine - 混合记忆分类器
规则优先(~60%覆盖) + LLM 回退

六分类: profile, preference, entity, event, case, pattern
"""

import os
import re
from typing import Optional, Tuple

from core.lancedb_store import MemoryCategory

# ─── 规则层 ───────────────────────────────────────────────

# 每条规则: (compiled_regex, category, base_confidence)
_RULES: list[Tuple[re.Pattern, str, float]] = []


def _r(pattern: str, cat: str, conf: float = 0.9):
    _RULES.append((re.compile(pattern, re.IGNORECASE), cat, conf))


# Event — 时间标记 / 发生了某事
_r(r"(昨天|今天|明天|上周|上个月|刚才|最近|前天|\d{4}[年\-/]\d{1,2})", "event", 0.9)
_r(r"(发生了|完成了|出了|遇到了|参加了|购买了|签了|上线了|部署了|发布了)", "event", 0.85)

# Preference — 偏好/喜好/讨厌
_r(r"(喜欢|偏好|讨厌|不喜欢|习惯用|总是用|prefer|favorite|hate|always use)", "preference", 0.9)
_r(r"(不要|别用|禁止|必须用|只用|never|always|must use)", "preference", 0.85)

# Profile — 自我介绍 / 身份信息
_r(r"(我是|我叫|我的名字|我在.*工作|我的职业|my name is|i am a)", "profile", 0.9)
_r(r"(我的邮箱|我的手机|我住在|我来自|联系方式)", "profile", 0.85)

# Entity — 具体事物/人名/公司
_r(r"(是一个|是一家|是一种|位于|成立于|创始人|CEO|CTO)", "entity", 0.85)
_r(r"^[\w\s]{1,30}(是|：|:)", "entity", 0.7)  # "XXX是..." 定义式句型

# Case — 经验/教训/复盘
_r(r"(经验|教训|复盘|总结|踩坑|注意事项|最佳实践|lesson|takeaway)", "case", 0.9)
_r(r"(下次|以后|应该|不应该|避免|记住)", "case", 0.8)

# Pattern — 规律/规则/流程 (兜底分类也是 pattern)
_r(r"(规律|规则|流程|步骤|模式|每次.*都|通常|一般来说|pattern|workflow)", "pattern", 0.85)


def classify_by_rules(content: str) -> Tuple[Optional[str], float]:
    """
    规则分类: 返回 (category, confidence) 或 (None, 0.0)
    取最高 confidence 的匹配。
    """
    best_cat: Optional[str] = None
    best_conf: float = 0.0

    for regex, cat, conf in _RULES:
        if regex.search(content):
            if conf > best_conf:
                best_cat = cat
                best_conf = conf

    return best_cat, best_conf


# ─── LLM 层 ──────────────────────────────────────────────

_CLASSIFY_PROMPT = """你是记忆分类器。将下面的文本分到恰好一个类别，只返回类别名称，不要解释。

六个类别:
- profile: 用户身份、个人信息
- preference: 偏好、喜好、习惯
- entity: 具体事物、人、公司、产品
- event: 发生的事件、时间相关
- case: 经验教训、复盘总结
- pattern: 规律、规则、流程、通用知识

文本: {content}

类别:"""

_VALID_CATEGORIES = {c.value for c in MemoryCategory}


def classify_by_llm(
    content: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[str, float]:
    """
    LLM 分类: 返回 (category, confidence)
    失败时回退到 pattern。
    """
    import openai

    key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    url = base_url or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "")
    mdl = model or os.getenv("LLM_MODEL") or "kimi-k2.5"

    if not key:
        return MemoryCategory.PATTERN.value, 0.5

    try:
        client = openai.OpenAI(api_key=key, base_url=url or None)
        resp = client.chat.completions.create(
            model=mdl,
            messages=[{"role": "user", "content": _CLASSIFY_PROMPT.format(content=content[:500])}],
            max_tokens=20,
            temperature=0,
        )
        answer = resp.choices[0].message.content.strip().lower()
        # 提取有效分类名
        for cat in _VALID_CATEGORIES:
            if cat in answer:
                return cat, 0.85
        return MemoryCategory.PATTERN.value, 0.5
    except Exception:
        return MemoryCategory.PATTERN.value, 0.5


# ─── 混合分类入口 ────────────────────────────────────────

def classify(
    content: str,
    rule_threshold: float = 0.8,
    llm_api_key: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_model: Optional[str] = None,
    use_llm: bool = True,
) -> Tuple[str, float]:
    """
    混合分类: 规则优先，confidence < threshold 时调 LLM。

    Returns:
        (category, confidence)
    """
    cat, conf = classify_by_rules(content)

    if cat and conf >= rule_threshold:
        return cat, conf

    if use_llm:
        llm_cat, llm_conf = classify_by_llm(
            content, api_key=llm_api_key, base_url=llm_base_url, model=llm_model
        )
        # 如果规则有低置信度结果，与 LLM 结果比较
        if cat and conf > llm_conf:
            return cat, conf
        return llm_cat, llm_conf

    # 无 LLM 且规则低置信度 → 用规则结果或默认 pattern
    return cat or MemoryCategory.PATTERN.value, conf or 0.5
