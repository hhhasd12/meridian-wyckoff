#!/usr/bin/env python3
"""
币安历史数据下载器
==================

从 Binance 获取 ETH/USDT 多周期 K 线数据，保存到 data/ 目录。

下载周期：1D / 4H / 1H / 15m / 5m
文件格式：data/ETHUSDT_{周期}.csv

运行方式：
    python fetch_data.py              # 下载全部 5 个周期
    python fetch_data.py 4h 1h        # 只下载指定周期
    python fetch_data.py --days 365   # 自定义天数

需要代理时：
    set HTTPS_PROXY=http://127.0.0.1:7890
    python fetch_data.py
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import ccxt
import pandas as pd


# ── 周期配置 ────────────────────────────────────────────────────
TIMEFRAME_CONFIG = {
    "1d": {"days": 730, "label": "D1"},
    "4h": {"days": 730, "label": "H4"},
    "1h": {"days": 365, "label": "H1"},
    "15m": {"days": 180, "label": "M15"},
    "5m": {"days": 90, "label": "M5"},
}

SYMBOL = "ETH/USDT"
DATA_DIR = "data"
BATCH_LIMIT = 1500  # 每次请求的 K 线数（Binance 最大 1500）
REQUEST_DELAY = 0.3  # 请求间隔（秒）


def create_exchange() -> ccxt.binance:
    """创建币安交易所连接（自动读取代理配置）"""
    config = {
        "enableRateLimit": True,
        "timeout": 30000,
    }

    # 代理：优先环境变量，其次 config.yaml
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        # ccxt 需要 http/https/socks 分开配置
        if proxy.startswith("socks"):
            config["socksProxy"] = proxy
        elif proxy.startswith("http"):
            config["httpsProxy"] = proxy
            config["httpProxy"] = proxy

    exchange = ccxt.binance(config)

    # 测试连接
    try:
        exchange.load_markets()
        print(f"[OK] 币安连接成功 (proxy={proxy or 'direct'})")
    except Exception as e:
        print(f"[FAIL] 币安连接失败: {e}")
        if not proxy:
            print("       提示: 如需代理，设置 HTTPS_PROXY=http://127.0.0.1:7890")
        raise

    return exchange


def fetch_ohlcv(
    exchange: ccxt.binance,
    timeframe: str,
    days: int,
) -> pd.DataFrame:
    """分页获取 OHLCV 数据

    Args:
        exchange: ccxt 交易所实例
        timeframe: K 线周期 (1d/4h/1h/15m/5m)
        days: 获取多少天的数据

    Returns:
        DataFrame，index 为 DatetimeIndex，列为 open/high/low/close/volume
    """
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    all_ohlcv = []

    while True:
        try:
            batch = exchange.fetch_ohlcv(
                symbol=SYMBOL,
                timeframe=timeframe,
                since=since,
                limit=BATCH_LIMIT,
            )
        except ccxt.RateLimitExceeded:
            print("    速率限制，等待 5 秒...")
            time.sleep(5)
            continue
        except Exception as e:
            print(f"    请求异常: {e}，重试...")
            time.sleep(2)
            continue

        if not batch:
            break

        all_ohlcv.extend(batch)

        # 进度
        last_ts = datetime.utcfromtimestamp(batch[-1][0] / 1000)
        print(
            f"    已获取 {len(all_ohlcv):>6} 条  最新: {last_ts.strftime('%Y-%m-%d %H:%M')}"
        )

        # 到头了
        if len(batch) < BATCH_LIMIT:
            break

        # 下一页
        since = batch[-1][0] + 1
        time.sleep(REQUEST_DELAY)

    if not all_ohlcv:
        raise RuntimeError(f"未获取到任何 {SYMBOL} {timeframe} 数据")

    # 转 DataFrame
    df = pd.DataFrame(
        all_ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)

    # 去重（偶尔分页边界有重复）
    df = df[~df.index.duplicated(keep="first")]
    df.sort_index(inplace=True)

    return df


def download_timeframe(exchange: ccxt.binance, timeframe: str, days: int) -> str:
    """下载单个周期数据并保存

    Returns:
        保存的文件路径
    """
    filename = f"ETHUSDT_{timeframe}.csv"
    filepath = os.path.join(DATA_DIR, filename)

    print(f"\n{'=' * 55}")
    print(f"  {SYMBOL} {timeframe}  |  {days} 天  |  -> {filepath}")
    print(f"{'=' * 55}")

    df = fetch_ohlcv(exchange, timeframe, days)

    # 保存
    df.to_csv(filepath)

    # 汇报
    print(f"  保存成功: {filepath}")
    print(f"  数据范围: {df.index[0]} ~ {df.index[-1]}")
    print(f"  总条数:   {len(df):,}")
    print(f"  文件大小: {os.path.getsize(filepath):,} bytes")

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description="从币安下载 ETH/USDT 历史 K 线数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python fetch_data.py                  # 下载全部 5 个周期
  python fetch_data.py 4h 1h           # 只下载 4h 和 1h
  python fetch_data.py --days 365      # 所有周期都取 365 天
  python fetch_data.py 1d --days 1000  # 日线取 1000 天
        """,
    )
    parser.add_argument(
        "timeframes",
        nargs="*",
        default=list(TIMEFRAME_CONFIG.keys()),
        help="要下载的周期 (默认全部: 1d 4h 1h 15m 5m)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="覆盖默认天数 (0=使用每个周期的默认值)",
    )

    args = parser.parse_args()

    # 验证周期
    for tf in args.timeframes:
        if tf not in TIMEFRAME_CONFIG:
            print(f"错误: 不支持的周期 '{tf}'")
            print(f"可用周期: {', '.join(TIMEFRAME_CONFIG.keys())}")
            sys.exit(1)

    # 创建数据目录
    os.makedirs(DATA_DIR, exist_ok=True)

    # 连接交易所
    print(f"\n连接币安交易所...")
    exchange = create_exchange()

    # 下载
    results = []
    for tf in args.timeframes:
        days = args.days if args.days > 0 else TIMEFRAME_CONFIG[tf]["days"]
        try:
            path = download_timeframe(exchange, tf, days)
            results.append((tf, "OK", path))
        except Exception as e:
            print(f"  下载失败: {e}")
            results.append((tf, "FAIL", str(e)))

    # 汇总
    print(f"\n{'=' * 55}")
    print("  下载结果汇总")
    print(f"{'=' * 55}")
    for tf, status, detail in results:
        label = TIMEFRAME_CONFIG[tf]["label"]
        if status == "OK":
            size = os.path.getsize(detail)
            print(f"  [{status}] {label:>3} ({tf:>3})  {size:>10,} bytes  {detail}")
        else:
            print(f"  [{status}] {label:>3} ({tf:>3})  {detail}")

    ok_count = sum(1 for _, s, _ in results if s == "OK")
    print(f"\n  {ok_count}/{len(results)} 成功")

    if ok_count < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
