#!/usr/bin/env python3
"""
威科夫系统 - 实盘交易入口
==========================

运行方式：
  BINANCE_API_KEY=xxx BINANCE_API_SECRET=yyy python run_live.py
  python run_live.py config_live.yaml

危险：本程序将使用真实资金交易，请确认 config.yaml 中 max_position_usdt 已正确设置！

注意：此脚本是独立运行方式，不通过 API 服务器。
建议使用 API 服务器方式：

1. 启动 API 服务器：
   python -m uvicorn src.api.app:app --port 9527

2. 通过 API 控制实盘：
   curl -X POST http://localhost:9527/api/system/start
   curl -X GET http://localhost:9527/api/system/status
   curl -X POST http://localhost:9527/api/system/stop

此脚本保留作为备用启动方式，适合：
- 命令行直接运行实盘交易
- 调试和开发测试
- 无需 Web 界面的场景
"""

import sys
import asyncio
import os
import time

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
import signal
from datetime import timezone, timedelta, datetime

sys.path.insert(0, ".")
from src.app import WyckoffApp


class UTC8Formatter(logging.Formatter):
    """强制使用 UTC+8 上海时间的日志格式化器"""
    def converter(self, timestamp):
        dt = logging.Formatter.converter(self, timestamp)
        return dt.timetuple()
    
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone(timedelta(hours=8)))
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def _setup_logging() -> None:
    """配置日志格式 - 使用 UTC+8 上海时间"""
    os.environ['TZ'] = 'Asia/Shanghai'
    if hasattr(time, 'tzset'):
        time.tzset()
    
    handler = logging.StreamHandler()
    formatter = UTC8Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
    )


async def main() -> None:
    _setup_logging()

    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    app = WyckoffApp(config_path=config_path)

    def _handle_signal(signum: int, frame: object) -> None:
        logging.info("收到信号 %s，准备退出", signum)
        asyncio.get_event_loop().create_task(app.stop())

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        await app.start()
        await app.run_loop()
    except KeyboardInterrupt:
        pass
    finally:
        if app.is_running:
            await app.stop()

    logging.info("实盘交易系统已退出")


if __name__ == "__main__":
    asyncio.run(main())
