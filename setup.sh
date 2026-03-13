#!/bin/bash
# Mars Memory Engine 快速启动脚本

set -e

echo "🚀 Mars Memory Engine - 初始化"
echo "================================"

WORKSPACE="/root/.openclaw/agents/main/workspace"
cd "$WORKSPACE"

# 1. 检查依赖
echo ""
echo "📦 Step 1: 检查依赖..."

python3 -c "import lancedb" 2>/dev/null || {
    echo "   安装 lancedb..."
    pip install lancedb pyarrow -q
}

python3 -c "import openai" 2>/dev/null || {
    echo "   安装 openai..."
    pip install openai -q
}

python3 -c "import sklearn" 2>/dev/null || {
    echo "   安装 scikit-learn (可选)..."
    pip install scikit-learn -q
}

echo "   ✅ 依赖检查完成"

# 2. 检查 API Key
echo ""
echo "🔑 Step 2: 检查 API Key..."

if [ -z "$JINA_API_KEY" ]; then
    echo "   ⚠️  未设置 JINA_API_KEY"
    echo "   请在 ~/.bashrc 中添加:"
    echo "   export JINA_API_KEY='your_key_here'"
    exit 1
fi

echo "   ✅ JINA_API_KEY 已配置"

# 3. 初始化目录结构
echo ""
echo "📁 Step 3: 初始化目录..."

mkdir -p memory_engine/{core,migration,topics,skills}
mkdir -p memory/topics

echo "   ✅ 目录结构就绪"

# 4. 执行数据迁移
echo ""
echo "🔄 Step 4: 数据迁移..."

if [ "$1" = "--reset" ]; then
    echo "   🚨 重置模式 - 将清空现有向量库"
    read -p "确认? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        python3 memory_engine/migration/migrate_memory.py --reset
    else
        echo "   取消"
        exit 0
    fi
else
    python3 memory_engine/migration/migrate_memory.py
fi

echo "   ✅ 迁移完成"

# 5. 测试检索
echo ""
echo "🔍 Step 5: 测试检索..."

python3 << 'EOF'
import sys
sys.path.insert(0, 'memory_engine')
from core.lancedb_store import get_memory_store

try:
    store = get_memory_store()
    tables = store.db.table_names()
    print(f"   数据表: {tables}")
    
    if 'memories' in tables:
        count = store.memories_table.count_rows()
        print(f"   记忆条目: {count}")
        print("   ✅ 向量库工作正常")
    else:
        print("   ⚠️  memories 表不存在")
except Exception as e:
    print(f"   ❌ 错误: {e}")
EOF

# 6. 配置定时任务
echo ""
echo "⏰ Step 6: 定时任务配置..."

echo "   建议添加到 crontab:"
echo ""
echo "   # Mars Memory Engine - 每日审查"
echo "   0 23 * * * cd $WORKSPACE && python3 memory_engine/cron_memory_review.py >> /var/log/memory_review.log 2>&1"
echo ""

# 7. 完成
echo ""
echo "================================"
echo "✅ Mars Memory Engine 初始化完成!"
echo ""
echo "可用命令:"
echo "   迁移数据:      python3 memory_engine/migration/migrate_memory.py"
echo "   强制归档:      python3 memory_engine/topics/auto_archiver.py --force"
echo "   知识蒸馏:      python3 memory_engine/skills/knowledge_distiller.py"
echo "   每日审查:      python3 memory_engine/cron_memory_review.py"
echo ""
echo "查看文档: memory_engine/README.md"
