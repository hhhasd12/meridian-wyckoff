#!/usr/bin/env python3
"""
进化档案员调试脚本
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


def debug_query_functionality():
    """调试查询功能"""
    print("调试查询功能...")

    # 创建测试配置
    config = {
        "storage_path": "./data/debug_evolution.jsonl",
        "embedding_provider": {"type": "mock"},
    }

    # 清理旧文件
    if os.path.exists(config["storage_path"]):
        os.remove(config["storage_path"])

    # 创建进化档案员
    archivist = EvolutionArchivist(config)
    archivist.start()

    # 记录一些测试日志
    print("\n1. 记录测试日志...")

    # 使用简化方法记录
    archivist.record_simple(
        event_type=EvolutionEventType.WEIGHT_ADJUSTMENT,
        module="period_weight_filter",
        parameter="H4_weight",
        old_value=0.18,
        new_value=0.22,
        reason="提高4小时周期权重，增强趋势跟踪能力",
        context={"performance_improvement": 0.15},
    )

    archivist.record_simple(
        event_type=EvolutionEventType.THRESHOLD_CHANGE,
        module="threshold_parameters",
        parameter="RSI_threshold",
        old_value=70,
        new_value=75,
        reason="降低假阳性率，提高信号质量",
        context={"market_regime": "trending"},
    )

    # 等待处理
    print("等待后台处理...")
    time.sleep(2.0)

    # 检查内存缓存
    print(f"\n2. 内存缓存大小: {len(archivist.memory_cache)}")
    print(f"   嵌入缓存大小: {len(archivist.embedding_cache)}")

    # 检查存储文件
    if os.path.exists(config["storage_path"]):
        with open(config["storage_path"], "r", encoding="utf-8") as f:
            lines = f.readlines()
        print(f"   存储文件记录数: {len(lines)}")

        # 显示记录内容
        for i, line in enumerate(lines[:2]):
            record = json.loads(line.strip())
            print(f"   记录{i + 1}: {record['event_type']} - {record['reason']}")

    # 测试查询
    print("\n3. 测试查询...")

    queries = ["提高4小时周期权重", "降低假阳性率", "权重调整", "阈值变化"]

    for query in queries:
        print(f"\n查询: '{query}'")
        results = archivist.query_history(query, limit=5)
        print(f"  结果数量: {len(results)}")

        for i, (log, similarity) in enumerate(results[:2]):
            print(f"  结果{i + 1}: 相似度={similarity:.3f}")
            print(f"      事件: {log.event_type.value}")
            print(f"      原因: {log.reason}")

    # 检查相似度阈值
    print(f"\n4. 系统配置:")
    print(f"   相似度阈值: {archivist.similarity_threshold}")
    print(f"   嵌入提供者: {archivist.embedding_provider.provider_type}")
    print(f"   嵌入维度: {archivist.embedding_provider.dimension}")

    # 手动测试嵌入生成
    print("\n5. 手动测试嵌入生成...")
    test_texts = [
        "提高4小时周期权重，增强趋势跟踪能力",
        "降低假阳性率，提高信号质量",
        "权重调整",
        "测试查询",
    ]

    for text in test_texts:
        embedding = archivist.embedding_provider.get_embedding(text)
        print(f"  文本: '{text[:20]}...'")
        print(f"    嵌入长度: {len(embedding)}")
        print(f"    嵌入样本: {embedding[:3] if embedding else '无'}")

    # 清理
    archivist.stop()
    if os.path.exists(config["storage_path"]):
        os.remove(config["storage_path"])

    print("\n调试完成")


if __name__ == "__main__":
    debug_query_functionality()
