#!/usr/bin/env python3
"""
Memory Migration Script
将现有的 Markdown 记忆文件迁移到 LanceDB 向量库

支持:
- MEMORY.md (长期记忆)
- memory/YYYY-MM-DD.md (每日记忆)
- memory/topics/*.md (主题记忆)

Usage:
    python migrate_memory.py [--dry-run] [--reset]
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import hashlib

# 添加 core 到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lancedb_store import (
    LanceDBMemoryStore, 
    MemoryEntry, 
    MemoryCategory, 
    MemoryTier,
    get_embedder
)

class MemoryMigrator:
    """记忆迁移器"""
    
    def __init__(self, workspace_path: str, dry_run: bool = False):
        self.workspace = Path(workspace_path)
        self.dry_run = dry_run
        self.store = LanceDBMemoryStore() if not dry_run else None
        self.embedder = get_embedder()
        
        # 统计
        self.stats = {
            "processed_files": 0,
            "extracted_memories": 0,
            "inserted_memories": 0,
            "errors": []
        }
    
    def migrate_all(self, reset: bool = False):
        """
        执行全量迁移
        
        Args:
            reset: 是否重置数据库
        """
        print("🚀 开始记忆迁移...")
        print(f"工作目录: {self.workspace}")
        print(f"模式: {'干跑 (dry-run)' if self.dry_run else '实际写入'}")
        
        if reset and not self.dry_run:
            print("⚠️  重置数据库...")
            self._reset_database()
        
        # 先初始化数据库表（在任何操作之前）
        if not self.dry_run:
            print("📦 初始化数据库表...")
            self._ensure_tables_exist()
        
        # 1. 迁移 MEMORY.md (长期记忆)
        self._migrate_file(
            self.workspace / "MEMORY.md",
            source_type="long_term"
        )
        
        # 2. 迁移每日记忆文件
        memory_dir = self.workspace / "memory"
        if memory_dir.exists():
            for md_file in sorted(memory_dir.glob("*.md")):
                if md_file.name.startswith("topics/"):
                    continue
                self._migrate_file(md_file, source_type="daily")
        
        # 3. 迁移主题记忆文件
        topics_dir = memory_dir / "topics"
        if topics_dir.exists():
            for topic_file in topics_dir.glob("*.md"):
                topic_name = topic_file.stem
                self._migrate_file(
                    topic_file, 
                    source_type="topic",
                    topic=topic_name
                )
        
        # 打印统计
        self._print_stats()
    
    def _ensure_tables_exist(self):
        """确保数据库表已创建"""
        from core.lancedb_store import LanceDBMemoryStore
        # 触发一次初始化即可创建所有表
        LanceDBMemoryStore()
    
    def _reset_database(self):
        """重置数据库"""
        import shutil
        db_path = os.path.expanduser("~/.openclaw/memory/lancedb")
        if os.path.exists(db_path):
            shutil.rmtree(db_path)
            print(f"已删除: {db_path}")
    
    def _migrate_file(self, file_path: Path, source_type: str, topic: Optional[str] = None):
        """迁移单个文件"""
        
        if not file_path.exists():
            return
        
        print(f"\n📄 处理: {file_path.name}")
        self.stats["processed_files"] += 1
        
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # 解析记忆条目
            memories = self._parse_markdown(content, source_type, topic)
            
            print(f"   提取到 {len(memories)} 条记忆")
            self.stats["extracted_memories"] += len(memories)
            
            # 生成 embeddings 并插入
            if memories and not self.dry_run:
                self._insert_memories(memories, str(file_path))
                
        except Exception as e:
            error_msg = f"{file_path.name}: {str(e)}"
            self.stats["errors"].append(error_msg)
            print(f"   ❌ 错误: {error_msg}")
    
    def _parse_markdown(
        self, 
        content: str, 
        source_type: str,
        topic: Optional[str] = None
    ) -> List[Dict]:
        """
        解析 Markdown 内容，提取记忆条目
        
        解析规则:
        - 按章节分割 (## 标题)
        - 每个章节作为一个记忆单元
        - 提取时间戳、置信度等元数据
        """
        memories = []
        
        # 按二级标题分割
        sections = re.split(r'\n##\s+', content)
        
        for section in sections[1:]:  # 跳过第一个(通常是文件头)
            lines = section.strip().split('\n')
            if not lines:
                continue
            
            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()
            
            if not body or len(body) < 50:  # 跳过太短的内容
                continue
            
            # 提取时间戳
            created_at = self._extract_timestamp(title, body, source_type)
            
            # 提取置信度
            confidence = self._extract_confidence(body)
            
            # 分类
            category = self._classify_content(title, body)
            
            # 确定主题
            entry_topic = topic or self._extract_topic(title, body)
            
            # 重要性评估
            importance = self._assess_importance(title, body, category)
            
            memories.append({
                "title": title,
                "content": f"## {title}\n\n{body}",
                "category": category,
                "topic": entry_topic,
                "created_at": created_at,
                "confidence": confidence,
                "importance": importance,
                "tier": MemoryTier.PERIPHERAL.value,  # 新记忆默认边缘层
                "access_count": 0,
                "related_topics": self._extract_related_topics(body),
                "metadata": {
                    "source_type": source_type,
                    "title": title,
                    "char_count": len(body)
                }
            })
        
        return memories
    
    def _extract_timestamp(self, title: str, body: str, source_type: str) -> datetime:
        """提取时间戳"""
        
        # 尝试从标题提取 (YYYY-MM-DD 格式)
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, title)
            if match:
                try:
                    date_str = match.group(1).replace('年', '-').replace('月', '-').replace('日', '')
                    return datetime.strptime(date_str, "%Y-%m-%d")
                except:
                    pass
        
        # 根据 source_type 默认时间
        if source_type == "daily":
            # 从文件名提取
            return datetime.now()
        
        return datetime(2024, 1, 1)  # 默认旧时间
    
    def _extract_confidence(self, body: str) -> float:
        """提取置信度 (从标记或内容分析)"""
        
        # 查找置信度标记: [confidence: 0.85]
        match = re.search(r'\[confidence:\s*(\d+\.?\d*)\]', body)
        if match:
            return min(float(match.group(1)), 1.0)
        
        # 查找确定性关键词
        high_confidence_words = ['确定', '肯定', '必须', '永远', '绝对']
        low_confidence_words = ['可能', '大概', '也许', '猜测', '不确定']
        
        score = 0.7  # 默认中等置信度
        
        for word in high_confidence_words:
            if word in body:
                score += 0.1
        
        for word in low_confidence_words:
            if word in body:
                score -= 0.1
        
        return max(0.3, min(0.95, score))
    
    def _classify_content(self, title: str, body: str) -> str:
        """
        6分类器 (简化版，可用 LLM 增强)
        """
        title_lower = title.lower()
        body_lower = body.lower()
        
        # PROFILE: 身份相关
        if any(kw in title_lower for kw in ['身份', '我是谁', 'profile', '家庭成员', '背景']):
            return MemoryCategory.PROFILE.value
        
        # PREFERENCE: 偏好设置
        if any(kw in title_lower for kw in ['偏好', '喜欢', '讨厌', '设置', 'preference', '配置']):
            return MemoryCategory.PREFERENCE.value
        
        # ENTITY: 实体对象
        if any(kw in title_lower for kw in ['仓库', '频道', 'id', 'token', '实体', 'entity']):
            return MemoryCategory.ENTITY.value
        
        # EVENT: 事件记录
        if any(kw in title_lower for kw in ['事故', '错误', '修复', '完成', 'event', 'incident']):
            return MemoryCategory.EVENT.value
        
        # CASE: 案例经验
        if any(kw in title_lower for kw in ['案例', '流程', '解决方案', 'case', 'workflow']):
            return MemoryCategory.CASE.value
        
        # PATTERN: 模式规律 (默认)
        return MemoryCategory.PATTERN.value
    
    def _extract_topic(self, title: str, body: str) -> str:
        """提取主题标签"""
        
        # 常见主题关键词映射
        topic_keywords = {
            'discord': 'discord',
            'github': 'github',
            'rss': 'content_pipeline',
            '选题': 'content_pipeline',
            'cron': 'automation',
            '定时任务': 'automation',
            'skill': 'agent_skills',
            '配置': 'configuration',
            '故障': 'incidents',
            '事故': 'incidents',
            '家庭成员': 'family',
            '身份': 'identity',
        }
        
        content = f"{title} {body}".lower()
        
        for keyword, topic in topic_keywords.items():
            if keyword in content:
                return topic
        
        return "general"
    
    def _extract_related_topics(self, body: str) -> List[str]:
        """提取相关主题"""
        
        related = []
        topic_mentions = re.findall(r'#(\w+)', body)
        
        # 去重并过滤
        for mention in set(topic_mentions):
            if len(mention) > 2:  # 过滤太短的
                related.append(mention)
        
        return related[:5]  # 最多5个相关主题
    
    def _assess_importance(self, title: str, body: str, category: str) -> float:
        """评估重要性"""
        
        importance = 0.5  # 基础分
        
        # 类别加权
        category_weights = {
            MemoryCategory.PROFILE.value: 0.9,
            MemoryCategory.PREFERENCE.value: 0.8,
            MemoryCategory.PATTERN.value: 0.7,
            MemoryCategory.CASE.value: 0.6,
            MemoryCategory.EVENT.value: 0.5,
            MemoryCategory.ENTITY.value: 0.4,
        }
        importance += category_weights.get(category, 0) * 0.3
        
        # 关键标记
        if any(mark in title for mark in ['⚠️', '🔴', '❗', '重要']):
            importance += 0.2
        
        # 长度加权 (详细说明更重要)
        if len(body) > 1000:
            importance += 0.1
        
        return min(0.95, importance)
    
    def _insert_memories(self, memories: List[Dict], source_path: str):
        """批量插入记忆"""
        
        # 批量生成 embeddings
        contents = [m["content"] for m in memories]
        print(f"   生成 embeddings... ({len(contents)} 条)")
        
        embeddings = []
        try:
            embeddings = self.embedder.embed(contents, task="retrieval.passage")
        except Exception as e:
            print(f"   ⚠️  Embedding 生成失败: {e}")
            print(f"   💡 使用零向量占位，后续可重新迁移")
            embeddings = [[0.0] * 1024 for _ in contents]  # 零向量占位
        
        # 插入数据库
        for mem_data, embedding in zip(memories, embeddings):
            entry = MemoryEntry(
                id="",
                content=mem_data["content"],
                embedding=embedding,
                category=mem_data["category"],
                tier=mem_data["tier"],
                created_at=mem_data["created_at"],
                updated_at=datetime.now(),
                last_accessed=mem_data["created_at"],
                confidence=mem_data["confidence"],
                importance=mem_data["importance"],
                access_count=mem_data["access_count"],
                topic=mem_data["topic"],
                related_topics=mem_data["related_topics"],
                source=source_path,
                source_id=hashlib.md5(mem_data["content"].encode()).hexdigest()[:16],
                scope="global",
                metadata=mem_data["metadata"]
            )
            
            try:
                self.store.insert_memory(entry)
                self.stats["inserted_memories"] += 1
            except Exception as e:
                self.stats["errors"].append(f"Insert error: {str(e)}")
    
    def _print_stats(self):
        """打印统计信息"""
        
        print("\n" + "="*50)
        print("📊 迁移统计")
        print("="*50)
        print(f"处理文件数: {self.stats['processed_files']}")
        print(f"提取记忆数: {self.stats['extracted_memories']}")
        print(f"插入记忆数: {self.stats['inserted_memories']}")
        
        if self.stats["errors"]:
            print(f"\n❌ 错误 ({len(self.stats['errors'])}):")
            for err in self.stats["errors"][:5]:
                print(f"   - {err}")
        
        print("\n✅ 迁移完成!")

def main():
    parser = argparse.ArgumentParser(description="记忆迁移工具")
    parser.add_argument("--workspace", default="/root/.openclaw/agents/main/workspace",
                       help="工作目录路径")
    parser.add_argument("--dry-run", action="store_true",
                       help="干跑模式，不实际写入数据库")
    parser.add_argument("--reset", action="store_true",
                       help="重置数据库后迁移")
    
    args = parser.parse_args()
    
    migrator = MemoryMigrator(args.workspace, dry_run=args.dry_run)
    migrator.migrate_all(reset=args.reset)

if __name__ == "__main__":
    main()
