#!/usr/bin/env python3
"""
测试进化档案员完整功能
"""

import sys
import os
import time
import json
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.evolution_archivist import (
    EvolutionArchivist,
    EvolutionEventType,
    EvolutionLog,
)


def test_complete_functionality():
    """测试完整功能"""
    print("测试进化档案员完整功能...")

    # 创建测试配置
    config = {
        "storage_path": "./data/test_complete.jsonl",
        "embedding_provider": {"type": "mock"},
        "similarity_threshold": 0.1,  # 进一步降低阈值
    }

    # 清理旧文件
    if os.path.exists(config["storage_path"]):
        os.remove(config["storage_path"])

    # 创建进化档案员
    archivist = EvolutionArchivist(config)
    archivist.start()

    print("\n1. 测试记录功能...")

    # 记录多个测试日志
    test_logs = [
        {
            "event_type": EvolutionEventType.WEIGHT_ADJUSTMENT,
            "module": "period_weight_filter",
            "parameter": "H4_weight",
            "old_value": 0.18,
            "new_value": 0.22,
            "reason": "提高4小时周期权重，增强趋势跟踪能力",
            "context": {"market": "BTCUSDT", "timeframe": "H4"},
        },
        {
            "event_type": EvolutionEventType.THRESHOLD_CHANGE,
            "module": "threshold_parameters",
            "parameter": "RSI_threshold",
            "old_value": 70,
            "new_value": 75,
            "reason": "降低假阳性率，提高信号质量",
            "context": {"market_regime": "trending"},
        },
        {
            "event_type": EvolutionEventType.PARAMETER_TUNING,
            "module": "entry_validator",
            "parameter": "min_volume_spike",
            "old_value": 1.5,
            "new_value": 1.8,
            "reason": "提高成交量门槛，过滤假突破",
            "context": {"volatility": "high"},
        },
    ]

    for i, log_data in enumerate(test_logs):
        success = archivist.record_simple(**log_data)
        print(f"  日志{i + 1}: {'成功' if success else '失败'} - {log_data['reason']}")

    # 等待处理
    print("\n等待后台处理...")
    time.sleep(2.0)

    print(f"\n2. 系统状态:")
    stats = archivist.get_statistics()
    print(f"   总记忆数: {stats['total_memories']}")
    print(f"   队列大小: {stats['queue_size']}")
    print(f"   事件统计: {stats['event_counts']}")

    print("\n3. 测试查询功能...")

    # 测试不同的查询
    test_queries = [
        ("权重调整相关", "weight_adjustment"),
        ("阈值变化", "threshold_change"),
        ("参数调优", "parameter_tuning"),
        ("提高信号质量", "提高信号质量"),
        ("过滤假突破", "过滤假突破"),
    ]

    for query, expected_type in test_queries:
        print(f"\n  查询: '{query}'")
        results = archivist.query_history(query, limit=3)

        if results:
            print(f"    找到 {len(results)} 条相关记录:")
            for i, (log, similarity) in enumerate(results):
                print(
                    f"    结果{i + 1}: 相似度={similarity:.3f}, 事件={log.event_type.value}"
                )
                print(f"        原因: {log.reason}")
        else:
            print(f"    未找到相关记录")

    print("\n4. 测试重新加载功能...")

    # 停止当前实例
    archivist.stop()
    time.sleep(0.5)

    # 创建新实例（应该从文件加载记忆）
    print("创建新实例（从文件加载）...")
    archivist2 = EvolutionArchivist(config)

    print(f"   加载后记忆数: {len(archivist2.memory_cache)}")

    # 测试查询是否还能工作
    query = "权重调整"
    results = archivist2.query_history(query, limit=3)
    print(f"   查询 '{query}' 结果数: {len(results)}")

    # 清理
    archivist2.stop()
    if os.path.exists(config["storage_path"]):
        os.remove(config["storage_path"])

    print("\n测试完成")


if __name__ == "__main__":
    test_complete_functionality()
