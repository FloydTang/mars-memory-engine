"""
Mars Memory Engine - 写入侧噪音过滤
在记忆写入前拦截无意义内容，防止垃圾数据进入记忆库
"""

import re

# 问候语 (中英文)
_GREETINGS = re.compile(
    r"^(hi|hello|hey|yo|sup|hola|"
    r"你好|嗨|早上好|下午好|晚上好|早安|晚安|good\s*(morning|afternoon|evening|night))[\s!！.。]*$",
    re.IGNORECASE,
)

# Agent 否定/空记忆
_AGENT_DENIAL = re.compile(
    r"(i don'?t have|no memories|没有记忆|无记忆|i'?m not sure|"
    r"i don'?t recall|i don'?t remember|no relevant|找不到相关)",
    re.IGNORECASE,
)

# 系统标记
_SYSTEM_MARKERS = re.compile(
    r"(HEARTBEAT|fresh session|session start|ping|pong|test$)",
    re.IGNORECASE,
)

# 纯表情 (emoji-only)
_EMOJI_ONLY = re.compile(
    r"^[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff"
    r"\U0001f1e0-\U0001f1ff\U00002702-\U000027b0\U0000fe00-\U0000fe0f"
    r"\U0000200d\s]+$"
)

# 单纯肯定/否定
_AFFIRMATIONS = re.compile(
    r"^(yes|no|ok|okay|sure|thanks|thank you|谢谢|好的|是的|不是|嗯|哦|对|好|行)[\s!！.。]*$",
    re.IGNORECASE,
)

MIN_CONTENT_LENGTH = 5


def filter_noise(content: str) -> tuple[bool, str]:
    """
    检查内容是否应被过滤。

    Returns:
        (should_filter, reason) — should_filter=True 表示应拒绝写入
    """
    text = content.strip()

    # 先匹配语义模式（可能短于 MIN_CONTENT_LENGTH）
    if _GREETINGS.match(text):
        return True, "greeting"

    if _AFFIRMATIONS.match(text):
        return True, "affirmation"

    if _EMOJI_ONLY.match(text):
        return True, "emoji_only"

    if _SYSTEM_MARKERS.search(text):
        return True, "system_marker"

    if _AGENT_DENIAL.search(text):
        return True, "agent_denial"

    if len(text) < MIN_CONTENT_LENGTH:
        return True, f"too_short (len={len(text)})"

    return False, ""
