"""
测试决策可视化模块与系统协调器的集成
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib

matplotlib.use("Agg")  # 使用非交互式后端，避免弹窗

# 导入系统协调器
from src.core.system_orchestrator import SystemOrchestrator, SystemMode


def create_test_config():
    """创建测试配置"""
    return {
        "paper_trading": True,
        "data_sources": {
            "crypto": {
                "enabled": True,
                "exchanges": ["binance"],
                "symbols": ["BTC/USDT"],
                "timeframes": ["1h"],
                "api_key": "",
                "api_secret": "",
            }
        },
        "orchestrator": {
            "default_mode": "paper",
            "environment": "development",
            "realtime": {
                "data_refresh_interval": 60,
                "signal_check_interval": 30,
                "max_concurrent_symbols": 1,
                "enable_auto_trading": False,
            },
            "decision": {
                "min_confidence": 0.65,
                "confirmation_required": True,
                "max_decisions_per_hour": 12,
            },
        },
        "decision_visualizer": {
            "snapshot_dir": "logs/snapshots/integration_test",
            "plot_candles": 100,
            "dpi": 100,
            "figsize": [12, 8],
            "enable_tr_visualization": True,
            "enable_state_visualization": True,
            "enable_signal_visualization": True,
            "max_snapshots_per_day": 50,
            "cleanup_old_snapshots": False,
            "retention_days": 1,
            "show_geometric_shapes": True,
            "show_support_resistance": True,
            "show_volume_profile": False,
            "show_indicators": False,
        },
    }


def create_test_data():
    """创建测试数据"""
    np.random.seed(42)
    n_candles = 300

    # 生成时间序列
    start_time = datetime.now() - timedelta(days=15)
    timestamps = [start_time + timedelta(hours=i) for i in range(n_candles)]

    # 生成价格数据（模拟TR形态）
    base_price = 50000

    # 前100根：上升趋势
    trend1 = np.linspace(0, 0.15, 100)
    # 中间100根：震荡区间
    trend2 = np.zeros(100)
    # 后100根：突破上升
    trend3 = np.linspace(0, 0.2, 100)

    trend = np.concatenate([trend1, trend2, trend3])
    noise = np.random.normal(0, 0.01, n_candles)

    # 生成OHLC数据
    closes = base_price * (1 + trend + noise)
    opens = closes * (1 + np.random.normal(0, 0.005, n_candles))
    highs = np.maximum(opens, closes) * (
        1 + np.abs(np.random.normal(0, 0.01, n_candles))
    )
    lows = np.minimum(opens, closes) * (
        1 - np.abs(np.random.normal(0, 0.01, n_candles))
    )
    volumes = np.random.uniform(100, 1000, n_candles)

    # 创建DataFrame
    data = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=timestamps,
    )

    return data


def test_integration():
    """测试集成功能"""
    print("开始测试决策可视化模块与系统协调器的集成...")

    # 创建测试配置
    test_config = create_test_config()

    # 创建系统协调器（模拟模式）
    print("创建系统协调器...")
    # 在配置中添加模式
    test_config["mode"] = "paper"
    orchestrator = SystemOrchestrator(config=test_config)

    # 模拟状态变化触发
    print("\n模拟状态变化触发...")
    try:
        if hasattr(orchestrator, "decision_visualizer"):
            filename = orchestrator.decision_visualizer.visualize_state_change(
                data=test_data,
                symbol="BTCUSDT",
                state_info={
                    "current_state": "Phase C",
                    "state_confidence": 0.85,
                    "state_direction": "UP",
                    "state_intensity": 0.7,
                },
                previous_state="Phase B",
            )
            print(f"状态变化可视化创建成功: {filename}")
        else:
            print("错误: decision_visualizer 属性不存在")
    except Exception as e:
        print(f"状态变化可视化失败: {e}")

    # 检查快照目录
    print("\n检查快照目录...")
    import os

    snapshot_dir = test_config["decision_visualizer"]["snapshot_dir"]
    if os.path.exists(snapshot_dir):
        files = os.listdir(snapshot_dir)
        print(f"快照目录存在，包含 {len(files)} 个文件:")
        for file in files[:5]:  # 只显示前5个文件
            print(f"  - {file}")
        if len(files) > 5:
            print(f"  ... 还有 {len(files) - 5} 个文件")
    else:
        print(f"警告: 快照目录不存在: {snapshot_dir}")

    print("\n集成测试完成!")
    print("请检查以下目录查看生成的图像:")
    print(f"  {snapshot_dir}")


if __name__ == "__main__":
    test_integration()
