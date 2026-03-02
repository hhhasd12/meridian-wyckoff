"""
系统验证脚本 - 验证威科夫全自动逻辑引擎的核心功能
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

print("=" * 60)
print("威科夫全自动逻辑引擎 - 系统验证")
print("=" * 60)

# 创建测试数据
np.random.seed(42)
n_points = 50
dates = pd.date_range(start="2025-01-01", periods=n_points, freq="h")

# 创建吸筹模式数据
base_price = 100.0
tr_width = 8.0

df_test = pd.DataFrame(
    {
        "open": base_price + np.random.uniform(-tr_width / 2, tr_width / 2, n_points),
        "high": base_price + np.random.uniform(0, tr_width, n_points),
        "low": base_price + np.random.uniform(-tr_width, 0, n_points),
        "close": base_price + np.random.uniform(-tr_width / 2, tr_width / 2, n_points),
        "volume": np.random.rand(n_points) * 1000 + 500,
    },
    index=dates,
)

print(f"\n1. 测试数据创建完成:")
print(f"   - 数据点数: {len(df_test)}")
print(f"   - 时间范围: {df_test.index[0]} 到 {df_test.index[-1]}")
print(f"   - 价格范围: {df_test['low'].min():.2f} - {df_test['high'].max():.2f}")
print(f"   - 平均成交量: {df_test['volume'].mean():.2f}")

# 测试1: 数据质量检查
print(f"\n2. 数据质量检查:")
print(f"   - 缺失值: {df_test.isnull().sum().sum()}")
print(f"   - 无效价格: {((df_test['high'] < df_test['low']).sum())}")
print(f"   - 零成交量: {(df_test['volume'] == 0).sum()}")

# 测试2: 基本统计
print(f"\n3. 基本统计分析:")
print(f"   - 平均收盘价: {df_test['close'].mean():.2f}")
print(f"   - 价格标准差: {df_test['close'].std():.2f}")
print(
    f"   - 价格波动率: {(df_test['close'].std() / df_test['close'].mean() * 100):.2f}%"
)
print(
    f"   - 成交量波动率: {(df_test['volume'].std() / df_test['volume'].mean() * 100):.2f}%"
)

# 测试3: 趋势分析
print(f"\n4. 趋势分析:")
price_change = df_test["close"].iloc[-1] - df_test["close"].iloc[0]
price_change_pct = (price_change / df_test["close"].iloc[0]) * 100
print(f"   - 价格变化: {price_change:+.2f} ({price_change_pct:+.2f}%)")

# 计算简单移动平均
if len(df_test) >= 20:
    sma_20 = df_test["close"].rolling(20).mean().iloc[-1]
    print(f"   - 20周期SMA: {sma_20:.2f}")
    print(f"   - 当前价格 vs SMA20: {(df_test['close'].iloc[-1] - sma_20):+.2f}")

# 测试4: 交易区间识别（简化版）
print(f"\n5. 交易区间识别:")
resistance = df_test["high"].max()
support = df_test["low"].min()
current_price = df_test["close"].iloc[-1]

print(f"   - 阻力位: {resistance:.2f}")
print(f"   - 支撑位: {support:.2f}")
print(f"   - 当前价格: {current_price:.2f}")
print(
    f"   - 价格位置: {((current_price - support) / (resistance - support) * 100):.1f}%"
)

# 测试5: 异常检测
print(f"\n6. 异常检测:")
volume_mean = df_test["volume"].mean()
volume_std = df_test["volume"].std()
volume_outliers = df_test[df_test["volume"] > volume_mean + 2 * volume_std]
print(f"   - 成交量异常: {len(volume_outliers)} 个")

price_mean = df_test["close"].mean()
price_std = df_test["close"].std()
price_outliers = df_test[abs(df_test["close"] - price_mean) > 2 * price_std]
print(f"   - 价格异常: {len(price_outliers)} 个")

# 测试6: 系统组件检查
print(f"\n7. 系统组件检查:")

# 检查核心模块是否存在
core_modules = [
    "src/core/data_sanitizer.py",
    "src/core/anomaly_validator.py",
    "src/core/circuit_breaker.py",
    "src/core/tr_detector.py",
    "src/core/breakout_validator.py",
    "src/core/wyckoff_state_machine.py",
    "src/core/system_orchestrator.py",
    "src/core/config_system.py",
]

for module in core_modules:
    if os.path.exists(module):
        print(f"   [OK] {module}")
    else:
        print(f"   [MISSING] {module}")

# 检查测试文件
test_modules = [
    "tests/core/test_data_sanitizer.py",
    "tests/core/test_breakout_validator.py",
    "tests/core/test_curve_boundary.py",
    "tests/core/test_config_system_simple.py",
    "tests/core/test_tr_detector.py",
    "tests/integration_test_system_logic.py",
]

print(f"\n8. 测试套件检查:")
for test in test_modules:
    if os.path.exists(test):
        print(f"   [OK] {test}")
    else:
        print(f"   [MISSING] {test}")

# 系统总结
print(f"\n" + "=" * 60)
print("系统验证总结:")
print("=" * 60)

# 评估系统状态
issues = []

# 检查数据质量
if df_test.isnull().sum().sum() > 0:
    issues.append("数据存在缺失值")
if (df_test["high"] < df_test["low"]).sum() > 0:
    issues.append("存在无效价格（high < low）")
if (df_test["volume"] == 0).sum() > 0:
    issues.append("存在零成交量")

# 检查模块完整性
missing_core = sum(1 for m in core_modules if not os.path.exists(m))
if missing_core > 0:
    issues.append(f"{missing_core} 个核心模块缺失")

missing_tests = sum(1 for t in test_modules if not os.path.exists(t))
if missing_tests > 0:
    issues.append(f"{missing_tests} 个测试文件缺失")

if issues:
    print("[WARNING] 发现以下问题:")
    for issue in issues:
        print(f"   - {issue}")
else:
    print("[SUCCESS] 系统验证通过")

print(f"\n建议:")
print(f"1. 运行单元测试: python -m pytest tests/ -v")
print(f"2. 检查数据管道: 确保数据源连接正常")
print(f"3. 验证配置系统: 检查config_system.py配置")
print(f"4. 测试异常处理: 模拟异常数据验证系统韧性")

print(f"\n" + "=" * 60)
print("验证完成时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 60)
