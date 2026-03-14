"""
Mars Memory Engine - Memory Gateway v3
多代理统一记忆接口: 写入隔离、并发控制、冲突检测

v3: + 噪音过滤 + 自适应检索 + 分类行为差异化
    + L0/L1/L2 三层写入 + Temporal Versioning
"""

import asyncio
import hashlib
import json
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

from config.models import MODEL_CLASSIFY

from core.lancedb_store import (
    LanceDBMemoryStore,
    EmbeddingProvider,
    MemoryEntry,
    MemoryCategory,
    MemoryTier,
    get_memory_store,
    get_embedder,
    generate_memory_layers,
)
from core.classifier import classify
from core.noise_filter import filter_noise
from core.adaptive_retrieval import should_skip_retrieval
from core.category_behaviors import get_behavior, EXACT_DUPLICATE_THRESHOLD


class MemoryGateway:
    """
    多代理记忆网关 v3

    职责:
    1. 写入隔离 — 每条记忆绑定 agent_id + guild_id
    2. 并发控制 — asyncio.Lock 防止写入冲突
    3. 噪音过滤 — 写入前拦截无意义内容
    4. 分类行为差异化 — 按类别选择冲突策略
    5. 冲突检测 — 写入前检查相似记忆，标记矛盾
    6. Temporal Versioning — preference/entity 用 supersede 替代 archive
    7. L0/L1/L2 三层写入 — 自动生成记忆摘要
    8. 自适应检索 — 跳过噪音查询
    9. 检索过滤 — 只返回 shared + 本 Agent 的 private
    10. DM 保护 — DM 频道记忆强制 private
    """

    DM_GUILD_ID = "__dm__"

    def __init__(
        self,
        store: Optional[LanceDBMemoryStore] = None,
        embedder: Optional[EmbeddingProvider] = None,
        conflict_threshold: float = 0.85,
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        use_llm_classify: bool = True,
        use_llm_conflict: bool = False,
    ):
        self.store = store or get_memory_store()
        self.embedder = embedder or get_embedder()
        self._write_lock = asyncio.Lock()
        self.conflict_threshold = conflict_threshold
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.use_llm_classify = use_llm_classify
        self.use_llm_conflict = use_llm_conflict

    async def write_memory(
        self,
        content: str,
        agent_id: str,
        guild_id: str,
        category: Optional[str] = None,
        scope: str = "private",
        channel_id: str = "",
        topic: str = "general",
        confidence: float = 0.7,
        importance: float = 0.5,
        source: str = "",
        source_id: str = "",
        related_topics: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        写入一条记忆

        v3 新增: 噪音过滤 + 分类行为差异化 + L0/L1/L2 + Temporal Versioning

        Returns:
            {"id": str, "conflict": bool, "action": str, "conflicting_memories": list}
            或 {"action": "filtered", "reason": str} 若被噪音过滤拦截
        """

        # ── Step 2: 噪音过滤 ──
        should_filter, reason = filter_noise(content)
        if should_filter:
            return {"action": "filtered", "reason": reason}

        # ── 自动分类 ──
        if category is None:
            category, classify_conf = classify(
                content,
                llm_api_key=self.llm_api_key,
                llm_base_url=self.llm_base_url,
                llm_model=self.llm_model,
                use_llm=self.use_llm_classify,
            )
            confidence = min(confidence, classify_conf)

        # DM 保护
        if guild_id == self.DM_GUILD_ID:
            scope = "private"

        # 生成 embedding
        embeddings = self.embedder.embed([content])
        embedding = embeddings[0]

        # ── Step 6: L0/L1/L2 生成 ──
        l0, l1, l2 = generate_memory_layers(content, category, topic)

        # ── Step 1: 分类行为差异化 ──
        behavior = get_behavior(category)

        async with self._write_lock:
            # 根据分类行为选择冲突策略
            if behavior["conflict_strategy"] == "append_only":
                # event/case: 只检查完全重复
                conflict_info = self._check_exact_duplicate(
                    embedding, agent_id, guild_id
                )
                if conflict_info["is_duplicate"]:
                    return {
                        "id": "",
                        "conflict": False,
                        "action": "skip_duplicate",
                        "conflicting_memories": [],
                    }
                conflict_info = {
                    "has_conflict": False, "action": "insert",
                    "replace_ids": [], "details": [],
                }
            elif behavior["conflict_strategy"] == "always_merge":
                # profile: 同 agent 高相似度直接 replace
                conflict_info = self._detect_conflict(
                    embedding, content, agent_id, guild_id,
                    force_replace_same_agent=True,
                )
            else:
                # merge_supported: 完整冲突检测
                conflict_info = self._detect_conflict(
                    embedding, content, agent_id, guild_id,
                )

            # 构造 MemoryEntry
            now = datetime.now()
            content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            memory_id = f"{topic}_{content_hash}_{int(now.timestamp())}"

            # ── Step 7: Temporal Versioning ──
            supersedes_id = None
            fact_key_val = None
            if behavior["allow_supersede"] and conflict_info["action"] == "replace":
                # preference/entity: 用 supersede 替代 archive
                fact_key_val = f"{category}:{topic}"
                for old_id in conflict_info["replace_ids"]:
                    self.store.update_memory_fields(old_id, {
                        "invalidated_at": now.isoformat(),
                        "superseded_by": memory_id,
                    })
                supersedes_id = conflict_info["replace_ids"][0] if conflict_info["replace_ids"] else None
            elif conflict_info["action"] == "replace":
                # 非 supersede 类别: 传统 archive
                for old_id in conflict_info["replace_ids"]:
                    self._archive_memory(old_id)

            entry = MemoryEntry(
                id=memory_id,
                content=content,
                embedding=embedding,
                category=category,
                tier=MemoryTier.PERIPHERAL.value,
                created_at=now,
                updated_at=now,
                last_accessed=now,
                confidence=confidence,
                importance=importance,
                access_count=0,
                topic=topic,
                related_topics=related_topics or [],
                source=source,
                source_id=source_id,
                scope=scope,
                agent_id=agent_id,
                guild_id=guild_id,
                channel_id=channel_id,
                conflict_flag=conflict_info["has_conflict"],
                metadata=metadata or {},
                # v3
                l0_abstract=l0,
                l1_overview=l1,
                l2_content=l2,
                supersedes=supersedes_id,
                fact_key=fact_key_val,
            )

            self.store.insert_memory(entry)

        return {
            "id": memory_id,
            "conflict": conflict_info["has_conflict"],
            "action": conflict_info["action"],
            "conflicting_memories": conflict_info.get("details", []),
        }

    def search(
        self,
        query: str,
        agent_id: str,
        guild_id: str,
        topic: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 5,
        include_history: bool = False,
    ) -> List[Dict]:
        """
        多代理隔离检索
        v3: + 自适应跳过 + include_history 参数
        """

        # ── Step 3: 自适应检索跳过 ──
        if should_skip_retrieval(query):
            return []

        embeddings = self.embedder.embed([query], task="retrieval.query")
        embedding = embeddings[0]

        results = self.store.search_hybrid(
            query=query,
            embedding=embedding,
            agent_id=agent_id,
            guild_id=guild_id,
            topic=topic,
            category=category,
            limit=limit,
            include_history=include_history,
        )

        for r in results:
            if r.get("conflict_flag"):
                r["_conflict_note"] = (
                    f"此记忆与其他记忆存在冲突，写入者: {r.get('agent_id', 'unknown')}"
                )

        return results

    def _check_exact_duplicate(
        self, embedding: List[float], agent_id: str, guild_id: str
    ) -> Dict:
        """检查是否完全重复 (append_only 类别用)"""
        try:
            similar = self.store.search_hybrid(
                query="", embedding=embedding,
                agent_id=agent_id, guild_id=guild_id, limit=1,
            )
        except Exception:
            return {"is_duplicate": False}

        if not similar:
            return {"is_duplicate": False}

        mem = similar[0]
        mem_embedding = mem.get("embedding", [])
        if mem_embedding is None or (hasattr(mem_embedding, '__len__') and len(mem_embedding) == 0):
            return {"is_duplicate": False}

        similarity = self._cosine_similarity(embedding, mem_embedding)
        return {"is_duplicate": similarity >= EXACT_DUPLICATE_THRESHOLD}

    def _detect_conflict(
        self,
        embedding: List[float],
        content: str,
        agent_id: str,
        guild_id: str,
        force_replace_same_agent: bool = False,
    ) -> Dict:
        """
        冲突检测

        force_replace_same_agent: True 时同 agent 高相似度直接 replace (always_merge 用)
        """
        try:
            similar = self.store.search_hybrid(
                query=content, embedding=embedding,
                agent_id=agent_id, guild_id=guild_id, limit=3,
            )
        except Exception:
            return {"has_conflict": False, "action": "insert", "replace_ids": [], "details": []}

        if not similar:
            return {"has_conflict": False, "action": "insert", "replace_ids": [], "details": []}

        conflicts = []
        for mem in similar:
            mem_embedding = mem.get("embedding", [])
            if mem_embedding is None or (hasattr(mem_embedding, '__len__') and len(mem_embedding) == 0):
                continue
            similarity = self._cosine_similarity(embedding, mem_embedding)
            if similarity >= self.conflict_threshold:
                conflicts.append({
                    "id": mem["id"],
                    "content_preview": mem["content"][:100],
                    "similarity": round(similarity, 3),
                    "agent_id": mem.get("agent_id", "unknown"),
                })

        if not conflicts:
            return {"has_conflict": False, "action": "insert", "replace_ids": [], "details": []}

        same_agent_conflicts = [c for c in conflicts if c["agent_id"] == agent_id]
        cross_agent_conflicts = [c for c in conflicts if c["agent_id"] != agent_id]

        if same_agent_conflicts and (not cross_agent_conflicts or force_replace_same_agent):
            return {
                "has_conflict": False,
                "action": "replace",
                "replace_ids": [c["id"] for c in same_agent_conflicts],
                "details": same_agent_conflicts,
            }
        else:
            action = "coexist"
            replace_ids = []

            if self.use_llm_conflict and cross_agent_conflicts:
                action, replace_ids = self._llm_conflict_resolve(
                    content, cross_agent_conflicts
                )

            return {
                "has_conflict": action == "coexist",
                "action": action,
                "replace_ids": replace_ids,
                "details": cross_agent_conflicts,
            }

    def _llm_conflict_resolve(
        self, new_content: str, conflicts: List[Dict]
    ) -> tuple:
        """用 LLM 判断跨 Agent 冲突: UPDATE vs SUPPLEMENT"""
        import openai
        import os

        key = self.llm_api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        url = self.llm_base_url or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "")
        mdl = self.llm_model or os.getenv("LLM_MODEL") or MODEL_CLASSIFY

        if not key:
            return "coexist", []

        old_previews = "\n".join(
            f"- [{c['id']}] {c['content_preview']}" for c in conflicts
        )
        prompt = (
            "你是记忆管理器。新记忆和旧记忆高度相似，判断新记忆应该：\n"
            "A) UPDATE — 新记忆是旧记忆的更新版本，应替换旧记忆\n"
            "B) SUPPLEMENT — 新记忆是补充信息，应与旧记忆共存\n\n"
            f"旧记忆:\n{old_previews}\n\n"
            f"新记忆:\n{new_content[:300]}\n\n"
            "只回答 UPDATE 或 SUPPLEMENT:"
        )

        try:
            client = openai.OpenAI(api_key=key, base_url=url or None)
            resp = client.chat.completions.create(
                model=mdl,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0,
            )
            answer = resp.choices[0].message.content.strip().upper()
            if "UPDATE" in answer:
                return "replace", [c["id"] for c in conflicts]
            return "coexist", []
        except Exception:
            return "coexist", []

    def _archive_memory(self, memory_id: str):
        """将旧记忆移入 archive (软删除)"""
        self.store.update_memory_fields(memory_id, {
            "tier": "archived",
            "updated_at": datetime.now(),
        })

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        a_arr = np.array(a, dtype=np.float32)
        b_arr = np.array(b, dtype=np.float32)
        dot = np.dot(a_arr, b_arr)
        norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        if norm == 0:
            return 0.0
        return float(dot / norm)


# 全局实例
_gateway = None


def get_gateway(**kwargs) -> MemoryGateway:
    global _gateway
    if _gateway is None:
        _gateway = MemoryGateway(**kwargs)
    return _gateway
