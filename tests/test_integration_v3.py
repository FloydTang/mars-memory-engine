#!/usr/bin/env python3
"""
Mars Memory Engine v3 — 自包含集成测试

使用临时目录初始化 LanceDB，无需外部依赖（除 lancedb/pyarrow/numpy）。
Embedding 用确定性 fake 向量，不需要 sentence-transformers 或 API key。

覆盖:
  1. 噪音过滤 (noise_filter)
  2. 自适应检索跳过 (adaptive_retrieval)
  3. 分类行为差异化 (category_behaviors)
  4. L0/L1/L2 生成 (generate_memory_layers)
  5. Temporal Versioning — supersede 链
  6. Weibull 衰减评分 (lifecycle decay)
  7. 复合晋升/降级 (promote_memory)
  8. Knowledge Distiller 双重门槛 + draft/active
  9. MemoryGateway 写入全链路
 10. MemoryGateway 检索全链路

运行:
  cd mars-memory-engine && python -m pytest tests/test_integration_v3.py -v
  或:
  cd mars-memory-engine && python tests/test_integration_v3.py
"""

import asyncio
import hashlib
import math
import os
import sys
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─── Fake Embedding Provider ───────────────────────────────────────────
class FakeEmbeddingProvider:
    """确定性 fake embeddings: 对相同文本返回相同向量，不同文本返回不同向量"""

    def __init__(self, dim=1024):
        self.dim = dim

    def embed(self, texts, task="retrieval.passage"):
        return [self._deterministic_vector(t) for t in texts]

    def _deterministic_vector(self, text: str):
        """用 MD5 seed 生成确定性单位向量"""
        import numpy as np
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
        rng = np.random.RandomState(seed)
        vec = rng.randn(self.dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


# ═══════════════════════════════════════════════════════════════════════
# 1. 噪音过滤
# ═══════════════════════════════════════════════════════════════════════

def test_noise_filter():
    from core.noise_filter import filter_noise

    # 应被拦截
    cases_filtered = [
        ("hi", "greeting"),
        ("Hello!", "greeting"),
        ("你好", "greeting"),
        ("ok", "affirmation"),
        ("yes", "affirmation"),
        ("谢谢", "affirmation"),
        ("ab", "too_short"),
        ("", "too_short"),
        ("HEARTBEAT", "system_marker"),
        ("ping", "system_marker"),
        ("I don't have any memories", "agent_denial"),
        ("😀🎉", "emoji_only"),
    ]
    for content, expected_reason in cases_filtered:
        should_filter, reason = filter_noise(content)
        assert should_filter, f"应被过滤但未被过滤: '{content}'"
        assert expected_reason in reason, f"'{content}' 原因不匹配: expected={expected_reason}, got={reason}"

    # 不应被拦截
    cases_pass = [
        "我喜欢用 Python 做数据分析",
        "Mars 的 Discord 频道 ID 是 123456",
        "今天修复了 Redis 连接超时的 bug",
    ]
    for content in cases_pass:
        should_filter, reason = filter_noise(content)
        assert not should_filter, f"不应被过滤但被过滤了: '{content}' reason={reason}"

    print("✅ test_noise_filter PASSED")


# ═══════════════════════════════════════════════════════════════════════
# 2. 自适应检索
# ═══════════════════════════════════════════════════════════════════════

def test_adaptive_retrieval():
    from core.adaptive_retrieval import should_skip_retrieval

    # 应跳过
    skip_cases = [
        "",
        "hi",
        "ok",
        "git status",
        "/help",
        "npm install",
        "😀",
        "ab",  # 短于 5 字符
    ]
    for query in skip_cases:
        assert should_skip_retrieval(query), f"应跳过但未跳过: '{query}'"

    # 不应跳过 (记忆意图 / 问号)
    keep_cases = [
        "你记得我上次说了什么？",
        "last time we discussed what?",
        "我之前提到过的配置是什么",
        "What did I mention about Redis?",
    ]
    for query in keep_cases:
        assert not should_skip_retrieval(query), f"不应跳过但被跳过了: '{query}'"

    # 普通足够长的查询也不应跳过
    assert not should_skip_retrieval("Discord 配置文件在哪里")

    print("✅ test_adaptive_retrieval PASSED")


# ═══════════════════════════════════════════════════════════════════════
# 3. 分类行为差异化
# ═══════════════════════════════════════════════════════════════════════

def test_category_behaviors():
    from core.category_behaviors import get_behavior, CATEGORY_BEHAVIORS

    # profile: always_merge, no supersede
    b = get_behavior("profile")
    assert b["conflict_strategy"] == "always_merge"
    assert b["allow_supersede"] is False

    # preference: merge_supported, allow supersede
    b = get_behavior("preference")
    assert b["conflict_strategy"] == "merge_supported"
    assert b["allow_supersede"] is True

    # event: append_only
    b = get_behavior("event")
    assert b["conflict_strategy"] == "append_only"

    # 未知分类 → pattern 行为
    b = get_behavior("unknown_category")
    assert b["conflict_strategy"] == CATEGORY_BEHAVIORS["pattern"]["conflict_strategy"]

    print("✅ test_category_behaviors PASSED")


# ═══════════════════════════════════════════════════════════════════════
# 4. L0/L1/L2 生成
# ═══════════════════════════════════════════════════════════════════════

def test_l0_l1_l2_generation():
    from core.lancedb_store import generate_memory_layers

    content = "我喜欢用 Python 做数据分析。因为 Pandas 和 NumPy 非常强大，适合处理大规模数据。"
    l0, l1, l2 = generate_memory_layers(content, "preference", "coding")

    # L0: 第一句话，≤100 字符
    assert len(l0) <= 100, f"L0 太长: {len(l0)} chars"
    assert "Python" in l0, f"L0 应包含 'Python': {l0}"

    # L1: 带标签前缀
    assert l1.startswith("[preference|coding]"), f"L1 标签前缀不正确: {l1[:30]}"
    assert len(l1) <= 320, f"L1 太长: {len(l1)} chars"

    # L2: 完整内容
    assert l2 == content, "L2 应等于完整内容"

    # 短文本: L0 = L1 overview = L2
    short = "短记忆"
    l0s, l1s, l2s = generate_memory_layers(short, "event", "test")
    assert l0s == short
    assert l2s == short

    print("✅ test_l0_l1_l2_generation PASSED")


# ═══════════════════════════════════════════════════════════════════════
# 5. LanceDB 存储 + Temporal Versioning (supersede 链)
# ═══════════════════════════════════════════════════════════════════════

def test_lancedb_store_and_temporal_versioning():
    """测试 LanceDB 写入/读取 + v3 新字段 + supersede 链"""
    from core.lancedb_store import LanceDBMemoryStore, MemoryEntry, MemoryTier
    import numpy as np

    tmpdir = tempfile.mkdtemp(prefix="mars_test_")
    try:
        store = LanceDBMemoryStore(db_path=tmpdir)
        fake = FakeEmbeddingProvider()

        # 插入原始偏好记忆
        now = datetime.now()
        emb1 = fake.embed(["我喜欢 Python"])[0]
        entry1 = MemoryEntry(
            id="pref_py_001",
            content="我喜欢 Python",
            embedding=emb1,
            category="preference",
            tier=MemoryTier.PERIPHERAL.value,
            created_at=now,
            updated_at=now,
            last_accessed=now,
            agent_id="agent_a",
            guild_id="guild_1",
            scope="private",
            l0_abstract="我喜欢 Python",
            l1_overview="[preference|coding] 我喜欢 Python",
            l2_content="我喜欢 Python",
        )
        store.insert_memory(entry1)

        # 模拟 supersede: 新偏好取代旧偏好
        store.update_memory_fields("pref_py_001", {
            "invalidated_at": now.isoformat(),
            "superseded_by": "pref_rust_002",
        })

        emb2 = fake.embed(["我现在更喜欢 Rust"])[0]
        entry2 = MemoryEntry(
            id="pref_rust_002",
            content="我现在更喜欢 Rust",
            embedding=emb2,
            category="preference",
            tier=MemoryTier.PERIPHERAL.value,
            created_at=now,
            updated_at=now,
            last_accessed=now,
            agent_id="agent_a",
            guild_id="guild_1",
            scope="private",
            supersedes="pref_py_001",
            fact_key="preference:coding",
            l0_abstract="我现在更喜欢 Rust",
            l1_overview="[preference|coding] 我现在更喜欢 Rust",
            l2_content="我现在更喜欢 Rust",
        )
        store.insert_memory(entry2)

        # 默认检索应过滤掉已失效记忆
        results = store.search_hybrid(
            query="编程语言偏好",
            embedding=fake.embed(["编程语言偏好"])[0],
            agent_id="agent_a",
            guild_id="guild_1",
            limit=10,
            include_history=False,
        )
        ids = [r["id"] for r in results]
        assert "pref_py_001" not in ids, "已失效记忆不应出现在默认检索中"
        assert "pref_rust_002" in ids, "新记忆应出现在检索结果中"

        # include_history=True 应返回全部
        results_all = store.search_hybrid(
            query="编程语言偏好",
            embedding=fake.embed(["编程语言偏好"])[0],
            agent_id="agent_a",
            guild_id="guild_1",
            limit=10,
            include_history=True,
        )
        ids_all = [r["id"] for r in results_all]
        assert "pref_py_001" in ids_all, "include_history=True 应返回旧记忆"
        assert "pref_rust_002" in ids_all, "include_history=True 应返回新记忆"

        # 验证 supersede 链字段
        old_mem = [r for r in results_all if r["id"] == "pref_py_001"][0]
        assert old_mem["superseded_by"] == "pref_rust_002", "旧记忆的 superseded_by 应指向新记忆"

        new_mem = [r for r in results_all if r["id"] == "pref_rust_002"][0]
        assert new_mem["supersedes"] == "pref_py_001", "新记忆的 supersedes 应指向旧记忆"
        assert new_mem["fact_key"] == "preference:coding", "fact_key 不正确"

        print("✅ test_lancedb_store_and_temporal_versioning PASSED")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# 6. Weibull 衰减评分
# ═══════════════════════════════════════════════════════════════════════

def test_weibull_decay_scoring():
    """验证 Weibull 衰减的分类差异化和访问强化效果"""
    from core.lancedb_store import LanceDBMemoryStore, MemoryEntry, MemoryTier
    import pandas as pd

    tmpdir = tempfile.mkdtemp(prefix="mars_test_decay_")
    try:
        store = LanceDBMemoryStore(db_path=tmpdir)
        fake = FakeEmbeddingProvider()
        now = datetime.now()

        # 插入两条同龄记忆: profile vs event
        for cat, mid in [("profile", "decay_profile"), ("event", "decay_event")]:
            emb = fake.embed([f"测试 {cat} 衰减"])[0]
            entry = MemoryEntry(
                id=mid,
                content=f"测试 {cat} 衰减内容，足够长以通过各种过滤",
                embedding=emb,
                category=cat,
                tier=MemoryTier.PERIPHERAL.value,
                created_at=now - timedelta(days=30),
                updated_at=now,
                last_accessed=now,
                access_count=0,
                importance=0.5,
                agent_id="agent_a",
                guild_id="guild_1",
                scope="shared",
                l0_abstract=f"测试 {cat}",
                l1_overview=f"[{cat}|test] 测试衰减",
                l2_content=f"测试 {cat} 衰减内容",
            )
            store.insert_memory(entry)

        # 检索并比较 decay_score
        results = store.search_hybrid(
            query="测试衰减",
            embedding=fake.embed(["测试衰减"])[0],
            agent_id="agent_a",
            guild_id="guild_1",
            limit=10,
        )

        profile_result = next((r for r in results if r["id"] == "decay_profile"), None)
        event_result = next((r for r in results if r["id"] == "decay_event"), None)

        if profile_result and event_result:
            # profile 衰减地板 0.9 >> event 衰减地板 0.5
            assert profile_result["decay_score"] > event_result["decay_score"], (
                f"Profile decay ({profile_result['decay_score']:.3f}) 应高于 "
                f"Event decay ({event_result['decay_score']:.3f})"
            )

        # 插入高访问量记忆，验证访问强化
        emb_freq = fake.embed(["高频访问记忆"])[0]
        entry_freq = MemoryEntry(
            id="decay_freq",
            content="高频访问记忆内容，足够长以通过过滤器的长度检查",
            embedding=emb_freq,
            category="pattern",
            tier=MemoryTier.WORKING.value,
            created_at=now - timedelta(days=60),
            updated_at=now,
            last_accessed=now,
            access_count=50,  # 高访问
            importance=0.7,
            agent_id="agent_a",
            guild_id="guild_1",
            scope="shared",
            l0_abstract="高频访问",
            l1_overview="[pattern|test] 高频访问记忆",
            l2_content="高频访问记忆内容",
        )
        store.insert_memory(entry_freq)

        emb_low = fake.embed(["低频访问记忆"])[0]
        entry_low = MemoryEntry(
            id="decay_low",
            content="低频访问记忆内容，足够长以通过过滤器的长度检查",
            embedding=emb_low,
            category="pattern",
            tier=MemoryTier.PERIPHERAL.value,
            created_at=now - timedelta(days=60),
            updated_at=now,
            last_accessed=now,
            access_count=0,  # 零访问
            importance=0.5,
            agent_id="agent_a",
            guild_id="guild_1",
            scope="shared",
            l0_abstract="低频访问",
            l1_overview="[pattern|test] 低频访问记忆",
            l2_content="低频访问记忆内容",
        )
        store.insert_memory(entry_low)

        results2 = store.search_hybrid(
            query="访问记忆",
            embedding=fake.embed(["访问记忆"])[0],
            agent_id="agent_a",
            guild_id="guild_1",
            limit=10,
        )
        freq_result = next((r for r in results2 if r["id"] == "decay_freq"), None)
        low_result = next((r for r in results2 if r["id"] == "decay_low"), None)

        if freq_result and low_result:
            assert freq_result["decay_score"] > low_result["decay_score"], (
                f"高频 ({freq_result['decay_score']:.3f}) 应高于低频 ({low_result['decay_score']:.3f})"
            )

        print("✅ test_weibull_decay_scoring PASSED")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# 7. 复合晋升/降级
# ═══════════════════════════════════════════════════════════════════════

def test_promote_demote():
    """测试 peripheral→working 晋升和 working→peripheral 降级"""
    from core.lancedb_store import LanceDBMemoryStore, MemoryEntry, MemoryTier

    tmpdir = tempfile.mkdtemp(prefix="mars_test_promote_")
    try:
        store = LanceDBMemoryStore(db_path=tmpdir)
        fake = FakeEmbeddingProvider()
        now = datetime.now()

        # 晋升测试: peripheral + access_count=5 + 新鲜 → working
        emb = fake.embed(["晋升测试记忆"])[0]
        entry = MemoryEntry(
            id="promote_001",
            content="晋升测试记忆内容",
            embedding=emb,
            category="pattern",
            tier=MemoryTier.PERIPHERAL.value,
            created_at=now,
            updated_at=now,
            last_accessed=now,
            access_count=5,
            importance=0.6,
            agent_id="agent_a",
            guild_id="guild_1",
            scope="shared",
        )
        store.insert_memory(entry)

        promoted = store.promote_memory("promote_001")
        assert promoted, "access_count=5 + 新鲜记忆应晋升"

        # 验证新 tier
        result = store.memories_table.search().where("id = 'promote_001'").limit(1).to_pandas()
        assert result.iloc[0]["tier"] == MemoryTier.WORKING.value, "应晋升为 working"

        # 降级测试: working + composite<0.15 → peripheral
        # 用 event 类别 (beta=1.3, half_life=14) + 90天前 + access_count=0 → composite 很低
        emb2 = fake.embed(["降级测试记忆"])[0]
        entry2 = MemoryEntry(
            id="demote_001",
            content="降级测试记忆内容",
            embedding=emb2,
            category="event",
            tier=MemoryTier.WORKING.value,
            created_at=now - timedelta(days=90),
            updated_at=now - timedelta(days=90),
            last_accessed=now - timedelta(days=90),
            access_count=0,
            importance=0.3,
            agent_id="agent_a",
            guild_id="guild_1",
            scope="shared",
        )
        store.insert_memory(entry2)

        demoted = store.promote_memory("demote_001")
        # 注意: event 的 decay_floor=0.5，composite = max(0.5*recency+0.3*freq+0.2*imp, 0.5)
        # 即使 recency≈0, freq=0, imp=0.3 → raw=0.06 → floored to 0.5
        # 0.5 >= 0.15 所以不降级... 除非 days_old>60 && access<3
        result2 = store.memories_table.search().where("id = 'demote_001'").limit(1).to_pandas()
        if demoted:
            assert result2.iloc[0]["tier"] == MemoryTier.PERIPHERAL.value, "应降级为 peripheral"
            print("  ↓ demote_001 降级成功 (days_old>60 + access<3 路径)")
        else:
            # decay_floor 可能让 composite >= 0.15，但 days_old>60+access<3 应触发降级
            # 重新检查: 代码里降级条件是 OR: composite<0.15 OR (days_old>60 AND access<3)
            assert False, "days_old=90 + access_count=0 应触发 working→peripheral 降级"

        print("✅ test_promote_demote PASSED")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# 8. Knowledge Distiller 双重门槛 + draft/active
# ═══════════════════════════════════════════════════════════════════════

def test_knowledge_distiller():
    """测试双重触发门槛 (>10KB AND >20 entries) 和 draft/active 状态"""
    from skills.knowledge_distiller import KnowledgeDistiller

    tmpdir = tempfile.mkdtemp(prefix="mars_test_distiller_")
    try:
        workspace = Path(tmpdir)
        topics_dir = workspace / "memory" / "topics"
        topics_dir.mkdir(parents=True)
        skills_dir = workspace / "memory_engine" / "skills"
        skills_dir.mkdir(parents=True)

        # Case 1: 超过 10KB 但不到 20 条 → 不触发
        small_entries_file = topics_dir / "small_topic.md"
        # 写入大文本但少量条目
        content_lines = ["# Small Topic\n"]
        for i in range(5):
            content_lines.append(f"\n### [{datetime.now().strftime('%Y-%m-%d')}] (confidence: 0.85)\n")
            content_lines.append("A" * 3000 + "\n")  # 3KB per entry
            content_lines.append("---\n")
        small_entries_file.write_text("\n".join(content_lines))
        assert small_entries_file.stat().st_size > 10 * 1024, "文件应超过 10KB"

        distiller = KnowledgeDistiller(str(workspace))
        result = distiller.scan_and_distill()
        assert len(result) == 0, "5条 entries + >10KB 不应触发蒸馏 (未达条目阈值)"

        # Case 2: 超过 20 条但不到 10KB → 不触发
        many_small = topics_dir / "many_small.md"
        lines = ["# Many Small\n"]
        for i in range(25):
            lines.append(f"\n### [{datetime.now().strftime('%Y-%m-%d')}] (confidence: 0.85)\n")
            lines.append(f"Entry {i}: short\n")
            lines.append("---\n")
        many_small.write_text("\n".join(lines))
        assert many_small.stat().st_size < 10 * 1024, "文件应小于 10KB"

        result2 = distiller.scan_and_distill()
        assert len(result2) == 0, "25条但 <10KB 不应触发蒸馏"

        # Case 3: 超过 10KB AND 超过 20 条 → 触发
        big_topic = topics_dir / "big_topic.md"
        lines = ["# Big Topic\n"]
        for i in range(25):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            conf = 0.9 if i < 10 else 0.6
            lines.append(f"\n### [{date}] (confidence: {conf})\n")
            lines.append(f"Entry {i}: " + "详细内容 " * 60 + "\n")
            lines.append("---\n")
        big_topic.write_text("\n".join(lines))
        assert big_topic.stat().st_size > 10 * 1024, "文件应超过 10KB"

        # 清理上轮的小文件避免干扰
        small_entries_file.unlink()
        many_small.unlink()

        result3 = distiller.scan_and_distill()
        assert len(result3) == 1, f"25条 + >10KB 应触发蒸馏, got {len(result3)}"

        # 验证 draft/active 状态
        import json
        skill_file = skills_dir / "skill_big_topic.json"
        assert skill_file.exists(), "应生成 skill JSON"
        skill_data = json.loads(skill_file.read_text())

        # 前 10 条 conf=0.9, 平均 >= 0.7 → active
        assert skill_data["status"] == "active", f"高置信度应为 active, got {skill_data['status']}"

        # Case 4: 低置信度 → draft
        low_conf = topics_dir / "low_conf.md"
        lines = ["# Low Conf\n"]
        for i in range(25):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            lines.append(f"\n### [{date}] (confidence: 0.45)\n")
            lines.append(f"Entry {i}: " + "内容填充 " * 60 + "\n")
            lines.append("---\n")
        low_conf.write_text("\n".join(lines))

        # 删掉 big_topic 避免重复处理
        big_topic.unlink()

        result4 = distiller.scan_and_distill()
        if result4:
            skill_low = skills_dir / "skill_low_conf.json"
            if skill_low.exists():
                data = json.loads(skill_low.read_text())
                assert data["status"] == "draft", f"低置信度应为 draft, got {data['status']}"

        print("✅ test_knowledge_distiller PASSED")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# 9. MemoryGateway 写入全链路
# ═══════════════════════════════════════════════════════════════════════

def test_gateway_write_pipeline():
    """测试 MemoryGateway 写入: 噪音过滤 → 分类 → L0/L1/L2 → 插入"""
    from core.lancedb_store import LanceDBMemoryStore
    from protocols.memory_gateway import MemoryGateway

    tmpdir = tempfile.mkdtemp(prefix="mars_test_gw_")
    try:
        store = LanceDBMemoryStore(db_path=tmpdir)
        fake = FakeEmbeddingProvider()
        gw = MemoryGateway(
            store=store,
            embedder=fake,
            use_llm_classify=False,
            use_llm_conflict=False,
        )

        async def run():
            # 噪音应被拦截
            r = await gw.write_memory("hi", agent_id="a1", guild_id="g1")
            assert r["action"] == "filtered", f"'hi' 应被过滤: {r}"

            # 正常写入
            r = await gw.write_memory(
                content="Mars 来自半斤九两科技，负责 B2B 外贸营销",
                agent_id="agent_main",
                guild_id="guild_001",
                category="profile",
                topic="identity",
                importance=0.9,
            )
            assert r["action"] in ("insert", "replace"), f"应成功写入: {r}"
            assert r["id"], "应返回记忆 ID"

            # 验证 L0/L1/L2 已写入
            mem = store.memories_table.search().where(f"id = '{r['id']}'").limit(1).to_pandas()
            assert len(mem) == 1, "应能查到刚写入的记忆"
            row = mem.iloc[0]
            assert row["l0_abstract"], "L0 不应为空"
            assert "[profile|identity]" in row["l1_overview"], f"L1 标签不正确: {row['l1_overview'][:50]}"
            assert row["l2_content"] == "Mars 来自半斤九两科技，负责 B2B 外贸营销"

            # DM 保护: guild_id="__dm__" 强制 private
            r2 = await gw.write_memory(
                content="这是 DM 频道的私密对话内容，不应公开",
                agent_id="agent_main",
                guild_id="__dm__",
                scope="shared",  # 尝试 shared
                category="event",
            )
            mem2 = store.memories_table.search().where(f"id = '{r2['id']}'").limit(1).to_pandas()
            assert mem2.iloc[0]["scope"] == "private", "DM 记忆应强制为 private"

            return True

        result = asyncio.run(run())
        assert result

        print("✅ test_gateway_write_pipeline PASSED")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# 10. MemoryGateway 检索全链路
# ═══════════════════════════════════════════════════════════════════════

def test_gateway_search_pipeline():
    """测试检索: 自适应跳过 + 隔离过滤 + invalidated_at 过滤"""
    from core.lancedb_store import LanceDBMemoryStore
    from protocols.memory_gateway import MemoryGateway

    tmpdir = tempfile.mkdtemp(prefix="mars_test_search_")
    try:
        store = LanceDBMemoryStore(db_path=tmpdir)
        fake = FakeEmbeddingProvider()
        gw = MemoryGateway(
            store=store,
            embedder=fake,
            use_llm_classify=False,
            use_llm_conflict=False,
        )

        async def run():
            # 写入几条记忆
            await gw.write_memory(
                content="Discord 的 webhook URL 配置在 openclaw.json 里",
                agent_id="a1", guild_id="g1", category="pattern", topic="discord",
            )
            await gw.write_memory(
                content="RSS 抓取频率设置为每 6 小时一次",
                agent_id="a1", guild_id="g1", category="pattern", topic="content",
            )
            # 另一个 guild 的记忆
            await gw.write_memory(
                content="另一个 guild 的秘密配置信息",
                agent_id="a2", guild_id="g2", category="pattern", topic="config",
            )

            # 自适应跳过: 短查询
            r = gw.search("hi", agent_id="a1", guild_id="g1")
            assert r == [], "短查询应返回空列表"

            # 正常搜索: 应只返回 g1 的记忆
            r2 = gw.search(
                "Discord 配置在哪里？",
                agent_id="a1", guild_id="g1",
            )
            for item in r2:
                assert item["guild_id"] == "g1", f"隔离失败: 返回了 guild={item['guild_id']} 的记忆"

            stored = store.memories_table.search().where("topic = 'discord'").limit(1).to_pandas()
            assert stored.iloc[0]["access_count"] >= 1, "命中检索后应更新 access_count"

            return True

        asyncio.run(run())

        print("✅ test_gateway_search_pipeline PASSED")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_openclaw_adapter_markdown_first():
    """测试 OpenClaw adapter: Markdown 写入、重建索引、可追溯检索、晋升"""
    from core.lancedb_store import LanceDBMemoryStore
    from openclaw.adapter import (
        MarkdownMemoryEntry,
        OpenClawMemoryAdapter,
        WorkspaceContext,
    )
    from protocols.memory_gateway import MemoryGateway

    tmpdir = tempfile.mkdtemp(prefix="mars_test_adapter_")
    try:
        workspace = Path(tmpdir)
        fake = FakeEmbeddingProvider()
        gateway = MemoryGateway(
            store=LanceDBMemoryStore(db_path=str(workspace / ".mars-memory-engine" / "lancedb")),
            embedder=fake,
            use_llm_classify=False,
            use_llm_conflict=False,
        )
        adapter = OpenClawMemoryAdapter(
            str(workspace),
            gateway=gateway,
            db_path=str(workspace / ".mars-memory-engine" / "lancedb"),
            embedder=fake,
        )
        ctx = WorkspaceContext(
            workspace_path=str(workspace),
            agent_id="agent_main",
            guild_id="guild_alpha",
            session_scope="shared",
        )

        result = adapter.ingest_markdown_memory(
            MarkdownMemoryEntry(
                title="Webhook 配置",
                content="Discord 的 webhook URL 配置在 openclaw.json 里",
                topic="discord",
                category="pattern",
            ),
            ctx,
        )
        assert result["id"], "adapter 写入应返回 memory id"

        topic_file = workspace / "memory" / "topics" / "discord.md"
        assert topic_file.exists(), "topic Markdown 应落盘"

        adapter.rebuild_index(str(workspace))
        search_results = adapter.search_memory("Discord webhook 配置", ctx)
        assert search_results, "重建索引后应能检索"
        top = search_results[0]
        assert top["source_file"].endswith("discord.md"), f"source_file 应可追溯: {top}"
        assert top["memory_ref"]["source_section"] == "Webhook 配置"
        assert top["summary_l1"], "应返回 L1 摘要"

        promoted = adapter.promote_memory(top["memory_ref"], "AGENTS.md")
        assert promoted.exists(), "晋升目标文档应存在"
        promoted_text = promoted.read_text(encoding="utf-8")
        assert "Promoted from" in promoted_text, "晋升文档应保留来源"

        print("✅ test_openclaw_adapter_markdown_first PASSED")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════

ALL_TESTS = [
    test_noise_filter,
    test_adaptive_retrieval,
    test_category_behaviors,
    test_l0_l1_l2_generation,
    test_lancedb_store_and_temporal_versioning,
    test_weibull_decay_scoring,
    test_promote_demote,
    test_knowledge_distiller,
    test_gateway_write_pipeline,
    test_gateway_search_pipeline,
    test_openclaw_adapter_markdown_first,
]


def main():
    print(f"\n{'='*60}")
    print(f" Mars Memory Engine v3 — 集成测试")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    passed = 0
    failed = 0
    errors = []

    for test_fn in ALL_TESTS:
        name = test_fn.__name__
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"❌ {name} FAILED: {e}")

    print(f"\n{'='*60}")
    print(f" 结果: {passed} passed, {failed} failed / {len(ALL_TESTS)} total")
    if errors:
        print(f"\n 失败列表:")
        for name, err in errors:
            print(f"   - {name}: {err}")
    print(f"{'='*60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
