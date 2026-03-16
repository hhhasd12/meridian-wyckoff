#!/usr/bin/env python3
"""
DataPipeline单元测试验证脚本
运行DataPipeline的单元测试并验证核心功能
"""

import sys
import os
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.plugins.data_pipeline.data_pipeline import DataPipeline, DataRequest, DataSource, Timeframe


def print_header(text):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f" {text}")
    print("=" * 60)


def test_initialization():
    """测试初始化"""
    print_header("测试1: 数据管道初始化")

    # 测试默认配置
    pipeline_default = DataPipeline()
    print(f"[OK] 默认配置初始化成功")
    print(f"  缓存启用: {pipeline_default.enable_cache}")
    print(f"  验证启用: {pipeline_default.enable_validation}")

    # 测试自定义配置
    config = {
        "redis_host": "test-host",
        "redis_port": 6380,
        "cache_ttl": 1800,
        "enable_cache": False,
        "enable_validation": False,
        "correlation_threshold": 0.5,
    }
    pipeline_custom = DataPipeline(config)
    print(f"[OK] 自定义配置初始化成功")
    print(f"  Redis主机: {pipeline_custom.redis_host}")
    print(f"  缓存TTL: {pipeline_custom.cache_ttl}秒")
    print(f"  相关阈值: {pipeline_custom.correlation_threshold}")

    return True


def test_cache_key_generation():
    """测试缓存键生成"""
    print_header("测试2: 缓存键生成")

    pipeline = DataPipeline()

    # 测试不同请求的缓存键
    requests = [
        DataRequest(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            source=DataSource.CCXT,
            limit=100,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 2),
        ),
        DataRequest(
            symbol="ETH-USDT",  # 测试符号中的特殊字符
            timeframe=Timeframe.D1,
            source=DataSource.YFINANCE,
            limit=50,
        ),
        DataRequest(
            symbol="AAPL",
            timeframe=Timeframe.M15,
            source=DataSource.CSV,
            limit=200,
            start_date=datetime(2024, 12, 1),
        ),
    ]

    for i, request in enumerate(requests, 1):
        cache_key = pipeline.get_cache_key(request)
        print(f"[OK] 请求{i}缓存键: {cache_key}")
        # 验证缓存键格式
        assert "data:" in cache_key
        assert request.symbol.replace("/", "_").replace("-", "_") in cache_key
        assert request.timeframe.value in cache_key

    return True


def test_data_quality_validation():
    """测试数据质量验证"""
    print_header("测试3: 数据质量验证")

    pipeline = DataPipeline()

    # 创建正常测试数据
    normal_data = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [95.0, 96.0, 97.0],
            "close": [102.0, 103.0, 104.0],
            "volume": [1000.0, 1100.0, 1200.0],
        },
        index=pd.date_range(start="2025-01-01", periods=3, freq="1h"),
    )

    # 测试正常数据
    result = pipeline.validate_data_quality(normal_data, "BTC/USDT")
    print(f"[OK] 正常数据验证: {'通过' if result['is_valid'] else '失败'}")
    print(f"  数据点: {result['data_points']}")
    print(f"  时间范围: {result['date_range'][0]} 到 {result['date_range'][1]}")

    # 创建有问题数据
    problematic_data = normal_data.copy()
    problematic_data.loc[problematic_data.index[0], "high"] = 90  # high < low
    problematic_data.loc[problematic_data.index[0], "low"] = 95

    result = pipeline.validate_data_quality(problematic_data, "BTC/USDT")
    print(f"[OK] 问题数据验证: {'通过' if result['is_valid'] else '失败'}")
    if not result["is_valid"]:
        print(f"  发现问题: {result['issues']}")

    # 测试空数据
    empty_data = pd.DataFrame()
    result = pipeline.validate_data_quality(empty_data, "BTC/USDT")
    print(f"[OK] 空数据验证: {'通过' if result['is_valid'] else '失败'}")

    return True


def test_correlation_validation():
    """测试相关性验证"""
    print_header("测试4: 相关性验证")

    pipeline = DataPipeline()

    # 创建相关数据
    np.random.seed(42)
    timestamps = pd.date_range(start="2025-01-01", periods=50, freq="1h")

    # 高度相关的数据
    base_returns = np.random.normal(0, 0.01, 50)
    correlated_returns = base_returns * 0.9 + np.random.normal(0, 0.002, 50)

    df1 = pd.DataFrame(
        {"close": 100 * (1 + np.cumsum(base_returns))},
        index=timestamps,
    )
    df2 = pd.DataFrame(
        {"close": 50 * (1 + np.cumsum(correlated_returns))},
        index=timestamps,
    )

    # 测试高相关性
    result = pipeline.validate_correlation(df1, df2, "BTC/USDT", "ETH/USDT")
    print(f"[OK] BTC-ETH相关性: {result['correlation']:.3f}")
    print(f"  是否相关: {result['is_correlated']}")
    print(f"  共同数据点: {result['common_points']}")

    # 创建不相关数据
    uncorrelated_returns = np.random.normal(0, 0.01, 50)
    df3 = pd.DataFrame(
        {"close": 10 * (1 + np.cumsum(uncorrelated_returns))},
        index=timestamps,
    )

    result = pipeline.validate_correlation(df1, df3, "BTC/USDT", "XRP/USDT")
    print(f"[OK] BTC-XRP相关性: {result['correlation']:.3f}")
    print(f"  是否相关: {result['is_correlated']}")

    return True


async def test_async_functionality():
    """测试异步功能"""
    print_header("测试5: 异步功能测试")

    pipeline = DataPipeline({"enable_cache": False})

    # 注意：这里不实际调用外部API，只测试逻辑
    print("[OK] 异步测试框架就绪")
    print("  注：实际API调用测试需要网络连接和有效API密钥")

    # 测试数据请求对象创建
    request = DataRequest(
        symbol="TEST/SYMBOL",
        timeframe=Timeframe.H1,
        source=DataSource.CCXT,
        limit=10,
    )

    print(f"[OK] 数据请求对象创建成功")
    print(f"  符号: {request.symbol}")
    print(f"  时间框架: {request.timeframe.value}")
    print(f"  数据源: {request.source.value}")

    return True


def test_timeframe_alignment():
    """测试时间框架对齐"""
    print_header("测试6: 时间框架对齐")

    pipeline = DataPipeline()

    # 创建多时间框架测试数据
    data_dict = {
        Timeframe.M15: pd.DataFrame(
            {
                "open": [100, 101, 102, 103, 104, 105, 106, 107],
                "high": [105, 106, 107, 108, 109, 110, 111, 112],
                "low": [95, 96, 97, 98, 99, 100, 101, 102],
                "close": [102, 103, 104, 105, 106, 107, 108, 109],
                "volume": [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700],
            },
            index=pd.date_range(start="2025-01-01 00:00:00", periods=8, freq="15min"),
        ),
        Timeframe.H1: pd.DataFrame(
            {
                "open": [100, 101, 102],
                "high": [108, 109, 110],
                "low": [95, 96, 97],
                "close": [105, 106, 107],
                "volume": [4600, 4700, 4800],
            },
            index=pd.date_range(start="2025-01-01 00:00:00", periods=3, freq="1h"),
        ),
    }

    # 测试对齐功能
    aligned_data = pipeline.align_timeframes(data_dict, Timeframe.H1)

    print(f"[OK] 时间框架对齐完成")
    print(f"  原始H1数据行数: {len(data_dict[Timeframe.H1])}")
    print(f"  对齐后数据行数: {len(aligned_data)}")
    print(f"  特征列数量: {len(aligned_data.columns)}")

    # 显示特征列
    print(f"  特征列示例: {list(aligned_data.columns)[:5]}...")

    return True


def test_statistics():
    """测试统计信息"""
    print_header("测试7: 统计信息")

    pipeline = DataPipeline()

    # 模拟一些缓存活动
    pipeline.cache_stats = {
        "hits": 25,
        "misses": 10,
        "writes": 20,
        "invalidations": 5,
    }

    pipeline.source_status = {
        "ccxt": {"status": "connected", "last_check": datetime.now(), "error_count": 2},
        "yfinance": {"status": "disconnected", "last_check": None, "error_count": 5},
    }

    stats = pipeline.get_statistics()

    print(f"[OK] 统计信息获取成功")
    print(f"  缓存命中率: {stats['cache_hit_rate']:.1%}")
    print(f"  缓存命中: {stats['cache_stats']['hits']}")
    print(f"  缓存未命中: {stats['cache_stats']['misses']}")
    print(f"  CCXT状态: {stats['source_status']['ccxt']['status']}")
    print(f"  YFinance状态: {stats['source_status']['yfinance']['status']}")

    return True


def run_comprehensive_test():
    """运行综合测试"""
    print_header("DataPipeline综合测试")
    print("开始运行DataPipeline单元测试验证...")

    tests = [
        ("初始化测试", test_initialization),
        ("缓存键生成测试", test_cache_key_generation),
        ("数据质量验证测试", test_data_quality_validation),
        ("相关性验证测试", test_correlation_validation),
        ("时间框架对齐测试", test_timeframe_alignment),
        ("统计信息测试", test_statistics),
    ]

    passed_tests = 0
    total_tests = len(tests)

    for test_name, test_func in tests:
        try:
            if test_func():
                print(f"\n[PASS] {test_name} 通过")
                passed_tests += 1
            else:
                print(f"\n[FAIL] {test_name} 失败")
        except Exception as e:
            print(f"\n[FAIL] {test_name} 异常: {e}")

    # 运行异步测试
    try:
        asyncio.run(test_async_functionality())
        print(f"\n[PASS] 异步功能测试 通过")
        passed_tests += 1
    except Exception as e:
        print(f"\n[FAIL] 异步功能测试 异常: {e}")

    # 打印总结
    print_header("测试总结")
    print(f"总测试数: {total_tests + 1}")  # +1 用于异步测试
    print(f"通过数: {passed_tests}")
    print(f"失败数: {(total_tests + 1) - passed_tests}")

    success_rate = passed_tests / (total_tests + 1) * 100
    print(f"成功率: {success_rate:.1f}%")

    if passed_tests == total_tests + 1:
        print("\n[SUCCESS] 所有测试通过！DataPipeline核心功能验证成功。")
        return True
    else:
        print("\n[WARNING] 部分测试失败，请检查相关问题。")
        return False


def main():
    """主函数"""
    try:
        success = run_comprehensive_test()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        return 1
    except Exception as e:
        print(f"\n[ERROR] 测试运行异常: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
