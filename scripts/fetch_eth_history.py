"""
ETH历史数据获取 - 多个交易所版
Binance限制太严，试试其他交易所
"""

import ccxt
import pandas as pd
import time
import os

SYMBOL = "ETH/USDT"
DATA_DIR = "data"

# 尝试多个交易所
EXCHANGES = [
    ("bybit", lambda: ccxt.bybit({"enableRateLimit": True})),
    ("kucoin", lambda: ccxt.kucoin({"enableRateLimit": True})),
    ("okx", lambda: ccxt.okx({"enableRateLimit": True})),
]


def fetch_with_exchange(exchange, tf, target=50000):
    tf_ms = {"15m": 15 * 60 * 1000, "1h": 60 * 60 * 1000, "4h": 4 * 60 * 60 * 1000}
    interval = tf_ms[tf]

    all_data = []

    # 从现在开始往回
    current_since = int(pd.Timestamp.now().timestamp() * 1000)

    for i in range(300):
        try:
            ohlcv = exchange.fetch_ohlcv(SYMBOL, tf, since=current_since, limit=2000)

            if not ohlcv:
                break

            before = len(all_data)
            all_data.extend(ohlcv)
            print(f"  +{len(ohlcv)} (总计: {len(all_data)})")

            if len(ohlcv) < 2000:
                break

            current_since = ohlcv[0][0] - interval
            time.sleep(0.5)

        except Exception as e:
            print(f"  错误: {str(e)[:40]}")
            break

    if not all_data:
        return None

    df = pd.DataFrame(all_data, columns=["t", "o", "h", "l", "c", "v"])
    df = df.drop_duplicates(subset="t").sort_values("t")
    df["t"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("t", inplace=True)
    df.index.name = "timestamp"

    return df


def main():
    print("ETH历史数据获取 - 多交易所版")

    os.makedirs(DATA_DIR, exist_ok=True)

    for tf in ["4h", "1h", "15m"]:
        print(f"\n{'=' * 60}")
        print(f"获取 {tf}")
        print(f"{'=' * 60}")

        best_df = None
        best_count = 0
        best_name = ""

        for name, create_exchange in EXCHANGES:
            print(f"\n尝试 {name}...")
            try:
                exchange = create_exchange()
                df = fetch_with_exchange(exchange, tf)

                if df is not None and len(df) > best_count:
                    best_df = df
                    best_count = len(df)
                    best_name = name
                    print(f"  {name}: {len(df)} 条")
                else:
                    print(f"  {name}: {len(df) if df else 0} 条")
            except Exception as e:
                print(f"  {name} 错误: {str(e)[:30]}")

        if best_df is not None:
            best_df.to_csv(f"{DATA_DIR}/ETHUSDT_{tf}.csv")
            print(f"\n✅ 最佳: {best_name}, {best_count} 条")
            print(f"   {best_df.index[0]} ~ {best_df.index[-1]}")
        else:
            print(f"\n❌ 所有交易所失败")

        time.sleep(1)

    # 结果
    print(f"\n{'=' * 60}")
    print("最终结果:")
    for tf in ["15m", "1h", "4h"]:
        df = pd.read_csv(f"{DATA_DIR}/ETHUSDT_{tf}.csv", index_col=0, parse_dates=True)
        print(f"  {tf}: {len(df)}")


if __name__ == "__main__":
    main()
