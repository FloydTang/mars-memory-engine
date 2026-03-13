"""
Mars Memory Engine - LanceDB Core Schema
基于 memory-lancedb-pro 架构的轻量级实现
"""

import lancedb
import pyarrow as pa
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
import hashlib
import json
import os

class MemoryCategory(Enum):
    """6分类记忆系统"""
    PROFILE = "profile"           # 用户画像
    PREFERENCE = "preference"     # 偏好设置
    ENTITY = "entity"             # 实体对象
    EVENT = "event"               # 事件记录
    CASE = "case"                 # 案例经验
    PATTERN = "pattern"           # 模式规律

class MemoryTier(Enum):
    """3层记忆晋升系统"""
    PERIPHERAL = "peripheral"     # 边缘记忆 (短期)
    WORKING = "working"           # 工作记忆 (中期)
    CORE = "core"                 # 核心记忆 (长期)

@dataclass
class MemoryEntry:
    """记忆条目 Schema"""
    id: str                       # UUID
    content: str                  # 记忆内容
    embedding: List[float]        # 向量嵌入
    category: str                 # 6分类之一
    tier: str                     # 3层之一
    
    # 时间戳
    created_at: datetime
    updated_at: datetime
    last_accessed: datetime
    
    # 置信度与权重
    confidence: float             # 0.0 - 1.0
    importance: float             # 0.0 - 1.0
    access_count: int             # 访问次数
    
    # 主题关联
    topic: str                    # 主题标签
    related_topics: List[str]     # 相关主题
    
    # 来源
    source: str                   # 来源文件/对话
    source_id: str                # 源ID
    
    # 作用域
    scope: str                    # global/agent:main/user:xxx
    
    # 元数据
    metadata: Dict                # 额外元数据

class LanceDBMemoryStore:
    """
    LanceDB 记忆存储引擎
    
    Schema 设计:
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
        
        # 主记忆表
        if "memories" not in self.db.table_names():
            memories_schema = pa.schema([
                ("id", pa.string()),
                ("content", pa.string()),
                ("embedding", pa.list_(pa.float32(), 1024)),  # Jina embeddings v5
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
                ("scope", pa.string()),
                ("metadata", pa.string()),  # JSON string
            ])
            self.db.create_table("memories", schema=memories_schema)
        
        # 主题聚类表
        if "topics" not in self.db.table_names():
            topics_schema = pa.schema([
                ("id", pa.string()),
                ("name", pa.string()),
                ("description", pa.string()),
                ("memory_count", pa.int32()),
                ("created_at", pa.timestamp('us')),
                ("updated_at", pa.timestamp('us')),
                ("centroid", pa.list_(pa.float32(), 1024)),  # 主题中心向量
                ("keywords", pa.list_(pa.string())),
                ("file_path", pa.string()),  # 对应 topics/xxx.md
            ])
            self.db.create_table("topics", schema=topics_schema)
        
        # 访问日志表 (用于生命周期管理)
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
        
        # 生成唯一ID
        if not entry.id:
            content_hash = hashlib.md5(entry.content.encode()).hexdigest()[:8]
            entry.id = f"{entry.topic}_{content_hash}_{int(datetime.now().timestamp())}"
        
        # 准备数据
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
            "scope": entry.scope,
            "metadata": json.dumps(entry.metadata),
        }
        
        self.memories_table.add([data])
        return entry.id
    
    def search_hybrid(
        self, 
        query: str, 
        embedding: List[float],
        topic: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 5,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3
    ) -> List[Dict]:
        """
        混合检索: Vector + BM25 (简化版RRF)
        
        Args:
            query: 原始查询文本 (用于BM25)
            embedding: 查询向量 (用于语义搜索)
            topic: 主题过滤
            category: 分类过滤
            limit: 返回数量
            vector_weight: 向量搜索权重
            bm25_weight: 全文搜索权重
        """
        
        # 1. 向量搜索
        vector_results = self.memories_table.search(embedding)
        if topic:
            vector_results = vector_results.where(f"topic = '{topic}'")
        if category:
            vector_results = vector_results.where(f"category = '{category}'")
        vector_results = vector_results.limit(limit * 2).to_pandas()
        
        # 2. BM25 全文搜索 (LanceDB FTS)
        try:
            text_results = self.memories_table.search(query, query_type="fts")
            if topic:
                text_results = text_results.where(f"topic = '{topic}'")
            text_results = text_results.limit(limit * 2).to_pandas()
        except Exception:
            text_results = vector_results.iloc[:0]  # 空表
        
        # 3. RRF 融合 (Reciprocal Rank Fusion)
        combined = self._rrf_fusion(
            vector_results, 
            text_results, 
            vector_weight, 
            bm25_weight,
            k=60
        )
        
        # 4. 应用生命周期衰减加权
        combined = self._apply_lifecycle_decay(combined)
        
        return combined.head(limit).to_dict('records')
    
    def _rrf_fusion(
        self, 
        vector_df, 
        text_df, 
        vector_weight: float, 
        bm25_weight: float,
        k: int = 60
    ):
        """RRF 融合算法"""
        
        # 给每个结果加上排名分数
        vector_df = vector_df.copy()
        vector_df['rrf_score'] = vector_weight / (k + vector_df.index + 1)
        
        text_df = text_df.copy()
        text_df['rrf_score'] = bm25_weight / (k + text_df.index + 1)
        
        # 合并
        combined = {}
        for _, row in vector_df.iterrows():
            combined[row['id']] = {
                **row.to_dict(),
                'rrf_score': row['rrf_score']
            }
        
        for _, row in text_df.iterrows():
            if row['id'] in combined:
                combined[row['id']]['rrf_score'] += row['rrf_score']
            else:
                combined[row['id']] = {
                    **row.to_dict(),
                    'rrf_score': row['rrf_score']
                }
        
        import pandas as pd
        result = pd.DataFrame(list(combined.values()))
        return result.sort_values('rrf_score', ascending=False)
    
    def _apply_lifecycle_decay(self, df):
        """应用生命周期衰减加权 (Weibull-inspired)"""
        
        now = datetime.now()
        
        def calc_decay_score(row):
            # 时间衰减 (Weibull)
            days_old = (now - row['created_at']).days
            time_decay = np.exp(-days_old / 60)  # 60天半衰期
            
            # 访问频率增强
            access_boost = min(row['access_count'] * 0.1, 1.0)
            
            # 重要性权重
            importance = row['importance']
            
            # 置信度
            confidence = row['confidence']
            
            return time_decay * (1 + access_boost) * importance * confidence
        
        df['decay_score'] = df.apply(calc_decay_score, axis=1)
        df['final_score'] = df['rrf_score'] * df['decay_score']
        
        return df.sort_values('final_score', ascending=False)
    
    def promote_memory(self, memory_id: str):
        """
        记忆晋升: Peripheral -> Working -> Core
        基于访问频率和重要性
        """
        table = self.memories_table
        result = table.search().where(f"id = '{memory_id}'").limit(1).to_pandas()
        
        if len(result) == 0:
            return False
        
        memory = result.iloc[0]
        current_tier = memory['tier']
        access_count = memory['access_count']
        importance = memory['importance']
        
        # 晋升规则
        new_tier = current_tier
        if current_tier == MemoryTier.PERIPHERAL.value and access_count >= 3:
            new_tier = MemoryTier.WORKING.value
        elif current_tier == MemoryTier.WORKING.value and access_count >= 10 and importance > 0.7:
            new_tier = MemoryTier.CORE.value
        
        if new_tier != current_tier:
            # 更新 tier
            table.update(where=f"id = '{memory_id}'", values={"tier": new_tier})
            return True
        
        return False

# Embedding 接口 (兼容 Jina/OpenAI)
class EmbeddingProvider:
    """Embedding 提供者抽象"""
    
    def __init__(
        self, 
        provider: str = "jina",
        api_key: Optional[str] = None,
        model: str = "jina-embeddings-v3",
        base_url: Optional[str] = None
    ):
        self.provider = provider
        self.api_key = api_key or os.getenv("JINA_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = base_url or self._default_base_url()
        
    def _default_base_url(self) -> str:
        if self.provider == "jina":
            return "https://api.jina.ai/v1"
        elif self.provider == "openai":
            return "https://api.openai.com/v1"
        return ""
    
    def embed(self, texts: List[str], task: str = "retrieval.passage") -> List[List[float]]:
        """
        生成 embeddings
        task: retrieval.query (查询) / retrieval.passage (文档)
        """
        import openai
        
        client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # Jina 支持 task 参数，但需要通过 extra_body
        extra_body = {}
        if self.provider == "jina":
            extra_body["task"] = task
        
        try:
            response = client.embeddings.create(
                model=self.model,
                input=texts,
                **extra_body
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            # 如果 task 参数不支持，重试不带 task
            if "task" in str(e).lower():
                response = client.embeddings.create(
                    model=self.model,
                    input=texts
                )
                return [item.embedding for item in response.data]
            raise

# 全局实例
_store = None
_embedder = None

def get_memory_store() -> LanceDBMemoryStore:
    global _store
    if _store is None:
        _store = LanceDBMemoryStore()
    return _store

def get_embedder() -> EmbeddingProvider:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingProvider()
    return _embedder
