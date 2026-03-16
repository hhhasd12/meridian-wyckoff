#!/usr/bin/env python3
"""
简单测试时间戳修复
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# 添加src目录到路径
sys.path.insert(0, ".")
sys.path.insert(0, "./src")

from src.plugins.orchestrator.system_orchestrator_legacy import SystemOrchestrator


def test_basic_conversion():
    """测试基本时间戳转换"""
    print("=== 测试基本时间戳转换 ===")

    # 创建测试数据
    dates = pd.date_range("2024-01-01", periods=5, freq="h")
    test_data = {
        "open": [50000, 50100, 50200, 50300, 50400],
        "high": [50100, 50200, 50300, 50400, 50500],
        "low": [49900, 50000, 50100, 50200, 50300],
        "close": [50050, 50150, 50250, 50350, 50450],
        "volume": [1000, 1100, 1200, 1300, 1400],
    }

    df = pd.DataFrame(test_data, index=dates)
    print(f"原始数据:")
    print(f"  索引类型: {type(df.index)}")
    print(f"  索引dtype: {df.index.dtype}")
    print(f"  索引值: {list(df.index)}")

    # 创建协调器实例
    config = {"mode": "paper"}
    orchestrator = SystemOrchestrator(config)

    # 测试转换函数
    converted_df = orchestrator._convert_timestamps_to_unix_ms(df)

    print(f"\n转换后数据:")
    print(f"  索引类型: {type(converted_df.index)}")
    print(f"  索引dtype: {converted_df.index.dtype}")
    print(f"  索引值: {list(converted_df.index)}")

    # 验证转换
    expected_values = [int(d.timestamp() * 1000) for d in dates]
    actual_values = list(converted_df.index)

    print(f"\n验证转换:")
    all_correct = True
    for i, (expected, actual) in enumerate(zip(expected_values, actual_values)):
        if expected == actual:
            print(f"  第{i}行: {expected} == {actual} [OK]")
        else:
            print(f"  第{i}行: {expected} != {actual} [ERROR]")
            all_correct = False

    if not all_correct:
        return False

    # 测试时间比较
    print(f"\n测试时间比较:")
    test_time = 1704067200000  # 2024-01-01 00:00:00

    try:
        for i, ts in enumerate(actual_values):
            if ts > test_time:
                print(f"  {ts} > {test_time}: True")
            else:
                print(f"  {ts} > {test_time}: False")

        print("  时间比较测试通过 [OK]")
        return True

    except TypeError as e:
        print(f"  时间比较测试失败: {e} [ERROR]")
        return False


def test_data_sanitizer_conversion():
    """测试数据清洗器的时间戳处理"""
    print("\n=== 测试数据清洗器时间戳处理 ===")

    from src.plugins.data_pipeline.data_sanitizer import DataSanitizer, DataSanitizerConfig, MarketType

    # 创建测试数据（Unix毫秒整数索引）
    timestamps = [
        1704067200000,
        1704070800000,
        1704074400000,
        1704078000000,
        1704081600000,
    ]  # 5个时间点
    test_data = {
        "open": [50000, 50100, 50200, 50300, 50400],
        "high": [50100, 50200, 50300, 50400, 50500],
        "low": [49900, 50000, 50100, 50200, 50300],
        "close": [50050, 50150, 50250, 50350, 50450],
        "volume": [1000, 1100, 1200, 1300, 1400],
    }

    df = pd.DataFrame(test_data, index=timestamps)
    df.index = df.index.astype("int64")  # 确保是int64

    print(f"输入数据:")
    print(f"  索引类型: {type(df.index)}")
    print(f"  索引dtype: {df.index.dtype}")
    print(f"  索引值: {list(df.index)}")

    # 创建数据清洗器
    config = DataSanitizerConfig()
    config.MARKET_TYPE = MarketType.CRYPTO
    sanitizer = DataSanitizer(config)

    try:
        # 清洗数据
        processed_df, anomalies = sanitizer.sanitize_dataframe(
            df, symbol="BTC/USDT", exchange="binance"
        )

        print(f"\n清洗后数据:")
        print(f"  索引类型: {type(processed_df.index)}")
        print(f"  索引dtype: {processed_df.index.dtype}")
        print(f"  索引值: {list(processed_df.index)}")

        # 验证索引仍然是int64
        if processed_df.index.dtype == "int64":
            print("  索引正确保持为int64 [OK]")

            # 验证值未改变
            if list(processed_df.index) == timestamps:
                print("  索引值未改变 [OK]")
                return True
            else:
                print(
                    f"  索引值改变: {list(processed_df.index)} != {timestamps} [ERROR]"
                )
                return False
        else:
            print(f"  索引类型错误: {processed_df.index.dtype} [ERROR]")
            return False

    except Exception as e:
        print(f"  数据清洗失败: {e} [ERROR]")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("运行时间戳修复测试...\n")

    test1_passed = test_basic_conversion()
    print("\n" + "=" * 50)

    test2_passed = test_data_sanitizer_conversion()

    print("\n" + "=" * 50)
    if test1_passed and test2_passed:
        print("所有测试通过！时间戳修复已成功应用。")
        sys.exit(0)
    else:
        print("测试失败，请检查修复代码。")
        sys.exit(1)
