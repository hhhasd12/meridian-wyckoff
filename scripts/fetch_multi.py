"""从多个数据源获取ETH历史数据"""

import ccxt
import pandas as pd
import time
import os

# 尝试多个交易所
exchanges_to_try = [
    ("binance", {"options": {"defaultType": "spot"}}),
    ("bybit", {}),
    ("okx", {}),
    ("kucoin", {}),
]


def try_fetch(tf, min_bars):
    """尝试从各个交易所获取数据"""

    for exch_name, exch_opts in exchanges_to_try:
        try:
            print(f"  Trying {exch_name}...")
            exchange = getattr(ccxt, exch_name)(exch_opts)

            symbol = "ETH/USDT"
            all_ohlcv = []

            # 从2020年开始
            since = int(pd.Timestamp("2020-01-01").timestamp() * 1000)
            limit = 2000

            while len(all_ohlcv) < min_bars:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, since=since, limit=limit)

                if not ohlcv:
                    break

                all_ohlcv.extend(ohlcv)
                print(f"    {exch_name} {tf}: {len(all_ohlcv)} bars")

                if len(ohlcv) < limit:
                    break

                since = ohlcv[-1][0] + 1
                time.sleep(0.5)

            if all_ohlcv:
                return all_ohlcv, exch_name

        except Exception as e:
            print(f"    {exch_name} failed: {str(e)[:30]}")
            continue

    return None, None


# 获取数据
for tf, target in [("4h", 3000), ("1h", 8000), ("15m", 10000)]:
    print(f"\nFetching {tf}...")
    ohlcv, exch = try_fetch(tf, target)

    if ohlcv:
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df.to_csv(f"data/ETHUSDT_{tf}.csv")
        print(f"  SUCCESS: {tf} from {exch}: {len(df)} bars")
    else:
        print(f"  FAILED: {tf}")

    time.sleep(1)

print("\n=== FINAL ===")
for f in sorted(os.listdir("data")):
    if "ETH" in f:
        df = pd.read_csv(f"data/{f}", index_col=0)
        print(f"  {f}: {len(df)} bars ({len(df) / 24:.0f} days)")
