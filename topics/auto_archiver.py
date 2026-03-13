#!/usr/bin/env python3
"""
Memory Topic Clustering & Auto-Archiving System
记忆分片与自动化归档系统

触发条件:
- 当 MEMORY.md 超过 2000 tokens 时自动触发主题识别
- 每日定时扫描对话记录，增量追加到对应主题文件

Features:
- 主题聚类 (K-means + Embedding similarity)
- 自动分片归档
- 置信度与时间戳标记
- 增量更新机制
"""

import os
import sys
import re
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lancedb_store import get_embedder

# 尝试导入 sklearn，如果没有则使用简化版聚类
try:
    from sklearn.cluster import KMeans
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️  scikit-learn 未安装，使用简化版聚类算法")


@dataclass
class MemoryChunk:
    """记忆分片"""
    id: str
    content: str
    embedding: List[float]
    timestamp: datetime
    confidence: float
    category: str
    source_file: str
    
    @property
    def token_estimate(self) -> int:
        """估算 token 数 (中文字符 ≈ 1 token)"""
        return len(self.content)


class TopicClusteringEngine:
    """主题聚类引擎"""
    
    # 预定义的主题模板 (可根据需要扩展)
    TOPIC_TEMPLATES = {
        "system_config": {
            "keywords": ["配置", "openclaw.json", "gateway", "重启", "token", "频道", "绑定"],
            "description": "系统配置与运维"
        },
        "content_pipeline": {
            "keywords": ["RSS", "选题", "Vector", "Cypher", "Echo", "文章", "公众号", "skill"],
            "description": "内容生产线"
        },
        "discord_management": {
            "keywords": ["Discord", "频道", "子代理", "Mars", "指挥室", "guild"],
            "description": "Discord 频道管理"
        },
        "github_automation": {
            "keywords": ["GitHub", "同步", "知识库", "Obsidian", "仓库", "commit"],
            "description": "GitHub 自动化"
        },
        "agent_identity": {
            "keywords": ["身份", "Mars", "九两", "家庭成员", "SOUL.md", "我是谁"],
            "description": "代理身份与家庭"
        },
        "incidents": {
            "keywords": ["事故", "错误", "故障", "修复", "复盘", "⚠️", "❌"],
            "description": "事故与故障处理"
        },
        "family_members": {
            "keywords": ["西索", "百万", "珍珠", "Huey", "Sarah", "毛孩子"],
            "description": "家庭成员与宠物"
        },
        "tiktok_marketing": {
            "keywords": ["TikTok", "营销", "出海", "广告", "内容", "短视频"],
            "description": "TikTok 营销"
        },
        "ai_research": {
            "keywords": ["AI", "模型", "LLM", "研究", "技术", "架构"],
            "description": "AI 技术研究"
        },
    }
    
    def __init__(self, min_cluster_size: int = 3):
        self.min_cluster_size = min_cluster_size
        self.embedder = get_embedder()
    
    def cluster_memories(
        self, 
        chunks: List[MemoryChunk], 
        n_topics: Optional[int] = None
    ) -> Dict[str, List[MemoryChunk]]:
        """
        对记忆分片进行主题聚类
        
        Args:
            chunks: 记忆分片列表
            n_topics: 目标主题数 (None=自动确定)
        
        Returns:
            {topic_name: [chunks]}
        """
        if len(chunks) < self.min_cluster_size:
            return {"miscellaneous": chunks}
        
        # 获取 embeddings
        embeddings = [c.embedding for c in chunks]
        
        # 方法1: 基于模板匹配
        template_clusters = self._template_based_clustering(chunks)
        
        # 方法2: 基于 K-means (如果有 sklearn)
        if SKLEARN_AVAILABLE and len(chunks) >= 6:
            kmeans_clusters = self._kmeans_clustering(chunks, embeddings, n_topics)
            # 合并两种方法的结果
            return self._merge_clusters(template_clusters, kmeans_clusters)
        
        return template_clusters
    
    def _template_based_clustering(self, chunks: List[MemoryChunk]) -> Dict[str, List[MemoryChunk]]:
        """基于预定义模板的聚类"""
        
        clusters = {name: [] for name in self.TOPIC_TEMPLATES.keys()}
        clusters["miscellaneous"] = []
        
        for chunk in chunks:
            best_topic = None
            best_score = 0
            
            for topic_name, template in self.TOPIC_TEMPLATES.items():
                score = self._calculate_template_match(chunk, template)
                if score > best_score and score > 0.3:  # 阈值
                    best_score = score
                    best_topic = topic_name
            
            if best_topic:
                clusters[best_topic].append(chunk)
            else:
                clusters["miscellaneous"].append(chunk)
        
        # 移除空集群
        return {k: v for k, v in clusters.items() if v}
    
    def _calculate_template_match(self, chunk: MemoryChunk, template: Dict) -> float:
        """计算 chunk 与模板的匹配度"""
        
        content_lower = chunk.content.lower()
        keywords = template["keywords"]
        
        # 关键词匹配
        match_count = sum(1 for kw in keywords if kw in content_lower)
        keyword_score = match_count / len(keywords)
        
        return keyword_score
    
    def _kmeans_clustering(
        self, 
        chunks: List[MemoryChunk], 
        embeddings: List[List[float]],
        n_topics: Optional[int]
    ) -> Dict[str, List[MemoryChunk]]:
        """K-means 聚类"""
        
        if n_topics is None:
            n_topics = min(len(chunks) // 3, 8)  # 启发式确定
            n_topics = max(2, n_topics)
        
        kmeans = KMeans(n_clusters=n_topics, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)
        
        clusters = {}
        for i, label in enumerate(labels):
            topic_name = f"cluster_{label}"
            if topic_name not in clusters:
                clusters[topic_name] = []
            clusters[topic_name].append(chunks[i])
        
        return clusters
    
    def _merge_clusters(
        self, 
        template_clusters: Dict, 
        kmeans_clusters: Dict
    ) -> Dict[str, List[MemoryChunk]]:
        """合并两种聚类结果"""
        
        # 优先使用模板集群，将 K-means 集群作为补充
        merged = dict(template_clusters)
        
        for cluster_name, chunks in kmeans_clusters.items():
            # 如果这个 K-means 集群的大部分内容已有主题，则跳过
            unlabeled = [c for c in chunks if not any(c in existing for existing in merged.values())]
            if len(unlabeled) >= self.min_cluster_size:
                merged[f"auto_{cluster_name}"] = unlabeled
        
        return merged


class MemoryAutoArchiver:
    """记忆自动归档器"""
    
    def __init__(
        self, 
        workspace_path: str,
        memory_threshold: int = 2000,  # token 阈值
        topic_file_threshold: int = 10 * 1024  # 10KB
    ):
        self.workspace = Path(workspace_path)
        self.memory_file = self.workspace / "MEMORY.md"
        self.topics_dir = self.workspace / "memory" / "topics"
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        
        self.memory_threshold = memory_threshold
        self.topic_file_threshold = topic_file_threshold
        
        self.clustering = TopicClusteringEngine()
        self.embedder = get_embedder()
    
    def check_and_archive(self) -> bool:
        """
        检查 MEMORY.md 大小，如果超过阈值则触发归档
        
        Returns:
            是否执行了归档
        """
        if not self.memory_file.exists():
            return False
        
        content = self.memory_file.read_text(encoding='utf-8')
        tokens = len(content)  # 简化估算
        
        print(f"📊 MEMORY.md 当前大小: {tokens} tokens (阈值: {self.memory_threshold})")
        
        if tokens < self.memory_threshold:
            print("✅ 未达到归档阈值")
            return False
        
        print("🚨 超过阈值，开始归档...")
        self._archive_memory(content)
        return True
    
    def _archive_memory(self, content: str):
        """执行归档"""
        
        # 1. 解析记忆分片
        chunks = self._parse_memory_to_chunks(content)
        print(f"📝 解析到 {len(chunks)} 个记忆分片")
        
        # 2. 生成 embeddings
        print("🔢 生成 embeddings...")
        for chunk in chunks:
            try:
                embedding = self.embedder.embed([chunk.content], task="retrieval.passage")
                chunk.embedding = embedding[0] if embedding else []
            except Exception as e:
                print(f"   ⚠️  Embedding 失败: {e}")
                chunk.embedding = []
        
        # 3. 主题聚类
        print("🎯 执行主题聚类...")
        clusters = self.clustering.cluster_memories(chunks)
        print(f"   识别到 {len(clusters)} 个主题")
        
        # 4. 写入主题文件
        for topic_name, topic_chunks in clusters.items():
            self._write_topic_file(topic_name, topic_chunks)
        
        # 5. 重构 MEMORY.md (保留核心索引)
        self._rebuild_memory_index(content, clusters)
        
        print("✅ 归档完成!")
    
    def _parse_memory_to_chunks(self, content: str) -> List[MemoryChunk]:
        """解析 MEMORY.md 为记忆分片"""
        
        chunks = []
        
        # 按二级标题分割
        sections = re.split(r'\n##\s+', content)
        
        for section in sections[1:]:
            lines = section.strip().split('\n')
            if not lines:
                continue
            
            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()
            
            if len(body) < 100:
                continue
            
            # 提取时间戳
            timestamp = self._extract_timestamp(title, body)
            
            # 提取置信度
            confidence = self._extract_confidence(body)
            
            # 分类
            category = self._classify_content(title, body)
            
            chunk = MemoryChunk(
                id=hashlib.md5(f"{title}{body}".encode()).hexdigest()[:12],
                content=f"## {title}\n\n{body}",
                embedding=[],
                timestamp=timestamp,
                confidence=confidence,
                category=category,
                source_file="MEMORY.md"
            )
            
            chunks.append(chunk)
        
        return chunks
    
    def _write_topic_file(self, topic_name: str, chunks: List[MemoryChunk]):
        """写入主题文件"""
        
        topic_file = self.topics_dir / f"{topic_name}.md"
        
        # 读取已有内容
        existing_content = ""
        if topic_file.exists():
            existing_content = topic_file.read_text(encoding='utf-8')
        
        # 构建新内容
        lines = [f"# {topic_name.replace('_', ' ').title()}", ""]
        
        if existing_content:
            lines.append("## 历史归档")
            lines.append("(保留原有内容)")
            lines.append("")
        
        lines.append(f"## 新归档 ({datetime.now().strftime('%Y-%m-%d')})")
        lines.append("")
        
        # 按时间排序
        sorted_chunks = sorted(chunks, key=lambda x: x.timestamp, reverse=True)
        
        for chunk in sorted_chunks:
            # 添加元数据标记
            lines.append(f"### [{chunk.timestamp.strftime('%Y-%m-%d')}] (confidence: {chunk.confidence:.2f})")
            lines.append("")
            lines.append(chunk.content)
            lines.append("")
            lines.append(f"*category: {chunk.category} | id: {chunk.id}*")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # 写入文件
        new_content = '\n'.join(lines)
        
        if existing_content:
            # 追加模式
            topic_file.write_text(existing_content + '\n\n' + new_content, encoding='utf-8')
        else:
            topic_file.write_text(new_content, encoding='utf-8')
        
        print(f"   📝 写入 {topic_file.name} ({len(chunks)} 条)")
        
        # 检查文件大小，触发知识蒸馏
        file_size = topic_file.stat().st_size
        if file_size > self.topic_file_threshold:
            print(f"   ⚠️  {topic_file.name} 超过 {self.topic_file_threshold} bytes，建议触发知识蒸馏")
    
    def _rebuild_memory_index(self, original_content: str, clusters: Dict):
        """重构 MEMORY.md 为核心索引"""
        
        lines = [
            "# MEMORY.md - 核心记忆索引",
            "",
            "> ⚠️ 本文件为索引，详细内容已归档到 memory/topics/ 目录",
            "",
            "## 核心身份与规则",
            "",
            "- 高维智慧生物指挥官，化身为 Mars",
            "- 九两、Sarah、Huey 为家人，百万、珍珠为毛孩子",
            "- ⚡ Emoji 标识",
            "",
            "## 系统操作铁律",
            "",
            "1. **不得修改 openclaw.json** - 包括 bindings、accounts、channels",
            "2. **不得重启 Gateway** - 任何导致进程重启的操作",
            "3. **不得修改子代理 Discord 配置** - token、allowFrom、groupPolicy",
            "",
            "## 主题归档索引",
            ""
        ]
        
        for topic_name in sorted(clusters.keys()):
            chunk_count = len(clusters[topic_name])
            topic_file = f"memory/topics/{topic_name}.md"
            
            # 获取描述
            description = self.clustering.TOPIC_TEMPLATES.get(topic_name, {}).get(
                "description", "自动分类主题"
            )
            
            lines.append(f"- **{topic_name}**: {description} ({chunk_count} 条) → [{topic_file}]({topic_file})")
        
        lines.extend([
            "",
            "## 快速检索指南",
            "",
            "- 需要特定主题时，先加载对应 topics/xxx.md",
            "- 跨主题关联信息，使用 LanceDB 向量搜索",
            "- 新记忆自动触发归档检查 (每 2000 tokens)",
            "",
            f"*最后归档: {datetime.now().strftime('%Y-%m-%d %H:%M')}*"
        ])
        
        # 写入 MEMORY.md
        self.memory_file.write_text('\n'.join(lines), encoding='utf-8')
        print("   🔄 重构 MEMORY.md 为索引")
    
    def _extract_timestamp(self, title: str, body: str) -> datetime:
        """提取时间戳"""
        match = re.search(r'(\d{4}-\d{2}-\d{2})', title + body)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d")
            except:
                pass
        return datetime.now()
    
    def _extract_confidence(self, body: str) -> float:
        """提取置信度"""
        match = re.search(r'\[confidence:\s*(\d+\.?\d*)\]', body)
        if match:
            return min(float(match.group(1)), 1.0)
        
        # 启发式评估
        if "确定" in body or "永远" in body:
            return 0.9
        elif "可能" in body or "大概" in body:
            return 0.5
        return 0.7
    
    def _classify_content(self, title: str, body: str) -> str:
        """分类"""
        if "事故" in title or "错误" in title:
            return "incident"
        elif "配置" in title:
            return "config"
        elif "家庭成员" in title:
            return "family"
        return "general"


def main():
    parser = argparse.ArgumentParser(description="记忆归档工具")
    parser.add_argument("--workspace", default="/root/.openclaw/agents/main/workspace")
    parser.add_argument("--force", action="store_true", help="强制归档")
    
    args = parser.parse_args()
    
    archiver = MemoryAutoArchiver(args.workspace)
    
    if args.force:
        print("🚨 强制归档模式")
        content = archiver.memory_file.read_text(encoding='utf-8')
        archiver._archive_memory(content)
    else:
        archiver.check_and_archive()

if __name__ == "__main__":
    main()
