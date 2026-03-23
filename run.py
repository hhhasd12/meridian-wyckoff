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
        time.tzset()  # type: ignore[attr-defined]  # Unix-only, guarded by hasattr

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
    """启动 API 服务器（自动打开浏览器 + 端口冲突检测）"""
    import socket
    import threading
    import webbrowser

    import uvicorn
    from src.api.app import app

    # 检测端口是否被占用，自动换端口
    original_port = port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                break  # 端口可用
            port += 1
            if port > original_port + 10:
                logger.error("端口 %d-%d 全部被占用", original_port, port)
                return

    if port != original_port:
        logger.warning("端口 %d 被占用，自动切换到 %d", original_port, port)

    # 延迟打开浏览器（等服务器启动）
    def _open_browser():
        import time

        time.sleep(2)
        url = f"http://localhost:{port}"
        logger.info("打开浏览器: %s", url)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    logger.info(f"Starting API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


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
    """启动进化系统 — 通过插件系统驱动

    使用 WyckoffApp + EvolutionPlugin 驱动进化。
    进化插件会自动分割数据（GA训练70% + WFA验证30%）。
    """
    from src.app import WyckoffApp

    def _load_evolution_data():
        """加载进化所需的多时间周期数据"""
        import pandas as pd

        csv_map = {
            "D1": "data/ETHUSDT_1d.csv",
            "H4": "data/ETHUSDT_4h.csv",
            "H1": "data/ETHUSDT_1h.csv",
            "M15": "data/ETHUSDT_15m.csv",
            "M5": "data/ETHUSDT_5m.csv",
        }
        col_rename = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        data = {}
        for tf, csv_path in csv_map.items():
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
                # 兼容大写列名和小写列名
                df = df.rename(columns=col_rename)
                core = [
                    c
                    for c in ["open", "high", "low", "close", "volume"]
                    if c in df.columns
                ]
                if not core:
                    logger.warning(
                        "跳过 %s: 无有效列 (有: %s)", tf, df.columns.tolist()
                    )
                    continue
                data[tf] = df[core]
                logger.info("Loaded %s: %d bars", tf, len(df))
            else:
                logger.warning("数据文件不存在: %s", csv_path)
        return data

    async def main():
        app = WyckoffApp(config_path="config.yaml")
        app.discover_and_load()

        from src.plugins.evolution.plugin import EvolutionPlugin

        _plugin = app.plugin_manager.get_plugin("evolution")
        if _plugin is None:
            logger.error("进化插件未加载")
            return

        evolution: EvolutionPlugin = _plugin  # type: ignore[assignment]

        # on_load() 已使用 plugin config 初始化，无需再调 activate
        # activate 只在 on_load 失败时作为回退

        try:
            data = _load_evolution_data()
            if not data or "H4" not in data:
                logger.error("无法加载H4数据，请先运行 python fetch_data.py")
                return
            evolution.set_data(data)
        except Exception as e:
            logger.error("数据加载失败: %s", e)
            return

        logger.info("通过 EvolutionPlugin 启动进化...")
        result = await evolution.start_evolution(max_cycles=50)
        logger.info("进化启动结果: %s", result)

        if result.get("status") == "started":
            try:
                while evolution._is_evolving:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("用户中断，停止进化...")
                await evolution.stop_evolution()

        logger.info("进化系统已退出")

    asyncio.run(main())


def run_web_server(port: int = 3000):
    """启动前端 Web 服务（通过 API 服务器提供静态文件）"""
    frontend_index = Path(__file__).parent / "frontend" / "dist" / "index.html"
    if frontend_index.exists():
        logger.info("前端已构建，通过 API 服务器提供静态文件服务")
        run_api_server(port=port)
    else:
        logger.error(
            "前端尚未构建。请先运行: cd frontend && npm install && npm run build"
        )
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
    print("  WYCKOFF TRADING ENGINE v3.0")
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
        print("  请使用: python run.py --mode=evolution")
        print("  或直接调用 BacktestEngine API")
    elif args.mode == "web":
        run_web_server(port=args.web_port)
    elif args.mode == "all":
        run_all_services(api_port=args.port, web_port=args.web_port)


if __name__ == "__main__":
    main()
