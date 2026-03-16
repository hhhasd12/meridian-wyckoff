#!/usr/bin/env python3
"""
币安 ETH/USDT 历史数据下载
==========================

运行: python fetch_data.py

从币安能拿到的最早时间开始，拉取全量历史数据。

需要代理时:
    set HTTPS_PROXY=http://127.0.0.1:7890
    python fetch_data.py

输出:
    data/ETHUSDT_1d.csv
    data/ETHUSDT_4h.csv
    data/ETHUSDT_1h.csv
    data/ETHUSDT_15m.csv
    data/ETHUSDT_5m.csv
"""

import os
import sys
import time
from datetime import datetime

import ccxt
import pandas as pd

SYMBOL = "ETH/USDT"
DATA_DIR = "data"
BATCH_LIMIT = 1500
REQUEST_DELAY = 0.3

# ETH/USDT 在币安上线时间: 2017-08-17
# since=0 让 ccxt 从交易所最早可用数据开始
ETH_LISTING_MS = int(datetime(2017, 8, 17).timestamp() * 1000)

TIMEFRAMES = ["1d", "4h", "1h", "15m", "5m"]


def create_exchange() -> ccxt.binance:
    """连接币安，自动读取代理"""
    config = {"enableRateLimit": True, "timeout": 30000}

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        if proxy.startswith("socks"):
            config["socksProxy"] = proxy
        else:
            config["httpsProxy"] = proxy
            config["httpProxy"] = proxy

    exchange = ccxt.binance(config)

    try:
        exchange.load_markets()
        print(f"  连接成功 (proxy={proxy or 'direct'})")
    except Exception as e:
        print(f"  连接失败: {e}")
        if not proxy:
            print("  提示: 如需代理 → set HTTPS_PROXY=http://127.0.0.1:7890")
        raise

    return exchange


def fetch_ohlcv(exchange: ccxt.binance, timeframe: str) -> pd.DataFrame:
    """从最早可用数据开始，分页拉取全量 K 线"""
    since = ETH_LISTING_MS
    all_ohlcv = []

    while True:
        try:
            batch = exchange.fetch_ohlcv(
                symbol=SYMBOL, timeframe=timeframe, since=since, limit=BATCH_LIMIT
            )
        except ccxt.RateLimitExceeded:
            print("    速率限制，等 5 秒...")
            time.sleep(5)
            continue
        except Exception as e:
            print(f"    异常: {e}，重试...")
            time.sleep(2)
            continue

        if not batch:
            break

        all_ohlcv.extend(batch)
        last_ts = datetime.utcfromtimestamp(batch[-1][0] / 1000)
        print(f"    {len(all_ohlcv):>6} 条  {last_ts:%Y-%m-%d %H:%M}")

        if len(batch) < BATCH_LIMIT:
            break

        since = batch[-1][0] + 1
        time.sleep(REQUEST_DELAY)

    if not all_ohlcv:
        raise RuntimeError(f"未获取到 {SYMBOL} {timeframe} 数据")

    df = pd.DataFrame(
        all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df.sort_index(inplace=True)

    return df


def main():
    print(f"\n{'=' * 55}")
    print(f"  {SYMBOL} 历史数据下载")
    print(f"{'=' * 55}")

    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"\n  连接币安...")
    exchange = create_exchange()

    results = []

    for timeframe in TIMEFRAMES:
        filepath = os.path.join(DATA_DIR, f"ETHUSDT_{timeframe}.csv")

        print(f"\n  [{timeframe:>3}] 全量 → {filepath}")

        try:
            df = fetch_ohlcv(exchange, timeframe)
            df.to_csv(filepath)

            size_kb = os.path.getsize(filepath) / 1024
            print(
                f"    {len(df):,} 条  {size_kb:.0f} KB  {df.index[0]:%Y-%m-%d} ~ {df.index[-1]:%Y-%m-%d}"
            )
            results.append((timeframe, True))
        except Exception as e:
            print(f"    失败: {e}")
            results.append((timeframe, False))

    # 汇总
    ok = sum(1 for _, s in results if s)
    print(f"\n{'=' * 55}")
    print(f"  完成: {ok}/{len(results)}")
    for tf, success in results:
        print(f"    {'OK' if success else 'FAIL':>4}  {tf}")
    print(f"{'=' * 55}\n")

    if ok < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
