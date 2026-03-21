"""
Orchestrator 插件 v3 — 事件桥梁

核心职责：
1. 持有 WyckoffEngine 实例（唯一信号路径）
2. 订阅 data_pipeline.ohlcv_ready → 调用 engine.process_market_data()
3. 将 TradingDecision 发布为 trading.signal 事件
4. 保留 run_loop 双模式（事件驱动 + 主动拉取）

事件流：
    data_pipeline.ohlcv_ready → _on_data_ready()
        → engine.process_market_data()
        → trading.signal（PositionManager 订阅）
        → orchestrator.decision_made（审计/仪表盘用）
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import (
    HealthCheckResult,
    HealthStatus,
    TradingDecision,
    TradingSignal,
)
from src.plugins.wyckoff_engine.engine import EngineEvents, WyckoffEngine

logger = logging.getLogger(__name__)


class OrchestratorPlugin(BasePlugin):
    """系统协调器插件 v3 — WyckoffEngine 事件桥梁

    设计原则：
    1. 持有 WyckoffEngine — 唯一信号路径（问题#1解决方案）
    2. 事件桥梁 — 将引擎输出转化为事件总线事件
    3. 双模式 — 既支持事件驱动，也支持 run_loop 主动拉取
    4. 审计日志 — 每次决策记录到决策历史

    事件发布：
    - trading.signal: PositionManager 订阅，包含完整 TradingDecision
    - orchestrator.decision_made: 仪表盘/审计用
    - orchestrator.engine_event: 状态变化/TR检测等引擎副作用
    """

    def __init__(self, name: str = "orchestrator") -> None:
        super().__init__(name)
        self._engine: Optional[WyckoffEngine] = None
        self._decision_history: List[TradingDecision] = []
        self._decision_count: int = 0
        self._process_count: int = 0
        self._signal_count: int = 0
        self._last_error: Optional[str] = None
        self._is_running: bool = False
        self._mode: str = "paper"
        self._symbols: List[str] = []
        self._timeframes: List[str] = ["H4", "H1", "M15"]
        self._stop_event: Optional[asyncio.Event] = None
        # 熔断状态 — 熔断时不发送信号
        self._circuit_breaker_tripped: bool = False

    # ================================================================
    # 生命周期
    # ================================================================

    def on_load(self) -> None:
        """加载插件：初始化引擎、订阅事件"""
        self._mode = self._config.get("mode", "paper")
        self._symbols = self._config.get("symbols", [])
        self._timeframes = self._config.get("timeframes", ["H4", "H1", "M15"])

        # 初始化 WyckoffEngine（唯一信号路径）
        engine_config = self._config.get("engine", {})
        engine_config.setdefault("timeframes", self._timeframes)
        self._engine = WyckoffEngine(engine_config)

        # 订阅事件
        self._subscribe_events()

        logger.info(
            "OrchestratorPlugin v3 loaded (mode=%s, symbols=%s, tf=%s)",
            self._mode,
            self._symbols,
            self._timeframes,
        )

    def on_unload(self) -> None:
        """卸载插件"""
        self._is_running = False
        self._engine = None
        self._decision_history.clear()
        logger.info("OrchestratorPlugin unloaded")

    def _subscribe_events(self) -> None:
        """订阅事件"""
        # 核心事件 — 数据就绪触发引擎处理
        self.subscribe_event("data_pipeline.ohlcv_ready", self._on_data_ready)
        # 熔断器事件 — 熔断时停止发送信号
        self.subscribe_event(
            "risk_management.circuit_breaker_tripped",
            self._on_circuit_breaker,
        )
        self.subscribe_event(
            "risk_management.circuit_breaker_recovered",
            self._on_circuit_breaker_recovered,
        )
        # 仓位事件 — 记录日志
        self.subscribe_event("position.opened", self._on_position_opened)
        self.subscribe_event("position.closed", self._on_position_closed)

        logger.info("OrchestratorPlugin 事件订阅完成")

    # ================================================================
    # 核心逻辑 — 数据到达 → 引擎处理 → 发布信号
    # ================================================================

    def _on_data_ready(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理数据就绪事件 — 核心信号路径

        Args:
            event_name: 事件名称
            data: 事件数据，期望包含:
                - symbol: 交易对
                - data_dict: {timeframe: DataFrame}
                - timeframes: 时间框架列表（可选）
        """
        symbol = data.get("symbol", "")
        data_dict = data.get("data_dict")
        timeframes = data.get("timeframes", self._timeframes)

        if not symbol or not data_dict:
            logger.warning(
                "ohlcv_ready 事件数据不完整: symbol=%s, has_data_dict=%s",
                symbol,
                data_dict is not None,
            )
            return

        self._process_market_data(symbol, timeframes, data_dict)

    def _process_market_data(
        self,
        symbol: str,
        timeframes: List[str],
        data_dict: Dict[str, pd.DataFrame],
    ) -> Optional[TradingDecision]:
        """调用引擎处理数据并发布信号

        此方法被 _on_data_ready（事件模式）和
        run_loop（主动模式）共同调用。

        Args:
            symbol: 交易对
            timeframes: 时间框架列表
            data_dict: {timeframe: DataFrame}

        Returns:
            TradingDecision 或 None（引擎未初始化时）
        """
        if self._engine is None:
            logger.error("WyckoffEngine 未初始化")
            return None

        self._process_count += 1

        try:
            # 调用引擎 — 唯一信号路径
            decision, events = self._engine.process_market_data(
                symbol=symbol,
                timeframes=timeframes,
                data_dict=data_dict,
            )

            # 处理引擎副作用事件
            self._handle_engine_events(symbol, events)

            # 发布交易信号
            self._publish_trading_signal(symbol, decision, data_dict)

            return decision

        except Exception as e:
            self._last_error = str(e)
            logger.exception("引擎处理失败: symbol=%s, error=%s", symbol, e)
            return None

    def _publish_trading_signal(
        self,
        symbol: str,
        decision: TradingDecision,
        data_dict: Dict[str, pd.DataFrame],
    ) -> None:
        """发布 trading.signal 事件

        Args:
            symbol: 交易对
            decision: 引擎产出的交易决策
            data_dict: 原始数据（传递给 PositionManager 计算止损用）
        """
        # 熔断中 → 只发 NEUTRAL
        if self._circuit_breaker_tripped:
            logger.warning("熔断中，强制降级为 NEUTRAL: %s", symbol)
            self._record_decision(decision)
            return

        # 构建 trading.signal 事件数据
        signal_data: Dict[str, Any] = {
            "symbol": symbol,
            "signal": decision.signal,
            "confidence": decision.confidence,
            "entry_price": decision.entry_price,
            "stop_loss": decision.stop_loss,
            "take_profit": decision.take_profit,
            "reasoning": decision.reasoning,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "wyckoff_state": "",
            "decision": decision,
        }

        # 从决策上下文提取威科夫状态
        if decision.context:
            signal_data["wyckoff_state"] = decision.context.wyckoff_state or ""

        # 附加主时间框架的 DataFrame（供 PositionManager 计算止损）
        primary_tf = self._timeframes[0] if self._timeframes else "H4"
        df = data_dict.get(primary_tf)
        if df is not None:
            signal_data["df"] = df

        # 发布信号
        self.emit_event("trading.signal", signal_data)
        self._signal_count += 1

        # 记录决策
        self._record_decision(decision)

        # 发布审计事件
        audit_data = decision.to_dict()
        audit_data["symbol"] = symbol
        audit_data["decision_count"] = self._decision_count
        self.emit_event("orchestrator.decision_made", audit_data)

        if decision.signal != TradingSignal.NEUTRAL:
            logger.info(
                "trading.signal 发布: %s %s (置信度: %.2f)",
                symbol,
                decision.signal.value,
                decision.confidence,
            )

    def _handle_engine_events(self, symbol: str, events: EngineEvents) -> None:
        """处理引擎副作用事件，转发到事件总线

        Args:
            symbol: 交易对
            events: 引擎产出的副作用事件
        """
        if events.tr_detected:
            self.emit_event(
                "orchestrator.engine_event",
                {
                    "symbol": symbol,
                    "type": "tr_detected",
                    "data": events.tr_data,
                },
            )

        if events.state_changed:
            self.emit_event(
                "orchestrator.engine_event",
                {
                    "symbol": symbol,
                    "type": "state_changed",
                    "old_state": events.old_state,
                    "new_state": events.new_state,
                },
            )
            logger.info(
                "状态变化: %s %s → %s",
                symbol,
                events.old_state,
                events.new_state,
            )

        if events.conflicts_detected:
            self.emit_event(
                "orchestrator.engine_event",
                {
                    "symbol": symbol,
                    "type": "conflicts_detected",
                    "data": events.conflict_details,
                },
            )

    def _record_decision(self, decision: TradingDecision) -> None:
        """记录决策到历史"""
        self._decision_count += 1
        self._decision_history.append(decision)
        if len(self._decision_history) > 100:
            self._decision_history = self._decision_history[-100:]

    # ================================================================
    # 辅助事件处理器
    # ================================================================

    def _on_circuit_breaker(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理熔断器触发事件"""
        reason = data.get("reason", "unknown")
        self._circuit_breaker_tripped = True
        logger.warning("熔断器触发，停止信号发送: %s", reason)

        self.emit_event(
            "orchestrator.error_occurred",
            {"error": "circuit_breaker_tripped", "reason": reason},
        )

    def _on_circuit_breaker_recovered(
        self, event_name: str, data: Dict[str, Any]
    ) -> None:
        """处理熔断器恢复事件"""
        self._circuit_breaker_tripped = False
        logger.info("熔断器恢复，重新开始信号发送")

    def _on_position_opened(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理仓位开启事件"""
        symbol = data.get("symbol", "unknown")
        side = data.get("side", "unknown")
        size = data.get("size", 0)
        logger.info("仓位开启: %s %s %.4f", symbol, side, size)

    def _on_position_closed(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理仓位关闭事件"""
        symbol = data.get("symbol", "unknown")
        pnl = data.get("pnl", 0)
        logger.info("仓位关闭: %s PnL=%.2f", symbol, pnl)

    # ================================================================
    # 健康检查
    # ================================================================

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        details: Dict[str, Any] = {
            "decision_count": self._decision_count,
            "process_count": self._process_count,
            "signal_count": self._signal_count,
            "is_running": self._is_running,
            "mode": self._mode,
            "engine_loaded": self._engine is not None,
            "circuit_breaker_tripped": self._circuit_breaker_tripped,
        }

        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近错误: {self._last_error}",
                details=details,
            )

        if self._circuit_breaker_tripped:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message="熔断中，信号暂停",
                details=details,
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="协调器运行正常",
            details=details,
        )

    # ================================================================
    # 双模式 — run_loop 主动拉取数据
    # ================================================================

    async def run_loop(self) -> None:
        """主运行循环（双模式之二：主动拉取）

        当 data_pipeline 不发布 ohlcv_ready 事件时，
        orchestrator 自己定期从 exchange_connector 拉取数据。

        流程：
        1. 启动系统
        2. 定期从 exchange_connector 获取数据
        3. 调用 _process_market_data()
        4. 响应停止信号
        """
        logger.info("OrchestratorPlugin run_loop 启动")

        await self.start_system()

        data_interval = self._config.get("data_refresh_interval", 60)
        self._stop_event = asyncio.Event()

        while self._is_running:
            try:
                for symbol in self._symbols:
                    data_dict = self._fetch_data_from_connector(symbol)
                    if data_dict:
                        self._process_market_data(symbol, self._timeframes, data_dict)

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=data_interval,
                    )
                    break
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                logger.error("run_loop 错误: %s", e)
                self._last_error = str(e)
                await asyncio.sleep(5)

        logger.info("OrchestratorPlugin run_loop 退出")

    def _fetch_data_from_connector(
        self, symbol: str
    ) -> Optional[Dict[str, pd.DataFrame]]:
        """从 exchange_connector 插件获取数据

        Args:
            symbol: 交易对

        Returns:
            {timeframe: DataFrame} 或 None
        """
        connector = self.get_plugin("exchange_connector")
        if connector is None:
            logger.debug("exchange_connector 插件未找到")
            return None

        # connector 是 BasePlugin 类型，通过 getattr 访问具体方法
        fetch_fn = getattr(connector, "fetch_ohlcv", None)
        if fetch_fn is None:
            logger.debug("exchange_connector 无 fetch_ohlcv 方法")
            return None

        # 时间框架映射（内部表示 → ccxt表示）
        tf_map: Dict[str, str] = {
            "D1": "1d",
            "H4": "4h",
            "H1": "1h",
            "M15": "15m",
            "M5": "5m",
        }

        data_dict: Dict[str, pd.DataFrame] = {}
        historical_bars = self._config.get("historical_bars", 200)

        for tf in self._timeframes:
            ccxt_tf = tf_map.get(tf, tf.lower())
            try:
                df = fetch_fn(
                    symbol=symbol,
                    timeframe=ccxt_tf,
                    limit=historical_bars,
                )
                if df is not None and len(df) > 0:
                    data_dict[tf] = df
            except Exception as e:
                logger.warning(
                    "获取 %s %s 数据失败: %s",
                    symbol,
                    tf,
                    e,
                )

        return data_dict if data_dict else None

    # ================================================================
    # 公共 API
    # ================================================================

    async def start_system(self) -> Dict[str, Any]:
        """启动系统"""
        self._is_running = True
        self.emit_event(
            "orchestrator.started",
            {"mode": self._mode, "symbols": self._symbols},
        )
        logger.info("系统启动: mode=%s", self._mode)
        return {"success": True, "mode": self._mode}

    async def stop_system(self) -> Dict[str, Any]:
        """停止系统"""
        self._is_running = False
        if self._stop_event:
            self._stop_event.set()
        self.emit_event("orchestrator.stopped", {})
        logger.info("系统停止")
        return {"success": True}

    def request_stop(self) -> None:
        """请求停止运行循环"""
        self._is_running = False
        if self._stop_event:
            self._stop_event.set()

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "status": "running" if self._is_running else "stopped",
            "mode": self._mode,
            "symbols": self._symbols,
            "timeframes": self._timeframes,
            "decision_count": self._decision_count,
            "process_count": self._process_count,
            "signal_count": self._signal_count,
            "last_error": self._last_error,
            "engine_loaded": self._engine is not None,
            "circuit_breaker_tripped": self._circuit_breaker_tripped,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "decision_count": self._decision_count,
            "process_count": self._process_count,
            "signal_count": self._signal_count,
            "last_error": self._last_error,
            "is_running": self._is_running,
            "mode": self._mode,
        }

    def get_decision_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取决策历史"""
        result = []
        for i, decision in enumerate(self._decision_history[-limit:]):
            d = decision.to_dict()
            d["id"] = str(i)
            result.append(d)
        return result

    @property
    def engine(self) -> Optional[WyckoffEngine]:
        """获取引擎实例（只读）"""
        return self._engine
