"""FastAPI 应用 - 后端 API 服务

提供 REST API 和 WebSocket 端点，支持前后端分离架构。

系统架构说明：
- 进化盘：使用本地数据，运行 SelfCorrectionWorkflow，通过 run_evolution.py 启动
- 实盘：连接交易所 API，实时数据获取，通过 run_live.py 启动
- API 服务器：提供查询接口，不主动运行交易或进化逻辑
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.app import WyckoffApp

logger = logging.getLogger(__name__)


class AppState:
    """应用状态管理"""
    
    def __init__(self):
        self.wyckoff_app: Optional[WyckoffApp] = None
        self.ws_clients: List[WebSocket] = []
        self._running: bool = False
        self._start_time: Optional[datetime] = None
    
    @property
    def is_running(self) -> bool:
        return self._running and self.wyckoff_app is not None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理
    
    注意：API 服务器只加载插件系统，不主动运行交易或进化逻辑。
    - 进化盘请运行: python run_evolution.py
    - 实盘请运行: python run_live.py
    """
    logger.info("=" * 60)
    logger.info("威科夫全自动逻辑引擎 API 服务启动中...")
    logger.info("=" * 60)
    
    app_state.wyckoff_app = WyckoffApp(config_path="config.yaml")
    app_state.wyckoff_app.discover_and_load()
    app_state._start_time = datetime.now()
    app_state._running = True
    
    logger.info("API Server 启动完成")
    logger.info("")
    logger.info("使用说明:")
    logger.info("  - 进化盘: python run_evolution.py")
    logger.info("  - 实盘:   python run_live.py")
    logger.info("")
    
    yield
    
    logger.info("API Server shutting down...")
    app_state._running = False
    logger.info("API Server 已完全关闭")


app = FastAPI(
    title="Wyckoff Trading Engine API",
    description="威科夫全自动逻辑引擎 API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PositionOpenRequest(BaseModel):
    """开仓请求"""
    symbol: str
    side: str
    size: float
    price: Optional[float] = None
    confidence: Optional[float] = 0.7


class PositionCloseRequest(BaseModel):
    """平仓请求"""
    symbol: str
    reason: str = "manual"


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    config: Dict[str, Any]


class SystemStatusResponse(BaseModel):
    """系统状态响应"""
    is_running: bool
    plugin_count: int
    plugins: Dict[str, str]
    uptime: Optional[str] = None


class PluginInfo(BaseModel):
    """插件信息"""
    name: str
    version: str
    state: str
    description: str


class PositionInfo(BaseModel):
    """持仓信息"""
    symbol: str
    side: str
    size: float
    entry_price: float
    entry_time: str
    stop_loss: float
    take_profit: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class TradeInfo(BaseModel):
    """交易记录"""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    entry_time: str
    exit_time: str


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "Wyckoff Trading Engine API",
        "version": "2.0.0",
        "status": "running" if app_state.is_running else "stopped",
    }


@app.get("/api/system/status", response_model=SystemStatusResponse)
async def get_system_status():
    """获取系统状态"""
    if not app_state.wyckoff_app:
        return SystemStatusResponse(
            is_running=False,
            plugin_count=0,
            plugins={},
        )
    
    status = app_state.wyckoff_app.get_status()
    return SystemStatusResponse(
        is_running=status["is_running"],
        plugin_count=status["plugin_count"],
        plugins=status["plugins"],
    )


@app.post("/api/system/start")
async def start_system():
    """启动交易系统"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    if app_state.wyckoff_app.is_running:
        return {"status": "already_running"}
    
    await app_state.wyckoff_app.start()
    return {"status": "started"}


@app.post("/api/system/stop")
async def stop_system():
    """停止交易系统"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    if not app_state.wyckoff_app.is_running:
        return {"status": "already_stopped"}
    
    await app_state.wyckoff_app.stop()
    return {"status": "stopped"}


@app.get("/api/plugins", response_model=List[PluginInfo])
async def get_plugins():
    """获取插件列表"""
    if not app_state.wyckoff_app:
        return []
    
    plugins = []
    manager = app_state.wyckoff_app.plugin_manager
    
    for name, plugin in manager._plugins.items():
        manifest = manager._manifests.get(name)
        plugins.append(PluginInfo(
            name=name,
            version=manifest.version if manifest else "unknown",
            state=plugin._state.value if hasattr(plugin, '_state') else "unknown",
            description=manifest.description if manifest else "",
        ))
    
    return plugins


@app.get("/api/plugins/{plugin_name}")
async def get_plugin_detail(plugin_name: str):
    """获取插件详情"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    manager = app_state.wyckoff_app.plugin_manager
    
    if plugin_name not in manager._plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    plugin = manager._plugins[plugin_name]
    manifest = manager._manifests.get(plugin_name)
    
    health = plugin.health_check() if hasattr(plugin, 'health_check') else None
    
    return {
        "name": plugin_name,
        "version": manifest.version if manifest else "unknown",
        "description": manifest.description if manifest else "",
        "state": plugin._state.value if hasattr(plugin, '_state') else "unknown",
        "health": health.to_dict() if health else None,
        "config": plugin._config if hasattr(plugin, '_config') else {},
    }


@app.post("/api/plugins/{plugin_name}/enable")
async def enable_plugin(plugin_name: str):
    """启用插件"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    
    if plugin_name not in manager._plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    await manager.activate_plugin(plugin_name)
    return {"status": "enabled", "plugin": plugin_name}


@app.post("/api/plugins/{plugin_name}/disable")
async def disable_plugin(plugin_name: str):
    """禁用插件"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    
    if plugin_name not in manager._plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    await manager.deactivate_plugin(plugin_name)
    return {"status": "disabled", "plugin": plugin_name}


@app.get("/api/positions", response_model=List[PositionInfo])
async def get_positions():
    """获取持仓列表"""
    if not app_state.wyckoff_app:
        return []
    
    manager = app_state.wyckoff_app.plugin_manager
    position_plugin = manager._plugins.get("position_manager")
    
    if not position_plugin:
        return []
    
    positions = position_plugin.get_all_positions() if hasattr(position_plugin, 'get_all_positions') else {}
    
    return [
        PositionInfo(
            symbol=p.symbol,
            side=p.side.value,
            size=p.size,
            entry_price=p.entry_price,
            entry_time=p.entry_time.isoformat(),
            stop_loss=p.stop_loss,
            take_profit=p.take_profit,
            unrealized_pnl=p.unrealized_pnl,
            unrealized_pnl_pct=p.unrealized_pnl_pct,
        )
        for p in positions.values()
    ]


@app.post("/api/positions")
async def open_position(request: PositionOpenRequest):
    """开仓"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    position_plugin = manager._plugins.get("position_manager")
    
    if not position_plugin:
        raise HTTPException(status_code=500, detail="PositionManager plugin not found")
    
    from src.kernel.types import TradingSignal
    from src.plugins.position_manager.types import PositionSide
    
    side = PositionSide.LONG if request.side.lower() == "long" else PositionSide.SHORT
    
    position = position_plugin.open_position(
        symbol=request.symbol,
        side=side,
        size=request.size,
        entry_price=request.price or 0.0,
        signal_confidence=request.confidence,
        wyckoff_state="MANUAL",
        entry_signal=TradingSignal.BUY if side == PositionSide.LONG else TradingSignal.SELL,
    )
    
    if not position:
        raise HTTPException(status_code=400, detail="Failed to open position")
    
    return {"status": "opened", "position": position.to_dict()}


@app.delete("/api/positions/{symbol}")
async def close_position(symbol: str, request: PositionCloseRequest):
    """平仓"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    position_plugin = manager._plugins.get("position_manager")
    
    if not position_plugin:
        raise HTTPException(status_code=500, detail="PositionManager plugin not found")
    
    from src.plugins.position_manager.types import ExitReason
    
    reason = ExitReason.MANUAL
    try:
        reason = ExitReason(request.reason)
    except ValueError:
        pass
    
    position = position_plugin.get_position(symbol)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    result = position_plugin.close_position(
        symbol=symbol,
        exit_price=position.entry_price,
        reason=reason,
    )
    
    if not result:
        raise HTTPException(status_code=400, detail="Failed to close position")
    
    return {"status": "closed", "trade": result.to_dict()}


@app.get("/api/trades", response_model=List[TradeInfo])
async def get_trades(limit: int = 100):
    """获取交易历史"""
    if not app_state.wyckoff_app:
        return []
    
    manager = app_state.wyckoff_app.plugin_manager
    position_plugin = manager._plugins.get("position_manager")
    
    if not position_plugin:
        return []
    
    trades = position_plugin.get_statistics() if hasattr(position_plugin, 'get_statistics') else {}
    history = position_plugin.manager.trade_history if hasattr(position_plugin, 'manager') else []
    
    return [
        TradeInfo(
            symbol=t.symbol,
            side=t.side.value,
            entry_price=t.entry_price,
            exit_price=t.exit_price,
            size=t.size,
            pnl=t.pnl,
            pnl_pct=t.pnl_pct,
            exit_reason=t.exit_reason.value,
            entry_time=t.entry_time.isoformat(),
            exit_time=t.exit_time.isoformat(),
        )
        for t in history[-limit:]
    ]


@app.get("/api/config")
async def get_config():
    """获取配置"""
    if not app_state.wyckoff_app:
        return {}
    
    return app_state.wyckoff_app.config_system._config


@app.put("/api/config")
async def update_config(request: ConfigUpdateRequest):
    """更新配置"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    app_state.wyckoff_app.config_system._config.update(request.config)
    return {"status": "updated"}


@app.get("/api/evolution/status")
async def get_evolution_status():
    """获取进化状态"""
    if not app_state.wyckoff_app:
        return {"status": "not_initialized", "generation": 0, "max_generations": 100, "fitness": 0, "best_fitness": 0, "avg_fitness": 0}
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin:
        return {"status": "plugin_not_found", "generation": 0, "max_generations": 100, "fitness": 0, "best_fitness": 0, "avg_fitness": 0}
    
    return evolution_plugin.get_evolution_status()


@app.get("/api/evolution/state-machine-logs")
async def get_state_machine_logs(limit: int = 50):
    """获取状态机转换日志"""
    if not app_state.wyckoff_app:
        return []
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin or not hasattr(evolution_plugin, 'get_state_machine_logs'):
        return []
    
    return evolution_plugin.get_state_machine_logs(limit)


@app.get("/api/evolution/decision-traces")
async def get_decision_traces(limit: int = 50):
    """获取决策追踪记录"""
    try:
        if not app_state.wyckoff_app:
            return []
        
        manager = app_state.wyckoff_app.plugin_manager
        evolution_plugin = manager._plugins.get("evolution")
        
        if not evolution_plugin:
            return []
        
        if not hasattr(evolution_plugin, 'get_decision_history'):
            return []
        
        result = evolution_plugin.get_decision_history(limit)
        return result if result else []
    except Exception as e:
        logger.error("获取决策追踪失败: %s", e)
        return []


@app.get("/api/evolution/logs")
async def get_evolution_logs(level: str = "all", limit: int = 100):
    """获取进化运行日志"""
    import os
    from pathlib import Path
    
    log_dir = Path("logs")
    if not log_dir.exists():
        return []
    
    logs = []
    log_files = [
        log_dir / "wyckoff_production.log",
        log_dir / "evolution.log",
        log_dir / "errors.log",
    ]
    
    for log_file in log_files:
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[-limit:]
                    for i, line in enumerate(lines):
                        line = line.strip()
                        if line:
                            parts = line.split(' - ', 3)
                            if len(parts) >= 4:
                                logs.append({
                                    "id": f"{log_file.stem}_{i}",
                                    "timestamp": parts[0],
                                    "level": parts[2],
                                    "source": log_file.stem,
                                    "message": parts[3] if len(parts) > 3 else ""
                                })
            except Exception:
                pass
    
    logs.sort(key=lambda x: x["timestamp"], reverse=True)
    logs = logs[:limit]
    
    if level != "all":
        logs = [l for l in logs if l["level"].lower() == level.lower()]
    
    return logs


@app.get("/api/risk/circuit-breakers")
async def get_circuit_breakers():
    """获取熔断器状态"""
    if not app_state.wyckoff_app:
        return []
    
    manager = app_state.wyckoff_app.plugin_manager
    risk_plugin = manager._plugins.get("risk_management")
    
    if not risk_plugin or not hasattr(risk_plugin, 'get_circuit_breakers'):
        return []
    
    return risk_plugin.get_circuit_breakers()


@app.get("/api/risk/metrics")
async def get_risk_metrics():
    """获取风险指标"""
    if not app_state.wyckoff_app:
        return []
    
    manager = app_state.wyckoff_app.plugin_manager
    risk_plugin = manager._plugins.get("risk_management")
    
    if not risk_plugin or not hasattr(risk_plugin, 'get_risk_metrics'):
        return []
    
    return risk_plugin.get_risk_metrics()


@app.get("/api/risk/anomalies")
async def get_anomalies(limit: int = 50):
    """获取异常事件"""
    if not app_state.wyckoff_app:
        return []
    
    manager = app_state.wyckoff_app.plugin_manager
    risk_plugin = manager._plugins.get("risk_management")
    
    if not risk_plugin or not hasattr(risk_plugin, 'get_anomalies'):
        return []
    
    return risk_plugin.get_anomalies(limit)


@app.get("/api/statistics/performance")
async def get_performance(days: int = 7):
    """获取性能统计"""
    if not app_state.wyckoff_app:
        return {"data": [], "labels": []}
    
    manager = app_state.wyckoff_app.plugin_manager
    position_plugin = manager._plugins.get("position_manager")
    
    if not position_plugin or not hasattr(position_plugin, 'get_performance_by_day'):
        return {"data": [], "labels": []}
    
    return position_plugin.get_performance_by_day(days)


@app.post("/api/evolution/start")
async def start_evolution():
    """启动进化系统"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin:
        raise HTTPException(status_code=404, detail="Evolution plugin not found")
    
    if not hasattr(evolution_plugin, 'start_evolution'):
        raise HTTPException(status_code=500, detail="Evolution plugin does not support start_evolution")
    
    return await evolution_plugin.start_evolution()


@app.post("/api/evolution/stop")
async def stop_evolution():
    """停止进化系统"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin:
        raise HTTPException(status_code=404, detail="Evolution plugin not found")
    
    if not hasattr(evolution_plugin, 'stop_evolution'):
        raise HTTPException(status_code=500, detail="Evolution plugin does not support stop_evolution")
    
    return await evolution_plugin.stop_evolution()


@app.get("/api/evolution/positions")
async def get_evolution_positions():
    """获取进化盘持仓"""
    if not app_state.wyckoff_app:
        return []
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin or not hasattr(evolution_plugin, 'get_positions'):
        return []
    
    return evolution_plugin.get_positions()


@app.get("/api/evolution/positions/{position_id}")
async def get_evolution_position(position_id: str):
    """获取单个进化盘持仓"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=404, detail="Position not found")
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin or not hasattr(evolution_plugin, 'get_position'):
        raise HTTPException(status_code=404, detail="Position not found")
    
    position = evolution_plugin.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    return position


@app.post("/api/evolution/positions")
async def add_evolution_position(request: PositionOpenRequest):
    """添加进化盘持仓"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin or not hasattr(evolution_plugin, 'add_position'):
        raise HTTPException(status_code=500, detail="Evolution plugin not found")
    
    position_data = {
        "symbol": request.symbol,
        "side": request.side,
        "size": request.size,
        "entry_price": request.price or 0.0,
        "confidence": request.confidence,
        "wyckoff_state": "MANUAL",
    }
    
    return evolution_plugin.add_position(position_data)


@app.delete("/api/evolution/positions/{position_id}")
async def close_evolution_position(position_id: str, exit_price: float = 0.0, reason: str = "manual"):
    """平仓进化盘持仓"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin or not hasattr(evolution_plugin, 'close_position'):
        raise HTTPException(status_code=500, detail="Evolution plugin not found")
    
    trade = evolution_plugin.close_position(
        position_id=position_id,
        exit_price=exit_price,
        exit_reason=reason,
    )
    
    if not trade:
        raise HTTPException(status_code=404, detail="Position not found")
    
    return {"status": "closed", "trade": trade}


@app.get("/api/evolution/trades")
async def get_evolution_trades(limit: int = 100):
    """获取进化盘交易历史"""
    if not app_state.wyckoff_app:
        return []
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin or not hasattr(evolution_plugin, 'get_trades'):
        return []
    
    return evolution_plugin.get_trades(limit)


@app.get("/api/evolution/statistics")
async def get_evolution_statistics():
    """获取进化盘统计信息"""
    if not app_state.wyckoff_app:
        return {}
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin or not hasattr(evolution_plugin, 'get_evolution_statistics'):
        return {}
    
    return evolution_plugin.get_evolution_statistics()


@app.delete("/api/evolution/data")
async def clear_evolution_data():
    """清空进化盘数据"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    manager = app_state.wyckoff_app.plugin_manager
    evolution_plugin = manager._plugins.get("evolution")
    
    if not evolution_plugin or not hasattr(evolution_plugin, 'clear_evolution_data'):
        raise HTTPException(status_code=500, detail="Evolution plugin not found")
    
    evolution_plugin.clear_evolution_data()
    return {"status": "cleared"}


@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    """实时数据推送 WebSocket - 统一推送所有数据"""
    await websocket.accept()
    app_state.ws_clients.append(websocket)
    logger.info(f"WebSocket client connected, total clients: {len(app_state.ws_clients)}")
    
    update_task = None
    
    try:
        async def send_periodic_updates():
            while True:
                try:
                    if app_state.wyckoff_app:
                        status = app_state.wyckoff_app.get_status()
                        await websocket.send_json({
                            "type": "system_status",
                            "data": {
                                "is_running": status["is_running"],
                                "plugin_count": status["plugin_count"],
                                "plugins": status["plugins"],
                            },
                            "timestamp": datetime.now().isoformat(),
                        })
                        
                        manager = app_state.wyckoff_app.plugin_manager
                        
                        plugins_data = []
                        for name, plugin in manager._plugins.items():
                            manifest = manager._manifests.get(name)
                            plugins_data.append({
                                "name": name,
                                "version": manifest.version if manifest else "unknown",
                                "state": plugin._state.value if hasattr(plugin, '_state') else "unknown",
                                "description": manifest.description if manifest else "",
                            })
                        await websocket.send_json({
                            "type": "plugins",
                            "data": plugins_data,
                            "timestamp": datetime.now().isoformat(),
                        })
                        
                        position_plugin = manager._plugins.get("position_manager")
                        if position_plugin and hasattr(position_plugin, 'get_all_positions'):
                            positions = position_plugin.get_all_positions()
                            positions_data = [
                                {
                                    "symbol": p.symbol,
                                    "side": p.side.value,
                                    "size": p.size,
                                    "entry_price": p.entry_price,
                                    "entry_time": p.entry_time.isoformat(),
                                    "stop_loss": p.stop_loss,
                                    "take_profit": p.take_profit,
                                    "unrealized_pnl": p.unrealized_pnl,
                                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                                }
                                for p in positions.values()
                            ]
                            await websocket.send_json({
                                "type": "positions",
                                "data": positions_data,
                                "timestamp": datetime.now().isoformat(),
                            })
                            
                            if hasattr(position_plugin, 'manager'):
                                history = position_plugin.manager.trade_history[-50:]
                                trades_data = [
                                    {
                                        "symbol": t.symbol,
                                        "side": t.side.value,
                                        "entry_price": t.entry_price,
                                        "exit_price": t.exit_price,
                                        "size": t.size,
                                        "pnl": t.pnl,
                                        "pnl_pct": t.pnl_pct,
                                        "exit_reason": t.exit_reason.value,
                                        "entry_time": t.entry_time.isoformat(),
                                        "exit_time": t.exit_time.isoformat(),
                                    }
                                    for t in history
                                ]
                                await websocket.send_json({
                                    "type": "trades",
                                    "data": trades_data,
                                    "timestamp": datetime.now().isoformat(),
                                })
                        
                        evolution_plugin = manager._plugins.get("evolution")
                        if evolution_plugin and hasattr(evolution_plugin, 'get_evolution_status'):
                            try:
                                evo_status = evolution_plugin.get_evolution_status()
                                await websocket.send_json({
                                    "type": "evolution_status",
                                    "data": evo_status,
                                    "timestamp": datetime.now().isoformat(),
                                })
                            except Exception as e:
                                logger.debug(f"Failed to get evolution status: {e}")
                    
                    await asyncio.sleep(2)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error sending periodic update: {e}")
                    await asyncio.sleep(5)
        
        update_task = asyncio.create_task(send_periodic_updates())
        
        while True:
            data = await websocket.receive_text()
            try:
                import json
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
            except:
                pass
                
    except WebSocketDisconnect:
        if update_task:
            update_task.cancel()
        if websocket in app_state.ws_clients:
            app_state.ws_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected, total clients: {len(app_state.ws_clients)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if update_task:
            update_task.cancel()
        if websocket in app_state.ws_clients:
            app_state.ws_clients.remove(websocket)


@app.websocket("/ws/positions")
async def websocket_positions(websocket: WebSocket):
    """持仓实时更新 WebSocket"""
    await websocket.accept()
    app_state.ws_clients.append(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "data": data})
    except WebSocketDisconnect:
        app_state.ws_clients.remove(websocket)


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """日志实时流 WebSocket"""
    await websocket.accept()
    app_state.ws_clients.append(websocket)
    
    try:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json({
                "type": "log",
                "timestamp": datetime.now().isoformat(),
                "message": "System running...",
            })
    except WebSocketDisconnect:
        app_state.ws_clients.remove(websocket)


async def broadcast_event(event_type: str, data: Dict[str, Any]):
    """广播事件到所有 WebSocket 客户端"""
    message = {"type": event_type, "data": data, "timestamp": datetime.now().isoformat()}
    
    for client in app_state.ws_clients:
        try:
            await client.send_json(message)
        except Exception:
            app_state.ws_clients.remove(client)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9527)
