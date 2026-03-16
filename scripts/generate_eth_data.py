"""
生成ETH模拟历史数据用于系统测试和进化演示
基于真实市场特征生成
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_eth_data(timeframe: str, days: int = 365) -> pd.DataFrame:
    """
    生成ETH风格的历史数据

    Args:
        timeframe: 时间周期 (4h, 1h, 15m)
        days: 天数
    """
    # 时间间隔（分钟）
    interval_minutes = {
        "4h": 240,
        "1h": 60,
        "15m": 15,
    }

    interval = interval_minutes.get(timeframe, 60)
    total_bars = int(days * 24 * 60 / interval)

    # 起始日期
    start_date = datetime.now() - timedelta(days=days)
    timestamps = pd.date_range(
        start=start_date, periods=total_bars, freq=f"{interval}min"
    )

    # 生成价格序列 - 使用随机游走 + 趋势
    np.random.seed(42)  # 可重现性

    # 基础参数
    initial_price = 3000  # ETH价格
    daily_volatility = 0.03  # 日波动率

    # 生成收益率 - 加入趋势和波动率聚集
    returns = np.random.normal(0.0001, daily_volatility / np.sqrt(24), total_bars)

    # 加入周期性波动（模拟市场周期）
    cycle = np.sin(np.linspace(0, 20 * np.pi, total_bars)) * 0.002
    returns = returns + cycle

    # 加入趋势反转（模拟威科夫循环）
    trend_reversals = np.sin(np.linspace(0, 5 * np.pi, total_bars)) * 0.003
    returns = returns + trend_reversals

    # 计算价格
    price = initial_price * np.exp(np.cumsum(returns))

    # 生成OHLC
    # 模拟日内波动
    intraday_vol = daily_volatility / 2

    high = price * (1 + np.abs(np.random.normal(0, intraday_vol, total_bars)))
    low = price * (1 - np.abs(np.random.normal(0, intraday_vol, total_bars)))
    open_price = price * (1 + np.random.normal(0, intraday_vol / 2, total_bars))
    close_price = price

    # 确保OHLC关系正确
    high = np.maximum.reduce([open_price, close_price, high, low])
    low = np.minimum.reduce([open_price, close_price, high, low])

    # 生成成交量 - 与波动率正相关
    base_volume = 10000
    volume = (
        base_volume
        * (1 + np.abs(returns) * 10)
        * np.random.uniform(0.5, 1.5, total_bars)
    )

    # 创建DataFrame
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
            "volume": volume.astype(int),
        }
    )

    df.set_index("timestamp", inplace=True)

    return df


def main():
    """生成所有时间周期的数据"""
    import os

    # 确保目录存在
    os.makedirs("data", exist_ok=True)

    timeframes = {
        "4h": 500,  # 4小时线，500天
        "1h": 365,  # 1小时线，365天
        "15m": 180,  # 15分钟线，180天
    }

    for tf, days in timeframes.items():
        print(f"Generate {tf} data ({days} days)...")
        df = generate_eth_data(tf, days)

        filename = f"data/ETHUSDT_{tf}.csv"
        df.to_csv(filename)

        print(f"  OK: {filename}")
        print(f"     Range: {df.index[0]} ~ {df.index[-1]}")
        print(f"     Bars: {len(df)}")
        print(f"     Price: ${df['close'].iloc[0]:.2f} ~ ${df['close'].iloc[-1]:.2f}")
        print()

    print("=" * 50)
    print("All data generated!")
    print("=" * 50)
    print("所有数据生成完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()
