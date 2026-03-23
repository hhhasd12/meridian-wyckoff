"""
Wyckoff State Machine 插件

将 EnhancedWyckoffStateMachine 包装为插件，
提供威科夫状态检测、K线处理、信号生成等功能。

修复记录 (2026-03-18):
- C-03: process_candle() 返回值是 str，需正确处理状态变化检测
- C-04: generate_signals() 不接受参数，移除错误传参
- C-05: 合并为单实例，消除双实例状态断裂
- 修复 process_candle 签名不匹配 (需要 candle: Series, context: dict)
- 修复 process_multi_timeframe 签名不匹配 (需要 candles_dict, context_dict)
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus, PluginError, StateConfig

logger = logging.getLogger(__name__)


class WyckoffStateMachinePlugin(BasePlugin):
    """威科夫状态机插件

    使用单个 EnhancedWyckoffStateMachine 实例（继承自 WyckoffStateMachine），
    同时承担 K线处理和信号生成，消除双实例状态断裂。

    提供：
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
        # 跟踪上一个状态，用于检测状态变化
        self._prev_state: Optional[str] = None

    def on_load(self) -> None:
        """加载插件，初始化 V4 状态机

        Raises:
            PluginError: 当核心状态机模块无法导入时
        """
        try:
            from src.plugins.wyckoff_state_machine.state_machine_v4 import (
                WyckoffStateMachineV4,
            )

            # 构建 StateConfig（不传 dict，避免类型不匹配）
            sm_config = StateConfig()
            if self._config:
                sm_config.update_from_dict(self._config)

            # V4 单实例
            instance = WyckoffStateMachineV4("H4", sm_config)
            self._state_machine = instance
            self._enhanced_sm = instance  # 兼容旧属性引用
            logger.info("WyckoffStateMachinePlugin loaded (V4)")
        except ImportError as e:
            logger.error("WyckoffStateMachine not available: %s", e)
            raise PluginError(
                f"核心状态机模块导入失败: {e}",
                plugin_name=self._name,
            ) from e
        except Exception as e:
            logger.error("Failed to load WyckoffStateMachine: %s", e)
            self._last_error = str(e)
            raise PluginError(
                f"状态机初始化失败: {e}",
                plugin_name=self._name,
            ) from e

    def on_unload(self) -> None:
        """卸载插件，清理资源"""
        self._state_machine = None
        self._enhanced_sm = None
        self._prev_state = None
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

    def process_candle(
        self,
        candle_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """处理单根K线数据

        Args:
            candle_data: K线数据字典，包含 open, high, low, close, volume
            context: 上下文信息（TR边界、市场体制等），可选

        Returns:
            Optional[Dict]: 状态检测结果，或 None
        """
        if self._state_machine is None:
            return None

        try:
            # 记录处理前的状态，用于检测状态变化
            prev_state = self._prev_state

            # StateMachineCore.process_candle() 签名为:
            #   process_candle(candle: pd.Series, context: dict) -> str
            # 需要将 dict 转换为 pd.Series，并提供 context
            candle_series = pd.Series(candle_data)
            candle_context = context if context is not None else {}

            # 返回值是 str（当前状态名），不是对象
            new_state = self._state_machine.process_candle(
                candle_series, candle_context
            )
            self._candle_count += 1

            # 从状态机读取当前状态的置信度和强度
            state_confidence = 0.0
            state_intensity = 0.0
            if new_state and hasattr(self._state_machine, "state_confidences"):
                state_confidence = self._state_machine.state_confidences.get(
                    new_state, 0.0
                )
            if new_state and hasattr(self._state_machine, "state_intensities"):
                state_intensity = self._state_machine.state_intensities.get(
                    new_state, 0.0
                )

            # 检测状态变化（修复 C-03：正确比较 str 状态）
            if new_state and prev_state is not None and prev_state != new_state:
                self._transition_count += 1
                self.emit_event(
                    "state_machine.state_changed",
                    {
                        "from_state": prev_state,
                        "to_state": new_state,
                        "confidence": state_confidence,
                    },
                )

            # 更新上一个状态
            self._prev_state = new_state

            self.emit_event(
                "state_machine.candle_processed",
                {
                    "candle_count": self._candle_count,
                    "has_result": new_state is not None,
                },
            )

            if new_state:
                return {
                    "state_name": new_state,
                    "confidence": state_confidence,
                    "intensity": state_intensity,
                }
            return None

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
        context_dict: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """处理多时间框架数据

        Args:
            timeframe_data: 各时间框架的DataFrame数据字典
            context_dict: 各时间框架的上下文字典，可选。
                          若未提供则使用空字典。

        Returns:
            Optional[Dict]: 多时间框架分析结果
        """
        if self._enhanced_sm is None:
            return None

        try:
            # EnhancedWyckoffStateMachine.process_multi_timeframe() 签名为:
            #   process_multi_timeframe(candles_dict, context_dict) -> dict
            contexts = context_dict if context_dict is not None else {}
            result = self._enhanced_sm.process_multi_timeframe(timeframe_data, contexts)
            return result
        except Exception as e:
            self._last_error = str(e)
            logger.error("Error processing multi-timeframe: %s", e)
            return None

    # === 信号生成 ===

    def generate_signals(self, df: Optional[pd.DataFrame] = None) -> Optional[Any]:
        """生成交易信号

        基于当前状态机的内部状态生成信号。
        注意：EnhancedWyckoffStateMachine.generate_signals() 不接受参数，
        它依赖 process_candle() 累积的内部状态。

        Args:
            df: 保留参数以维持 API 兼容性，实际不使用。
                信号基于状态机内部状态生成。

        Returns:
            信号列表 list[dict]，或 None
        """
        if self._enhanced_sm is None:
            return None

        try:
            # 修复 C-04: generate_signals() 不接受参数
            signals = self._enhanced_sm.generate_signals()
            if signals:
                self._signal_count += 1
                # signals 是 list[dict]，取第一个信号的类型用于事件
                first_signal_type = "unknown"
                if isinstance(signals, list) and len(signals) > 0:
                    first_signal_type = str(signals[0].get("type", "unknown"))
                elif isinstance(signals, dict):
                    first_signal_type = str(signals.get("type", "unknown"))
                self.emit_event(
                    "state_machine.signal_generated",
                    {
                        "signal_count": self._signal_count,
                        "signal_type": first_signal_type,
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
