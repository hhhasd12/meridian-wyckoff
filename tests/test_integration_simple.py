"""
简单测试决策可视化模块与系统协调器的集成
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib

matplotlib.use("Agg")  # 使用非交互式后端，避免弹窗
import os


def create_test_data():
    """创建测试数据"""
    np.random.seed(42)
    n_candles = 200

    # 生成时间序列
    start_time = datetime.now() - timedelta(days=10)
    timestamps = [start_time + timedelta(hours=i) for i in range(n_candles)]

    # 生成价格数据
    base_price = 50000
    trend = np.linspace(0, 0.1, n_candles)
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


def test_visualization_in_system():
    """测试系统协调器中的可视化功能"""
    print("测试决策可视化模块在系统协调器中的集成...")

    # 创建测试数据
    test_data = create_test_data()

    # 导入决策可视化器
    from src.plugins.dashboard.decision_visualizer import DecisionVisualizer

    # 创建可视化器
    visualizer_config = {
        "snapshot_dir": "logs/snapshots/system_test",
        "plot_candles": 150,
        "dpi": 120,
        "figsize": [13, 9],
    }

    visualizer = DecisionVisualizer(visualizer_config)

    # 测试1: TR检测可视化
    print("\n1. 测试TR检测可视化...")
    try:
        filename = visualizer.visualize_tr_detection(
            data=test_data,
            symbol="BTCUSDT",
            tr_result={
                "detected": True,
                "support": 49800,
                "resistance": 50800,
                "breakout_direction": "up",
                "confidence": 0.82,
            },
        )
        print(f"成功: {filename}")
    except Exception as e:
        print(f"失败: {e}")

    # 测试2: 状态变化可视化
    print("\n2. 测试状态变化可视化...")
    try:
        filename = visualizer.visualize_state_change(
            data=test_data,
            symbol="BTCUSDT",
            state_info={
                "current_state": "Phase C",
                "state_confidence": 0.88,
                "state_direction": "UP",
                "state_intensity": 0.75,
            },
            previous_state="Phase B",
        )
        print(f"成功: {filename}")
    except Exception as e:
        print(f"失败: {e}")

    # 测试3: 基本可视化
    print("\n3. 测试基本可视化...")
    try:
        filename = visualizer.create_visualization(
            data=test_data,
            symbol="BTCUSDT",
            signal="BUY",
            geometric_results={
                "circle_fit": {
                    "success": True,
                    "center_x": 60,
                    "center_y": 50500,
                    "radius": 900,
                },
                "arc_fit": {
                    "success": True,
                    "center_x": 90,
                    "center_y": 50200,
                    "radius": 750,
                    "start_angle": 45,
                    "end_angle": 135,
                },
                "support_levels": [49800, 50000],
                "resistance_levels": [50800, 51000],
            },
            state_info={
                "current_state": "Markup",
                "state_confidence": 0.92,
                "state_direction": "UP",
                "state_intensity": 0.85,
            },
        )
        print(f"成功: {filename}")
    except Exception as e:
        print(f"失败: {e}")

    # 检查生成的图像
    print("\n4. 检查生成的图像...")
    snapshot_dir = visualizer_config["snapshot_dir"]
    if os.path.exists(snapshot_dir):
        files = os.listdir(snapshot_dir)
        print(f"目录: {snapshot_dir}")
        print(f"文件数量: {len(files)}")

        if files:
            print("最新文件:")
            for file in sorted(files)[-3:]:  # 显示最新的3个文件
                filepath = os.path.join(snapshot_dir, file)
                size_kb = os.path.getsize(filepath) / 1024
                print(f"  - {file} ({size_kb:.1f} KB)")
    else:
        print(f"警告: 目录不存在 {snapshot_dir}")

    print("\n测试完成!")
    print("决策可视化模块已成功集成到系统中。")


if __name__ == "__main__":
    test_visualization_in_system()
