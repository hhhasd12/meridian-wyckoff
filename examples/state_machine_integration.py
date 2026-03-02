"""
威科夫状态机集成示例
演示如何将状态机集成到现有数据管道中
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.wyckoff_state_machine import EnhancedWyckoffStateMachine, StateConfig
from src.core.data_pipeline import DataPipeline
from src.core.tr_detector import TRDetector
from src.core.market_regime import RegimeDetector


def generate_sample_data(n_bars: int = 100) -> pd.DataFrame:
    """生成示例价格数据（模拟盘整到突破）"""
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="H")

    # 模拟威科夫吸筹模式
    prices = []
    volumes = []

    # 阶段1: 下跌趋势
    base_price = 100.0
    for i in range(n_bars):
        if i < 20:
            # 下跌趋势
            trend_factor = -0.5 * (20 - i) / 20
            noise = np.random.randn() * 1.0
            price = base_price * (1 + trend_factor / 100) + noise
            volume = 800 + np.random.rand() * 400
        elif i < 40:
            # SC抛售高潮（高成交量，大幅下跌）
            if i == 25:
                price = base_price * 0.95  # 大幅下跌
                volume = 3000  # 高成交量
            else:
                price = base_price * 0.96 + np.random.randn() * 0.5
                volume = 1000 + np.random.rand() * 500
        elif i < 60:
            # AR自动反弹（成交量收缩）
            bounce_factor = 0.02 * (i - 40) / 20
            price = base_price * 0.97 * (1 + bounce_factor) + np.random.randn() * 0.3
            volume = 600 + np.random.rand() * 300  # 成交量收缩
        elif i < 80:
            # ST二次测试（进一步收缩）
            retrace_factor = -0.01 * (i - 60) / 20
            price = base_price * 0.98 * (1 + retrace_factor) + np.random.randn() * 0.2
            volume = 500 + np.random.rand() * 200  # 进一步收缩
        else:
            # 突破上涨
            breakout_factor = 0.03 * (i - 80) / 20
            price = base_price * (1 + breakout_factor) + np.random.randn() * 0.5
            volume = 1200 + np.random.rand() * 600

        prices.append(price)
        volumes.append(volume)

    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p + abs(np.random.randn() * 0.5) for p in prices],
            "low": [p - abs(np.random.randn() * 0.5) for p in prices],
            "close": prices,
            "volume": volumes,
        },
        index=dates,
    )

    return df


def main():
    """主集成示例"""
    print("=" * 60)
    print("威科夫状态机集成示例")
    print("=" * 60)

    # 1. 生成示例数据
    print("\n1. 生成示例数据...")
    df = generate_sample_data(100)
    print(f"   数据形状: {df.shape}")
    print(f"   时间范围: {df.index[0]} 到 {df.index[-1]}")
    print(f"   价格范围: {df['low'].min():.2f} - {df['high'].max():.2f}")

    # 2. 初始化各个模块
    print("\n2. 初始化各个模块...")

    # 数据管道
    data_pipeline = DataPipeline({"data_source": "memory"})

    # 市场体制检测器
    regime_detector = RegimeDetector()

    # TR识别器
    tr_detector = TRDetector(
        {
            "min_tr_width_pct": 1.0,
            "min_tr_bars": 10,
            "enable_stability_lock": True,
        }
    )

    # 威科夫状态机（增强版）
    state_config = StateConfig()
    state_machine = EnhancedWyckoffStateMachine(state_config)

    print("   所有模块初始化完成")

    # 3. 模拟实时处理
    print("\n3. 模拟实时处理...")
    print("-" * 40)

    # 用于存储结果
    state_history = []
    tr_history = []
    regime_history = []

    # 处理每根K线
    for i in range(20, len(df)):
        current_df = df.iloc[: i + 1]
        latest_candle = df.iloc[i]

        # 3.1 检测市场体制
        try:
            # 尝试不同的API调用方式
            regime_result = regime_detector.detect_regime(current_df["close"])
            market_regime = (
                regime_result.regime.value
                if hasattr(regime_result, "regime")
                else "UNKNOWN"
            )
        except Exception as e:
            # 如果失败，使用默认值
            market_regime = "UNKNOWN"

        # 3.2 检测交易区间
        tr = tr_detector.detect_trading_range(
            current_df, market_regime=market_regime, volatility_index=1.0
        )

        # 3.3 准备状态机上下文
        context = {
            "market_regime": market_regime,
            "tr_detected": tr is not None,
            "timestamp": latest_candle.name
            if hasattr(latest_candle, "name")
            else datetime.now(),
        }

        if tr:
            context.update(
                {
                    "tr_upper": tr.upper_boundary,
                    "tr_lower": tr.lower_boundary,
                    "tr_confidence": tr.confidence,
                    "tr_status": tr.status.value,
                }
            )

        # 3.4 处理状态机
        current_state = state_machine.process_candle(latest_candle, context)

        # 记录历史
        state_history.append(current_state)
        tr_history.append(tr.tr_id if tr else None)
        regime_history.append(market_regime)

        # 显示状态变化
        if i % 10 == 0 or current_state != "IDLE":
            print(
                f"   K线 {i:3d} | 状态: {current_state:8s} | 体制: {market_regime:12s} | TR: {tr.tr_id if tr else '无':10s}"
            )

    # 4. 分析结果
    print("\n4. 结果分析...")
    print("-" * 40)

    # 统计状态分布
    from collections import Counter

    state_counter = Counter(state_history)
    print("   状态分布:")
    for state, count in state_counter.most_common():
        print(
            f"     {state:8s}: {count:3d} 次 ({count / len(state_history) * 100:.1f}%)"
        )

    # 检测到的关键状态
    key_states = ["SC", "AR", "ST", "SPRING", "JOC", "BU"]
    detected_key_states = [s for s in key_states if s in state_history]
    print(
        f"\n   检测到的关键状态: {', '.join(detected_key_states) if detected_key_states else '无'}"
    )

    # 5. 生成状态机报告
    print("\n5. 状态机报告...")
    print("-" * 40)
    report = state_machine.get_state_report()
    for key, value in report.items():
        if key not in ["critical_price_levels", "timeout_counters"]:
            print(f"   {key}: {value}")

    # 6. 多时间框架示例
    print("\n6. 多时间框架状态同步示例...")
    print("-" * 40)

    # 创建多时间框架数据
    multi_tf_data = {
        "1h": df.iloc[-20:],  # 最近20根1小时K线
        "4h": df.iloc[::4].iloc[-10:],  # 最近10根4小时K线（下采样）
    }

    multi_tf_context = {
        "1h": {"market_regime": market_regime},
        "4h": {"market_regime": market_regime},
    }

    # 处理多时间框架
    multi_tf_results = state_machine.process_multi_timeframe(
        multi_tf_data, multi_tf_context
    )
    print("   多时间框架状态:")
    for timeframe, state in multi_tf_results.items():
        print(f"     {timeframe}: {state}")

    print("\n" + "=" * 60)
    print("集成示例完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
