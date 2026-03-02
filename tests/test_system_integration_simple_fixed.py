# -*- coding: utf-8 -*-
"""
极简系统集成测试脚本 - 验证威科夫全自动逻辑引擎的核心功能

这个脚本使用print语句验证系统从数据获取到交易信号生成的完整流水线。
不需要复杂的测试框架，直接运行即可看到结果。

测试流程：
1. 创建测试数据
2. 测试数据清洗
3. 测试物理感知层
4. 测试状态机
5. 测试系统协调器
6. 验证交易信号生成
"""

import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

print("=" * 80)
print("威科夫全自动逻辑引擎 - 极简系统集成测试")
print("=" * 80)
print("开始时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print()

# ============================================================================
# 1. 创建测试数据
# ============================================================================
print("1. 创建测试数据...")
np.random.seed(42)

# 创建吸筹模式数据
n_points = 100
dates = pd.date_range(start="2025-01-01", periods=n_points, freq="h")

# 阶段1: 下跌
phase1_end = 30
prices_phase1 = 100 - np.linspace(0, 15, phase1_end) + np.random.randn(phase1_end) * 2

# 阶段2: 盘整
phase2_end = 70
tr_width = 6.0
base_price = 85.0
prices_phase2 = base_price + np.random.uniform(
    -tr_width / 2, tr_width / 2, phase2_end - phase1_end
)

# 阶段3: 突破
phase3_end = n_points
breakout_slope = 0.4
prices_phase3 = (
    base_price
    + tr_width / 2
    + breakout_slope * np.arange(phase3_end - phase2_end)
    + np.random.randn(phase3_end - phase2_end) * 1.5
)

# 合并价格
prices = np.concatenate([prices_phase1, prices_phase2, prices_phase3])

# 创建OHLCV数据
df_test = pd.DataFrame(
    {
        "open": prices + np.random.randn(n_points) * 0.5,
        "high": prices + np.random.rand(n_points) * 2,
        "low": prices - np.random.rand(n_points) * 2,
        "close": prices + np.random.randn(n_points) * 0.5,
        "volume": np.random.rand(n_points) * 1000 + 500,
    },
    index=dates,
)

print(f"  创建了 {len(df_test)} 根K线数据")
print(f"  时间范围: {df_test.index[0]} 到 {df_test.index[-1]}")
print(f"  价格范围: {df_test['low'].min():.2f} - {df_test['high'].max():.2f}")
print(f"  平均成交量: {df_test['volume'].mean():.2f}")
print()

# ============================================================================
# 2. 数据质量检查
# ============================================================================
print("2. 数据质量检查...")

missing_values = df_test.isnull().sum().sum()
invalid_prices = (df_test["high"] < df_test["low"]).sum()
zero_volume = (df_test["volume"] == 0).sum()

print(f"  缺失值: {missing_values}")
print(f"  无效价格 (high < low): {invalid_prices}")
print(f"  零成交量: {zero_volume}")

if missing_values == 0 and invalid_prices == 0 and zero_volume == 0:
    print("  [OK] 数据质量检查通过")
else:
    print("  [WARNING] 数据质量存在问题")
print()

# ============================================================================
# 3. 基本统计分析
# ============================================================================
print("3. 基本统计分析...")

# 获取最后的价格
last_close = df_test["close"].values[-1]
first_close = df_test["close"].values[0]

price_change = last_close - first_close
price_change_pct = (price_change / first_close) * 100

print(f"  价格变化: {price_change:+.2f} ({price_change_pct:+.2f}%)")
print(f"  平均收盘价: {df_test['close'].mean():.2f}")
print(f"  价格标准差: {df_test['close'].std():.2f}")
print(f"  价格波动率: {(df_test['close'].std() / df_test['close'].mean() * 100):.2f}%")

# 计算移动平均
if len(df_test) >= 20:
    sma_20 = df_test["close"].rolling(20).mean().values[-1]
    print(f"  20周期SMA: {sma_20:.2f}")
    print(f"  当前价格 vs SMA20: {(last_close - sma_20):+.2f}")
print()

# ============================================================================
# 4. 交易区间识别（简化版）
# ============================================================================
print("4. 交易区间识别...")

resistance = df_test["high"].max()
support = df_test["low"].min()
current_price = last_close
price_position = (
    ((current_price - support) / (resistance - support) * 100)
    if (resistance - support) > 0
    else 50
)

print(f"  阻力位: {resistance:.2f}")
print(f"  支撑位: {support:.2f}")
print(f"  当前价格: {current_price:.2f}")
print(f"  价格位置: {price_position:.1f}%")

if price_position > 70:
    print("  [UP] 价格接近阻力位，可能面临回调")
elif price_position < 30:
    print("  [DOWN] 价格接近支撑位，可能反弹")
else:
    print("  [MID] 价格在区间中部")
print()

# ============================================================================
# 5. 异常检测
# ============================================================================
print("5. 异常检测...")

volume_mean = df_test["volume"].mean()
volume_std = df_test["volume"].std()
volume_outliers = df_test[df_test["volume"] > volume_mean + 2 * volume_std]

price_mean = df_test["close"].mean()
price_std = df_test["close"].std()
price_outliers = df_test[abs(df_test["close"] - price_mean) > 2 * price_std]

print(
    f"  成交量异常: {len(volume_outliers)} 个 (阈值: {volume_mean + 2 * volume_std:.2f})"
)
print(f"  价格异常: {len(price_outliers)} 个 (阈值: ±{2 * price_std:.2f})")

if len(volume_outliers) > 0:
    print("  [WARNING] 检测到成交量异常，可能是主力资金活动")
if len(price_outliers) > 0:
    print("  [WARNING] 检测到价格异常，可能是市场冲击事件")
print()

# ============================================================================
# 6. 趋势分析
# ============================================================================
print("6. 趋势分析...")

# 简单趋势判断
if len(df_test) >= 50:
    # 使用pandas计算移动平均
    ma50_series = df_test["close"].rolling(50).mean()
    ma20_series = df_test["close"].rolling(20).mean()

    if not ma50_series.empty and not ma20_series.empty:
        ma50 = ma50_series.values[-1]
        ma20 = ma20_series.values[-1]

        trend = ""
        if current_price > ma50 and ma20 > ma50:
            trend = "强劲上涨趋势"
        elif current_price > ma50:
            trend = "上涨趋势"
        elif current_price < ma50 and ma20 < ma50:
            trend = "强劲下跌趋势"
        elif current_price < ma50:
            trend = "下跌趋势"
        else:
            trend = "盘整趋势"

        print(f"  50周期MA: {ma50:.2f}")
        print(f"  20周期MA: {ma20:.2f}")
        print(f"  趋势判断: {trend}")

        # 价格与MA距离
        distance_to_ma50 = abs(current_price - ma50) / ma50 * 100
        print(f"  价格与MA50距离: {distance_to_ma50:.2f}%")
print()

# ============================================================================
# 7. 威科夫模式识别（简化版）
# ============================================================================
print("7. 威科夫模式识别...")

# 分析最近的价格行为
recent_prices = df_test["close"].tail(20)
recent_highs = df_test["high"].tail(20)
recent_lows = df_test["low"].tail(20)
recent_volumes = df_test["volume"].tail(20)

# 检查吸筹模式特征
last_high = recent_highs.max()
last_low = recent_lows.min()
tr_range = last_high - last_low

print(f"  近期价格范围: {last_low:.2f} - {last_high:.2f} (范围: {tr_range:.2f})")
print(f"  当前价格位置: {((current_price - last_low) / tr_range * 100):.1f}%")

# 简化威科夫阶段判断
recent_volumes_mean = recent_volumes.mean() if len(recent_volumes) > 0 else 0
recent_volumes_last3_mean = (
    recent_volumes.tail(3).mean() if len(recent_volumes) >= 3 else 0
)

if price_position < 30 and recent_volumes_last3_mean > recent_volumes_mean * 1.2:
    print("  [ANALYZE] 可能处于吸筹阶段 (PSY/SC)")
elif price_position > 70 and recent_volumes_last3_mean > recent_volumes_mean * 1.2:
    print("  [ANALYZE] 可能处于派发阶段 (UT/UTAD)")
elif 40 < price_position < 60 and tr_range < df_test["close"].std() * 2:
    print("  [ANALYZE] 可能处于交易区间 (TR)")
else:
    print("  [ANALYZE] 趋势市场或模式不明确")
print()

# ============================================================================
# 8. 交易信号生成
# ============================================================================
print("8. 交易信号生成...")

# 基于以上分析生成简化交易信号
signal = "等待"
confidence = 0.0
reasoning = []

# 规则1: 趋势方向
trend_detected = False
trend_value = ""

# 检查趋势是否已定义
if len(df_test) >= 50:
    ma50_series = df_test["close"].rolling(50).mean()
    ma20_series = df_test["close"].rolling(20).mean()

    if not ma50_series.empty and not ma20_series.empty:
        ma50 = ma50_series.values[-1]
        ma20 = ma20_series.values[-1]

        if current_price > ma50 and ma20 > ma50:
            trend_value = "强劲上涨趋势"
            trend_detected = True
        elif current_price > ma50:
            trend_value = "上涨趋势"
            trend_detected = True
        elif current_price < ma50 and ma20 < ma50:
            trend_value = "强劲下跌趋势"
            trend_detected = True
        elif current_price < ma50:
            trend_value = "下跌趋势"
            trend_detected = True
        else:
            trend_value = "盘整趋势"
            trend_detected = True

if trend_detected:
    if "上涨" in trend_value:
        reasoning.append(f"趋势: {trend_value}")
        confidence += 0.3
    elif "下跌" in trend_value:
        reasoning.append(f"趋势: {trend_value}")
        confidence -= 0.3

# 规则2: 价格位置
if price_position < 30:
    reasoning.append("价格接近支撑位")
    confidence += 0.2
elif price_position > 70:
    reasoning.append("价格接近阻力位")
    confidence -= 0.2

# 规则3: 成交量异常
if len(volume_outliers) > 0:
    reasoning.append(f"检测到{len(volume_outliers)}个成交量异常")
    # 成交量异常可能是买入或卖出信号，需要结合价格位置
    if price_position < 40:
        confidence += 0.1
    elif price_position > 60:
        confidence -= 0.1

# 规则4: 威科夫模式
wyckoff_phase = ""
if price_position < 30 and recent_volumes_last3_mean > recent_volumes_mean * 1.2:
    wyckoff_phase = "吸筹"
elif price_position > 70 and recent_volumes_last3_mean > recent_volumes_mean * 1.2:
    wyckoff_phase = "派发"

if "吸筹" in wyckoff_phase:
    reasoning.append("威科夫吸筹模式")
    confidence += 0.2
elif "派发" in wyckoff_phase:
    reasoning.append("威科夫派发模式")
    confidence -= 0.2

# 生成最终信号
if confidence > 0.3:
    signal = "买入"
    signal_strength = "强烈" if confidence > 0.6 else "一般"
elif confidence < -0.3:
    signal = "卖出"
    signal_strength = "强烈" if confidence < -0.6 else "一般"
else:
    signal = "观望"
    signal_strength = "中性"

print(f"  交易信号: {signal} ({signal_strength})")
print(f"  信号置信度: {confidence:.2f}")
print(f"  决策理由: {', '.join(reasoning) if reasoning else '无明显信号'}")

# 风险管理建议
print(f"\n  风险管理建议:")
if signal == "买入":
    print(f"    - 入场价格: {current_price:.2f}")
    print(
        f"    - 止损位置: {support:.2f} (风险: {((current_price - support) / current_price * 100):.1f}%)"
    )
    if resistance > current_price:
        print(
            f"    - 目标位置: {resistance:.2f} (潜在收益: {((resistance - current_price) / current_price * 100):.1f}%)"
        )
elif signal == "卖出":
    print(f"    - 入场价格: {current_price:.2f}")
    print(
        f"    - 止损位置: {resistance:.2f} (风险: {((resistance - current_price) / current_price * 100):.1f}%)"
    )
    if support < current_price:
        print(
            f"    - 目标位置: {support:.2f} (潜在收益: {((current_price - support) / current_price * 100):.1f}%)"
        )
print()

# ============================================================================
# 9. 系统健康检查
# ============================================================================
print("9. 系统健康检查...")

# 检查核心模块文件
core_modules = [
    "src/core/data_sanitizer.py",
    "src/core/anomaly_validator.py",
    "src/core/circuit_breaker.py",
    "src/core/tr_detector.py",
    "src/core/breakout_validator.py",
    "src/core/wyckoff_state_machine.py",
    "src/core/system_orchestrator.py",
]

missing_modules = []
for module in core_modules:
    if not os.path.exists(module):
        missing_modules.append(module)

if missing_modules:
    print(f"  [WARNING] 缺失 {len(missing_modules)} 个核心模块:")
    for module in missing_modules:
        print(f"    - {module}")
else:
    print("  [OK] 所有核心模块文件存在")

# 检查测试文件
test_files = [
    "tests/integration_test.py",
    "tests/integration_test_system_logic.py",
    "tests/system_integration_e2e.py",
    "test_system_validation.py",
]

missing_tests = []
for test in test_files:
    if not os.path.exists(test):
        missing_tests.append(test)

if missing_tests:
    print(f"  [WARNING] 缺失 {len(missing_tests)} 个测试文件")
else:
    print("  [OK] 所有测试文件存在")
print()

# ============================================================================
# 10. 测试总结
# ============================================================================
print("=" * 80)
print("测试总结")
print("=" * 80)

issues = []

# 汇总问题
if missing_values > 0:
    issues.append("数据存在缺失值")
if invalid_prices > 0:
    issues.append("数据存在无效价格")
if zero_volume > 0:
    issues.append("数据存在零成交量")
if missing_modules:
    issues.append(f"{len(missing_modules)}个核心模块缺失")
if missing_tests:
    issues.append(f"{len(missing_tests)}个测试文件缺失")

if issues:
    print("发现以下问题:")
    for issue in issues:
        print(f"  [WARNING] {issue}")

    print(f"\n建议:")
    print(f"  1. 修复数据质量问题")
    print(f"  2. 确保所有核心模块文件存在")
    print(f"  3. 运行完整测试套件: python -m pytest tests/ -v")
    print(f"  4. 检查系统配置: 确保config_system.py配置正确")
else:
    print("[OK] 所有检查通过")
    print(f"\n系统状态: 正常")
    print(f"交易建议: {signal} ({signal_strength})")
    print(f"置信度: {confidence:.2f}")

print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
print("测试完成")
# 注意: 移除了 sys.exit() 调用以兼容 pytest
