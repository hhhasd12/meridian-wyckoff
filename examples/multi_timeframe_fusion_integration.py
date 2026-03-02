"""
多周期融合集成示例
演示第三阶段模块的完整工作流程：
1. 周期权重过滤器 - 动态分配各时间框架权重
2. 冲突检测与解决模块 - 识别并解决多时间框架冲突
3. 微观入场验证器 - 生成精确入场参数

本示例模拟一个典型的"日线派发 vs 4小时吸筹"冲突场景，并展示完整的辩证解决流程。
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.period_weight_filter import PeriodWeightFilter, Timeframe
from src.core.conflict_resolver import ConflictResolutionManager, ConflictType
from src.core.micro_entry_validator import MicroEntryValidator
from src.core.wyckoff_state_machine import EnhancedWyckoffStateMachine, StateConfig
from src.core.market_regime import RegimeDetector, MarketRegime


def generate_multi_timeframe_sample_data():
    """
    生成多时间框架示例数据
    模拟典型的"日线派发 vs 4小时吸筹"冲突场景
    """
    print("生成多时间框架示例数据...")

    # 创建基础数据（日线级别）
    dates_daily = pd.date_range("2024-01-01", periods=30, freq="D")

    # 日线数据 - 派发模式（下跌趋势）
    daily_prices = []
    daily_volumes = []
    base_price = 50000

    for i in range(len(dates_daily)):
        # 日线呈现派发特征：价格逐步下跌
        trend_factor = -0.2 * (i / len(dates_daily))
        noise = np.random.randn() * 100
        price = base_price * (1 + trend_factor) + noise

        # 成交量特征：派发阶段通常伴随高成交量
        if i < 10:
            volume = 5000 + np.random.rand() * 2000  # 初始高成交量
        elif i < 20:
            volume = 3000 + np.random.rand() * 1500  # 成交量收缩
        else:
            volume = 4000 + np.random.rand() * 2000  # 成交量再次放大

        daily_prices.append(price)
        daily_volumes.append(volume)

    daily_df = pd.DataFrame(
        {
            "open": daily_prices,
            "high": [p + abs(np.random.randn() * 150) for p in daily_prices],
            "low": [p - abs(np.random.randn() * 150) for p in daily_prices],
            "close": daily_prices,
            "volume": daily_volumes,
        },
        index=dates_daily,
    )

    # 4小时数据 - 吸筹模式（盘整上涨）
    # 生成更多数据点用于4小时级别
    dates_h4 = pd.date_range(
        "2024-01-01", periods=180, freq="4h"
    )  # 30天 * 6根4小时K线/天

    h4_prices = []
    h4_volumes = []

    for i in range(len(dates_h4)):
        # 4小时呈现吸筹特征：盘整后上涨
        day_idx = i // 6
        intraday_idx = i % 6

        # 基础价格跟随日线趋势
        base = daily_prices[day_idx] if day_idx < len(daily_prices) else base_price

        # 吸筹模式：前4天盘整，后1天上涨
        if day_idx < 20:
            # 盘整阶段：在窄幅区间内波动
            cycle_factor = np.sin(intraday_idx * np.pi / 3) * 0.005
            price = base * (1 + cycle_factor) + np.random.randn() * 50
            volume = 800 + np.random.rand() * 400
        else:
            # 上涨阶段：突破上涨
            breakout_factor = 0.01 * (day_idx - 20)
            price = base * (1 + breakout_factor) + np.random.randn() * 80
            volume = 1500 + np.random.rand() * 800  # 突破放量

        h4_prices.append(price)
        h4_volumes.append(volume)

    h4_df = pd.DataFrame(
        {
            "open": h4_prices,
            "high": [p + abs(np.random.randn() * 80) for p in h4_prices],
            "low": [p - abs(np.random.randn() * 80) for p in h4_prices],
            "close": h4_prices,
            "volume": h4_volumes,
        },
        index=dates_h4,
    )

    # 1小时数据 - 混合信号
    dates_h1 = pd.date_range("2024-01-01", periods=720, freq="h")

    h1_prices = []
    h1_volumes = []

    for i in range(len(dates_h1)):
        h4_idx = i // 4
        if h4_idx < len(h4_prices):
            base = h4_prices[h4_idx]
        else:
            base = base_price

        # 1小时呈现混合信号：既有上涨也有回调
        cycle_factor = np.sin(i * np.pi / 12) * 0.003
        price = base * (1 + cycle_factor) + np.random.randn() * 30
        volume = 400 + np.random.rand() * 200

        h1_prices.append(price)
        h1_volumes.append(volume)

    h1_df = pd.DataFrame(
        {
            "open": h1_prices,
            "high": [p + abs(np.random.randn() * 40) for p in h1_prices],
            "low": [p - abs(np.random.randn() * 40) for p in h1_prices],
            "close": h1_prices,
            "volume": h1_volumes,
        },
        index=dates_h1,
    )

    print(f"  日线数据: {daily_df.shape}")
    print(f"  4小时数据: {h4_df.shape}")
    print(f"  1小时数据: {h1_df.shape}")

    return {"D": daily_df, "H4": h4_df, "H1": h1_df}


def analyze_timeframe_states(data_dict):
    """
    分析各时间框架状态
    在实际应用中，这里会调用威科夫状态机进行状态检测
    本示例中模拟分析结果
    """
    print("\n分析各时间框架状态...")

    # 模拟状态分析结果
    # 日线：派发模式 (BEARISH)
    # 4小时：吸筹模式 (BULLISH)
    # 1小时：混合信号 (BULLISH)

    timeframe_states = {
        "W": {"state": "BULLISH", "confidence": 0.7},  # 周线看涨
        "D": {"state": "BEARISH", "confidence": 0.8},  # 日线派发，置信度高
        "H4": {"state": "BULLISH", "confidence": 0.75},  # 4小时吸筹，置信度中高
        "H1": {"state": "BULLISH", "confidence": 0.6},  # 1小时看涨，置信度中等
        "M15": {"state": "BEARISH", "confidence": 0.7},  # 15分钟回调
        "M5": {"state": "BULLISH", "confidence": 0.65},  # 5分钟看涨
    }

    print("  时间框架状态分析结果:")
    for tf, state_info in timeframe_states.items():
        print(
            f"    {tf}: {state_info['state']} (置信度: {state_info['confidence']:.2f})"
        )

    return timeframe_states


def demonstrate_period_weight_filter(timeframe_states):
    """
    演示周期权重过滤器
    """
    print("\n" + "=" * 60)
    print("1. 周期权重过滤器演示")
    print("=" * 60)

    # 创建过滤器
    filter = PeriodWeightFilter()

    # 获取不同市场体制下的权重
    regimes = ["TRENDING_BULLISH", "TRENDING_BEARISH", "RANGING", "HIGH_VOLATILITY"]

    for regime in regimes:
        weights = filter.get_weights(regime)
        print(f"\n  {regime} 体制下的权重分配:")
        for tf in Timeframe.get_all():
            if tf in weights:
                print(f"    {tf.name:8s}: {weights[tf]:.3f} ({weights[tf] * 100:.1f}%)")

    # 计算加权决策分数
    print("\n  加权决策计算:")
    timeframe_scores = {
        tf: state_info["confidence"] for tf, state_info in timeframe_states.items()
    }

    for regime in ["RANGING", "TRENDING_BULLISH"]:
        weighted_score = filter.calculate_weighted_score(timeframe_scores, regime)
        print(f"    {regime} 体制下的加权总分: {weighted_score:.3f}")

        # 获取加权决策
        decision = filter.get_weighted_decision(timeframe_states, regime)
        print(
            f"    加权决策: {decision['primary_bias']} (置信度: {decision['confidence']:.3f})"
        )

    return filter


def demonstrate_conflict_resolution(timeframe_states, filter):
    """
    演示冲突检测与解决
    """
    print("\n" + "=" * 60)
    print("2. 冲突检测与解决模块演示")
    print("=" * 60)

    # 创建冲突解决管理器
    resolver = ConflictResolutionManager()

    # 检测冲突
    print("\n  冲突检测:")
    conflict_type, conflict_detail = resolver.detect_conflict(timeframe_states)
    print(f"    检测到的冲突类型: {conflict_type}")
    print(f"    冲突详情: {conflict_detail.get('type', 'N/A')}")

    if conflict_type == ConflictType.DISTRIBUTION_ACCUMULATION:
        print("    → 日线派发 vs 4小时吸筹冲突 (典型辩证场景)")
    elif conflict_type == ConflictType.MULTI_TIMEFRAME_CONFLICT:
        print("    → 多时间框架混合冲突")
    elif conflict_type == ConflictType.TREND_CORRECTION:
        print("    → 趋势 vs 回调冲突")
    else:
        print("    → 无冲突")

    # 解决冲突
    print("\n  冲突解决:")
    market_context = {
        "regime": "RANGING",  # 市场处于盘整体制
        "timestamp": datetime.now().isoformat(),
        "volatility": 1.2,  # 中等波动
    }

    resolution = resolver.resolve_conflict(timeframe_states, market_context)

    print(f"    最终决策: {resolution['primary_bias']}")
    print(f"    决策置信度: {resolution['confidence']:.3f}")
    risk_multiplier = resolution.get("risk_multiplier", 1.0)
    risk_level = (
        "高" if risk_multiplier >= 1.0 else "中" if risk_multiplier >= 0.5 else "低"
    )
    print(f"    风险等级: {risk_level} (风险乘数: {risk_multiplier})")

    if "dominant_timeframe" in resolution:
        print(f"    主导时间框架: {resolution['dominant_timeframe']}")

    if "resolution_logic" in resolution:
        print(f"    解决逻辑: {resolution['resolution_logic']}")

    # 显示解决历史
    print("\n  冲突解决历史:")
    history = resolver.get_resolution_history()
    if history:
        for i, entry in enumerate(history[-3:], 1):  # 显示最近3条
            print(
                f"    {i}. {entry['timestamp']}: {entry['conflict_type']} → {entry['resolution']['primary_bias'] if 'resolution' in entry else 'N/A'}"
            )
    else:
        print("    无历史记录")

    return resolver, resolution


def demonstrate_micro_entry_validation(data_dict, resolution, timeframe_states):
    """
    演示微观入场验证器
    """
    print("\n" + "=" * 60)
    print("3. 微观入场验证器演示")
    print("=" * 60)

    # 创建验证器
    validator = MicroEntryValidator()

    # 准备数据
    h4_data = data_dict["H4"].iloc[-20:]  # 最近20根4小时K线
    h1_data = data_dict["H1"].iloc[-80:]  # 最近80根1小时K线
    m15_data = data_dict["H1"].iloc[-320:]  # 使用1小时数据模拟15分钟数据

    # 创建H4结构（模拟突破）
    h4_structure = {
        "type": "CREEK",  # 阻力结构
        "price_level": h4_data["high"].max() * 0.995,  # 略低于最高点
        "direction": "RESISTANCE",
        "confidence": 0.8,
        "timestamp": datetime.now().isoformat(),
    }

    print("\n  H4结构分析:")
    print(f"    结构类型: {h4_structure['type']}")
    print(f"    价格水平: {h4_structure['price_level']:.2f}")
    print(f"    方向: {h4_structure['direction']}")

    # 宏观偏向来自冲突解决结果
    macro_bias = resolution.get("primary_bias", "NEUTRAL")

    # 市场上下文
    market_context = {
        "regime": "RANGING",
        "timestamp": datetime.now().isoformat(),
        "volatility": 1.2,
    }

    # 使用公共API进行完整验证
    print("\n  完整入场验证:")
    validation_result = validator.validate_entry(
        h4_structure, h1_data, m15_data, macro_bias, market_context
    )

    print(f"    入场信号类型: {validation_result['signal_type']}")
    print(f"    总体得分: {validation_result['overall_score']:.2f}")
    print(
        f"    置信度: {validation_result.get('confidence', validation_result['overall_score']):.2f}"
    )
    print(
        f"    建议动作: {validation_result.get('recommended_action', validation_result['signal_type'])}"
    )

    # 提取入场参数（如果验证通过）
    if validation_result["signal_type"] in ["AGGRESSIVE_ENTRY", "CONFIRMED_ENTRY"]:
        entry_params = validation_result.get("entry_parameters", {})
        print(f"\n    入场参数:")
        print(f"      方向: {entry_params.get('direction', 'N/A')}")
        print(f"      入场价格: {entry_params.get('entry_price', 0):.2f}")
        print(f"      止损: {entry_params.get('stop_loss', 0):.2f}")
        print(f"      止盈: {entry_params.get('take_profit', 0):.2f}")
        print(f"      风险回报比: {entry_params.get('risk_reward_ratio', 0):.2f}")
    else:
        entry_params = {
            "entry_confidence": validation_result.get("overall_score", 0.0),
            "direction": "N/A",
        }
        print(f"    建议: {validation_result.get('reason', '等待更好时机')}")

    # 确保entry_params包含必要的键
    if "entry_confidence" not in entry_params:
        entry_params["entry_confidence"] = validation_result.get("overall_score", 0.0)

    return validator, entry_params


def demonstrate_full_integration():
    """
    演示完整集成流程
    """
    print("\n" + "=" * 60)
    print("完整多周期融合集成流程演示")
    print("=" * 60)

    # 1. 生成多时间框架数据
    data_dict = generate_multi_timeframe_sample_data()

    # 2. 分析时间框架状态
    timeframe_states = analyze_timeframe_states(data_dict)

    # 3. 周期权重过滤器
    weight_filter = demonstrate_period_weight_filter(timeframe_states)

    # 4. 冲突检测与解决
    resolver, resolution = demonstrate_conflict_resolution(
        timeframe_states, weight_filter
    )

    # 5. 微观入场验证
    validator, entry_params = demonstrate_micro_entry_validation(
        data_dict, resolution, timeframe_states
    )

    # 6. 综合决策
    print("\n" + "=" * 60)
    print("综合决策总结")
    print("=" * 60)

    print("\n多周期融合分析完成!")
    print(f"\n检测到的冲突: {resolution['conflict_type']}")
    print(
        f"最终决策: {resolution['primary_bias']} (置信度: {resolution['confidence']:.2f})"
    )
    risk_multiplier = resolution.get("risk_multiplier", 1.0)
    risk_level = (
        "高" if risk_multiplier >= 1.0 else "中" if risk_multiplier >= 0.5 else "低"
    )
    print(f"风险等级: {risk_level} (风险乘数: {risk_multiplier})")

    entry_confidence = entry_params.get("entry_confidence", 0.0)
    if entry_confidence >= 0.6:
        print(f"\n[通过] 微观入场验证通过!")
        print(f"   建议入场方向: {entry_params.get('direction', 'N/A')}")
        print(f"   入场价格: {entry_params.get('entry_price', 0):.2f}")
        print(
            f"   止损: {entry_params.get('stop_loss', 0):.2f} (风险: {abs(entry_params.get('entry_price', 0) - entry_params.get('stop_loss', 0)):.2f})"
        )
        print(
            f"   止盈: {entry_params.get('take_profit', 0):.2f} (回报: {abs(entry_params.get('take_profit', 0) - entry_params.get('entry_price', 0)):.2f})"
        )
        print(f"   风险回报比: {entry_params.get('risk_reward_ratio', 0):.1f}")
        print(f"   仓位大小: {entry_params.get('position_size', 0):.2f} (基于2%风险)")
    else:
        print(f"\n[未通过] 微观入场验证未通过!")
        print(f"   入场置信度: {entry_confidence:.2f} (< 0.6)")
        print("   建议等待更好的入场时机")

    print("\n" + "=" * 60)
    print("集成演示完成!")
    print("=" * 60)


def main():
    """主函数"""
    print("多周期融合集成示例")
    print("模拟典型的'日线派发 vs 4小时吸筹'冲突场景")
    print("展示完整的辩证解决流程")
    print("")

    try:
        demonstrate_full_integration()
    except Exception as e:
        print(f"\n[错误] 演示过程中出现错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
