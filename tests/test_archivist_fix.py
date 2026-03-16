#!/usr/bin/env python3
"""
测试进化档案员修复
"""

import sys
import os
import time
import json
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.plugins.evolution.archivist import (
    EvolutionArchivist,
    EvolutionEventType,
    EvolutionLog,
)


def test_archivist_fix():
    """测试修复"""
    print("测试进化档案员修复...")

    # 创建测试配置
    config = {
        "storage_path": "./data/test_fix.jsonl",
        "embedding_provider": {"type": "mock"},
        "similarity_threshold": 0.3,  # 降低阈值以便测试
    }

    # 清理旧文件
    if os.path.exists(config["storage_path"]):
        os.remove(config["storage_path"])

    # 创建进化档案员
    archivist = EvolutionArchivist(config)

    # 检查初始状态
    print(f"\n1. 初始状态:")
    print(f"   内存缓存大小: {len(archivist.memory_cache)}")
    print(f"   嵌入缓存大小: {len(archivist.embedding_cache)}")

    # 启动后台线程
    archivist.start()

    # 记录测试日志
    print("\n2. 记录测试日志...")

    # 使用record_simple方法
    archivist.record_simple(
        event_type=EvolutionEventType.WEIGHT_ADJUSTMENT,
        module="period_weight_filter",
        parameter="H4_weight",
        old_value=0.18,
        new_value=0.22,
        reason="提高4小时周期权重，增强趋势跟踪能力",
        context={"test": "fix"},
    )

    # 等待处理
    print("等待后台处理...")
    time.sleep(1.0)

    # 检查处理后的状态
    print(f"\n3. 处理后的状态:")
    print(f"   内存缓存大小: {len(archivist.memory_cache)}")
    print(f"   嵌入缓存大小: {len(archivist.embedding_cache)}")

    # 检查存储文件
    if os.path.exists(config["storage_path"]):
        with open(config["storage_path"], "r", encoding="utf-8") as f:
            lines = f.readlines()
        print(f"   存储文件记录数: {len(lines)}")

        # 检查第一条记录
        if lines:
            record = json.loads(lines[0].strip())
            print(f"   第一条记录嵌入长度: {len(record.get('embedding', []))}")

    # 测试查询 - 使用完全相同的文本
    print("\n4. 测试查询（使用相同文本）...")
    query = "提高4小时周期权重，增强趋势跟踪能力"
    results = archivist.query_history(query, limit=5)
    print(f"   查询: '{query}'")
    print(f"   结果数量: {len(results)}")

    if results:
        for i, (log, similarity) in enumerate(results):
            print(f"   结果{i + 1}: 相似度={similarity:.3f}")
            print(f"       事件: {log.event_type.value}")
            print(f"       原因: {log.reason}")
    else:
        print("   未找到结果")

        # 调试信息
        print(f"\n   调试信息:")
        print(f"     内存缓存大小: {len(archivist.memory_cache)}")
        print(f"     嵌入缓存大小: {len(archivist.embedding_cache)}")

        # 检查嵌入向量
        if archivist.memory_cache:
            log = archivist.memory_cache[0]
            print(
                f"     第一条记录嵌入: {log.embedding[:3] if log.embedding else '无'}"
            )

        # 手动计算相似度
        if archivist.memory_cache and archivist.embedding_cache:
            query_embedding = archivist.embedding_provider.get_embedding(query)
            memory_embedding = archivist.embedding_cache[0]

            # 计算余弦相似度
            import numpy as np

            v1 = np.array(query_embedding)
            v2 = np.array(memory_embedding)

            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)

            if norm1 > 0 and norm2 > 0:
                similarity = dot_product / (norm1 * norm2)
                print(f"     手动计算相似度: {similarity:.3f}")
                print(f"     系统阈值: {archivist.similarity_threshold}")

    # 停止并清理
    archivist.stop()
    if os.path.exists(config["storage_path"]):
        os.remove(config["storage_path"])

    print("\n测试完成")


if __name__ == "__main__":
    test_archivist_fix()
