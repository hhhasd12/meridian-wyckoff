"""FastAPI 应用 - 威科夫交易引擎后端 API

提供 22 个 REST 端点和 1 个 WebSocket 端点：
- GET /api/candles/{symbol}/{tf} — 历史K线数据
- GET /api/system/snapshot — 系统状态快照
- GET /api/wyckoff/state — V4 状态机完整状态（三层语义+原则分数+边界）
- GET /api/evolution/results — 进化结果历史
- GET /api/evolution/latest — 最新进化结果
- GET /api/backtest/{cycle_index}/detail — 回测详情
- POST /api/analyze — 状态机逐bar分析（含V4原则分数+假设）
- POST /api/evolution/start — 启动进化流程
- POST /api/evolution/stop — 停止进化流程
- GET /api/trades — 交易历史
- GET /api/decisions — 决策历史
- GET /api/advisor/latest — AI 顾问最新分析
- POST /api/config — 更新配置
- POST /api/annotations — 创建威科夫标注
- GET /api/annotations?symbol=&timeframe= — 获取标注列表
- DELETE /api/annotations/{id}?symbol=&timeframe= — 删除标注
- GET /api/annotations/auto-compare — 增量标注自动对比结果
- GET /api/annotations/compare — 对比标注与检测结果
- GET /api/annotations/suggestions — 获取修改建议列表
- POST /api/annotations/suggestions/{id}/apply — 应用参数修改建议
- POST /api/annotations/chat — 标注诊断对话（AI分析）
- GET /api/annotations/chat/history — 获取对话历史
- DELETE /api/annotations/chat/history — 清空对话历史
- GET /api/annotations/knowledge — 搜索/统计检测器知识库
- POST /api/annotations/knowledge — 添加检测器知识规则
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

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

from src.app import WyckoffApp

logger = logging.getLogger(__name__)


class AppState:
    """应用全局状态"""

    def __init__(self) -> None:
        self.wyckoff_app: Optional[WyckoffApp] = None
        self.start_time: Optional[float] = None
        self._last_analysis: Optional[Dict[str, Any]] = None

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

    # 优雅关闭：如果进化正在运行，保存 checkpoint
    if app_state.wyckoff_app:
        manager = app_state.wyckoff_app.plugin_manager
        evolution = manager.get_plugin("evolution")
        if evolution is not None and getattr(evolution, "_is_evolving", False):
            logger.info("进化正在运行，保存 checkpoint...")
            if hasattr(evolution, "_save_checkpoint"):
                evolution._save_checkpoint()  # type: ignore[union-attr]
            logger.info("Checkpoint 已保存，下次启动可恢复")

    app_state.wyckoff_app = None
    app_state.start_time = None
    logger.info("API Server 已完全关闭")


app = FastAPI(
    title="Wyckoff Trading Engine API",
    description="威科夫全自动逻辑引擎 API",
    version="3.0.0",
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

# ---------------------------------------------------------------------------
# Bearer Token 认证中间件
# ---------------------------------------------------------------------------
# 从环境变量 WYCKOFF_API_TOKEN 读取 token
# - 设置了 token: POST/PUT/DELETE 请求需要 Authorization: Bearer {token}
# - GET/WebSocket 请求不需要认证（只读）
# - 未设置环境变量: 跳过认证（开发模式）
_api_token = os.environ.get("WYCKOFF_API_TOKEN", "")


@app.middleware("http")
async def bearer_token_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
    """简单 Bearer Token 认证 — 仅拦截写操作"""
    if _api_token and request.method in ("POST", "PUT", "DELETE"):
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {_api_token}":
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing Bearer token"},
            )
    return await call_next(request)


class ConfigUpdateRequest(BaseModel):
    """配置更新请求体"""

    config: Dict[str, Any]


@app.get("/api/candles/{symbol:path}/{tf}")
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

    df = getattr(data_pipeline, "get_cached_data")(symbol, tf)

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
            orchestrator_status = getattr(orchestrator, "get_system_status")()

    # 持仓状态
    positions_data: Optional[List[Dict[str, Any]]] = None
    position_mgr = manager.get_plugin("position_manager")
    if position_mgr is not None:
        if hasattr(position_mgr, "get_all_positions"):
            raw_positions = getattr(position_mgr, "get_all_positions")()
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
            evolution_status = getattr(evolution, "get_evolution_status")()

    # 威科夫引擎状态
    engine_state: Optional[Dict[str, Any]] = None
    engine = manager.get_plugin("wyckoff_engine")
    if engine is not None:
        if hasattr(engine, "get_current_state"):
            engine_state = getattr(engine, "get_current_state")()

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


# ── V4 状态机专用 API ──


@app.get("/api/wyckoff/state")
async def get_wyckoff_v4_state() -> Dict[str, Any]:
    """获取 V4 状态机完整状态 — 轻量专用端点

    返回每个时间框架的状态机数据，包含：
    - 三层语义（phase / last_confirmed_event / hypothesis）
    - 三大原则分数（supply_demand / cause_effect / effort_result）
    - BarFeatures 快照（volume_ratio / body_ratio 等）
    - 关键价位边界（SC_LOW / AR_HIGH 等）
    - 最近证据链

    Returns:
        {state_machines: {H4: {...}, ...}, bar_index: int}
    """
    if not app_state.wyckoff_app:
        return {"state_machines": {}, "bar_index": 0}

    manager = app_state.wyckoff_app.plugin_manager
    engine = manager.get_plugin("wyckoff_engine")
    if engine is None or not hasattr(engine, "get_current_state"):
        return {"state_machines": {}, "bar_index": 0}

    state = getattr(engine, "get_current_state")()
    if state is None:
        return {"state_machines": {}, "bar_index": 0}

    return state


# ── 进化结果 API ──


@app.get("/api/evolution/results")
async def get_evolution_results() -> Dict[str, Any]:
    """读取进化结果 — 从 data/evolution_results.json

    Returns:
        {"cycles": [...], "total": int}
    """
    results_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "evolution_results.json",
    )

    cycles: List[Dict[str, Any]] = []
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    cycles = json.loads(content)
        except Exception as e:
            logger.warning("进化结果文件读取失败: %s", e)

    return {"cycles": cycles, "total": len(cycles)}


@app.get("/api/evolution/latest")
async def get_evolution_latest() -> Dict[str, Any]:
    """返回最新一个 cycle 的详细信息

    Returns:
        最新 cycle 数据或 {"cycle": null}
    """
    results_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "evolution_results.json",
    )

    if not os.path.exists(results_path):
        return {"cycle": None, "total": 0}

    try:
        with open(results_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"cycle": None, "total": 0}
            cycles = json.loads(content)
            if not cycles:
                return {"cycle": None, "total": 0}
            return {"cycle": cycles[-1], "total": len(cycles)}
    except Exception as e:
        logger.warning("最新进化周期读取失败: %s", e)
        return {"cycle": None, "total": 0}


@app.get("/api/backtest/{cycle_index}/detail")
async def get_backtest_detail(cycle_index: int) -> Dict[str, Any]:
    """获取指定 cycle 的回测详情（trades + equity_curve + 威科夫阶段）

    Args:
        cycle_index: cycle 索引（0-based），-1 表示最新

    Returns:
        {"backtest_detail": {...}, "cycle": int} 或 {"error": "..."}
    """
    results_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "evolution_results.json",
    )

    if not os.path.exists(results_path):
        return {"error": "进化结果文件不存在", "backtest_detail": None}

    try:
        with open(results_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"error": "进化结果文件为空", "backtest_detail": None}
            cycles = json.loads(content)

        if not cycles:
            return {"error": "无进化记录", "backtest_detail": None}

        # -1 表示最新
        if cycle_index == -1:
            cycle_index = len(cycles) - 1

        if cycle_index < 0 or cycle_index >= len(cycles):
            return {
                "error": f"cycle_index {cycle_index} 超出范围 [0, {len(cycles) - 1}]",
                "backtest_detail": None,
            }

        cycle_data = cycles[cycle_index]
        detail = cycle_data.get("backtest_detail")

        return {
            "cycle": cycle_data.get("cycle", cycle_index),
            "generation": cycle_data.get("generation"),
            "best_fitness": cycle_data.get("best_fitness"),
            "adopted": cycle_data.get("adopted"),
            "backtest_detail": detail,
            "total_cycles": len(cycles),
        }

    except Exception as e:
        logger.warning("回测详情读取失败: %s", e)
        return {"error": str(e), "backtest_detail": None}


class AnalyzeRequest(BaseModel):
    symbol: str = "ETHUSDT"
    timeframe: str = "H4"
    bars: int = 2000  # 分析最近N根K线（默认2000，覆盖更多历史）


# ---- 分析结果缓存（T2.4）----
class _AnalysisCache:
    """分析结果缓存 — 以最后K线时间戳做key，数据不变不重算"""

    def __init__(self) -> None:
        self._key: Optional[str] = None
        self._result: Optional[Dict[str, Any]] = None

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if self._key == key:
            return self._result
        return None

    def set(self, key: str, result: Dict[str, Any]) -> None:
        self._key = key
        self._result = result


_analysis_cache = _AnalysisCache()


def _sync_analyze(
    data: Dict[str, Any],
    symbol: str,
    n_bars: int,
    config: Dict[str, Any],
    request_timeframe: str = "H4",
) -> Dict[str, Any]:
    """同步CPU密集分析 — 在线程池中运行（T2.2）

    内含 searchsorted 向量化预计算（T2.3）：
    对每个TF只做一次 searchsorted(primary.index)，得到完整映射数组，
    循环内直接查表，从 n_bars*5次 searchsorted → 5次。
    """
    import numpy as np
    import pandas as pd

    from src.plugins.wyckoff_engine.engine import WyckoffEngine

    # 使用请求的 timeframe 作为主时间框架，不存在时 fallback 到 H4
    tf_key = request_timeframe if request_timeframe in data else "H4"
    h4 = data[tf_key]
    engine = WyckoffEngine(config)
    warmup = 50

    # --- T2.3: 预计算各TF的索引映射（向量化 searchsorted）---
    # 对每个TF，计算 h4.index 中每个时间点在该TF中的 searchsorted 位置
    max_bars_tf = {"D1": 200, "H4": 500, "H1": 500, "M15": 500, "M5": 500}
    tf_index_maps: Dict[str, np.ndarray] = {}
    for tf_name, tf_df in data.items():
        if not isinstance(tf_df, pd.DataFrame):
            continue
        # 一次性计算所有 h4 时间点在此 TF 中的右侧位置
        tf_index_maps[tf_name] = tf_df.index.searchsorted(
            h4.index[:n_bars], side="right"
        )

    # --- 逐bar处理 ---
    bar_details: list = []

    for i in range(n_bars):
        bar_data: Dict[str, pd.DataFrame] = {}
        for tf_name, tf_df in data.items():
            if tf_name not in tf_index_maps:
                continue
            pos = int(tf_index_maps[tf_name][i])
            if pos < 10:
                continue
            start = max(0, pos - max_bars_tf.get(tf_name, 500))
            bar_data[tf_name] = tf_df.iloc[start:pos]

        if not bar_data:
            continue

        bar_signal = engine.process_bar(symbol, bar_data)

        if i >= warmup:
            # 提取V4信息
            v4_data: Dict[str, Any] = {}
            primary_sm = engine._state_machines.get(tf_key)
            if primary_sm is not None:
                scorer = getattr(primary_sm, "_scorer", None)
                last_features = (
                    getattr(scorer, "_last_features", None) if scorer else None
                )
                if last_features is not None:
                    v4_data["pr"] = {
                        "sd": round(last_features.supply_demand, 3),
                        "ce": round(last_features.cause_effect, 3),
                        "er": round(last_features.effort_result, 3),
                    }
                    v4_data["bf"] = {
                        "vr": round(last_features.volume_ratio, 3),
                        "br": round(last_features.body_ratio, 3),
                        "sa": last_features.is_stopping_action,
                    }

                hyp = getattr(primary_sm, "active_hypothesis", None)
                if hyp is not None:
                    v4_data["hyp"] = {
                        "e": hyp.event_name,
                        "st": hyp.status.value if hyp.status else None,
                        "c": round(hyp.confidence, 3),
                        "bh": hyp.bars_held,
                        "cq": round(hyp.confirmation_quality, 3),
                    }

                lce = getattr(primary_sm, "last_confirmed_event", None)
                if lce is not None:
                    v4_data["lce"] = lce

            detail = {
                "bar_index": i,
                "timestamp": str(h4.index[i]),
                "p": bar_signal.phase,
                "s": bar_signal.wyckoff_state,
                "c": round(float(bar_signal.confidence), 3),
                "ts": (
                    round(float(bar_signal.tr_support), 2)
                    if bar_signal.tr_support is not None
                    else None
                ),
                "tr": (
                    round(float(bar_signal.tr_resistance), 2)
                    if bar_signal.tr_resistance is not None
                    else None
                ),
                "tc": (
                    round(float(bar_signal.tr_confidence), 3)
                    if bar_signal.tr_confidence is not None
                    else None
                ),
                "mr": bar_signal.market_regime,
                "d": bar_signal.direction,
                "ss": bar_signal.signal_strength,
                "sc": bar_signal.state_changed,
                "sig": bar_signal.signal.value,
                "cl": (
                    {
                        k: round(float(v), 2)
                        for k, v in bar_signal.critical_levels.items()
                    }
                    if bar_signal.critical_levels
                    else {}
                ),
                **v4_data,
            }
            bar_details.append(detail)

    # 构建 K线 OHLCV 数据
    candles_out: List[Dict[str, Any]] = []
    for i in range(warmup, n_bars):
        if i >= len(h4):
            break
        row = h4.iloc[i]
        candles_out.append(
            {
                "timestamp": str(h4.index[i]),
                "open": round(float(row["open"]), 6),
                "high": round(float(row["high"]), 6),
                "low": round(float(row["low"]), 6),
                "close": round(float(row["close"]), 6),
                "volume": round(float(row["volume"]), 2),
            }
        )

    return {
        "symbol": symbol,
        "timeframe": tf_key,
        "total_bars": len(bar_details),
        "warmup_bars": warmup,
        "bar_details": bar_details,
        "candles": candles_out,
    }


@app.post("/api/analyze")
async def analyze_state_machine(request: AnalyzeRequest) -> Dict[str, Any]:
    """逐bar状态机分析 — 不依赖进化，直接用当前配置跑

    优化（T2.2+T2.3+T2.4）：
    - CPU密集计算放到线程池（run_in_executor），不阻塞事件循环
    - 各TF searchsorted 向量化预计算（n_bars*5次→5次）
    - 分析结果缓存（数据不变不重算）
    """
    import pandas as pd

    # 加载数据
    data = _load_evolution_data_for_api(symbol=request.symbol)
    if not data or request.timeframe not in data:
        # fallback: 如果请求的 timeframe 不在数据中，检查 H4
        if not data or "H4" not in data:
            return {
                "error": "数据文件缺失，请先运行 python fetch_data.py",
                "bar_details": [],
            }

    tf_key = request.timeframe if request.timeframe in data else "H4"
    h4 = data.get(tf_key)
    if h4 is None or not isinstance(h4, pd.DataFrame) or len(h4) < 60:
        return {"error": f"{tf_key} 数据不足", "bar_details": []}

    n_bars = min(request.bars, len(h4))

    # T2.4: 缓存检查 — 以 symbol+timeframe+最后K线时间+bars数做key
    cache_key = f"{request.symbol}_{tf_key}_{str(h4.index[-1])}_{n_bars}"
    cached = _analysis_cache.get(cache_key)
    if cached is not None:
        logger.info("分析缓存命中: %s", cache_key)
        app_state._last_analysis = cached
        return cached

    # 获取引擎配置
    config: Dict[str, Any] = {}
    if app_state.wyckoff_app:
        manager = app_state.wyckoff_app.plugin_manager
        engine_plugin = manager.get_plugin("wyckoff_engine")
        if engine_plugin and hasattr(engine_plugin, "_engine"):
            _engine = getattr(engine_plugin, "_engine", None)
            if _engine is not None:
                config = getattr(_engine, "config", {})

    # T2.2: CPU密集计算放到线程池
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _sync_analyze, data, request.symbol, n_bars, config, request.timeframe
    )

    # T2.4: 写入缓存
    _analysis_cache.set(cache_key, result)

    # 缓存供诊断对话使用
    app_state._last_analysis = result

    return result


class EvolutionStartRequest(BaseModel):
    max_cycles: int = 10


@app.post("/api/evolution/start")
async def start_evolution(request: EvolutionStartRequest) -> Dict[str, Any]:
    """启动进化流程

    自动加载 data/ETHUSDT_*.csv 数据并注入到进化插件。
    """
    if not app_state.wyckoff_app:
        return {"status": "not_initialized"}
    manager = app_state.wyckoff_app.plugin_manager
    evolution = manager.get_plugin("evolution")
    if evolution is None or not hasattr(evolution, "start_evolution"):
        return {"status": "error", "message": "evolution plugin not available"}

    # 自动加载数据（如果尚未设置）
    if not getattr(evolution, "_data_dict", None):
        data = _load_evolution_data_for_api()
        if not data or "H4" not in data:
            return {
                "status": "error",
                "message": "数据文件缺失，请先运行 python fetch_data.py",
            }
        getattr(evolution, "set_data")(data)
        logger.info("API 模式：已加载进化数据")

    result = await getattr(evolution, "start_evolution")(max_cycles=request.max_cycles)
    return result


def _load_evolution_data_for_api(symbol: str = "ETHUSDT") -> Dict[str, Any]:
    """为 API 模式加载进化数据

    Args:
        symbol: 交易对（如 ETHUSDT/BTCUSDT），用于匹配 CSV 文件名
    """
    import pandas as pd

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    # 时间框架到文件后缀的映射
    tf_suffix_map = {
        "D1": "1d",
        "H4": "4h",
        "H1": "1h",
        "M15": "15m",
        "M5": "5m",
    }

    col_rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    data: Dict[str, Any] = {}
    for tf, suffix in tf_suffix_map.items():
        # 优先用请求的 symbol，fallback 到 ETHUSDT
        csv_path = os.path.join(project_root, "data", f"{symbol}_{suffix}.csv")
        if not os.path.exists(csv_path) and symbol != "ETHUSDT":
            csv_path = os.path.join(project_root, "data", f"ETHUSDT_{suffix}.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            df = df.rename(columns=col_rename)
            core = [
                c for c in ["open", "high", "low", "close", "volume"] if c in df.columns
            ]
            if core:
                data[tf] = df[core]
                logger.info("API 进化数据加载: %s = %d bars", tf, len(df))
    return data


@app.post("/api/evolution/stop")
async def stop_evolution() -> Dict[str, Any]:
    """停止进化流程"""
    if not app_state.wyckoff_app:
        return {"status": "not_initialized"}
    manager = app_state.wyckoff_app.plugin_manager
    evolution = manager.get_plugin("evolution")
    if evolution is None or not hasattr(evolution, "stop_evolution"):
        return {"status": "error", "message": "evolution plugin not available"}
    result = await getattr(evolution, "stop_evolution")()
    return result


@app.get("/api/decisions")
async def get_decision_history() -> Dict[str, Any]:
    """获取决策历史"""
    if not app_state.wyckoff_app:
        return {"decisions": [], "total": 0}
    manager = app_state.wyckoff_app.plugin_manager
    orchestrator = manager.get_plugin("orchestrator")
    if orchestrator is None or not hasattr(orchestrator, "get_decision_history"):
        return {"decisions": [], "total": 0}
    decisions = getattr(orchestrator, "get_decision_history")(limit=50)
    return {"decisions": decisions, "total": len(decisions)}


@app.get("/api/evolution/config")
async def get_evolution_config() -> Dict[str, Any]:
    """获取当前进化配置（GA参数）"""
    if not app_state.wyckoff_app:
        return {"config": {}}
    manager = app_state.wyckoff_app.plugin_manager
    evolution = manager.get_plugin("evolution")
    if evolution is None or not hasattr(evolution, "get_current_config"):
        return {"config": {}}
    config = getattr(evolution, "get_current_config")()
    return {"config": config}


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
            # 附加最新交易信号供 SignalPanel 使用
            # 信号来自 orchestrator 的决策历史（orchestrator 持有真正的引擎实例）
            latest_signal = None
            orchestrator = manager.get_plugin("orchestrator")
            if orchestrator is not None and hasattr(
                orchestrator, "get_decision_history"
            ):
                try:
                    history = orchestrator.get_decision_history(limit=1)
                    if history:
                        latest_signal = history[-1]
                except Exception:
                    pass
            data: Dict[str, Any] = {
                "type": "wyckoff_state",
                "data": state,
                "timestamp": now_iso,
            }
            if latest_signal is not None:
                data["data"] = {
                    **(state if isinstance(state, dict) else {}),
                    "latest_signal": latest_signal,
                }
            return data

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
            # 附加最近日志供 LogsTab 使用
            recent_logs: List[Dict[str, Any]] = []
            audit = manager.get_plugin("audit_logger")
            if audit is not None and hasattr(audit, "get_recent_logs"):
                try:
                    raw_logs = audit.get_recent_logs(limit=20)
                    if isinstance(raw_logs, list):
                        recent_logs = raw_logs
                except Exception:
                    pass
            result_data: Dict[str, Any] = (
                status if isinstance(status, dict) else {"raw": status}
            )
            result_data["recent_logs"] = recent_logs
            return {
                "type": "system_status",
                "data": result_data,
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

    心跳机制：
        - 服务端每 15 秒主动发送 {"type": "ping"} 给客户端
        - 客户端可回 pong 或自身 ping（均视为活跃）
        - 90 秒无任何双向活动才判定连接死亡并断开
        - 服务端推送数据（send_json）成功也视为活跃信号

    服务器每 2 秒按订阅主题推送数据。
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
        nonlocal last_activity
        while True:
            try:
                if app_state.wyckoff_app and subscribed_topics:
                    manager = app_state.wyckoff_app.plugin_manager
                    for topic in list(subscribed_topics):
                        msg = _collect_topic_data(topic, manager)
                        if msg is not None:
                            await websocket.send_json(msg)
                            last_activity = time.time()
                await asyncio.sleep(2)
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.error("WebSocket 推送异常: %s", exc)
                break

    # ── 服务端主动心跳 ──
    # 浏览器后台标签页会节流 JS 定时器（setInterval 降频到 ≥60s），
    # 导致客户端 ping 无法按时到达。改为服务端主动 ping，
    # 并用 last_activity 追踪双向活跃，避免依赖 receive_text timeout。
    _ping_interval = 15  # 服务端每 15 秒发一次 ping
    _activity_timeout = 90  # 90 秒无任何活动才判定死连接
    last_activity = time.time()

    async def server_ping() -> None:
        """服务端主动发送心跳 ping"""
        nonlocal last_activity
        while True:
            try:
                await asyncio.sleep(_ping_interval)
                if websocket.client_state.name != "CONNECTED":
                    break
                await websocket.send_json(
                    {
                        "type": "ping",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                # send 成功本身说明连接存活
                last_activity = time.time()
            except Exception:
                break

    async def activity_watchdog() -> None:
        """监控连接活跃度，超时则关闭"""
        while True:
            await asyncio.sleep(_ping_interval)
            if time.time() - last_activity > _activity_timeout:
                logger.info("WebSocket 连接不活跃 %ds，断开", _activity_timeout)
                try:
                    await websocket.close(code=1000)
                except Exception:
                    pass
                break

    ping_task: Optional[asyncio.Task[None]] = None
    watchdog_task: Optional[asyncio.Task[None]] = None

    try:
        update_task = asyncio.create_task(periodic_push())
        ping_task = asyncio.create_task(server_ping())
        watchdog_task = asyncio.create_task(activity_watchdog())

        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break

            last_activity = time.time()

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
            elif msg_type == "pong":
                # 客户端回应服务端 ping，仅更新活跃时间
                pass
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
        for t in (update_task, ping_task, watchdog_task):
            if t is not None:
                t.cancel()
        _ws_clients.discard(websocket)
        logger.info(
            "WebSocket 客户端断开, 当前总数: %d",
            len(_ws_clients),
        )


# ── 交易历史 API ──


@app.get("/api/trades")
async def get_trades() -> Dict[str, Any]:
    """获取交易历史

    从 position_manager 插件读取已平仓交易记录。

    Returns:
        {"trades": [...]} 交易记录列表
    """
    if not app_state.wyckoff_app:
        return {"trades": []}

    manager = app_state.wyckoff_app.plugin_manager
    pm = manager.get_plugin("position_manager")

    if pm is None:
        return {"trades": []}

    try:
        if hasattr(pm, "get_closed_trades"):
            trades = getattr(pm, "get_closed_trades")()
            return {"trades": trades}
        elif hasattr(pm, "_trade_journal"):
            journal = getattr(pm, "_trade_journal")
            return {"trades": journal if journal else []}
        return {"trades": []}
    except Exception as e:
        logger.warning("获取交易历史失败: %s", e)
        return {"trades": []}


# ── 进化顾问 API ──


@app.get("/api/advisor/latest")
async def get_advisor_latest() -> Dict[str, Any]:
    """获取最新的 AI 顾问分析结果

    从 evolution_advisor 插件获取最近一次分析。
    插件不存在或无数据时安全回退。

    Returns:
        {"analysis": dict|null, "status": str}
    """
    if not app_state.wyckoff_app:
        return {"analysis": None, "status": "not_initialized"}

    manager = app_state.wyckoff_app.plugin_manager
    advisor = manager.get_plugin("evolution_advisor")

    if advisor is None:
        return {"analysis": None, "status": "plugin_not_found"}

    if not hasattr(advisor, "get_last_analysis"):
        return {"analysis": None, "status": "no_method"}

    try:
        analysis = getattr(advisor, "get_last_analysis")()
        if analysis is None:
            return {"analysis": None, "status": "no_data"}
        return {"analysis": analysis, "status": "ok"}
    except Exception as e:
        logger.warning("获取顾问分析失败: %s", e)
        return {"analysis": None, "status": "error"}


# ========== 标注 API ==========


@app.post("/api/annotations")
async def create_annotation(request: Request) -> Dict[str, Any]:
    """创建威科夫标注"""
    if not app_state.wyckoff_app:
        return {"error": "System not initialized"}
    body = await request.json()
    manager = app_state.wyckoff_app.plugin_manager
    annotation_plugin = manager.get_plugin("annotation")
    if annotation_plugin is None:
        return {"error": "Annotation plugin not loaded"}
    if not hasattr(annotation_plugin, "create_annotation"):
        return {"error": "Annotation plugin missing create_annotation method"}
    try:
        result = annotation_plugin.create_annotation(body)
        return {"success": True, "annotation": result}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/annotations")
async def get_annotations(symbol: str = "", timeframe: str = "") -> Dict[str, Any]:
    """获取标注列表"""
    if not app_state.wyckoff_app:
        return {"annotations": []}
    if not symbol or not timeframe:
        return {"error": "symbol and timeframe are required"}
    manager = app_state.wyckoff_app.plugin_manager
    annotation_plugin = manager.get_plugin("annotation")
    if annotation_plugin is None:
        return {"annotations": []}
    if not hasattr(annotation_plugin, "get_annotations"):
        return {"annotations": []}
    annotations = annotation_plugin.get_annotations(symbol, timeframe)
    return {"annotations": annotations}


@app.delete("/api/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: str, symbol: str = "", timeframe: str = ""
) -> Dict[str, Any]:
    """删除标注"""
    if not app_state.wyckoff_app:
        return {"error": "System not initialized"}
    if not symbol or not timeframe:
        return {"error": "symbol and timeframe are required"}
    manager = app_state.wyckoff_app.plugin_manager
    annotation_plugin = manager.get_plugin("annotation")
    if annotation_plugin is None:
        return {"error": "Annotation plugin not loaded"}
    if not hasattr(annotation_plugin, "delete_annotation"):
        return {"error": "Annotation plugin missing delete_annotation method"}
    success = annotation_plugin.delete_annotation(annotation_id, symbol, timeframe)
    return {"success": success}


@app.get("/api/annotations/compare")
async def compare_annotations(symbol: str = "", timeframe: str = "") -> Dict[str, Any]:
    """对比标注和状态机检测结果"""
    if not app_state.wyckoff_app or not symbol or not timeframe:
        return {"error": "symbol and timeframe required"}
    manager = app_state.wyckoff_app.plugin_manager
    annotation_plugin = manager.get_plugin("annotation")
    engine_plugin = manager.get_plugin("wyckoff_engine")
    if annotation_plugin is None or engine_plugin is None:
        return {"error": "Required plugins not loaded"}
    # 获取状态机转换历史
    state = (
        engine_plugin.get_current_state()
        if hasattr(engine_plugin, "get_current_state")
        else {}
    )
    transition_history = state.get("transition_history", [])
    if hasattr(annotation_plugin, "compare_with_detections"):
        result = annotation_plugin.compare_with_detections(
            symbol, timeframe, transition_history
        )
        return result
    return {"error": "compare method not available"}


@app.get("/api/annotations/auto-compare")
async def get_auto_compare() -> Dict[str, Any]:
    """T5.3: 获取最新的增量标注自动对比结果"""
    if not app_state.wyckoff_app:
        return {"error": "System not initialized"}
    manager = app_state.wyckoff_app.plugin_manager
    ann = manager.get_plugin("annotation")
    if ann is None or not hasattr(ann, "get_auto_compare_result"):
        return {"error": "Auto-compare not available"}
    result = ann.get_auto_compare_result()
    if result is None:
        return {"result": None, "message": "No auto-compare result yet"}
    return {"result": result}


# ========== 修改建议 API ==========


@app.get("/api/annotations/suggestions")
async def get_suggestions(status: str = "") -> Dict[str, Any]:
    """获取修改建议列表

    Args:
        status: 按状态筛选（pending/applied/rejected），空返回全部

    Returns:
        {"suggestions": [...]}
    """
    if not app_state.wyckoff_app:
        return {"suggestions": []}
    manager = app_state.wyckoff_app.plugin_manager
    ann = manager.get_plugin("annotation")
    if ann is None or not hasattr(ann, "get_suggestions"):
        return {"suggestions": []}
    return {"suggestions": ann.get_suggestions(status)}


@app.post("/api/annotations/suggestions/{suggestion_id}/apply")
async def apply_suggestion(suggestion_id: str) -> Dict[str, Any]:
    """应用参数修改建议到检测器注册表

    需要 annotation 和 wyckoff_state_machine 插件同时加载。

    Args:
        suggestion_id: 建议 UUID

    Returns:
        应用结果 {applied: int, skipped: int, errors: [...]}
    """
    if not app_state.wyckoff_app:
        return {"error": "System not initialized"}
    manager = app_state.wyckoff_app.plugin_manager
    ann = manager.get_plugin("annotation")
    if ann is None:
        return {"error": "Annotation plugin not loaded"}
    sm = manager.get_plugin("wyckoff_state_machine")
    if sm is None:
        return {"error": "State machine plugin not loaded"}
    # 获取检测器注册表
    registry = getattr(sm, "_registry", None) or getattr(sm, "registry", None)
    if registry is None:
        return {"error": "Detector registry not found"}
    mgr = ann.get_suggestion_manager()
    result = mgr.apply_param_changes(suggestion_id, registry)
    return result


# ========== 诊断对话 API ==========


@app.post("/api/annotations/chat")
async def annotation_chat(request: Request) -> Dict[str, Any]:
    """标注诊断对话 — AI 分析标注与检测差异

    接收用户消息和上下文，返回结构化诊断结果。
    支持多轮对话。

    Request body:
        {"message": "...", "context": {...}}

    Returns:
        {"success": true, "response": {text, suggested_params, ...}}
    """
    if not app_state.wyckoff_app:
        return {"error": "System not initialized"}
    body = await request.json()
    message = body.get("message", "")
    context = body.get("context", {})
    if not message:
        return {"error": "message is required"}
    manager = app_state.wyckoff_app.plugin_manager
    annotation_plugin = manager.get_plugin("annotation")
    if annotation_plugin is None or not hasattr(annotation_plugin, "diagnose_chat"):
        return {"error": "Diagnosis not available"}

    # ===== 自动注入上下文（bar_features / knowledge_rules / detector_params） =====
    selected_bar = context.get("selected_bar")

    # 1. 注入 bar_features — 从最近的 analyze 缓存获取选中K线数据
    if selected_bar is not None and "bar_features" not in context:
        last = app_state._last_analysis
        if last and "bar_details" in last:
            for bar in last["bar_details"]:
                if bar.get("bar_index") == selected_bar:
                    context["bar_features"] = json.dumps(
                        bar, ensure_ascii=False, default=str
                    )
                    context["focus_items"] = (
                        f"Bar #{selected_bar} "
                        f"(timestamp: {bar.get('timestamp', 'unknown')})"
                    )
                    break

    # 2. 注入 knowledge_rules — 用消息搜索相关知识
    if "knowledge_rules" not in context and hasattr(
        annotation_plugin, "search_knowledge"
    ):
        try:
            rules = annotation_plugin.search_knowledge(message, k=3)
            if rules:
                context["knowledge_rules"] = json.dumps(
                    rules, ensure_ascii=False, default=str
                )
        except Exception:
            pass

    # 3. 注入 detector_params — 当前检测器参数快照
    if "detector_params" not in context:
        sm_plugin = manager.get_plugin("wyckoff_state_machine")
        if sm_plugin is not None:
            try:
                registry = getattr(sm_plugin, "_registry", None) or getattr(
                    sm_plugin, "registry", None
                )
                if registry:
                    all_params: Dict[str, Any] = {}
                    detectors = getattr(registry, "_detectors", {})
                    for name, det in detectors.items():
                        if hasattr(det, "get_evolvable_params"):
                            params = det.get_evolvable_params()
                            if params:
                                all_params[name] = {
                                    k: {
                                        "current": v.current,
                                        "min": v.min,
                                        "max": v.max,
                                    }
                                    for k, v in params.items()
                                }
                    if all_params:
                        context["detector_params"] = json.dumps(
                            all_params, ensure_ascii=False, default=str
                        )
            except Exception:
                pass
    # ===== 注入结束 =====

    try:
        result = annotation_plugin.diagnose_chat(message, context)
        # 自动保存对话历史
        if hasattr(annotation_plugin, "save_chat_message"):
            now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
            annotation_plugin.save_chat_message(
                {"role": "user", "content": message, "timestamp": now_ts}
            )
            annotation_plugin.save_chat_message(
                {
                    "role": "assistant",
                    "content": result.get("text", ""),
                    "timestamp": now_ts,
                    "suggested_params": result.get("suggested_params", []),
                    "highlighted_bars": result.get("highlighted_bars", []),
                }
            )
        return {"success": True, "response": result}
    except Exception as e:
        logger.error("诊断对话失败: %s", e)
        return {"error": str(e)}


@app.get("/api/annotations/chat/history")
async def get_chat_history() -> Dict[str, Any]:
    """获取对话历史"""
    if not app_state.wyckoff_app:
        return {"messages": []}
    manager = app_state.wyckoff_app.plugin_manager
    ann = manager.get_plugin("annotation")
    if ann is None or not hasattr(ann, "get_chat_history"):
        return {"messages": []}
    return {"messages": ann.get_chat_history()}


@app.delete("/api/annotations/chat/history")
async def clear_chat_history() -> Dict[str, Any]:
    """清空对话历史"""
    if not app_state.wyckoff_app:
        return {"error": "System not initialized"}
    manager = app_state.wyckoff_app.plugin_manager
    ann = manager.get_plugin("annotation")
    if ann is None or not hasattr(ann, "clear_chat_history"):
        return {"error": "Not available"}
    ann.clear_chat_history()
    return {"success": True}


@app.get("/api/annotations/knowledge")
async def get_knowledge(detector: str = "", query: str = "") -> Dict[str, Any]:
    """搜索检测器知识库"""
    if not app_state.wyckoff_app:
        return {"rules": []}
    manager = app_state.wyckoff_app.plugin_manager
    ann = manager.get_plugin("annotation")
    if ann is None or not hasattr(ann, "search_knowledge"):
        return {"rules": []}
    if query:
        rules = ann.search_knowledge(query, detector, k=10)
    elif detector:
        kb = ann.get_knowledge_base()
        from dataclasses import asdict

        rules = [asdict(r) for r in kb.get_detector_rules(detector)]
    else:
        stats = ann.get_knowledge_stats() if hasattr(ann, "get_knowledge_stats") else {}
        return {"stats": stats}
    return {"rules": rules}


@app.post("/api/annotations/knowledge")
async def add_knowledge(request: Request) -> Dict[str, Any]:
    """添加检测器知识规则"""
    if not app_state.wyckoff_app:
        return {"error": "System not initialized"}
    body = await request.json()
    manager = app_state.wyckoff_app.plugin_manager
    ann = manager.get_plugin("annotation")
    if ann is None or not hasattr(ann, "add_knowledge_rule"):
        return {"error": "Knowledge base not available"}
    rule = ann.add_knowledge_rule(
        detector_name=body.get("detector_name", ""),
        rule_text=body.get("rule_text", ""),
        source=body.get("source", ""),
        confidence=body.get("confidence", 0.8),
    )
    return {"success": True, "rule": rule}


# 前端静态文件服务（必须在所有 API 路由之后，"/" 是 catch-all）
_frontend_dist = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "frontend",
    "dist",
)
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9527)
