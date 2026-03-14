#!/usr/bin/env python3
"""
Mars Memory Engine v3 — LanceDB 迁移脚本

将旧版 memories 表添加 v3 新字段:
  - l0_abstract, l1_overview, l2_content (三层记忆)
  - invalidated_at, supersedes, superseded_by, fact_key (Temporal Versioning)

策略: LanceDB 不支持 ALTER TABLE，所以:
  1. 读出旧表全部数据
  2. 为每条记忆生成 L0/L1/L2 (规则生成，零 LLM)
  3. 填充 v3 新字段默认值
  4. 删掉旧表，建新 schema 表，写回数据

Usage:
  python migration/migrate_v3_fields.py                    # 默认路径
  python migration/migrate_v3_fields.py --db-path /path/to/lancedb
  python migration/migrate_v3_fields.py --dry-run          # 仅预览，不修改
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.lancedb_store import generate_memory_layers


def migrate(db_path: str, dry_run: bool = False):
    import lancedb
    import pyarrow as pa

    db_path = os.path.expanduser(db_path)
    print(f"📂 数据库路径: {db_path}")

    db = lancedb.connect(db_path)

    if "memories" not in db.table_names():
        print("⚠️  memories 表不存在，无需迁移")
        return

    table = db.open_table("memories")
    df = table.to_pandas()
    total = len(df)
    print(f"📊 共 {total} 条记忆")

    if total == 0:
        print("⚠️  表为空，无需迁移")
        return

    # 检查是否已有 v3 字段
    existing_cols = set(df.columns)
    v3_fields = {"l0_abstract", "l1_overview", "l2_content", "invalidated_at", "supersedes", "superseded_by", "fact_key"}
    if v3_fields.issubset(existing_cols):
        # 检查是否有数据
        has_l0 = df["l0_abstract"].apply(lambda x: bool(x) if isinstance(x, str) else False).any()
        if has_l0:
            print("✅ v3 字段已存在且有数据，无需迁移")
            return
        print("⚠️  v3 字段存在但为空，将填充 L0/L1/L2...")

    if dry_run:
        print("\n🔍 [DRY RUN] 预览前 3 条迁移效果:\n")
        for i, row in df.head(3).iterrows():
            content = row.get("content", "")
            category = row.get("category", "pattern")
            topic = row.get("topic", "general")
            l0, l1, l2 = generate_memory_layers(content, category, topic)
            print(f"  [{row.get('id', '?')}]")
            print(f"    L0: {l0[:60]}...")
            print(f"    L1: {l1[:60]}...")
            print()
        print(f"共 {total} 条将被迁移。加 --no-dry-run 执行。")
        return

    # 填充 v3 字段
    print("\n🔧 填充 v3 字段...")
    l0_list, l1_list, l2_list = [], [], []
    for _, row in df.iterrows():
        content = row.get("content", "")
        category = row.get("category", "pattern")
        topic = row.get("topic", "general")
        l0, l1, l2 = generate_memory_layers(content, category, topic)
        l0_list.append(l0)
        l1_list.append(l1)
        l2_list.append(l2)

    df["l0_abstract"] = l0_list
    df["l1_overview"] = l1_list
    df["l2_content"] = l2_list

    # Temporal Versioning 字段: 默认空字符串
    for col in ["invalidated_at", "supersedes", "superseded_by", "fact_key"]:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("").astype(str)

    # 重建表
    print("🗄️  重建 memories 表...")
    db.drop_table("memories")

    new_schema = pa.schema([
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
        ("scope", pa.string()),
        ("agent_id", pa.string()),
        ("guild_id", pa.string()),
        ("channel_id", pa.string()),
        ("conflict_flag", pa.bool_()),
        ("metadata", pa.string()),
        # v3
        ("l0_abstract", pa.string()),
        ("l1_overview", pa.string()),
        ("l2_content", pa.string()),
        ("invalidated_at", pa.string()),
        ("supersedes", pa.string()),
        ("superseded_by", pa.string()),
        ("fact_key", pa.string()),
    ])

    new_table = db.create_table("memories", schema=new_schema)

    # 转为 records 写入
    records = df.to_dict("records")
    # 确保所有字段类型正确
    for r in records:
        for str_field in ["l0_abstract", "l1_overview", "l2_content",
                          "invalidated_at", "supersedes", "superseded_by", "fact_key"]:
            if r.get(str_field) is None:
                r[str_field] = ""

    new_table.add(records)

    print(f"\n✅ 迁移完成! {total} 条记忆已更新 v3 字段")
    print(f"   - L0/L1/L2 三层摘要: ✅")
    print(f"   - Temporal Versioning 字段: ✅ (默认空)")


def main():
    parser = argparse.ArgumentParser(description="Mars Memory Engine v3 迁移脚本")
    parser.add_argument("--db-path", default="~/.openclaw/memory/lancedb", help="LanceDB 数据库路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不修改数据")
    args = parser.parse_args()

    migrate(args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
