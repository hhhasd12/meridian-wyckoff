"""
Wyckoff State Machine 插件

将 WyckoffStateMachine 和 EnhancedWyckoffStateMachine 包装为插件，
提供威科夫状态检测、K线处理、信号生成等功能。
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class WyckoffStateMachinePlugin(BasePlugin):
    """威科夫状态机插件

    包装 WyckoffStateMachine 和 EnhancedWyckoffStateMachine，提供：
    - K线数据处理和状态检测
    - 多时间框架状态同步
    - 交易信号生成
    - 状态报告查询
    - 参数优化
    """

    def __init__(self, name: str = "wyckoff_state_machine") -> None:
        """初始化威科夫状态机插件

        Args:
            name: 插件名称
        """
        super().__init__(name)
        self._state_machine: Optional[Any] = None
        self._enhanced_sm: Optional[Any] = None
        self._candle_count: int = 0
        self._transition_count: int = 0
        self._signal_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件，初始化状态机"""
        try:
            from src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy import (
                EnhancedWyckoffStateMachine,
                WyckoffStateMachine,
            )

            sm_config = self._config.copy() if self._config else {}
            self._state_machine = WyckoffStateMachine(sm_config)
            self._enhanced_sm = EnhancedWyckoffStateMachine(sm_config)
            logger.info("WyckoffStateMachinePlugin loaded successfully")
        except ImportError as e:
            logger.warning("WyckoffStateMachine not available: %s", e)
            self._state_machine = None
            self._enhanced_sm = None
        except Exception as e:
            logger.error("Failed to load WyckoffStateMachine: %s", e)
            self._state_machine = None
            self._enhanced_sm = None
            self._last_error = str(e)

    def on_unload(self) -> None:
        """卸载插件，清理资源"""
        self._state_machine = None
        self._enhanced_sm = None
        logger.info("WyckoffStateMachinePlugin unloaded")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """处理配置更新

        Args:
            new_config: 新的配置字典
        """
        if self._state_machine is not None:
            if hasattr(self._state_machine, "config"):
                self._state_machine.config.update_from_dict(new_config)
            logger.info("State machine config updated")

    def health_check(self) -> HealthCheckResult:
        """执行健康检查

        Returns:
            HealthCheckResult: 健康检查结果
        """
        if self._state_machine is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                details={
                    "error": "State machine not loaded",
                    "candle_count": self._candle_count,
                },
            )

        if self._last_error is not None:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                details={
                    "last_error": self._last_error,
                    "candle_count": self._candle_count,
                    "transition_count": self._transition_count,
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            details={
                "candle_count": self._candle_count,
                "transition_count": self._transition_count,
                "signal_count": self._signal_count,
            },
        )

    # === K线处理 ===

    def process_candle(self, candle_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理单根K线数据

        Args:
            candle_data: K线数据字典，包含 open, high, low, close, volume

        Returns:
            Optional[Dict]: 状态检测结果，或 None
        """
        if self._state_machine is None:
            return None

        try:
            result = self._state_machine.process_candle(candle_data)
            self._candle_count += 1

            if result and hasattr(result, "state_name"):
                prev_state = getattr(self._state_machine, "current_state", None)
                if prev_state and prev_state != result.state_name:
                    self._transition_count += 1
                    self.emit_event(
                        "state_machine.state_changed",
                        {
                            "from_state": str(prev_state),
                            "to_state": result.state_name,
                            "confidence": result.confidence,
                        },
                    )

            self.emit_event(
                "state_machine.candle_processed",
                {
                    "candle_count": self._candle_count,
                    "has_result": result is not None,
                },
            )
            return (
                {
                    "state_name": result.state_name,
                    "confidence": result.confidence,
                    "intensity": result.intensity,
                }
                if result
                else None
            )
        except Exception as e:
            self._last_error = str(e)
            logger.error("Error processing candle: %s", e)
            self.emit_event(
                "state_machine.error_occurred",
                {"error": str(e), "operation": "process_candle"},
            )
            return None

    # === 多时间框架处理 ===

    def process_multi_timeframe(
        self,
        timeframe_data: Dict[str, pd.DataFrame],
    ) -> Optional[Dict[str, Any]]:
        """处理多时间框架数据

        Args:
            timeframe_data: 各时间框架的数据字典

        Returns:
            Optional[Dict]: 多时间框架分析结果
        """
        if self._enhanced_sm is None:
            return None

        try:
            result = self._enhanced_sm.process_multi_timeframe(timeframe_data)
            return result
        except Exception as e:
            self._last_error = str(e)
            logger.error("Error processing multi-timeframe: %s", e)
            return None

    # === 信号生成 ===

    def generate_signals(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """生成交易信号

        Args:
            df: 包含OHLCV数据的DataFrame

        Returns:
            Optional[Dict]: 交易信号结果
        """
        if self._enhanced_sm is None:
            return None

        try:
            signals = self._enhanced_sm.generate_signals(df)
            if signals:
                self._signal_count += 1
                self.emit_event(
                    "state_machine.signal_generated",
                    {
                        "signal_count": self._signal_count,
                        "signal_type": str(signals.get("type", "unknown")),
                    },
                )
            return signals
        except Exception as e:
            self._last_error = str(e)
            logger.error("Error generating signals: %s", e)
            return None

    # === 状态查询 ===

    def get_state_report(self) -> Dict[str, Any]:
        """获取当前状态报告

        Returns:
            Dict: 状态报告
        """
        if self._state_machine is None:
            return {
                "status": "not_loaded",
                "candle_count": self._candle_count,
            }

        try:
            return self._state_machine.get_state_report()
        except Exception as e:
            self._last_error = str(e)
            logger.error("Error getting state report: %s", e)
            return {
                "status": "error",
                "error": str(e),
            }

    def get_current_state_info(self) -> Dict[str, Any]:
        """获取当前状态信息

        Returns:
            Dict: 当前状态信息
        """
        if self._enhanced_sm is None:
            return {"status": "not_loaded"}

        try:
            return self._enhanced_sm.get_current_state_info()
        except Exception as e:
            self._last_error = str(e)
            logger.error("Error getting current state info: %s", e)
            return {"status": "error", "error": str(e)}

    # === 参数优化 ===

    def optimize_parameters(
        self,
        historical_data: pd.DataFrame,
        optimization_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """优化状态机参数

        Args:
            historical_data: 历史数据
            optimization_config: 优化配置

        Returns:
            Optional[Dict]: 优化结果
        """
        if self._enhanced_sm is None:
            return None

        try:
            result = self._enhanced_sm.optimize_parameters(
                historical_data, optimization_config
            )
            return result
        except Exception as e:
            self._last_error = str(e)
            logger.error("Error optimizing parameters: %s", e)
            return None

    # === 统计信息 ===

    def get_statistics(self) -> Dict[str, Any]:
        """获取插件统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "candle_count": self._candle_count,
            "transition_count": self._transition_count,
            "signal_count": self._signal_count,
            "last_error": self._last_error,
            "state_machine_loaded": self._state_machine is not None,
            "enhanced_sm_loaded": self._enhanced_sm is not None,
        }

    def get_transition_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取状态转换历史（供API调用）

        Args:
            limit: 返回记录数量限制

        Returns:
            List: 状态转换历史列表
        """
        if self._state_machine is None:
            return []

        history = getattr(self._state_machine, "transition_history", [])
        if not history:
            return []

        result = []
        for i, record in enumerate(history[-limit:]):
            if hasattr(record, "to_dict"):
                record_dict = record.to_dict()
            elif hasattr(record, "__dict__"):
                record_dict = record.__dict__
            else:
                record_dict = record if isinstance(record, dict) else {}

            result.append(
                {
                    "id": str(i),
                    "timestamp": getattr(
                        record, "timestamp", record_dict.get("timestamp", "")
                    ),
                    "from_state": getattr(
                        record, "from_state", record_dict.get("from_state", "")
                    ),
                    "to_state": getattr(
                        record, "to_state", record_dict.get("to_state", "")
                    ),
                    "trigger": getattr(
                        record, "trigger", record_dict.get("trigger", "")
                    ),
                    "confidence": getattr(
                        record, "confidence", record_dict.get("confidence", 0)
                    ),
                    "symbol": getattr(record, "symbol", record_dict.get("symbol", "")),
                }
            )
        return result
