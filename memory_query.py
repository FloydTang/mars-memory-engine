#!/usr/bin/env python3
"""
Memory Query Tool - 记忆检索命令行工具

Usage:
    python memory_query.py "Discord 配置问题"
    python memory_query.py --topic content_pipeline "RSS 采集"
    python memory_query.py --category incident --limit 3
"""

import sys
import argparse
sys.path.insert(0, '/root/.openclaw/agents/main/workspace/memory_engine')

from core.lancedb_store import get_memory_store, get_embedder

def main():
    parser = argparse.ArgumentParser(description="记忆检索工具")
    parser.add_argument("query", nargs="?", help="查询文本")
    parser.add_argument("--topic", help="主题过滤")
    parser.add_argument("--category", help="分类过滤")
    parser.add_argument("--limit", type=int, default=5, help="返回数量")
    parser.add_argument("--vector-weight", type=float, default=0.7, help="向量权重")
    parser.add_argument("--bm25-weight", type=float, default=0.3, help="BM25权重")
    
    args = parser.parse_args()
    
    if not args.query:
        parser.print_help()
        return
    
    print(f"🔍 检索: {args.query}")
    print(f"   主题: {args.topic or '全部'}")
    print(f"   分类: {args.category or '全部'}")
    print(f"   数量: {args.limit}")
    print("-" * 60)
    
    try:
        store = get_memory_store()
        embedder = get_embedder()
        
        # 生成查询向量
        embedding = embedder.embed([args.query], task="retrieval.query")[0]
        
        # 检索
        results = store.search_hybrid(
            query=args.query,
            embedding=embedding,
            topic=args.topic,
            category=args.category,
            limit=args.limit,
            vector_weight=args.vector_weight,
            bm25_weight=args.bm25_weight
        )
        
        if not results:
            print("❌ 未找到相关记忆")
            return
        
        for i, r in enumerate(results, 1):
            print(f"\n[{i}] {r.get('topic', 'unknown')} | {r.get('category', 'general')}")
            print(f"    得分: {r.get('final_score', 0):.3f}")
            print(f"    时间: {r.get('created_at', 'unknown')}")
            content = r.get('content', '')[:200].replace('\n', ' ')
            print(f"    内容: {content}...")
        
        print(f"\n✅ 共 {len(results)} 条结果")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
