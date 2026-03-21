"""FastAPI 应用 - 威科夫交易引擎后端 API

提供 3 个 REST 端点和 1 个 WebSocket 端点：
- GET /api/candles/{symbol}/{tf} — 历史K线数据
- GET /api/system/snapshot — 系统状态快照
- POST /api/config — 更新配置
- WS /ws/realtime — 主题订阅式实时推送
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.app import WyckoffApp

logger = logging.getLogger(__name__)


class AppState:
    """应用全局状态"""

    def __init__(self) -> None:
        self.wyckoff_app: Optional[WyckoffApp] = None
        self.start_time: Optional[float] = None

    @property
    def is_ready(self) -> bool:
        """系统是否就绪"""
        return self.wyckoff_app is not None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    启动时创建 WyckoffApp 并加载插件，
    关闭时清理资源。
    """
    logger.info("=" * 60)
    logger.info("威科夫全自动逻辑引擎 API 服务启动中...")
    logger.info("=" * 60)

    app_state.wyckoff_app = WyckoffApp(config_path="config.yaml")
    app_state.wyckoff_app.discover_and_load()
    app_state.start_time = time.time()

    logger.info("API Server 启动完成")

    yield

    logger.info("API Server shutting down...")
    app_state.wyckoff_app = None
    app_state.start_time = None
    logger.info("API Server 已完全关闭")


app = FastAPI(
    title="Wyckoff Trading Engine API",
    description="威科夫全自动逻辑引擎 API",
    version="2.1.0",
    lifespan=lifespan,
)

_cors_origins_str = os.environ.get(
    "WYCKOFF_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000",
)
_cors_origins = [
    origin.strip() for origin in _cors_origins_str.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConfigUpdateRequest(BaseModel):
    """配置更新请求体"""

    config: Dict[str, Any]


@app.get("/api/candles/{symbol}/{tf}")
async def get_candles(symbol: str, tf: str, limit: int = 500) -> List[Dict[str, Any]]:
    """获取历史K线数据

    通过 data_pipeline 插件获取缓存的 OHLCV 数据。

    Args:
        symbol: 交易对（如 BTC/USDT）
        tf: 时间框架（如 H4, H1, M15）
        limit: 返回K线数量上限，默认 500

    Returns:
        K线字典列表，每条包含 timestamp/open/high/low/close/volume
    """
    if not app_state.wyckoff_app:
        return []

    manager = app_state.wyckoff_app.plugin_manager
    data_pipeline = manager.get_plugin("data_pipeline")

    if data_pipeline is None:
        return []

    if not hasattr(data_pipeline, "get_cached_data"):
        return []

    df = data_pipeline.get_cached_data(symbol, tf)

    if df is None or (hasattr(df, "empty") and df.empty):
        return []

    candles: List[Dict[str, Any]] = []
    rows = df.tail(limit) if hasattr(df, "tail") else df

    for idx, row in rows.iterrows():
        candles.append(
            {
                "timestamp": str(idx),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0)),
            }
        )

    return candles


@app.get("/api/system/snapshot")
async def get_system_snapshot() -> Dict[str, Any]:
    """获取系统状态全景快照

    聚合多个插件状态，返回包含引擎状态、持仓、
    进化状态、插件列表等的完整快照。

    Returns:
        系统状态字典，包含 uptime、plugins、orchestrator、
        positions、evolution、wyckoff_engine 等字段
    """
    if not app_state.wyckoff_app:
        return {
            "uptime": 0,
            "plugin_count": 0,
            "plugins": [],
            "orchestrator": None,
            "positions": None,
            "evolution": None,
            "wyckoff_engine": None,
        }

    manager = app_state.wyckoff_app.plugin_manager

    # 计算运行时长
    uptime = 0.0
    if app_state.start_time is not None:
        uptime = time.time() - app_state.start_time

    # 插件列表（通过公共 API）
    plugin_list = []
    for info in manager.list_plugins():
        plugin_list.append(
            {
                "name": info.name,
                "display_name": info.display_name,
                "version": info.version,
                "state": info.state.value,
            }
        )

    # orchestrator 状态
    orchestrator_status: Optional[Dict[str, Any]] = None
    orchestrator = manager.get_plugin("orchestrator")
    if orchestrator is not None:
        if hasattr(orchestrator, "get_system_status"):
            orchestrator_status = orchestrator.get_system_status()

    # 持仓状态
    positions_data: Optional[List[Dict[str, Any]]] = None
    position_mgr = manager.get_plugin("position_manager")
    if position_mgr is not None:
        if hasattr(position_mgr, "get_all_positions"):
            raw_positions = position_mgr.get_all_positions()
            if isinstance(raw_positions, dict):
                positions_data = []
                for sym, pos in raw_positions.items():
                    if hasattr(pos, "to_dict"):
                        positions_data.append(pos.to_dict())
                    else:
                        positions_data.append({"symbol": sym})

    # 进化状态
    evolution_status: Optional[Dict[str, Any]] = None
    evolution = manager.get_plugin("evolution")
    if evolution is not None:
        if hasattr(evolution, "get_evolution_status"):
            evolution_status = evolution.get_evolution_status()

    # 威科夫引擎状态
    engine_state: Optional[Dict[str, Any]] = None
    engine = manager.get_plugin("wyckoff_engine")
    if engine is not None:
        if hasattr(engine, "get_current_state"):
            engine_state = engine.get_current_state()

    return {
        "uptime": round(uptime, 2),
        "is_running": app_state.wyckoff_app.is_running,
        "plugin_count": len(plugin_list),
        "plugins": plugin_list,
        "orchestrator": orchestrator_status,
        "positions": positions_data,
        "evolution": evolution_status,
        "wyckoff_engine": engine_state,
    }


@app.post("/api/config")
async def update_config(
    request: ConfigUpdateRequest,
) -> Dict[str, str]:
    """更新系统配置

    接收 JSON 配置字典，合并更新到全局配置中。

    Args:
        request: 包含 config 字段的请求体

    Returns:
        更新状态字典
    """
    if not app_state.wyckoff_app:
        return {"status": "not_initialized"}

    config_system = app_state.wyckoff_app.config_system
    config_system._global_config.update(request.config)

    return {"status": "updated"}


def _collect_topic_data(
    topic: str,
    manager: Any,
) -> Optional[Dict[str, Any]]:
    """根据主题收集推送数据

    Args:
        topic: 订阅主题名
        manager: PluginManager 实例

    Returns:
        对应主题的数据字典，无数据时返回 None
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    if topic == "candles":
        dp = manager.get_plugin("data_pipeline")
        if dp is not None and hasattr(dp, "get_cached_data"):
            df = dp.get_cached_data("BTC/USDT", "H1")
            if df is not None and hasattr(df, "empty") and not df.empty:
                last = df.iloc[-1]
                return {
                    "type": "candle_update",
                    "data": {
                        "timestamp": str(df.index[-1]),
                        "open": float(last.get("open", 0)),
                        "high": float(last.get("high", 0)),
                        "low": float(last.get("low", 0)),
                        "close": float(last.get("close", 0)),
                        "volume": float(last.get("volume", 0)),
                    },
                    "timestamp": now_iso,
                }

    elif topic == "wyckoff":
        engine = manager.get_plugin("wyckoff_engine")
        if engine is not None and hasattr(engine, "get_current_state"):
            state = engine.get_current_state()
            return {
                "type": "wyckoff_state",
                "data": state,
                "timestamp": now_iso,
            }

    elif topic == "positions":
        pm = manager.get_plugin("position_manager")
        if pm is not None and hasattr(pm, "get_all_positions"):
            raw = pm.get_all_positions()
            pos_list = []
            if isinstance(raw, dict):
                for sym, pos in raw.items():
                    if hasattr(pos, "to_dict"):
                        pos_list.append(pos.to_dict())
                    else:
                        pos_list.append({"symbol": sym})
            return {
                "type": "position_update",
                "data": pos_list,
                "timestamp": now_iso,
            }

    elif topic == "evolution":
        evo = manager.get_plugin("evolution")
        if evo is not None and hasattr(evo, "get_evolution_status"):
            status = evo.get_evolution_status()
            return {
                "type": "evolution_progress",
                "data": status,
                "timestamp": now_iso,
            }

    elif topic == "system_status":
        if app_state.wyckoff_app:
            status = app_state.wyckoff_app.get_status()
            return {
                "type": "system_status",
                "data": status,
                "timestamp": now_iso,
            }

    return None


# 已连接的 WebSocket 客户端集合
_ws_clients: Set[WebSocket] = set()


@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket) -> None:
    """实时数据推送 WebSocket

    支持主题订阅模式，客户端可订阅以下主题：
    candles, wyckoff, positions, evolution, system_status

    客户端消息格式：
        {"type": "subscribe", "topics": ["candles", "wyckoff"]}
        {"type": "ping"}

    服务器每 2 秒按订阅主题推送数据。
    60 秒无消息自动断开。
    """
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(
        "WebSocket 客户端连接, 当前总数: %d",
        len(_ws_clients),
    )

    subscribed_topics: Set[str] = set()
    update_task: Optional[asyncio.Task[None]] = None

    async def periodic_push() -> None:
        """周期性推送订阅数据"""
        while True:
            try:
                if app_state.wyckoff_app and subscribed_topics:
                    manager = app_state.wyckoff_app.plugin_manager
                    for topic in list(subscribed_topics):
                        msg = _collect_topic_data(topic, manager)
                        if msg is not None:
                            await websocket.send_json(msg)
                await asyncio.sleep(2)
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.error("WebSocket 推送异常: %s", exc)
                break

    try:
        update_task = asyncio.create_task(periodic_push())
        _ws_timeout = 60

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=_ws_timeout,
                )
            except asyncio.TimeoutError:
                logger.info("WebSocket 心跳超时，断开连接")
                break

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            elif msg_type == "subscribe":
                topics = msg.get("topics", [])
                valid = {
                    "candles",
                    "wyckoff",
                    "positions",
                    "evolution",
                    "system_status",
                }
                for t in topics:
                    if t in valid:
                        subscribed_topics.add(t)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket 错误: %s", exc)
    finally:
        if update_task is not None:
            update_task.cancel()
        _ws_clients.discard(websocket)
        logger.info(
            "WebSocket 客户端断开, 当前总数: %d",
            len(_ws_clients),
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9527)
