#!/usr/bin/env python3
"""
威科夫全自动逻辑引擎 - 统一启动入口（唯一入口）

用法:
    python run.py --mode=api        # 启动 API 服务器
    python run.py --mode=trading    # 启动交易系统（生产模式）
    python run.py --mode=evolution  # 启动进化系统
    python run.py --mode=backtest   # 回测模式
    python run.py --mode=web        # 启动前端开发服务器
    python run.py --mode=all        # 启动全部服务

交易模式说明:
    --mode=trading 等价于原 run_live.py 的全部功能，包含：
    - UTC+8 上海时间日志
    - Windows asyncio 兼容策略
    - 优雅的信号处理与退出

危险：--mode=trading 将使用真实资金交易，请确认 config.yaml 中
      max_position_usdt 已正确设置！
"""

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows asyncio 兼容策略 — 必须在任何 asyncio 使用之前设置
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# UTC+8 日志格式化器（所有模式共享）
# ---------------------------------------------------------------------------


class UTC8Formatter(logging.Formatter):
    """强制使用 UTC+8 上海时间的日志格式化器"""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone(timedelta(hours=8)))
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def _setup_logging() -> None:
    """配置日志格式 - 使用 UTC+8 上海时间"""
    os.environ["TZ"] = "Asia/Shanghai"
    if hasattr(time, "tzset"):
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


_setup_logging()
logger = logging.getLogger(__name__)


def run_api_server(host: str = "0.0.0.0", port: int = 8000):
    """启动 API 服务器"""
    import uvicorn
    from src.api.app import app

    logger.info(f"Starting API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_trading_system(config_path: str = "config.yaml"):
    """启动交易系统（生产模式）

    等价于原 run_live.py 的全部功能：
    - UTC+8 日志时间戳（已在模块级别设置）
    - Windows asyncio 兼容策略（已在模块级别设置）
    - 优雅的信号处理（SIGINT/SIGTERM）
    - 安全退出（try/finally + is_running 检查）
    """
    from src.app import WyckoffApp

    async def main():
        app = WyckoffApp(config_path=config_path)

        def _handle_signal(signum: int, frame: object) -> None:
            logging.info("收到信号 %s，准备退出", signum)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return  # 没有运行中的事件循环，无需处理
            loop.create_task(app.stop())

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

    asyncio.run(main())


def run_evolution_system():
    """启动进化系统"""
    logger.info("Starting evolution system...")

    evolution_script = Path(__file__).parent / "run_evolution.py"
    if evolution_script.exists():
        subprocess.run([sys.executable, str(evolution_script)])
    else:
        logger.error("Evolution script not found: run_evolution.py")


def run_web_server(port: int = 3000):
    """启动前端开发服务器（v3.0 Phase 6 重建）"""
    logger.error("Frontend not yet built. Will be available after Phase 6.")
    return


def run_all_services(api_port: int = 8000, web_port: int = 3000):
    """启动全部服务"""
    import threading
    import time

    def api_thread():
        run_api_server(port=api_port)

    def web_thread():
        time.sleep(2)
        run_web_server(port=web_port)

    logger.info("Starting all services...")

    api_t = threading.Thread(target=api_thread, daemon=True)
    web_t = threading.Thread(target=web_thread, daemon=True)

    api_t.start()
    web_t.start()

    logger.info(f"API Server: http://localhost:{api_port}")
    logger.info(f"Web Dashboard: http://localhost:{web_port}")
    logger.info("Press Ctrl+C to stop all services")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down all services...")


def main():
    parser = argparse.ArgumentParser(
        description="威科夫全自动逻辑引擎 - 统一启动入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python run.py --mode=api                    # 启动 API 服务器
    python run.py --mode=trading                # 启动交易系统
    python run.py --mode=evolution              # 启动进化系统
    python run.py --mode=web                    # 启动前端开发服务器
    python run.py --mode=all                    # 启动全部服务
    python run.py --mode=api --port=8080        # 指定 API 端口
    python run.py --mode=trading --config=my.yaml  # 指定配置文件
        """,
    )

    parser.add_argument(
        "--mode",
        "-m",
        choices=["api", "trading", "evolution", "backtest", "web", "all"],
        default="api",
        help="运行模式 (默认: api)",
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="API 服务器主机 (默认: 0.0.0.0)",
    )

    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=9527,
        help="API 服务器端口 (默认: 9527)",
    )

    parser.add_argument(
        "--web-port",
        type=int,
        default=5173,
        help="前端服务器端口 (默认: 5173)",
    )

    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  WYCKOFF TRADING ENGINE v2.0")
    print("  威科夫全自动逻辑引擎")
    print("=" * 60 + "\n")

    if args.mode == "api":
        run_api_server(host=args.host, port=args.port)
    elif args.mode == "trading":
        run_trading_system(config_path=args.config)
    elif args.mode == "evolution":
        run_evolution_system()
    elif args.mode == "backtest":
        print("  [backtest] 回测模式 — 使用 WyckoffEngine 统一信号引擎")
        print("  请使用: python run_evolution.py --backtest-only")
        print("  或直接调用 BacktestEngine API")
    elif args.mode == "web":
        run_web_server(port=args.web_port)
    elif args.mode == "all":
        run_all_services(api_port=args.port, web_port=args.web_port)


if __name__ == "__main__":
    main()
