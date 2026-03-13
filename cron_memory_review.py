#!/usr/bin/env python3
"""
Cron Memory Review - 每日记忆审查与增量归档

定时任务: 每天 23:00 运行
功能:
1. 扫描当日对话记录，提取新知识
2. 按主题增量追加到对应 topics/xxx.md 文件
3. 触发 MEMORY.md 大小检查，必要时归档
4. 触发知识蒸馏 (主题文件超过阈值)

Usage:
    python cron_memory_review.py [--dry-run]
    
Cron setup:
    0 23 * * * cd /root/.openclaw/agents/main/workspace && python memory_engine/cron_memory_review.py >> /var/log/memory_review.log 2>&1
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from topics.auto_archiver import MemoryAutoArchiver
from skills.knowledge_distiller import KnowledgeDistiller
from core.lancedb_store import get_embedder


class DailyMemoryReviewer:
    """每日记忆审查器"""
    
    def __init__(self, workspace_path: str, dry_run: bool = False):
        self.workspace = Path(workspace_path)
        self.dry_run = dry_run
        self.memory_dir = self.workspace / "memory"
        self.topics_dir = self.memory_dir / "topics"
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        
        self.embedder = get_embedder()
        
        # 组件
        self.archiver = MemoryAutoArchiver(str(self.workspace))
        self.distiller = KnowledgeDistiller(str(self.workspace))
        
        # 统计
        self.stats = {
            "new_entries": 0,
            "archived_topics": [],
            "distilled_skills": [],
            "errors": []
        }
    
    def run_daily_review(self):
        """执行每日审查"""
        
        print(f"\n{'='*60}")
        print(f"📅 每日记忆审查 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}\n")
        
        # 1. 扫描今日记忆文件
        print("🔍 Step 1: 扫描今日记忆...")
        today_entries = self._scan_today_memories()
        print(f"   发现 {len(today_entries)} 条新记忆")
        
        # 2. 主题识别与归档
        if today_entries:
            print("\n🎯 Step 2: 主题归档...")
            self._archive_to_topics(today_entries)
        
        # 3. 检查 MEMORY.md 大小
        print("\n📦 Step 3: 检查 MEMORY.md 大小...")
        archived = self.archiver.check_and_archive()
        if archived:
            self.stats["archived_topics"] = list(self._get_archived_topics())
        
        # 4. 知识蒸馏
        print("\n🧠 Step 4: 知识蒸馏...")
        distilled = self.distiller.scan_and_distill()
        self.stats["distilled_skills"] = [Path(s).stem for s in distilled]
        
        # 5. 生成日报
        print("\n📝 Step 5: 生成审查报告...")
        self._generate_report()
        
        print(f"\n✅ 审查完成!")
        return self.stats
    
    def _scan_today_memories(self) -> List[Dict]:
        """扫描今天的记忆文件"""
        
        entries = []
        today = datetime.now()
        
        # 扫描模式: 今日日期格式的文件
        today_file = self.memory_dir / f"{today.strftime('%Y-%m-%d')}.md"
        
        if today_file.exists():
            print(f"   读取: {today_file.name}")
            entries.extend(self._parse_daily_memory(today_file))
        
        # 同时检查最近3天的文件（避免遗漏）
        for i in range(1, 3):
            date = today - timedelta(days=i)
            file = self.memory_dir / f"{date.strftime('%Y-%m-%d')}.md"
            if file.exists():
                file_entries = self._parse_daily_memory(file)
                # 只取未归档的条目
                new_entries = [e for e in file_entries if not self._is_archived(e)]
                entries.extend(new_entries)
                if new_entries:
                    print(f"   读取: {file.name} ({len(new_entries)} 条未归档)")
        
        return entries
    
    def _parse_daily_memory(self, file_path: Path) -> List[Dict]:
        """解析每日记忆文件"""
        
        entries = []
        content = file_path.read_text(encoding='utf-8')
        
        # 按时间戳分割条目
        # 模式: ## HH:MM 或 ### 标题
        sections = re.split(r'\n##\s+(\d{2}:\d{2}.*?|\w+.*?)\n', content)
        
        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break
            
            timestamp = sections[i].strip()
            body = sections[i + 1].strip()
            
            if len(body) < 50:
                continue
            
            # 提取主题
            topic = self._identify_topic(body)
            
            # 计算置信度
            confidence = self._calculate_confidence(body)
            
            entry = {
                "id": f"{file_path.stem}_{i}",
                "timestamp": timestamp,
                "content": body,
                "topic": topic,
                "confidence": confidence,
                "source": str(file_path),
                "archived": False
            }
            
            entries.append(entry)
        
        return entries
    
    def _identify_topic(self, content: str) -> str:
        """识别内容主题"""
        
        content_lower = content.lower()
        
        # 主题关键词映射
        topic_keywords = {
            "discord": ["discord", "频道", "guild", "bot", "mention"],
            "system_config": ["配置", "openclaw.json", "gateway", "重启", "绑定"],
            "content_pipeline": ["rss", "选题", "vector", "cypher", "文章", "skill"],
            "github_automation": ["github", "同步", "知识库", "obsidian", "仓库"],
            "agent_identity": ["身份", "soul.md", "家庭成员", "mars", "九两"],
            "incidents": ["事故", "错误", "故障", "修复", "⚠️"],
        }
        
        scores = {}
        for topic, keywords in topic_keywords.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                scores[topic] = score
        
        if scores:
            return max(scores, key=scores.get)
        
        return "general"
    
    def _calculate_confidence(self, content: str) -> float:
        """计算内容置信度"""
        
        # 基础分
        score = 0.7
        
        # 确定性关键词
        if any(kw in content for kw in ["确定", "完成", "已修复", "已配置"]):
            score += 0.15
        
        # 否定/不确定性
        if any(kw in content for kw in ["可能", "大概", "猜测", "不确定"]):
            score -= 0.1
        
        # 详细程度
        if len(content) > 500:
            score += 0.05
        
        return max(0.3, min(0.95, score))
    
    def _is_archived(self, entry: Dict) -> bool:
        """检查条目是否已归档"""
        
        # 检查标记
        if entry.get("archived"):
            return True
        
        # 检查是否已存在于主题文件中
        topic_file = self.topics_dir / f"{entry['topic']}.md"
        if not topic_file.exists():
            return False
        
        # 简单检查内容哈希
        content_hash = hash(entry['content'][:100])
        existing_content = topic_file.read_text(encoding='utf-8')
        
        return str(content_hash) in existing_content
    
    def _archive_to_topics(self, entries: List[Dict]):
        """归档到主题文件"""
        
        # 按主题分组
        by_topic = {}
        for entry in entries:
            topic = entry["topic"]
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(entry)
        
        for topic, topic_entries in by_topic.items():
            self._write_topic_entries(topic, topic_entries)
            self.stats["new_entries"] += len(topic_entries)
    
    def _write_topic_entries(self, topic: str, entries: List[Dict]):
        """写入主题条目"""
        
        topic_file = self.topics_dir / f"{topic}.md"
        
        # 构建追加内容
        lines = [f"\n## 每日归档 ({datetime.now().strftime('%Y-%m-%d')})", ""]
        
        for entry in entries:
            lines.append(f"### [{entry['timestamp']}] (confidence: {entry['confidence']:.2f})")
            lines.append("")
            lines.append(entry['content'])
            lines.append("")
            lines.append(f"*source: {Path(entry['source']).name}*")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # 追加或创建
        new_content = '\n'.join(lines)
        
        if topic_file.exists():
            existing = topic_file.read_text(encoding='utf-8')
            topic_file.write_text(existing + '\n' + new_content, encoding='utf-8')
        else:
            # 创建新主题文件
            header = [
                f"# {topic.replace('_', ' ').title()}",
                "",
                f"*自动归档主题 - 创建于 {datetime.now().strftime('%Y-%m-%d')}*",
                "",
                new_content
            ]
            topic_file.write_text('\n'.join(header), encoding='utf-8')
        
        print(f"   📝 {topic}: +{len(entries)} 条")
    
    def _get_archived_topics(self) -> List[str]:
        """获取已归档的主题列表"""
        
        if not self.topics_dir.exists():
            return []
        
        return [f.stem for f in self.topics_dir.glob("*.md")]
    
    def _generate_report(self):
        """生成审查报告"""
        
        report_lines = [
            f"# 记忆审查日报 - {datetime.now().strftime('%Y-%m-%d')}",
            "",
            "## 统计",
            "",
            f"- **新增记忆条目**: {self.stats['new_entries']}",
            f"- **归档主题数**: {len(self.stats['archived_topics'])}",
            f"- **生成 Skill**: {len(self.stats['distilled_skills'])}",
            "",
        ]
        
        if self.stats['archived_topics']:
            report_lines.extend([
                "## 归档主题",
                ""
            ])
            for topic in self.stats['archived_topics']:
                report_lines.append(f"- `{topic}`")
            report_lines.append("")
        
        if self.stats['distilled_skills']:
            report_lines.extend([
                "## 生成 Skill",
                ""
            ])
            for skill in self.stats['distilled_skills']:
                report_lines.append(f"- `{skill}`")
            report_lines.append("")
        
        if self.stats['errors']:
            report_lines.extend([
                "## 错误",
                ""
            ])
            for error in self.stats['errors']:
                report_lines.append(f"- ⚠️ {error}")
            report_lines.append("")
        
        report_lines.append(f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        
        # 写入报告
        report_file = self.memory_dir / f"review_{datetime.now().strftime('%Y-%m-%d')}.md"
        report_file.write_text('\n'.join(report_lines), encoding='utf-8')
        
        print(f"   报告已保存: {report_file.name}")


def main():
    parser = argparse.ArgumentParser(description="每日记忆审查")
    parser.add_argument("--workspace", default="/root/.openclaw/agents/main/workspace")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式")
    
    args = parser.parse_args()
    
    reviewer = DailyMemoryReviewer(args.workspace, dry_run=args.dry_run)
    stats = reviewer.run_daily_review()
    
    print(f"\n📊 最终统计:")
    print(f"   新增条目: {stats['new_entries']}")
    print(f"   归档主题: {len(stats['archived_topics'])}")
    print(f"   生成 Skill: {len(stats['distilled_skills'])}")

if __name__ == "__main__":
    main()
