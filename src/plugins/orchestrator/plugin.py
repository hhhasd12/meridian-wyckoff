"""
Orchestrator 插件 - 系统协调器

真正的事件驱动协调器，不依赖 legacy 代码。
通过事件总线订阅其他插件的输出，汇总生成最终决策。

事件流:
1. data_pipeline.ohlcv_ready → 触发数据处理
2. market_regime.detected → 记录市场体制
3. state_machine.signal_generated → 记录威科夫信号
4. signal_validation.entry_validated → 记录验证结果
5. risk_management.anomaly_validated → 记录风险状态
6. 汇总所有输入 → orchestrator.decision_made
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import (
    DecisionContext,
    HealthCheckResult,
    HealthStatus,
    TradingDecision,
    TradingSignal,
)

logger = logging.getLogger(__name__)


@dataclass
class MarketState:
    """市场状态缓存"""
    regime: Optional[str] = None
    regime_confidence: float = 0.0
    wyckoff_state: Optional[str] = None
    wyckoff_confidence: float = 0.0
    signal_validated: bool = False
    signal_confidence: float = 0.0
    risk_status: str = "normal"
    last_update: Optional[datetime] = None


@dataclass
class DecisionInput:
    """决策输入数据"""
    symbol: str
    timeframe: str
    timestamp: datetime
    market_state: MarketState
    additional_context: Dict[str, Any] = field(default_factory=dict)


class OrchestratorPlugin(BasePlugin):
    """系统协调器插件

    事件驱动架构的核心协调器：
    - 订阅所有决策相关事件
    - 汇总各插件输出
    - 生成最终交易决策
    - 发布决策事件

    不再依赖 SystemOrchestrator legacy 代码。
    """

    def __init__(self, name: str = "orchestrator") -> None:
        super().__init__(name)
        self._market_states: Dict[str, MarketState] = {}
        self._decision_history: List[TradingDecision] = []
        self._decision_count: int = 0
        self._process_count: int = 0
        self._evolution_count: int = 0
        self._last_error: Optional[str] = None
        self._is_running: bool = False
        self._mode: str = "paper"
        self._symbols: List[str] = []
        self._timeframes: List[str] = ["H4", "H1", "M15"]
        self._pending_decisions: Dict[str, DecisionInput] = {}
        self._decision_lock: asyncio.Lock = asyncio.Lock()
        self._stop_event: Optional[asyncio.Event] = None

    def on_load(self) -> None:
        """加载插件，订阅事件"""
        self._mode = self._config.get("mode", "paper")
        self._symbols = self._config.get("symbols", [])
        self._timeframes = self._config.get("timeframes", ["H4", "H1", "M15"])

        self._subscribe_events()
        logger.info(
            "OrchestratorPlugin loaded (mode=%s, symbols=%s)",
            self._mode, self._symbols
        )

    def on_unload(self) -> None:
        """卸载插件"""
        self._is_running = False
        self._market_states.clear()
        self._pending_decisions.clear()
        logger.info("OrchestratorPlugin unloaded")

    def _subscribe_events(self) -> None:
        """订阅所有决策相关事件"""
        self.subscribe_event("market_regime.detected", self._on_regime_detected)
        self.subscribe_event("market_regime.changed", self._on_regime_changed)
        self.subscribe_event("state_machine.signal_generated", self._on_signal_generated)
        self.subscribe_event("state_machine.state_changed", self._on_state_changed)
        self.subscribe_event("signal_validation.entry_validated", self._on_entry_validated)
        self.subscribe_event("signal_validation.conflict_resolved", self._on_conflict_resolved)
        self.subscribe_event("risk_management.anomaly_validated", self._on_anomaly_validated)
        self.subscribe_event("risk_management.circuit_breaker_tripped", self._on_circuit_breaker)
        self.subscribe_event("position.opened", self._on_position_opened)
        self.subscribe_event("position.closed", self._on_position_closed)
        self.subscribe_event("data_pipeline.ohlcv_ready", self._on_data_ready)
        logger.info("OrchestratorPlugin subscribed to all events")

    def health_check(self) -> HealthCheckResult:
        """健康检查"""
        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近错误: {self._last_error}",
                details={
                    "decision_count": self._decision_count,
                    "process_count": self._process_count,
                    "is_running": self._is_running,
                    "mode": self._mode,
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="协调器运行正常",
            details={
                "decision_count": self._decision_count,
                "process_count": self._process_count,
                "evolution_count": self._evolution_count,
                "is_running": self._is_running,
                "mode": self._mode,
                "tracked_symbols": list(self._market_states.keys()),
            },
        )

    # === 事件处理器 ===

    def _on_regime_detected(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理市场体制检测事件"""
        symbol = data.get("symbol", "unknown")
        regime = data.get("regime", "UNKNOWN")
        confidence = data.get("confidence", 0.0)

        if symbol not in self._market_states:
            self._market_states[symbol] = MarketState()

        self._market_states[symbol].regime = regime
        self._market_states[symbol].regime_confidence = confidence
        self._market_states[symbol].last_update = datetime.now()

        logger.debug(
            "市场体制更新: %s -> %s (置信度: %.2f)",
            symbol, regime, confidence
        )

    def _on_regime_changed(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理市场体制变化事件"""
        symbol = data.get("symbol", "unknown")
        old_regime = data.get("old_regime", "UNKNOWN")
        new_regime = data.get("new_regime", "UNKNOWN")

        logger.info(
            "市场体制变化: %s %s -> %s",
            symbol, old_regime, new_regime
        )

        self.emit_event(
            "orchestrator.market_data_processed",
            {
                "symbol": symbol,
                "event": "regime_changed",
                "old_regime": old_regime,
                "new_regime": new_regime,
            }
        )

    def _on_signal_generated(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理威科夫信号生成事件"""
        symbol = data.get("symbol", "unknown")
        signal = data.get("signal", "no_signal")
        confidence = data.get("confidence", 0.0)
        state = data.get("state", "")

        if symbol not in self._market_states:
            self._market_states[symbol] = MarketState()

        self._market_states[symbol].wyckoff_state = state
        self._market_states[symbol].wyckoff_confidence = confidence

        logger.info(
            "威科夫信号: %s -> %s (状态: %s, 置信度: %.2f)",
            symbol, signal, state, confidence
        )

        if signal in ("buy_signal", "sell_signal"):
            self._try_make_decision(symbol, data)

    def _on_state_changed(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理状态机状态变化事件"""
        symbol = data.get("symbol", "unknown")
        from_state = data.get("from_state", "")
        to_state = data.get("to_state", "")

        logger.debug(
            "状态机变化: %s %s -> %s",
            symbol, from_state, to_state
        )

    def _on_entry_validated(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理入场验证事件"""
        symbol = data.get("symbol", "unknown")
        validated = data.get("validated", False)
        confidence = data.get("confidence", 0.0)

        if symbol not in self._market_states:
            self._market_states[symbol] = MarketState()

        self._market_states[symbol].signal_validated = validated
        self._market_states[symbol].signal_confidence = confidence

        logger.info(
            "入场验证: %s -> %s (置信度: %.2f)",
            symbol, "通过" if validated else "未通过", confidence
        )

        if validated:
            self._try_make_decision(symbol, data)

    def _on_conflict_resolved(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理冲突解决事件"""
        symbol = data.get("symbol", "unknown")
        resolution = data.get("resolution", "hold")

        logger.info(
            "冲突解决: %s -> %s",
            symbol, resolution
        )

    def _on_anomaly_validated(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理异常验证事件"""
        symbol = data.get("symbol", "unknown")
        is_anomaly = data.get("is_anomaly", False)
        risk_level = data.get("risk_level", "normal")

        if symbol not in self._market_states:
            self._market_states[symbol] = MarketState()

        self._market_states[symbol].risk_status = "anomaly" if is_anomaly else "normal"

        logger.warning(
            "异常验证: %s -> %s (风险级别: %s)",
            symbol, "异常" if is_anomaly else "正常", risk_level
        )

    def _on_circuit_breaker(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理熔断器触发事件"""
        reason = data.get("reason", "unknown")

        logger.warning("熔断器触发: %s", reason)

        self.emit_event(
            "orchestrator.error_occurred",
            {
                "error": "circuit_breaker_tripped",
                "reason": reason,
            }
        )

    def _on_position_opened(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理仓位开启事件"""
        symbol = data.get("symbol", "unknown")
        side = data.get("side", "unknown")
        size = data.get("size", 0)

        logger.info(
            "仓位开启: %s %s %.4f",
            symbol, side, size
        )

    def _on_position_closed(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理仓位关闭事件"""
        symbol = data.get("symbol", "unknown")
        pnl = data.get("pnl", 0)

        logger.info(
            "仓位关闭: %s PnL=%.2f",
            symbol, pnl
        )

    def _on_data_ready(self, event_name: str, data: Dict[str, Any]) -> None:
        """处理数据就绪事件"""
        symbol = data.get("symbol", "unknown")
        timeframe = data.get("timeframe", "")

        self._process_count += 1

        logger.debug(
            "数据就绪: %s %s",
            symbol, timeframe
        )

    # === 决策逻辑 ===

    def _try_make_decision(self, symbol: str, trigger_data: Dict[str, Any]) -> None:
        """尝试生成决策"""
        state = self._market_states.get(symbol)
        if state is None:
            logger.debug("未找到 %s 的市场状态，跳过决策", symbol)
            return

        if state.risk_status == "anomaly":
            logger.warning("%s 存在异常，跳过决策", symbol)
            return

        if not state.signal_validated and state.wyckoff_confidence < 0.5:
            logger.debug("%s 信号未验证且置信度低，跳过决策", symbol)
            return

        decision = self._generate_decision(symbol, state, trigger_data)
        if decision:
            self._publish_decision(decision)

    def _generate_decision(
        self,
        symbol: str,
        state: MarketState,
        trigger_data: Dict[str, Any]
    ) -> Optional[TradingDecision]:
        """生成交易决策"""
        try:
            signal_raw = trigger_data.get("signal", "no_signal")

            if signal_raw == "buy_signal":
                signal = TradingSignal.BUY
            elif signal_raw == "sell_signal":
                signal = TradingSignal.SELL
            else:
                signal = TradingSignal.NEUTRAL

            if signal == TradingSignal.NEUTRAL:
                return None

            confidence = self._calculate_confidence(state, trigger_data)
            if confidence < 0.5:
                logger.debug(
                    "%s 决策置信度 %.2f 低于阈值，跳过",
                    symbol, confidence
                )
                return None

            context = DecisionContext(
                timestamp=datetime.now(),
                market_regime=state.regime or "UNKNOWN",
                regime_confidence=state.regime_confidence,
                timeframe_weights={tf: 1.0 / len(self._timeframes) for tf in self._timeframes},
                detected_conflicts=[],
                wyckoff_state=state.wyckoff_state,
                wyckoff_confidence=state.wyckoff_confidence,
            )

            decision = TradingDecision(
                signal=signal,
                confidence=confidence,
                context=context,
                entry_price=trigger_data.get("entry_price"),
                stop_loss=trigger_data.get("stop_loss"),
                take_profit=trigger_data.get("take_profit"),
                reasoning=[
                    f"市场体制: {state.regime}",
                    f"威科夫状态: {state.wyckoff_state}",
                    f"信号验证: {'通过' if state.signal_validated else '未验证'}",
                ],
            )

            return decision

        except Exception as e:
            logger.error("生成决策失败: %s", e)
            self._last_error = str(e)
            return None

    def _calculate_confidence(
        self,
        state: MarketState,
        trigger_data: Dict[str, Any]
    ) -> float:
        """计算决策置信度"""
        base_confidence = trigger_data.get("confidence", 0.5)

        regime_factor = state.regime_confidence * 0.2
        wyckoff_factor = state.wyckoff_confidence * 0.3
        validation_factor = 0.2 if state.signal_validated else 0.0

        total = base_confidence * 0.3 + regime_factor + wyckoff_factor + validation_factor

        return min(1.0, max(0.0, total))

    def _publish_decision(self, decision: TradingDecision) -> None:
        """发布决策事件"""
        self._decision_count += 1
        self._decision_history.append(decision)

        if len(self._decision_history) > 100:
            self._decision_history = self._decision_history[-100:]

        decision_data = decision.to_dict()
        decision_data["decision_count"] = self._decision_count

        self.emit_event("orchestrator.decision_made", decision_data)

        logger.info(
            "决策发布: %s (置信度: %.2f)",
            decision.signal.value, decision.confidence
        )

    # === 公共 API ===

    async def start_system(self) -> Dict[str, Any]:
        """启动系统"""
        self._is_running = True
        self.emit_event(
            "orchestrator.started",
            {"mode": self._mode, "symbols": self._symbols}
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

    async def run_evolution_cycle(self) -> Dict[str, Any]:
        """运行进化周期"""
        self._evolution_count += 1
        logger.info("进化周期: #%d", self._evolution_count)

        self.emit_event(
            "orchestrator.evolution_cycle_completed",
            {"cycle_count": self._evolution_count}
        )

        return {
            "success": True,
            "cycle_count": self._evolution_count,
        }

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "status": "running" if self._is_running else "stopped",
            "mode": self._mode,
            "symbols": self._symbols,
            "timeframes": self._timeframes,
            "decision_count": self._decision_count,
            "process_count": self._process_count,
            "evolution_count": self._evolution_count,
            "tracked_symbols": list(self._market_states.keys()),
            "last_error": self._last_error,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "decision_count": self._decision_count,
            "process_count": self._process_count,
            "evolution_count": self._evolution_count,
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

    async def run_loop(self) -> None:
        """主运行循环

        事件驱动的主循环：
        1. 启动系统
        2. 定期触发数据刷新
        3. 定期运行进化周期
        4. 响应停止信号
        """
        logger.info("OrchestratorPlugin run_loop 启动")

        await self.start_system()

        data_interval = self._config.get("data_refresh_interval", 60)
        evolution_interval = self._config.get("evolution_interval", 3600)

        last_evolution_time = datetime.now()
        self._stop_event = asyncio.Event()

        while self._is_running:
            try:
                for symbol in self._symbols:
                    self.emit_event(
                        "orchestrator.data_refresh_requested",
                        {"symbol": symbol, "timeframes": self._timeframes}
                    )

                now = datetime.now()
                elapsed = (now - last_evolution_time).total_seconds()
                if elapsed >= evolution_interval:
                    await self.run_evolution_cycle()
                    last_evolution_time = now

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=data_interval
                    )
                    break
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                logger.error("run_loop 错误: %s", e)
                self._last_error = str(e)
                await asyncio.sleep(5)

        logger.info("OrchestratorPlugin run_loop 退出")

    def request_stop(self) -> None:
        """请求停止运行循环"""
        self._is_running = False
        if hasattr(self, '_stop_event') and self._stop_event:
            self._stop_event.set()
