#!/usr/bin/env python3
"""
Knowledge Distillation & Skill Generation System
知识蒸馏与 Skill 转化系统

触发条件:
- 当某个主题文件 (如 tiktok_marketing.md) 超过 10KB 时
- 自动汇总核心方法论，生成 Sub-Agent 配置

输出:
- System Prompt (system_xxx.md)
- Skill 配置 (skill_xxx.json)
- Sub-Agent 启动配置
"""

import os
import sys
import re
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.models import MODEL_DISTILL


@dataclass
class DistilledKnowledge:
    """蒸馏后的知识"""
    topic: str
    summary: str                    # 核心摘要
    key_concepts: List[str]         # 关键概念
    workflows: List[Dict]           # 工作流
    best_practices: List[str]       # 最佳实践
    common_pitfalls: List[str]      # 常见陷阱
    tools_and_configs: List[Dict]   # 工具与配置
    confidence_score: float         # 蒸馏置信度


class KnowledgeDistiller:
    """知识蒸馏器"""
    
    def __init__(self, workspace_path: str):
        self.workspace = Path(workspace_path)
        self.topics_dir = self.workspace / "memory" / "topics"
        self.skills_output_dir = self.workspace / "memory_engine" / "skills"
        self.skills_output_dir.mkdir(parents=True, exist_ok=True)
        
        # 蒸馏阈值 (v3: 双重门槛)
        self.threshold_bytes = 10 * 1024  # 10KB
        self.threshold_entries = 20       # 最少 20 条
    
    def scan_and_distill(self) -> List[str]:
        """
        扫描所有主题文件，对超过阈值的进行蒸馏
        
        Returns:
            生成的 Skill 文件列表
        """
        print("🔍 扫描主题文件...")
        
        generated_skills = []
        
        if not self.topics_dir.exists():
            print("⚠️  topics 目录不存在")
            return generated_skills
        
        for topic_file in self.topics_dir.glob("*.md"):
            file_size = topic_file.stat().st_size
            
            if file_size < self.threshold_bytes:
                print(f"   ⏭️  {topic_file.name} ({file_size} bytes) - 未达到字节阈值")
                continue

            # v3: 双重门槛 — 还需检查条目数
            content_preview = topic_file.read_text(encoding='utf-8')
            entry_count = len(re.findall(r'###\s*\[\d{4}-\d{2}-\d{2}\]', content_preview))
            if entry_count < self.threshold_entries:
                print(f"   ⏭️  {topic_file.name} ({entry_count} 条) - 未达到条目阈值")
                continue
            
            print(f"\n🎯 处理: {topic_file.name} ({file_size} bytes)")
            
            try:
                skill_file = self._distill_topic(topic_file)
                if skill_file:
                    generated_skills.append(skill_file)
            except Exception as e:
                print(f"   ❌ 蒸馏失败: {e}")
        
        return generated_skills
    
    def _distill_topic(self, topic_file: Path) -> Optional[str]:
        """
        蒸馏单个主题文件
        
        Returns:
            生成的 Skill 文件路径
        """
        topic_name = topic_file.stem
        content = topic_file.read_text(encoding='utf-8')
        
        # 1. 解析内容
        entries = self._parse_entries(content)
        print(f"   解析到 {len(entries)} 条记录")
        
        # 2. 按置信度加权 (旧内容权重降低)
        weighted_entries = self._apply_temporal_decay(entries)
        
        # 3. 提取核心知识
        knowledge = self._extract_knowledge(topic_name, weighted_entries)
        
        # 4. 生成 Skill 配置
        skill_file = self._generate_skill(topic_name, knowledge)
        
        # 5. 生成 System Prompt
        self._generate_system_prompt(topic_name, knowledge)
        
        print(f"   ✅ 生成 Skill: {skill_file}")
        return skill_file
    
    def _parse_entries(self, content: str) -> List[Dict]:
        """解析主题文件中的条目"""
        
        entries = []
        
        # 匹配条目块: ### [YYYY-MM-DD] (confidence: 0.85)
        pattern = r'###\s*\[(\d{4}-\d{2}-\d{2})\]\s*\(confidence:\s*(\d+\.?\d*)\)(.*?)\n---'
        
        for match in re.finditer(pattern, content, re.DOTALL):
            date_str = match.group(1)
            confidence = float(match.group(2))
            body = match.group(3).strip()
            
            # 提取分类
            category_match = re.search(r'\*category:\s*(\w+)', body)
            category = category_match.group(1) if category_match else "general"
            
            entries.append({
                "date": datetime.strptime(date_str, "%Y-%m-%d"),
                "confidence": confidence,
                "category": category,
                "content": body,
                "char_count": len(body)
            })
        
        return entries
    
    def _apply_temporal_decay(self, entries: List[Dict]) -> List[Dict]:
        """
        应用时间衰减 (旧内容权重降低)
        
        衰减公式: weight = confidence * exp(-days_old / 365)
        1年后的内容权重衰减到 37%
        """
        now = datetime.now()
        
        for entry in entries:
            days_old = (now - entry["date"]).days
            
            # 衰减因子 (1年衰减到 37%)
            decay = 0.37 ** (days_old / 365)
            
            # 加权得分
            entry["weighted_score"] = entry["confidence"] * decay * (entry["char_count"] / 1000)
        
        # 按得分排序
        return sorted(entries, key=lambda x: x["weighted_score"], reverse=True)
    
    def _extract_knowledge(self, topic: str, entries: List[Dict]) -> DistilledKnowledge:
        """从条目中提取核心知识"""
        
        # 合并内容
        all_content = '\n\n'.join([e["content"] for e in entries[:20]])  # 取前20条
        
        # 提取关键概念
        key_concepts = self._extract_key_concepts(all_content)
        
        # 提取工作流
        workflows = self._extract_workflows(all_content)
        
        # 提取最佳实践
        best_practices = self._extract_best_practices(all_content)
        
        # 提取常见陷阱
        pitfalls = self._extract_pitfalls(all_content)
        
        # 提取工具与配置
        tools = self._extract_tools(all_content)
        
        # 生成摘要
        summary = self._generate_summary(topic, entries, key_concepts)
        
        # 计算整体置信度
        avg_confidence = sum(e["confidence"] for e in entries[:10]) / min(10, len(entries))
        
        return DistilledKnowledge(
            topic=topic,
            summary=summary,
            key_concepts=key_concepts,
            workflows=workflows,
            best_practices=best_practices,
            common_pitfalls=pitfalls,
            tools_and_configs=tools,
            confidence_score=avg_confidence
        )
    
    def _extract_key_concepts(self, content: str) -> List[str]:
        """提取关键概念"""
        
        concepts = set()
        
        # 从标题提取
        title_pattern = r'##\s+(.+)'
        for match in re.finditer(title_pattern, content):
            title = match.group(1).strip()
            if len(title) < 50:
                concepts.add(title)
        
        # 从强调文本提取
        bold_pattern = r'\*\*(.+?)\*\*'
        for match in re.finditer(bold_pattern, content):
            concept = match.group(1).strip()
            if 5 < len(concept) < 40:
                concepts.add(concept)
        
        # 从列表项提取
        list_pattern = r'^\s*[-*]\s+(.+)$'
        for match in re.finditer(list_pattern, content, re.MULTILINE):
            item = match.group(1).strip()
            if 10 < len(item) < 50:
                concepts.add(item)
        
        return sorted(list(concepts))[:15]  # 最多15个
    
    def _extract_workflows(self, content: str) -> List[Dict]:
        """提取工作流"""
        
        workflows = []
        
        # 查找流程描述 (通常包含数字序号或箭头)
        workflow_pattern = r'(流程|步骤|Stage|Phase).*?\n((?:\d+[.\)]\s+.+\n?)+)'
        
        for match in re.finditer(workflow_pattern, content, re.DOTALL | re.IGNORECASE):
            workflow_name = match.group(1)
            steps_text = match.group(2)
            
            steps = []
            for line in steps_text.strip().split('\n'):
                line = line.strip()
                if re.match(r'^\d+[.\)]\s+', line):
                    step = re.sub(r'^\d+[.\)]\s+', '', line)
                    steps.append(step)
            
            if len(steps) >= 2:
                workflows.append({
                    "name": f"{workflow_name}流程",
                    "steps": steps
                })
        
        return workflows
    
    def _extract_best_practices(self, content: str) -> List[str]:
        """提取最佳实践"""
        
        practices = []
        
        # 查找 "最佳实践"、"建议"、"推荐" 等关键词后面的内容
        patterns = [
            r'(?:最佳实践|建议|推荐|应该|必须)[：:]\s*(.+)',
            r'✅\s*(.+)',
            r'💡\s*(.+)',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                practice = match.group(1).strip()
                if 10 < len(practice) < 200:
                    practices.append(practice)
        
        return list(set(practices))[:10]
    
    def _extract_pitfalls(self, content: str) -> List[str]:
        """提取常见陷阱"""
        
        pitfalls = []
        
        patterns = [
            r'(?:注意|警告|⚠️|❌|错误|陷阱|不要)[：:]\s*(.+)',
            r'⚠️\s*(.+)',
            r'❌\s*(.+)',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                pitfall = match.group(1).strip()
                if 10 < len(pitfall) < 200:
                    pitfalls.append(pitfall)
        
        return list(set(pitfalls))[:10]
    
    def _extract_tools(self, content: str) -> List[Dict]:
        """提取工具与配置"""
        
        tools = []
        
        # 查找代码块
        code_pattern = r'```(?:json|bash|python|yaml)?\n(.*?)```'
        
        for match in re.finditer(code_pattern, content, re.DOTALL):
            code = match.group(1).strip()
            
            # 尝试识别配置类型
            tool_name = "config"
            if '"channel"' in code or '"discord"' in code:
                tool_name = "discord_config"
            elif '"cron"' in code or "schedule" in code:
                tool_name = "cron_config"
            elif "embed" in code or "vector" in code:
                tool_name = "embedding_config"
            
            tools.append({
                "name": tool_name,
                "config": code[:500]  # 截取前500字符
            })
        
        return tools[:5]
    
    def _generate_summary(self, topic: str, entries: List[Dict], concepts: List[str]) -> str:
        """生成摘要"""
        
        # 统计
        total_entries = len(entries)
        date_range = f"{entries[-1]['date'].strftime('%Y-%m')} 至 {entries[0]['date'].strftime('%Y-%m')}"
        
        # 构建摘要
        summary_parts = [
            f"## {topic.replace('_', ' ').title()} 核心知识",
            "",
            f"**知识范围**: {date_range}",
            f"**记忆条目**: {total_entries} 条",
            f"**关键概念**: {', '.join(concepts[:5])}",
            "",
            "### 核心要点",
            ""
        ]
        
        # 添加最高置信度的内容摘要
        top_entries = [e for e in entries if e["confidence"] > 0.8][:3]
        for entry in top_entries:
            # 提取第一行作为摘要
            first_line = entry["content"].split('\n')[0][:100]
            summary_parts.append(f"- {first_line}...")
        
        return '\n'.join(summary_parts)
    
    def _generate_skill(self, topic: str, knowledge: DistilledKnowledge) -> str:
        """生成 Skill 配置"""
        
        skill_config = {
            "name": f"distilled_{topic}",
            "version": "1.0.0",
            "status": "active" if knowledge.confidence_score >= 0.7 else "draft",
            "description": f"基于 {knowledge.topic} 知识蒸馏生成的专业 Skill",
            "distilled_from": f"memory/topics/{topic}.md",
            "distilled_at": datetime.now().isoformat(),
            "confidence": knowledge.confidence_score,
            
            "capabilities": {
                "domains": [topic],
                "key_concepts": knowledge.key_concepts[:10],
                "expertise_level": "intermediate" if knowledge.confidence_score > 0.7 else "basic"
            },
            
            "workflows": knowledge.workflows,
            
            "best_practices": knowledge.best_practices,
            
            "common_pitfalls": knowledge.common_pitfalls,
            
            "tools_and_configs": knowledge.tools_and_configs,
            
            "system_prompt_reference": f"system_{topic}.md",
            
            "activation_keywords": [
                topic.replace('_', ' '),
                *knowledge.key_concepts[:5]
            ],
            
            "subagent_config": {
                "model": MODEL_DISTILL,
                "thinking": "medium",
                "context_files": [
                    f"memory/topics/{topic}.md",
                    f"memory_engine/skills/system_{topic}.md"
                ]
            }
        }
        
        # 写入文件
        skill_file = self.skills_output_dir / f"skill_{topic}.json"
        skill_file.write_text(
            json.dumps(skill_config, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        
        return str(skill_file)
    
    def _generate_system_prompt(self, topic: str, knowledge: DistilledKnowledge):
        """生成 System Prompt"""
        
        prompt_lines = [
            f"# System Prompt: {topic.replace('_', ' ').title()} Specialist",
            "",
            f"你是 **{topic.replace('_', ' ').title()}** 领域的专家助手。",
            "",
            "## 你的知识基础",
            "",
            knowledge.summary,
            "",
            "## 关键概念",
            ""
        ]
        
        for concept in knowledge.key_concepts[:10]:
            prompt_lines.append(f"- **{concept}**")
        
        if knowledge.workflows:
            prompt_lines.extend([
                "",
                "## 标准工作流",
                ""
            ])
            for wf in knowledge.workflows[:3]:
                prompt_lines.append(f"### {wf['name']}")
                for i, step in enumerate(wf['steps'], 1):
                    prompt_lines.append(f"{i}. {step}")
                prompt_lines.append("")
        
        if knowledge.best_practices:
            prompt_lines.extend([
                "## 最佳实践",
                ""
            ])
            for practice in knowledge.best_practices[:5]:
                prompt_lines.append(f"✅ {practice}")
        
        if knowledge.common_pitfalls:
            prompt_lines.extend([
                "",
                "## 常见陷阱",
                ""
            ])
            for pitfall in knowledge.common_pitfalls[:5]:
                prompt_lines.append(f"⚠️  {pitfall}")
        
        prompt_lines.extend([
            "",
            "## 行为准则",
            "",
            "1. **专业优先**: 始终基于蒸馏知识回答问题",
            "2. **承认未知**: 如果不确定，明确告知需要查询",
            "3. **引用来源**: 必要时引用 memory/topics/ 中的原始记录",
            "4. **持续学习**: 新知识会定期蒸馏更新",
            "",
            f"*本 Prompt 由 KnowledgeDistiller 于 {datetime.now().strftime('%Y-%m-%d')} 自动生成*"
        ])
        
        # 写入文件
        prompt_file = self.skills_output_dir / f"system_{topic}.md"
        prompt_file.write_text('\n'.join(prompt_lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description="知识蒸馏工具")
    parser.add_argument("--workspace", default="/root/.openclaw/agents/main/workspace")
    parser.add_argument("--topic", help="指定单个主题进行蒸馏")
    
    args = parser.parse_args()
    
    distiller = KnowledgeDistiller(args.workspace)
    
    if args.topic:
        topic_file = distiller.topics_dir / f"{args.topic}.md"
        if topic_file.exists():
            skill_file = distiller._distill_topic(topic_file)
            print(f"✅ 完成: {skill_file}")
        else:
            print(f"❌ 主题文件不存在: {topic_file}")
    else:
        generated = distiller.scan_and_distill()
        print(f"\n📊 共生成 {len(generated)} 个 Skill")

if __name__ == "__main__":
    main()
