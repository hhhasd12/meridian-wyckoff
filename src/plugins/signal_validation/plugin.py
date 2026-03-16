"""信号验证插件 - 整合突破验证、微观入场验证和冲突解决

将 BreakoutValidator、MicroEntryValidator 和 ConflictResolutionManager
封装为统一的插件接口，通过事件总线与其他插件通信。
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class SignalValidationPlugin(BasePlugin):
    """信号验证插件

    整合三个核心验证组件：
    1. BreakoutValidator - 突破检测与回踩验证
    2. MicroEntryValidator - 微观入场信号验证
    3. ConflictResolutionManager - 多周期冲突解决

    设计原则：
    - 懒加载：组件在 on_load() 时才导入和创建
    - 事件驱动：验证结果通过事件总线广播
    - 配置隔离：三个子组件各自独立配置
    """

    def __init__(self, name: str = "signal_validation") -> None:
        super().__init__(name)
        self._breakout_validator: Any = None
        self._micro_entry_validator: Any = None
        self._conflict_resolver: Any = None

        # 统计计数器
        self._breakout_detect_count: int = 0
        self._breakout_update_count: int = 0
        self._entry_validate_count: int = 0
        self._conflict_resolve_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件，初始化三个验证组件"""
        from src.plugins.signal_validation.breakout_validator import BreakoutValidator
        from src.plugins.signal_validation.conflict_resolver import ConflictResolutionManager
        from src.plugins.signal_validation.micro_entry_validator import MicroEntryValidator

        config = self._config or {}

        # 初始化突破验证器
        bv_config = config.get("breakout_validator", {})
        self._breakout_validator = BreakoutValidator(config=bv_config)

        # 初始化微观入场验证器
        me_config = config.get("micro_entry_validator", {})
        self._micro_entry_validator = MicroEntryValidator(config=me_config)

        # 初始化冲突解决管理器
        cr_config = config.get("conflict_resolver", {})
        self._conflict_resolver = ConflictResolutionManager(
            config=cr_config
        )

        # 订阅配置更新事件
        self.subscribe_event(
            "system.config_update", self._on_config_update
        )

        logger.info("信号验证插件加载完成")

    def on_unload(self) -> None:
        """卸载插件，清理所有组件"""
        self._breakout_validator = None
        self._micro_entry_validator = None
        self._conflict_resolver = None
        self._breakout_detect_count = 0
        self._breakout_update_count = 0
        self._entry_validate_count = 0
        self._conflict_resolve_count = 0
        self._last_error = None
        logger.info("信号验证插件已卸载")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """处理配置更新

        Args:
            new_config: 新的配置字典
        """
        if self._breakout_validator is not None:
            from src.plugins.signal_validation.breakout_validator import BreakoutValidator
            from src.plugins.signal_validation.conflict_resolver import (
                ConflictResolutionManager,
            )
            from src.plugins.signal_validation.micro_entry_validator import MicroEntryValidator

            bv_config = new_config.get("breakout_validator", {})
            self._breakout_validator = BreakoutValidator(config=bv_config)

            me_config = new_config.get("micro_entry_validator", {})
            self._micro_entry_validator = MicroEntryValidator(
                config=me_config
            )

            cr_config = new_config.get("conflict_resolver", {})
            self._conflict_resolver = ConflictResolutionManager(
                config=cr_config
            )

            logger.info("信号验证插件配置已更新")

    def _on_config_update(
        self, event_name: str, data: Dict[str, Any]
    ) -> None:
        """事件总线配置更新回调

        Args:
            event_name: 事件名称
            data: 事件数据
        """
        if "signal_validation" in data:
            self.on_config_update(data["signal_validation"])

    def health_check(self) -> HealthCheckResult:
        """健康检查

        Returns:
            HealthCheckResult: 健康检查结果
        """
        from src.kernel.types import PluginState

        if self._state != PluginState.ACTIVE:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="插件未处于活跃状态",
                details={"state": self._state.value},
            )

        components_ok = (
            self._breakout_validator is not None
            and self._micro_entry_validator is not None
            and self._conflict_resolver is not None
        )

        if not components_ok:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="部分验证组件未初始化",
                details={
                    "breakout_validator": (
                        self._breakout_validator is not None
                    ),
                    "micro_entry_validator": (
                        self._micro_entry_validator is not None
                    ),
                    "conflict_resolver": (
                        self._conflict_resolver is not None
                    ),
                },
            )

        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近有错误: {self._last_error}",
                details={
                    "last_error": self._last_error,
                    "breakout_detect_count": self._breakout_detect_count,
                    "entry_validate_count": self._entry_validate_count,
                    "conflict_resolve_count": (
                        self._conflict_resolve_count
                    ),
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="信号验证插件运行正常",
            details={
                "breakout_detect_count": self._breakout_detect_count,
                "breakout_update_count": self._breakout_update_count,
                "entry_validate_count": self._entry_validate_count,
                "conflict_resolve_count": self._conflict_resolve_count,
            },
        )

    # ==================== 突破验证 API ====================

    def detect_breakout(
        self,
        df: pd.DataFrame,
        resistance_level: float,
        support_level: float,
        current_atr: float,
    ) -> Optional[Dict[str, Any]]:
        """检测初始突破

        Args:
            df: 包含OHLCV数据的DataFrame
            resistance_level: 阻力位
            support_level: 支撑位
            current_atr: 当前ATR值

        Returns:
            突破信息字典，或None（无突破）

        Raises:
            RuntimeError: 当突破验证器未加载时
        """
        if self._breakout_validator is None:
            raise RuntimeError("突破验证器未加载")

        try:
            result = self._breakout_validator.detect_initial_breakout(
                df, resistance_level, support_level, current_atr
            )
            self._breakout_detect_count += 1

            if result is not None:
                self.emit_event(
                    "signal_validation.breakout_detected",
                    {
                        "breakout_id": result.get("breakout_id"),
                        "direction": result.get("direction"),
                        "breakout_price": result.get("breakout_price"),
                        "breakout_strength": result.get(
                            "breakout_strength"
                        ),
                        "volume_confirmation": result.get(
                            "volume_confirmation"
                        ),
                    },
                )

            return result

        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("突破检测失败: %s", e)
            raise

    def get_breakout_signal(
        self, breakout_id: str
    ) -> Dict[str, Any]:
        """获取突破信号状态

        Args:
            breakout_id: 突破记录ID

        Returns:
            突破信号状态字典

        Raises:
            RuntimeError: 当突破验证器未加载时
        """
        if self._breakout_validator is None:
            raise RuntimeError("突破验证器未加载")

        try:
            return self._breakout_validator.get_breakout_signal(
                breakout_id
            )
        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("获取突破信号失败: %s", e)
            raise

    def cleanup_old_breakouts(
        self, max_age_hours: int = 24
    ) -> None:
        """清理过期突破记录

        Args:
            max_age_hours: 最大保留时间（小时）

        Raises:
            RuntimeError: 当突破验证器未加载时
        """
        if self._breakout_validator is None:
            raise RuntimeError("突破验证器未加载")

        try:
            self._breakout_validator.cleanup_old_breakouts(
                max_age_hours
            )
        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("清理突破记录失败: %s", e)
            raise

    # ==================== 微观入场验证 API ====================

    def validate_entry(
        self,
        h4_structure: Dict[str, Any],
        m15_data: pd.DataFrame,
        m5_data: pd.DataFrame,
        macro_bias: str,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """验证微观入场信号

        Args:
            h4_structure: H4时间框架结构信息
            m15_data: M15数据DataFrame
            m5_data: M5数据DataFrame
            macro_bias: 宏观偏向（BULLISH/BEARISH/NEUTRAL）
            market_context: 市场上下文（可选）

        Returns:
            验证结果字典

        Raises:
            RuntimeError: 当微观入场验证器未加载时
        """
        if self._micro_entry_validator is None:
            raise RuntimeError("微观入场验证器未加载")

        try:
            result = self._micro_entry_validator.validate_entry(
                h4_structure,
                m15_data,
                m5_data,
                macro_bias,
                market_context,
            )
            self._entry_validate_count += 1

            self.emit_event(
                "signal_validation.entry_validated",
                {
                    "signal_type": str(
                        result.get("signal_type", "UNKNOWN")
                    ),
                    "is_valid": result.get("is_valid", False),
                    "confidence": result.get("confidence", 0.0),
                    "macro_bias": macro_bias,
                },
            )

            return result

        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("入场验证失败: %s", e)
            raise

    def get_validation_history(
        self, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取验证历史

        Args:
            limit: 返回记录数量限制

        Returns:
            验证历史列表

        Raises:
            RuntimeError: 当微观入场验证器未加载时
        """
        if self._micro_entry_validator is None:
            raise RuntimeError("微观入场验证器未加载")

        try:
            return self._micro_entry_validator.get_validation_history(
                limit
            )
        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("获取验证历史失败: %s", e)
            raise

    def clear_validation_history(self) -> None:
        """清除验证历史

        Raises:
            RuntimeError: 当微观入场验证器未加载时
        """
        if self._micro_entry_validator is None:
            raise RuntimeError("微观入场验证器未加载")

        try:
            self._micro_entry_validator.clear_history()
        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("清除验证历史失败: %s", e)
            raise

    # ==================== 冲突解决 API ====================

    def resolve_conflict(
        self,
        timeframe_states: Dict[str, Dict[str, Any]],
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """解决多周期冲突

        Args:
            timeframe_states: 各时间框架状态字典
            market_context: 市场上下文

        Returns:
            冲突解决决策字典

        Raises:
            RuntimeError: 当冲突解决器未加载时
        """
        if self._conflict_resolver is None:
            raise RuntimeError("冲突解决器未加载")

        try:
            result = self._conflict_resolver.resolve_conflict(
                timeframe_states, market_context
            )
            self._conflict_resolve_count += 1

            self.emit_event(
                "signal_validation.conflict_resolved",
                {
                    "conflict_type": result.get(
                        "conflict_type", "UNKNOWN"
                    ),
                    "primary_bias": str(
                        result.get("primary_bias", "NEUTRAL")
                    ),
                    "confidence": result.get("confidence", 0.0),
                    "risk_multiplier": result.get(
                        "risk_multiplier", 1.0
                    ),
                },
            )

            return result

        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("冲突解决失败: %s", e)
            raise

    def get_resolution_history(
        self, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取冲突解决历史

        Args:
            limit: 返回记录数量限制

        Returns:
            解决历史列表

        Raises:
            RuntimeError: 当冲突解决器未加载时
        """
        if self._conflict_resolver is None:
            raise RuntimeError("冲突解决器未加载")

        try:
            return self._conflict_resolver.get_resolution_history(
                limit
            )
        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("获取解决历史失败: %s", e)
            raise

    def clear_resolution_history(self) -> None:
        """清除冲突解决历史

        Raises:
            RuntimeError: 当冲突解决器未加载时
        """
        if self._conflict_resolver is None:
            raise RuntimeError("冲突解决器未加载")

        try:
            self._conflict_resolver.clear_history()
        except RuntimeError:
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.error("清除解决历史失败: %s", e)
            raise

    # ==================== 综合 API ====================

    def get_statistics(self) -> Dict[str, Any]:
        """获取综合统计信息

        Returns:
            包含三个组件统计的字典

        Raises:
            RuntimeError: 当组件未加载时
        """
        if self._breakout_validator is None:
            raise RuntimeError("信号验证插件未加载")

        stats: Dict[str, Any] = {
            "plugin_stats": {
                "breakout_detect_count": (
                    self._breakout_detect_count
                ),
                "breakout_update_count": (
                    self._breakout_update_count
                ),
                "entry_validate_count": (
                    self._entry_validate_count
                ),
                "conflict_resolve_count": (
                    self._conflict_resolve_count
                ),
                "last_error": self._last_error,
            }
        }

        try:
            stats["breakout_statistics"] = (
                self._breakout_validator.get_statistics()
            )
        except Exception as e:
            stats["breakout_statistics"] = {"error": str(e)}

        return stats

    def get_status_report(self) -> Dict[str, Any]:
        """获取状态报告

        Returns:
            包含所有组件状态的报告字典
        """
        report: Dict[str, Any] = {
            "plugin_name": self.name,
            "components": {
                "breakout_validator": (
                    self._breakout_validator is not None
                ),
                "micro_entry_validator": (
                    self._micro_entry_validator is not None
                ),
                "conflict_resolver": (
                    self._conflict_resolver is not None
                ),
            },
            "counters": {
                "breakout_detect_count": (
                    self._breakout_detect_count
                ),
                "breakout_update_count": (
                    self._breakout_update_count
                ),
                "entry_validate_count": (
                    self._entry_validate_count
                ),
                "conflict_resolve_count": (
                    self._conflict_resolve_count
                ),
            },
            "last_error": self._last_error,
        }

        return report
