"""
Mars Memory Engine - LanceDB Core Schema
基于 memory-lancedb-pro 架构的轻量级实现

v3.0: L0/L1/L2 三层记忆 + Temporal Versioning + Weibull 衰减
      + Embedding 缓存 + 检索 pipeline 增强 + 复合晋升/降级
"""

import lancedb
import pyarrow as pa
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import hashlib
import json
import math
import os
import re
import time
import threading


class MemoryCategory(Enum):
    """6分类记忆系统"""
    PROFILE = "profile"
    PREFERENCE = "preference"
    ENTITY = "entity"
    EVENT = "event"
    CASE = "case"
    PATTERN = "pattern"


class MemoryTier(Enum):
    """3层记忆晋升系统"""
    PERIPHERAL = "peripheral"
    WORKING = "working"
    CORE = "core"


@dataclass
class MemoryEntry:
    """记忆条目 Schema — v3: L0/L1/L2 三层 + Temporal Versioning"""
    id: str
    content: str                  # 完整内容 (兼容旧版)
    embedding: List[float]        # 向量嵌入
    category: str
    tier: str

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)

    # 置信度与权重
    confidence: float = 0.7
    importance: float = 0.5
    access_count: int = 0

    # 主题关联
    topic: str = "general"
    related_topics: List[str] = field(default_factory=list)

    # 来源
    source: str = ""
    source_id: str = ""
    source_file: str = ""
    source_section: str = ""
    source_type: str = ""
    entry_hash: str = ""

    # 多代理隔离
    scope: str = "private"
    agent_id: str = ""
    guild_id: str = ""
    channel_id: str = ""

    # 冲突标记
    conflict_flag: bool = False

    # 元数据
    metadata: Dict = field(default_factory=dict)

    # ── v3 新增: L0/L1/L2 三层记忆 ──
    l0_abstract: str = ""         # 一句话摘要 (向量匹配用)
    l1_overview: str = ""         # 结构化概览 (上下文注入用)
    l2_content: str = ""          # 完整内容 (深度回忆用)

    # ── v3 新增: Temporal Versioning ──
    invalidated_at: Optional[str] = None   # ISO 时间戳, 被取代时设置
    supersedes: Optional[str] = None       # 取代的旧记忆 ID
    superseded_by: Optional[str] = None    # 被谁取代
    fact_key: Optional[str] = None         # 主题键 (如 "preference:语言偏好")


class LanceDBMemoryStore:
    """
    LanceDB 记忆存储引擎 v3

    Schema:
    - 主表: memories (向量索引 + 全文索引)
    - 辅助表: topics (主题聚类)
    - 辅助表: access_log (访问日志)
    """

    def __init__(self, db_path: str = "~/.openclaw/memory/lancedb"):
        self.db_path = os.path.expanduser(db_path)
        self.db = lancedb.connect(self.db_path)
        self._init_tables()

    def _init_tables(self):
        """初始化数据表"""

        if "memories" not in self.db.table_names():
            memories_schema = pa.schema([
                ("id", pa.string()),
                ("content", pa.string()),
                ("embedding", pa.list_(pa.float32(), 1024)),
                ("category", pa.string()),
                ("tier", pa.string()),
                ("created_at", pa.timestamp('us')),
                ("updated_at", pa.timestamp('us')),
                ("last_accessed", pa.timestamp('us')),
                ("confidence", pa.float32()),
                ("importance", pa.float32()),
                ("access_count", pa.int32()),
                ("topic", pa.string()),
                ("related_topics", pa.list_(pa.string())),
                ("source", pa.string()),
                ("source_id", pa.string()),
                ("source_file", pa.string()),
                ("source_section", pa.string()),
                ("source_type", pa.string()),
                ("entry_hash", pa.string()),
                ("scope", pa.string()),
                ("agent_id", pa.string()),
                ("guild_id", pa.string()),
                ("channel_id", pa.string()),
                ("conflict_flag", pa.bool_()),
                ("metadata", pa.string()),
                # v3 新增字段
                ("l0_abstract", pa.string()),
                ("l1_overview", pa.string()),
                ("l2_content", pa.string()),
                ("invalidated_at", pa.string()),   # ISO timestamp or ""
                ("supersedes", pa.string()),
                ("superseded_by", pa.string()),
                ("fact_key", pa.string()),
            ])
            self.db.create_table("memories", schema=memories_schema)

        if "topics" not in self.db.table_names():
            topics_schema = pa.schema([
                ("id", pa.string()),
                ("name", pa.string()),
                ("description", pa.string()),
                ("memory_count", pa.int32()),
                ("created_at", pa.timestamp('us')),
                ("updated_at", pa.timestamp('us')),
                ("centroid", pa.list_(pa.float32(), 1024)),
                ("keywords", pa.list_(pa.string())),
                ("file_path", pa.string()),
            ])
            self.db.create_table("topics", schema=topics_schema)

        if "access_log" not in self.db.table_names():
            access_schema = pa.schema([
                ("memory_id", pa.string()),
                ("accessed_at", pa.timestamp('us')),
                ("query", pa.string()),
                ("relevance_score", pa.float32()),
            ])
            self.db.create_table("access_log", schema=access_schema)

    @property
    def memories_table(self):
        return self.db.open_table("memories")

    @property
    def topics_table(self):
        return self.db.open_table("topics")

    @property
    def access_log_table(self):
        return self.db.open_table("access_log")

    def insert_memory(self, entry: MemoryEntry) -> str:
        """插入新记忆"""
        if not entry.id:
            content_hash = hashlib.md5(entry.content.encode()).hexdigest()[:8]
            entry.id = f"{entry.topic}_{content_hash}_{int(datetime.now().timestamp())}"

        data = {
            "id": entry.id,
            "content": entry.content,
            "embedding": entry.embedding,
            "category": entry.category,
            "tier": entry.tier,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "last_accessed": entry.last_accessed,
            "confidence": entry.confidence,
            "importance": entry.importance,
            "access_count": entry.access_count,
            "topic": entry.topic,
            "related_topics": entry.related_topics,
            "source": entry.source,
            "source_id": entry.source_id,
            "source_file": entry.source_file,
            "source_section": entry.source_section,
            "source_type": entry.source_type,
            "entry_hash": entry.entry_hash,
            "scope": entry.scope,
            "agent_id": entry.agent_id,
            "guild_id": entry.guild_id,
            "channel_id": entry.channel_id,
            "conflict_flag": entry.conflict_flag,
            "metadata": json.dumps(entry.metadata),
            # v3
            "l0_abstract": entry.l0_abstract,
            "l1_overview": entry.l1_overview,
            "l2_content": entry.l2_content,
            "invalidated_at": entry.invalidated_at or "",
            "supersedes": entry.supersedes or "",
            "superseded_by": entry.superseded_by or "",
            "fact_key": entry.fact_key or "",
        }

        self.memories_table.add([data])
        return entry.id

    def search_hybrid(
        self,
        query: str,
        embedding: List[float],
        agent_id: str,
        guild_id: str,
        topic: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 5,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        include_history: bool = False,
    ) -> List[Dict]:
        """
        混合检索: Vector + BM25 (RRF 融合)
        v3: + Length Norm + Recency Boost + Hardmin 截断 + invalidated_at 过滤
        """

        # 构建隔离过滤条件
        isolation_filter = (
            f"guild_id = '{guild_id}' AND "
            f"(scope = 'shared' OR agent_id = '{agent_id}')"
        )

        # 默认过滤已失效记忆
        if not include_history:
            isolation_filter += " AND invalidated_at = ''"

        # 1. 向量搜索
        vector_results = self.memories_table.search(embedding)
        vector_results = vector_results.where(isolation_filter)
        if topic:
            vector_results = vector_results.where(f"topic = '{topic}'")
        if category:
            vector_results = vector_results.where(f"category = '{category}'")
        vector_results = vector_results.limit(limit * 2).to_pandas()

        # 2. BM25 全文搜索
        try:
            text_results = self.memories_table.search(query, query_type="fts")
            text_results = text_results.where(isolation_filter)
            if topic:
                text_results = text_results.where(f"topic = '{topic}'")
            text_results = text_results.limit(limit * 2).to_pandas()
        except Exception:
            text_results = vector_results.iloc[:0]

        # 3. RRF 融合
        combined = self._rrf_fusion(
            vector_results, text_results, vector_weight, bm25_weight, k=60
        )

        if combined.empty:
            return []

        # 4. Weibull 生命周期衰减 (Step 8)
        combined = self._apply_lifecycle_decay(combined)

        # 5. Length Normalization (Step 5)
        combined = self._apply_length_normalization(combined)

        # 6. Recency Boost (Step 5)
        combined = self._apply_recency_boost(combined)

        # 7. Hardmin 截断 (Step 5)
        combined = combined[combined['final_score'] >= 0.05]

        results = combined.head(limit).to_dict('records')
        self.record_access(results, query)
        return results

    def _rrf_fusion(self, vector_df, text_df, vector_weight, bm25_weight, k=60):
        """RRF 融合算法"""
        import pandas as pd

        vector_df = vector_df.copy()
        vector_df['rrf_score'] = vector_weight / (k + vector_df.index + 1)

        text_df = text_df.copy()
        text_df['rrf_score'] = bm25_weight / (k + text_df.index + 1)

        combined = {}
        for _, row in vector_df.iterrows():
            combined[row['id']] = {**row.to_dict(), 'rrf_score': row['rrf_score']}

        for _, row in text_df.iterrows():
            if row['id'] in combined:
                combined[row['id']]['rrf_score'] += row['rrf_score']
            else:
                combined[row['id']] = {**row.to_dict(), 'rrf_score': row['rrf_score']}

        result = pd.DataFrame(list(combined.values()))
        if result.empty:
            return result
        return result.sort_values('rrf_score', ascending=False)

    # ── Weibull 衰减配置 (Step 8) ──
    DECAY_CONFIG = {
        "profile":    {"half_life": 365, "beta": 0.8, "decay_floor": 0.9},
        "preference": {"half_life": 180, "beta": 1.0, "decay_floor": 0.7},
        "entity":     {"half_life": 90,  "beta": 1.0, "decay_floor": 0.7},
        "pattern":    {"half_life": 120, "beta": 1.0, "decay_floor": 0.6},
        "case":       {"half_life": 30,  "beta": 1.2, "decay_floor": 0.5},
        "event":      {"half_life": 14,  "beta": 1.3, "decay_floor": 0.5},
    }

    def _apply_lifecycle_decay(self, df):
        """Weibull 拉伸指数衰减 + 访问强化 + 频率分量"""
        now = datetime.now()

        def compute_decay(row):
            category = row.get('category', 'pattern')
            config = self.DECAY_CONFIG.get(
                category, {"half_life": 60, "beta": 1.0, "decay_floor": 0.5}
            )
            hl = config['half_life']
            beta = config['beta']
            floor = config['decay_floor']

            days_old = max((now - row['created_at']).days, 0)
            access_count = row.get('access_count', 0)
            importance = row.get('importance', 0.5)

            # Weibull 衰减
            lam = math.log(2) / (hl ** beta) if hl > 0 else 1.0
            recency = math.exp(-lam * (days_old ** beta))

            # 访问强化: 高频访问延长有效半衰期 (最大 3x)
            reinforcement = min(1.0 + 0.5 * math.log1p(access_count), 3.0)
            recency = recency ** (1.0 / reinforcement)

            # 频率分量: 对数饱和
            frequency = 1.0 - math.exp(-access_count / 5.0)

            # 综合评分
            score = 0.5 * recency + 0.3 * frequency + 0.2 * importance
            return max(score, floor)

        df['decay_score'] = df.apply(compute_decay, axis=1)
        df['final_score'] = df['rrf_score'] * df['decay_score']
        return df.sort_values('final_score', ascending=False)

    def _apply_length_normalization(self, df):
        """长文本降权 (Step 5)"""
        anchor = 500.0

        def length_penalty(row):
            text = row.get('content', '')
            char_len = max(len(text), anchor)
            return 1.0 / (1.0 + math.log2(char_len / anchor))

        df['final_score'] = df['final_score'] * df.apply(length_penalty, axis=1)
        return df

    def _apply_recency_boost(self, df):
        """近期记忆加成 (Step 5)"""
        now = datetime.now()
        half_life_days = 14.0

        def recency_bonus(row):
            days_old = max((now - row['created_at']).days, 0)
            return 0.1 * math.exp(-days_old / half_life_days)

        df['final_score'] = df['final_score'] + df.apply(recency_bonus, axis=1)
        return df.sort_values('final_score', ascending=False)

    # ── 晋升/降级 (Step 9) ──

    def promote_memory(self, memory_id: str) -> bool:
        """记忆晋升/降级: 复合条件评估"""
        table = self.memories_table
        result = table.search().where(f"id = '{memory_id}'").limit(1).to_pandas()

        if len(result) == 0:
            return False

        memory = result.iloc[0]
        current_tier = memory['tier']
        access_count = memory.get('access_count', 0)
        importance = memory.get('importance', 0.5)
        category = memory.get('category', 'pattern')

        # 计算 composite score
        config = self.DECAY_CONFIG.get(
            category, {"half_life": 60, "beta": 1.0, "decay_floor": 0.5}
        )
        days_old = max((datetime.now() - memory['created_at']).days, 0)
        hl = config['half_life']
        beta = config['beta']
        lam = math.log(2) / (hl ** beta) if hl > 0 else 1.0
        recency = math.exp(-lam * (days_old ** beta))
        reinforcement = min(1.0 + 0.5 * math.log1p(access_count), 3.0)
        recency = recency ** (1.0 / reinforcement)
        frequency = 1.0 - math.exp(-access_count / 5.0)
        composite = 0.5 * recency + 0.3 * frequency + 0.2 * importance
        composite = max(composite, config['decay_floor'])

        new_tier = current_tier

        # 晋升
        if current_tier == MemoryTier.PERIPHERAL.value:
            if access_count >= 3 and composite >= 0.4:
                new_tier = MemoryTier.WORKING.value
        elif current_tier == MemoryTier.WORKING.value:
            if access_count >= 10 and composite >= 0.7 and importance >= 0.8:
                new_tier = MemoryTier.CORE.value

        # 降级
        if current_tier == MemoryTier.WORKING.value:
            if composite < 0.15 or (days_old > 60 and access_count < 3):
                new_tier = MemoryTier.PERIPHERAL.value
        elif current_tier == MemoryTier.CORE.value:
            if composite < 0.15 and access_count < 3:
                new_tier = MemoryTier.WORKING.value

        if new_tier != current_tier:
            table.update(where=f"id = '{memory_id}'", values={"tier": new_tier})
            return True

        return False

    def update_memory_fields(self, memory_id: str, values: dict):
        """通用字段更新"""
        try:
            self.memories_table.update(where=f"id = '{memory_id}'", values=values)
        except Exception:
            pass

    def record_access(self, results: List[Dict], query: str):
        """记录检索命中并更新访问统计"""
        now = datetime.now()
        for row in results:
            memory_id = row.get("id")
            if not memory_id:
                continue

            new_access_count = int(row.get("access_count", 0)) + 1
            self.update_memory_fields(memory_id, {
                "last_accessed": now,
                "updated_at": now,
                "access_count": new_access_count,
            })

            try:
                self.access_log_table.add([{
                    "memory_id": memory_id,
                    "accessed_at": now,
                    "query": query,
                    "relevance_score": float(row.get("final_score", row.get("rrf_score", 0.0))),
                }])
            except Exception:
                continue


# ── Embedding 接口 (Step 4: LRU 缓存) ──

class EmbeddingProvider:
    """
    Embedding 提供者抽象
    v3: LRU 缓存 (256条, 30min TTL)
    """

    CACHE_SIZE = 256
    CACHE_TTL = 1800  # 30 minutes

    def __init__(
        self,
        provider: str = "local",
        api_key: Optional[str] = None,
        model: str = "BAAI/bge-m3",
        base_url: Optional[str] = None
    ):
        self.provider = provider
        self.model = model
        self._local_model = None
        self._cache: Dict[str, Tuple[List[float], float]] = {}  # hash -> (embedding, timestamp)
        self._cache_lock = threading.Lock()

        if provider == "local":
            self._init_local_model()
        else:
            self.api_key = api_key or os.getenv("JINA_API_KEY") or os.getenv("OPENAI_API_KEY")
            self.base_url = base_url or self._default_base_url()

    def _init_local_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(self.model)
            print(f"[EmbeddingProvider] 本地模型已加载: {self.model}")
        except ImportError:
            print("[EmbeddingProvider] sentence-transformers 未安装，回退到 Jina API")
            self.provider = "jina"
            self.api_key = os.getenv("JINA_API_KEY") or os.getenv("OPENAI_API_KEY")
            self.base_url = self._default_base_url()

    def _default_base_url(self) -> str:
        if self.provider == "jina":
            return "https://api.jina.ai/v1"
        elif self.provider == "openai":
            return "https://api.openai.com/v1"
        return ""

    def embed(self, texts: List[str], task: str = "retrieval.passage") -> List[List[float]]:
        """生成 embeddings (带 LRU 缓存)"""
        results = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []
        now = time.time()

        with self._cache_lock:
            for i, text in enumerate(texts):
                key = hashlib.md5(text.encode()).hexdigest()
                cached = self._cache.get(key)
                if cached and (now - cached[1]) < self.CACHE_TTL:
                    results[i] = cached[0]
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)

        if uncached_texts:
            if self.provider == "local" and self._local_model is not None:
                new_embeddings = self._embed_local(uncached_texts)
            else:
                new_embeddings = self._embed_api(uncached_texts, task)

            with self._cache_lock:
                for idx, emb in zip(uncached_indices, new_embeddings):
                    results[idx] = emb
                    key = hashlib.md5(texts[idx].encode()).hexdigest()
                    self._cache[key] = (emb, now)

                    # LRU 淘汰
                    if len(self._cache) > self.CACHE_SIZE:
                        oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
                        del self._cache[oldest_key]

        return results

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        embeddings = self._local_model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def _embed_api(self, texts: List[str], task: str = "retrieval.passage") -> List[List[float]]:
        import openai

        client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        extra_body = {}
        if self.provider == "jina":
            extra_body["task"] = task

        try:
            response = client.embeddings.create(
                model=self.model, input=texts, **extra_body
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            if "task" in str(e).lower():
                response = client.embeddings.create(model=self.model, input=texts)
                return [item.embedding for item in response.data]
            raise


# ── L0/L1/L2 生成工具 (Step 6) ──

def generate_memory_layers(content: str, category: str, topic: str) -> Tuple[str, str, str]:
    """
    从原始 content 生成 L0/L1/L2 三层 (规则生成，零 LLM 成本)

    Returns: (l0_abstract, l1_overview, l2_content)
    """
    # L2: 完整内容
    l2 = content

    # L0: 第一句话 (截断 100 字符)
    first_sentence = content.split('\n')[0].strip()
    for sep in ['。', '！', '？', '.', '!', '?', '；', ';']:
        if sep in first_sentence:
            first_sentence = first_sentence[:first_sentence.index(sep) + 1]
            break
    l0 = first_sentence[:100]

    # L1: 前 300 字符 + 标签
    overview = content[:300].strip()
    if len(content) > 300:
        overview += "..."
    l1 = f"[{category}|{topic}] {overview}"

    return l0, l1, l2


def slugify_section(value: str) -> str:
    """把标题或主题压平成稳定 slug，用于 Markdown 记忆定位。"""
    text = re.sub(r"\s+", "-", value.strip().lower())
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff\-_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "memory"


def derive_fact_key(
    category: str,
    topic: str,
    content: str,
    source_section: str = "",
    metadata: Optional[Dict] = None,
) -> Optional[str]:
    """
    生成较稳定的事实键。

    优先级:
    1. metadata 中显式指定的 stable_fact_key / entity_name / preference_key
    2. source_section slug
    3. topic + 内容前缀
    """
    meta = metadata or {}
    explicit = (
        meta.get("stable_fact_key")
        or meta.get("entity_name")
        or meta.get("preference_key")
    )
    if explicit:
        return f"{category}:{slugify_section(str(explicit))}"

    if source_section:
        return f"{category}:{slugify_section(source_section)}"

    normalized = content.strip()
    if len(normalized) < 12:
        return None

    prefix = slugify_section(normalized[:48])
    if not prefix or prefix == "memory":
        return None
    return f"{category}:{slugify_section(topic)}:{prefix}"


# ── 全局实例 ──

_store = None
_embedder = None


def get_memory_store(db_path: str = "~/.openclaw/memory/lancedb") -> LanceDBMemoryStore:
    global _store
    if _store is None:
        _store = LanceDBMemoryStore(db_path=db_path)
    return _store


def get_embedder(provider: str = "local", model: str = "BAAI/bge-m3") -> EmbeddingProvider:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingProvider(provider=provider, model=model)
    return _embedder
