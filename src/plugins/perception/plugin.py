"""
感知层插件 - K线物理属性分析、FVG缺口检测、针vs实体辩证识别

将 src/perception/ 下的三个模块封装为统一的插件接口：
- CandlePhysical: K线物理属性模型
- FVGDetector: FVG缺口检测器
- analyze_pin_vs_body: 针vs实体辩证分析函数
"""

import logging
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus, PluginState

logger = logging.getLogger(__name__)


class PerceptionPlugin(BasePlugin):
    """感知层插件 - 封装K线分析、FVG检测、针vs实体分析

    整合 src/perception/ 下的三个核心模块，通过事件总线
    发布分析结果，供下游插件（如 pattern_detection）消费。

    Attributes:
        _fvg_detector: FVG缺口检测器实例
        _analysis_count: 分析计数器
        _fvg_count: FVG检测计数器
        _last_error: 最近一次错误信息
    """

    def __init__(
        self,
        name: str = "perception",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """初始化感知层插件

        Args:
            name: 插件名称
            config: 插件配置
        """
        super().__init__(name=name, config=config)
        self._fvg_detector: Any = None
        self._analysis_count: int = 0
        self._fvg_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件 - 初始化FVG检测器"""
        from src.perception.fvg_detector import FVGDetector

        fvg_config = {
            "threshold_percent": self._config.get(
                "fvg_threshold_percent", 0.5
            ),
            "auto_threshold": self._config.get(
                "fvg_auto_threshold", True
            ),
            "max_gap_age_bars": self._config.get(
                "fvg_max_gap_age_bars", 100
            ),
        }
        self._fvg_detector = FVGDetector(config=fvg_config)
        self._analysis_count = 0
        self._fvg_count = 0
        self._last_error = None
        self._logger.info("感知层插件已加载，FVG检测器已初始化")

    def on_unload(self) -> None:
        """卸载插件 - 清理资源"""
        self._fvg_detector = None
        self._analysis_count = 0
        self._fvg_count = 0
        self._last_error = None
        self._logger.info("感知层插件已卸载")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """配置更新回调 - 重新初始化FVG检测器

        Args:
            new_config: 新的配置字典
        """
        self._config.update(new_config)
        if self._fvg_detector is not None:
            from src.perception.fvg_detector import FVGDetector

            fvg_config = {
                "threshold_percent": self._config.get(
                    "fvg_threshold_percent", 0.5
                ),
                "auto_threshold": self._config.get(
                    "fvg_auto_threshold", True
                ),
                "max_gap_age_bars": self._config.get(
                    "fvg_max_gap_age_bars", 100
                ),
            }
            self._fvg_detector = FVGDetector(config=fvg_config)
            self._logger.info("FVG检测器已根据新配置重新初始化")

    def health_check(self) -> HealthCheckResult:
        """健康检查

        Returns:
            HealthCheckResult: 健康检查结果
        """
        if self._state != PluginState.ACTIVE:
            return HealthCheckResult(
                status=HealthStatus.UNKNOWN,
                message=f"插件状态: {self._state.value}",
                details={"state": self._state.value},
            )

        if self._fvg_detector is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="FVG检测器未初始化",
                details={"fvg_detector": None},
            )

        if self._last_error:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近错误: {self._last_error}",
                details={
                    "last_error": self._last_error,
                    "analysis_count": self._analysis_count,
                    "fvg_count": self._fvg_count,
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="感知层插件运行正常",
            details={
                "analysis_count": self._analysis_count,
                "fvg_count": self._fvg_count,
            },
        )

    def analyze_candle(
        self,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> Dict[str, Any]:
        """分析单根K线的物理属性

        Args:
            open_price: 开盘价
            high: 最高价
            low: 最低价
            close: 收盘价
            volume: 成交量

        Returns:
            Dict: K线物理属性分析结果

        Raises:
            RuntimeError: 插件未加载时调用
        """
        if self._state != PluginState.ACTIVE:
            raise RuntimeError("感知层插件未加载，无法分析K线")

        try:
            from src.perception.candle_physical import CandlePhysical

            candle = CandlePhysical(
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )

            result = {
                "body": candle.body,
                "body_direction": candle.body_direction,
                "upper_shadow": candle.upper_shadow,
                "lower_shadow": candle.lower_shadow,
                "body_ratio": candle.body_ratio,
                "shadow_ratio": candle.shadow_ratio,
            }

            self._analysis_count += 1
            self.emit_event(
                "perception.candle_analyzed",
                {"result": result, "symbol": "unknown"},
            )
            return result

        except Exception as e:
            self._last_error = str(e)
            self._logger.error("K线分析失败: %s", e)
            raise

    def detect_fvg(
        self,
        df: pd.DataFrame,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """检测FVG缺口

        Args:
            df: 包含OHLCV数据的DataFrame
            context: 可选的上下文信息

        Returns:
            List: 检测到的FVG缺口列表

        Raises:
            RuntimeError: 插件未加载时调用
        """
        if self._state != PluginState.ACTIVE:
            raise RuntimeError("感知层插件未加载，无法检测FVG")

        if self._fvg_detector is None:
            raise RuntimeError("FVG检测器未初始化")

        try:
            gaps = self._fvg_detector.detect_fvg_gaps(
                df, context=context
            )
            self._fvg_count += len(gaps)

            for gap in gaps:
                self.emit_event(
                    "perception.fvg_detected",
                    {
                        "gap_id": gap.gap_id,
                        "direction": gap.direction.value,
                        "max_price": gap.max_price,
                        "min_price": gap.min_price,
                        "confidence": gap.confidence,
                    },
                )

            return gaps

        except Exception as e:
            self._last_error = str(e)
            self._logger.error("FVG检测失败: %s", e)
            raise

    def analyze_pin_vs_body(
        self,
        candle: Union[Any, Dict[str, float]],
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """针vs实体辩证分析

        Args:
            candle: CandlePhysical实例或包含OHLCV的字典
            context: 分析上下文

        Returns:
            PinBodyAnalysisResult: 分析结果

        Raises:
            RuntimeError: 插件未加载时调用
        """
        if self._state != PluginState.ACTIVE:
            raise RuntimeError("感知层插件未加载，无法分析针vs实体")

        try:
            from src.perception.pin_body_analyzer import (
                analyze_pin_vs_body,
            )

            result = analyze_pin_vs_body(candle, context)

            self._analysis_count += 1
            self.emit_event(
                "perception.pin_body_analyzed",
                {
                    "is_pin_dominant": result.is_pin_dominant,
                    "is_body_dominant": result.is_body_dominant,
                    "pin_strength": result.pin_strength,
                    "body_strength": result.body_strength,
                    "confidence": result.confidence,
                },
            )

            return result

        except Exception as e:
            self._last_error = str(e)
            self._logger.error("针vs实体分析失败: %s", e)
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """获取插件统计信息

        Returns:
            Dict: 统计信息
        """
        stats: Dict[str, Any] = {
            "analysis_count": self._analysis_count,
            "fvg_count": self._fvg_count,
            "last_error": self._last_error,
        }

        if self._fvg_detector is not None:
            try:
                fvg_stats = self._fvg_detector.get_statistics()
                stats["fvg_statistics"] = fvg_stats
            except Exception as e:
                stats["fvg_statistics_error"] = str(e)

        return stats
