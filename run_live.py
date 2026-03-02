#!/usr/bin/env python3
"""
威科夫系统 - 实盘交易入口
==========================
  BINANCE_API_KEY=xxx BINANCE_API_SECRET=yyy python run_live.py
  python run_live.py config_live.yaml

危险：本程序将使用真实资金交易，请确认 config.yaml 中 max_position_usdt 已正确设置！
"""

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
import signal

sys.path.insert(0, ".")
from src.runners.live_runner import LiveRunner


async def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    runner = LiveRunner(config_path)

    def _handle_signal(signum, frame):
        logging.info(f"收到信号 {signum}，准备退出")
        asyncio.get_event_loop().create_task(runner.stop())

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        await runner.run_loop()
    except KeyboardInterrupt:
        pass
    finally:
        if runner.is_running:
            await runner.stop()

    logging.info("实盘交易系统已退出")


if __name__ == "__main__":
    asyncio.run(main())
