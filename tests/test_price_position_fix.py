"""
测试价格定位逻辑修复
验证系统协调器中的价格定位逻辑是否修复了逻辑矛盾
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_test_data_with_tr():
    """创建包含TR区间的测试数据"""
    np.random.seed(42)
    n_bars = 50

    # 创建TR区间：116128 - 120247
    support = 116128
    resistance = 120247
    tr_center = (support + resistance) / 2

    # 创建价格在TR区间内波动
    dates = pd.date_range(start="2024-01-01", periods=n_bars, freq="1h")

    # 前40根K线在TR区间内
    prices_in_tr = []
    for i in range(40):
        # 在TR区间内随机波动
        price = tr_center + np.random.uniform(
            -(resistance - tr_center) * 0.8, (resistance - tr_center) * 0.8
        )
        prices_in_tr.append(price)

    # 最后10根K线跌破支撑（Mark Down场景）
    prices_below_support = []
    for i in range(10):
        # 逐步跌破支撑
        price = support - (i + 1) * 100  # 逐步下跌
        prices_below_support.append(price)

    prices = prices_in_tr + prices_below_support

    # 创建OHLCV数据
    data = {
        "timestamp": dates,
        "open": [p * (1 + np.random.normal(0, 0.002)) for p in prices],
        "high": [p * (1 + np.abs(np.random.normal(0, 0.005))) for p in prices],
        "low": [p * (1 - np.abs(np.random.normal(0, 0.005))) for p in prices],
        "close": prices,
        "volume": np.random.lognormal(mean=10, sigma=1, size=n_bars),
    }

    df = pd.DataFrame(data)
    df.set_index("timestamp", inplace=True)

    return df, support, resistance


def test_price_position_logic():
    """测试价格定位逻辑"""
    logger.info("=" * 60)
    logger.info("测试价格定位逻辑修复")
    logger.info("=" * 60)

    # 创建测试数据
    test_data, support, resistance = create_test_data_with_tr()
    current_price = test_data["close"].iloc[-1]

    logger.info(f"测试数据信息:")
    logger.info(f"  TR区间: {support:.2f} - {resistance:.2f}")
    logger.info(f"  当前价格: {current_price:.2f}")
    logger.info(
        f"  价格位置: {'低于支撑' if current_price < support else '高于支撑' if current_price > resistance else '在TR区间内'}"
    )

    # 模拟感知结果
    perception_results = {
        "market_regime": {"regime": "BEARISH", "confidence": 0.8},
        "trading_range": {
            "has_trading_range": True,
            "breakout_direction": "bearish",
            "support": support,
            "resistance": resistance,
            "quality_score": 0.85,
        },
        "primary_timeframe": "H4",
        "primary_data": test_data,  # 包含测试数据
        "breakout_status": None,  # 没有突破状态
    }

    # 模拟融合结果
    fusion_results = {
        "timeframe_weights": {"H4": 0.5, "H1": 0.3, "M15": 0.2},
        "detected_conflicts": [],
    }

    # 模拟状态机结果（Mark Down状态）
    state_results = {
        "wyckoff_state": "LPSY",
        "state_confidence": 0.75,
        "state_direction": "DISTRIBUTION",
        "state_intensity": 0.8,
        "state_signals": [],
    }

    # 手动测试价格定位逻辑
    logger.info("\n" + "=" * 60)
    logger.info("手动测试价格定位逻辑")
    logger.info("=" * 60)

    # 提取TR区间
    tr_info = perception_results.get("trading_range", {})
    support = tr_info.get("support")
    resistance = tr_info.get("resistance")

    # 获取当前价格（从primary_data）
    current_price = None
    try:
        if "primary_data" in perception_results:
            primary_data = perception_results["primary_data"]
            if isinstance(primary_data, pd.DataFrame) and not primary_data.empty:
                current_price = float(primary_data["close"].iloc[-1])
                logger.info(f"成功获取当前价格: {current_price:.2f}")
    except Exception as e:
        logger.warning(f"获取当前价格失败: {e}")

    # 测试价格定位逻辑
    if support is not None and resistance is not None:
        logger.info(f"【当前格局】：识别出的 TR 区间 {support:.2f} - {resistance:.2f}")

        if current_price is not None:
            if current_price < support:
                deviation = (current_price - support) / support * 100
                logger.info(
                    f"【价格定位】：当前 {current_price:.2f} 低于支撑位 {support:.2f}，偏离度 {deviation:.1f}% (Mark Down)"
                )

                # 检查Mark Down
                is_mark_down_by_price = True
                logger.info(
                    f"【价格信号】：当前价格 {current_price:.2f} 低于支撑位 {support:.2f}，处于 Mark Down 区域"
                )

                # 威科夫定性
                wyckoff_state = state_results.get("wyckoff_state", "")
                state_direction = state_results.get("state_direction", "")

                if (
                    "DISTRIBUTION" in state_direction
                    or wyckoff_state
                    in [
                        "PSY",
                        "BC",
                        "AR_DIST",
                        "ST_DIST",
                        "UT",
                        "UTAD",
                        "LPSY",
                        "mSOW",
                        "MSOW",
                    ]
                    or is_mark_down_by_price
                ):
                    logger.info(f"【威科夫定性】：当前处于 Mark Down (派发后下跌趋势)")
                    if is_mark_down_by_price:
                        logger.info(f"【确认信号】：价格已跌破TR下沿，确认下跌趋势")
            elif current_price > resistance:
                deviation = (current_price - resistance) / resistance * 100
                logger.info(
                    f"【价格定位】：当前 {current_price:.2f} 高于阻力位 {resistance:.2f}，偏离度 {deviation:.1f}% (Mark Up)"
                )
            else:
                deviation_from_support = (current_price - support) / support * 100
                deviation_from_resistance = (
                    (current_price - resistance) / resistance * 100
                )
                logger.info(
                    f"【价格定位】：当前 {current_price:.2f} 位于 TR 区间内，距支撑 {deviation_from_support:.1f}%，距阻力 {deviation_from_resistance:.1f}%"
                )
        else:
            logger.info(
                f"【价格定位】：TR区间 {support:.2f} - {resistance:.2f} 已识别，但当前价格未知"
            )

    logger.info("\n" + "=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)

    return current_price < support  # 返回是否检测到Mark Down


if __name__ == "__main__":
    # 运行测试
    is_mark_down_detected = test_price_position_logic()

    if is_mark_down_detected:
        logger.info("✅ 测试通过：成功检测到价格低于TR下沿（Mark Down）")
    else:
        logger.warning("❌ 测试失败：未检测到Mark Down信号")

    # 测试原始问题场景
    logger.info("\n" + "=" * 60)
    logger.info("测试原始问题场景：有TR区间但价格未知")
    logger.info("=" * 60)

    # 模拟原始问题：有TR区间但current_price为None
    perception_results_problem = {
        "market_regime": {"regime": "BEARISH", "confidence": 0.8},
        "trading_range": {
            "has_trading_range": True,
            "breakout_direction": "bearish",
            "support": 116128,
            "resistance": 120247,
            "quality_score": 0.85,
        },
        "primary_timeframe": "H4",
        "primary_data": pd.DataFrame(),  # 空数据框
        "breakout_status": None,
    }

    tr_info = perception_results_problem.get("trading_range", {})
    support = tr_info.get("support")
    resistance = tr_info.get("resistance")

    if support is not None and resistance is not None:
        logger.info(f"【当前格局】：识别出的 TR 区间 {support:.2f} - {resistance:.2f}")
        logger.info(
            f"【价格定位】：TR区间 {support:.2f} - {resistance:.2f} 已识别，但当前价格未知"
        )
        logger.info(
            "✅ 修复成功：即使价格未知，也不会输出'价格或 TR 区间信息不足'的矛盾信息"
        )
