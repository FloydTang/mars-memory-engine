"""
Mars Memory Engine - 查询侧自适应检索
在执行向量搜索前，快速判断查询是否值得检索
"""

import re
import unicodedata

# 命令前缀 — 不需要记忆检索的操作型查询
_COMMAND_PREFIXES = (
    "/", "git ", "npm ", "pip ", "docker ", "cd ", "ls ", "cat ",
    "mkdir ", "rm ", "cp ", "mv ", "curl ", "wget ",
)

# 问候/肯定/表情 — 复用 noise_filter 的模式
_SKIP_PATTERNS = re.compile(
    r"^(hi|hello|hey|yo|good\s*(morning|afternoon|evening)|"
    r"你好|嗨|早上好|下午好|晚上好|"
    r"yes|no|ok|okay|sure|thanks|谢谢|好的|是的|嗯|哦|"
    r"go ahead|continue|proceed|继续|实施|开始吧|"
    r"ping|pong|test|HEARTBEAT)[\s!！.。]*$",
    re.IGNORECASE,
)

# 纯表情
_EMOJI_ONLY = re.compile(
    r"^[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff"
    r"\U0001f1e0-\U0001f1ff\U00002702-\U000027b0\U0000fe00-\U0000fe0f"
    r"\U0000200d\s]+$"
)

# 记忆意图词 — 即使查询很短也要强制检索
_MEMORY_INTENT = re.compile(
    r"(remember|recall|forgot|上次|之前|以前|你记得|还记得|"
    r"did i (tell|mention|say)|what did i|我说过|提到过|"
    r"last time|before|yesterday|my name|my email|my prefer)",
    re.IGNORECASE,
)

# CJK 字符范围
_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")

MIN_LENGTH_DEFAULT = 5
MIN_LENGTH_CJK = 3


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RANGE.search(text))


def _has_question_mark(text: str) -> bool:
    return "?" in text or "？" in text


def should_skip_retrieval(query: str) -> bool:
    """
    判断是否应跳过记忆检索。

    Returns:
        True = 跳过检索（返回空结果），False = 正常检索
    """
    text = query.strip()

    # 空查询
    if not text:
        return True

    # 强制检索: 含记忆意图词
    if _MEMORY_INTENT.search(text):
        return False

    # 强制检索: 含问号（可能在问关于过去的事）
    if _has_question_mark(text):
        return False

    # 短查询过滤 (CJK 感知)
    min_len = MIN_LENGTH_CJK if _has_cjk(text) else MIN_LENGTH_DEFAULT
    if len(text) < min_len:
        return True

    # 命令前缀
    text_lower = text.lower()
    for prefix in _COMMAND_PREFIXES:
        if text_lower.startswith(prefix):
            return True

    # 问候/肯定/表情
    if _SKIP_PATTERNS.match(text):
        return True

    if _EMOJI_ONLY.match(text):
        return True

    return False
