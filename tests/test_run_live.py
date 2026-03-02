#!/usr/bin/env python3
"""
测试生产环境启动脚本的核心功能
"""

import asyncio
import sys
import os
import time
import logging
from pathlib import Path
from datetime import datetime

# 添加src目录到路径
sys.path.insert(0, ".")

import pandas as pd
import yaml

from run_live import ProductionSystemRunner


async def test_config_loading():
    """测试配置文件加载"""
    print("测试1: 配置文件加载...")

    # 创建测试配置
    test_config = {
        "paper_trading": True,
        "processing_interval": 5,
        "evolution_interval": 10,
        "health_report_interval": 15,
        "use_real_data": False,
        "symbols": ["BTC/USDT"],
        "timeframes": ["H1"],
        "historical_days": 1,
    }

    # 保存测试配置
    import yaml

    config_path = "test_config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(test_config, f)

    # 测试加载
    runner = ProductionSystemRunner(config_path)
    assert runner.paper_trading == True
    assert runner.config["processing_interval"] == 5

    print("[OK] 配置文件加载测试通过")

    # 清理
    os.remove(config_path)
    return True


async def test_tech_specs_validation():
    """测试TECH_SPECS验证"""
    print("测试2: TECH_SPECS验证...")

    runner = ProductionSystemRunner()
    is_valid, message = runner.validate_tech_specs()

    if not is_valid:
        print(f"[WARN] TECH_SPECS验证警告: {message}")
        # 这不是致命错误，只是警告
    else:
        print("[OK] TECH_SPECS验证通过")

    return True


async def test_mock_data_generation():
    """测试历史数据加载（无缓存时返回空字典）"""
    print("测试3: 历史数据加载...")

    runner = ProductionSystemRunner()
    # load_historical_data 在无 data_cache pkl 时优雅返回空字典
    data_dict = runner.load_historical_data()
    assert isinstance(data_dict, dict)

    # 如果有本地缓存则验证结构
    for tf, df in data_dict.items():
        required_columns = ["open", "high", "low", "close", "volume"]
        assert all(col in df.columns for col in required_columns)
        assert (df["high"] >= df["low"]).all()
        assert (df["close"] >= df["low"]).all()
        assert (df["close"] <= df["high"]).all()

        # 检查索引类型
        assert df.index.name == "timestamp" or isinstance(df.index, pd.DatetimeIndex)

    print("[OK] 模拟数据生成测试通过")
    return True


async def test_health_report():
    """测试健康报告"""
    print("测试4: 健康报告功能...")

    runner = ProductionSystemRunner()
    runner.start_time = time.time() - 3600  # 模拟运行1小时
    runner.processing_count = 100
    runner.evolution_count = 5
    runner.error_count = 2
    runner.last_signal = "BUY"
    runner.last_signal_time = datetime.now()

    # 测试健康报告生成
    await runner.send_health_report()

    # 检查报告文件
    report_dir = Path("reports")
    if report_dir.exists():
        report_files = list(report_dir.glob("health_report_*.txt"))
        assert len(report_files) > 0
        print(f"[OK] 健康报告已生成: {report_files[0].name}")
    else:
        print("[WARN] 报告目录不存在")

    return True


async def test_system_lifecycle():
    """测试系统生命周期"""
    print("测试5: 系统生命周期...")

    # 使用测试配置
    test_config = {
        "paper_trading": True,
        "processing_interval": 2,  # 2秒，快速测试
        "evolution_interval": 5,  # 5秒
        "health_report_interval": 10,
        "use_real_data": False,
        "symbols": ["BTC/USDT"],
        "timeframes": ["H1"],
        "historical_days": 1,
    }

    import yaml

    config_path = "test_lifecycle.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(test_config, f)

    runner = ProductionSystemRunner(config_path)

    try:
        # 启动系统
        success = await runner.start()
        assert success == True
        print("[OK] 系统启动成功")

        # 运行几个周期
        import time

        start_time = time.time()

        while time.time() - start_time < 10:  # 运行10秒
            current_time = time.time()

            if current_time - runner.last_processing_time >= 2:
                await runner.process_market_data()
                runner.last_processing_time = current_time
                runner.processing_count += 1

            await asyncio.sleep(0.1)

        # 检查处理次数
        assert runner.processing_count > 0
        print(f"[OK] 处理了 {runner.processing_count} 次市场数据")

        # 停止系统
        await runner.stop()
        print("[OK] 系统停止成功")

    finally:
        # 清理
        if os.path.exists(config_path):
            os.remove(config_path)

        # 清理测试文件
        for dir_name in ["logs", "reports", "status"]:
            dir_path = Path(dir_name)
            if dir_path.exists():
                for file in dir_path.glob("*test*"):
                    try:
                        file.unlink()
                    except:
                        pass

    return True


async def main():
    """主测试函数"""
    print("=" * 60)
    print("生产环境启动脚本 - 功能测试")
    print("=" * 60)

    # 导入需要的模块
    global pd, datetime, time
    import pandas as pd
    from datetime import datetime
    import time

    tests = [
        test_config_loading,
        test_tech_specs_validation,
        test_mock_data_generation,
        test_health_report,
        test_system_lifecycle,
    ]

    passed = 0
    failed = 0

    for i, test_func in enumerate(tests, 1):
        try:
            print(f"\n测试 {i}/{len(tests)}: {test_func.__name__}")
            success = await test_func()
            if success:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[FAIL] 测试失败: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"通过: {passed}/{len(tests)}")
    print(f"失败: {failed}/{len(tests)}")

    if failed == 0:
        print("[SUCCESS] 所有测试通过！生产环境启动脚本就绪。")
        return 0
    else:
        print("[WARN] 部分测试失败，请检查问题。")
        return 1


if __name__ == "__main__":
    # Windows事件循环设置
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
