#!/usr/bin/env python3
"""
测试 Binance 数据获取和系统集成
"""

import asyncio
import sys
import os

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


async def test_binance_fetcher():
    """测试 Binance 数据获取器"""
    print("测试 Binance 数据获取器...")

    try:
        from data.binance_fetcher import BinanceFetcher

        async with BinanceFetcher(max_retries=2, request_timeout=10) as fetcher:
            # 获取 ETH/USDT 1小时数据
            print("获取 ETH/USDT 1小时数据...")
            df = await fetcher.fetch_klines(symbol="ETHUSDT", interval="1h", limit=10)

            if not df.empty:
                print(f"成功获取 {len(df)} 行数据")
                print(f"列: {df.columns.tolist()}")
                print(f"最近3行:")
                print(df[["open", "high", "low", "close", "volume"]].tail(3))

                # 验证数据质量
                validation = fetcher.validate_data_quality(df, "ETHUSDT", "1h")
                print(f"数据质量: {'有效' if validation['is_valid'] else '无效'}")
                if validation["issues"]:
                    print(f"问题: {validation['issues']}")
            else:
                print("警告: 获取的数据为空")

    except ImportError as e:
        print(f"导入错误: {e}")
        print("请安装所需依赖: pip install aiohttp pandas numpy")
        return False
    except Exception as e:
        print(f"测试失败: {e}")
        return False

    return True


async def test_system_orchestrator():
    """测试系统协调器导入"""
    print("\n测试系统协调器导入...")

    try:
        from core.system_orchestrator import SystemOrchestrator

        print("系统协调器导入成功")

        # 尝试创建实例
        config = {
            "mode": "backtest",
            "enable_monitoring": False,
            "enable_evolution": False,
        }

        orchestrator = SystemOrchestrator(config)
        print("系统协调器实例创建成功")

        return True
    except ImportError as e:
        print(f"导入错误: {e}")
        return False
    except Exception as e:
        print(f"实例化错误: {e}")
        return False


async def test_data_pipeline():
    """测试数据管道集成"""
    print("\n测试数据管道集成...")

    try:
        from core.data_pipeline import DataPipeline, DataSource, Timeframe
        from datetime import datetime, timedelta

        print("数据管道导入成功")

        # 创建数据管道（禁用缓存）
        pipeline = DataPipeline({"enable_cache": False, "enable_validation": False})

        # 创建数据请求 - 正确导入方式
        from core.data_pipeline import DataRequest

        request = DataRequest(
            symbol="ETH/USDT",
            timeframe=Timeframe.H1,
            source=DataSource.CCXT,
            exchange="binance",
            limit=10,
        )

        print("数据管道初始化成功")
        print(f"数据请求: {request.symbol} {request.timeframe.value}")

        return True
    except ImportError as e:
        print(f"导入错误: {e}")
        return False
    except Exception as e:
        print(f"数据管道错误: {e}")
        return False


async def main():
    """主测试函数"""
    print("=" * 60)
    print("威科夫全自动逻辑引擎 - 集成测试")
    print("=" * 60)

    # 测试 Binance 数据获取器
    binance_ok = await test_binance_fetcher()

    # 测试系统协调器导入
    orchestrator_ok = await test_system_orchestrator()

    # 测试数据管道
    pipeline_ok = await test_data_pipeline()

    print("\n" + "=" * 60)
    print("测试结果:")
    print(f"  Binance 数据获取器: {'通过' if binance_ok else '失败'}")
    print(f"  系统协调器导入: {'通过' if orchestrator_ok else '失败'}")
    print(f"  数据管道集成: {'通过' if pipeline_ok else '失败'}")
    print("=" * 60)

    # 总结
    if binance_ok and orchestrator_ok and pipeline_ok:
        print("\n所有测试通过！系统可以继续集成回测优化。")
        return True
    else:
        print("\n部分测试失败，需要修复问题。")
        print("\n建议:")
        if not binance_ok:
            print("  - 安装依赖: pip install aiohttp pandas numpy")
            print("  - 检查网络连接")
        if not orchestrator_ok:
            print("  - 修复系统协调器中的类型错误")
        if not pipeline_ok:
            print("  - 修复数据管道中的类型错误")
        return False


if __name__ == "__main__":
    # Windows 事件循环修复
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试发生未预期错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n测试发生未预期错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
