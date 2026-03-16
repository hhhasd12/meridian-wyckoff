"""
ETH历史数据下载脚本
使用CCXT从Binance获取ETH/USDT历史K线数据
"""

import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time


def download_eth_data():
    """下载ETH/USDT历史数据"""

    # 初始化Binance交易所
    exchange = ccxt.binance(
        {
            "enableRateLimit": True,
        }
    )

    # 时间周期配置
    timeframes = {
        "4h": "4h",  # 主决策周期
        "1h": "1h",  # 入场周期
        "15m": "15m",  # 微观验证周期
    }

    symbol = "ETH/USDT"

    for name, tf in timeframes.items():
        print(f"\n{'=' * 50}")
        print(f"下载 {symbol} {name} 数据...")
        print(f"{'=' * 50}")

        try:
            # 计算开始时间（获取足够的历史数据）
            # 4h: 500天, 1h: 365天, 15m: 180天
            days_map = {"4h": 500, "1h": 365, "15m": 180}
            days = days_map.get(name, 365)
            since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

            # 获取数据
            all_ohlcv = []
            limit = 2000  # Binance最大限制

            while True:
                ohlcv = exchange.fetch_ohlcv(
                    symbol=symbol, timeframe=tf, since=since, limit=limit
                )

                if not ohlcv:
                    break

                all_ohlcv.extend(ohlcv)

                # 更新since获取下一批
                since = ohlcv[-1][0] + 1

                print(
                    f"  已获取 {len(all_ohlcv)} 条数据，最新时间: {datetime.fromtimestamp(ohlcv[-1][0] / 1000)}"
                )

                # 如果获取的数据少于limit，说明已经到头了
                if len(ohlcv) < limit:
                    break

                # 避免请求过快
                time.sleep(0.5)

            # 转换为DataFrame
            df = pd.DataFrame(
                all_ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)

            # 保存到CSV
            filename = f"data/ETHUSDT_{name}.csv"
            df.to_csv(filename)

            print(f"  ✅ 保存成功: {filename}")
            print(f"  数据范围: {df.index[0]} ~ {df.index[-1]}")
            print(f"  总条数: {len(df)}")

        except Exception as e:
            print(f"  ❌ 下载失败: {e}")

        # 避免请求过快
        time.sleep(1)

    print(f"\n{'=' * 50}")
    print("所有数据下载完成!")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    download_eth_data()
