"""
形态检测插件 - 整合TR识别、威科夫阶段检测和曲线边界拟合

包装以下核心模块（已迁移到插件目录）：
- src/plugins/pattern_detection/tr_detector.py (TRDetector)
- src/plugins/pattern_detection/wyckoff_phase_detector.py (WyckoffPhaseDetector)
- src/plugins/pattern_detection/curve_boundary.py (CurveBoundaryFitter)
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class PatternDetectionPlugin(BasePlugin):
    """形态检测插件

    整合交易区间识别、威科夫阶段检测和曲线边界拟合三大功能，
    通过事件总线发布检测结果。

    设计原则：
    1. 懒加载：仅在 on_load() 时导入底层模块
    2. 委托模式：所有检测逻辑委托给底层检测器
    3. 事件驱动：检测结果通过事件总线发布
    4. 统计追踪：记录各类检测的调用次数
    """

    def __init__(self, name: str = "pattern_detection") -> None:
        super().__init__(name)
        self._tr_detector: Optional[Any] = None
        self._phase_detector: Optional[Any] = None
        self._boundary_fitter: Optional[Any] = None
        self._tr_detect_count: int = 0
        self._phase_detect_count: int = 0
        self._boundary_fit_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件，初始化三个检测器"""
        from src.plugins.pattern_detection.tr_detector import TRDetector
        from src.plugins.pattern_detection.wyckoff_phase_detector import WyckoffPhaseDetector
        from src.plugins.pattern_detection.curve_boundary import CurveBoundaryFitter

        config = self._config or {}

        tr_config = config.get("tr_detector", {})
        phase_config = config.get("wyckoff_phase", {})
        boundary_config = config.get("curve_boundary", {})

        self._tr_detector = TRDetector(tr_config)
        self._phase_detector = WyckoffPhaseDetector(phase_config)
        self._boundary_fitter = CurveBoundaryFitter(boundary_config)

        logger.info("形态检测插件加载完成")

    def on_unload(self) -> None:
        """卸载插件，清理资源"""
        self._tr_detector = None
        self._phase_detector = None
        self._boundary_fitter = None
        self._tr_detect_count = 0
        self._phase_detect_count = 0
        self._boundary_fit_count = 0
        self._last_error = None
        logger.info("形态检测插件已卸载")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """配置更新时重新创建检测器

        Args:
            new_config: 新的配置字典
        """
        if self._tr_detector is not None:
            from src.plugins.pattern_detection.tr_detector import TRDetector
            from src.plugins.pattern_detection.wyckoff_phase_detector import (
                WyckoffPhaseDetector,
            )
            from src.plugins.pattern_detection.curve_boundary import CurveBoundaryFitter

            tr_config = new_config.get("tr_detector", {})
            phase_config = new_config.get("wyckoff_phase", {})
            boundary_config = new_config.get("curve_boundary", {})

            self._tr_detector = TRDetector(tr_config)
            self._phase_detector = WyckoffPhaseDetector(phase_config)
            self._boundary_fitter = CurveBoundaryFitter(boundary_config)

            logger.info("形态检测插件配置已更新")

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
            )

        if self._tr_detector is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="TR检测器未初始化",
            )

        if self._phase_detector is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="威科夫阶段检测器未初始化",
            )

        if self._boundary_fitter is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="曲线边界拟合器未初始化",
            )

        if self._last_error is not None:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近有错误: {self._last_error}",
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=(
                f"正常运行 - TR检测:{self._tr_detect_count}次, "
                f"阶段检测:{self._phase_detect_count}次, "
                f"边界拟合:{self._boundary_fit_count}次"
            ),
        )

    def detect_trading_range(
        self, df: pd.DataFrame
    ) -> Dict[str, Any]:
        """检测交易区间

        Args:
            df: 包含OHLCV数据的DataFrame

        Returns:
            Dict: TR检测结果

        Raises:
            RuntimeError: 插件未加载时
        """
        if self._tr_detector is None:
            raise RuntimeError("形态检测插件未加载，无法检测TR")

        try:
            result = self._tr_detector.detect_trading_range(df)
            self._tr_detect_count += 1
            self._last_error = None

            self.emit_event(
                "pattern_detection.tr_detected",
                {
                    "status": result.status.value
                    if hasattr(result, "status")
                    else "UNKNOWN",
                    "confidence": result.confidence
                    if hasattr(result, "confidence")
                    else 0.0,
                },
            )

            return result
        except Exception as e:
            self._last_error = str(e)
            logger.error("TR检测失败: %s", e)
            raise

    def detect_wyckoff_phases(
        self,
        candle: pd.Series,
        context: Dict[str, Any],
        current_state: str = "IDLE",
    ) -> Dict[str, Dict[str, Any]]:
        """检测威科夫阶段

        Args:
            candle: 当前K线数据
            context: 上下文信息（TR边界、趋势方向等）
            current_state: 当前状态

        Returns:
            Dict: 各威科夫阶段的检测结果

        Raises:
            RuntimeError: 插件未加载时
        """
        if self._phase_detector is None:
            raise RuntimeError(
                "形态检测插件未加载，无法检测威科夫阶段"
            )

        try:
            results = self._phase_detector.detect(
                candle, context, current_state
            )
            self._phase_detect_count += 1
            self._last_error = None

            # 找出置信度最高的阶段
            best_phase = None
            best_confidence = 0.0
            for phase_name, phase_result in results.items():
                conf = phase_result.get("confidence", 0.0)
                if conf > best_confidence:
                    best_confidence = conf
                    best_phase = phase_name

            self.emit_event(
                "pattern_detection.wyckoff_phase_detected",
                {
                    "best_phase": best_phase,
                    "best_confidence": best_confidence,
                    "phase_count": len(results),
                },
            )

            return results
        except Exception as e:
            self._last_error = str(e)
            logger.error("威科夫阶段检测失败: %s", e)
            raise

    def fit_boundary(
        self, df: pd.DataFrame
    ) -> Dict[str, Any]:
        """拟合曲线边界

        Args:
            df: 包含OHLCV数据的DataFrame

        Returns:
            Dict: 边界拟合结果

        Raises:
            RuntimeError: 插件未加载时
        """
        if self._boundary_fitter is None:
            raise RuntimeError(
                "形态检测插件未加载，无法拟合边界"
            )

        try:
            # 检测枢轴点
            pivots = self._boundary_fitter.detect_pivot_points(
                df["close"]
            )

            result = {
                "pivots": pivots,
                "boundary_history": (
                    self._boundary_fitter.get_boundary_history()
                ),
                "current_boundary": (
                    self._boundary_fitter.get_current_boundary()
                ),
            }

            self._boundary_fit_count += 1
            self._last_error = None

            self.emit_event(
                "pattern_detection.boundary_fitted",
                {
                    "high_count": len(pivots.get("highs", [])),
                    "low_count": len(pivots.get("lows", [])),
                },
            )

            return result
        except Exception as e:
            self._last_error = str(e)
            logger.error("曲线边界拟合失败: %s", e)
            raise

    def get_tr_signals(
        self, current_price: float
    ) -> Dict[str, Any]:
        """获取TR信号

        Args:
            current_price: 当前价格

        Returns:
            Dict: TR信号数据

        Raises:
            RuntimeError: 插件未加载时
        """
        if self._tr_detector is None:
            raise RuntimeError(
                "形态检测插件未加载，无法获取TR信号"
            )

        try:
            signals = self._tr_detector.get_tr_signals(
                current_price
            )
            self._last_error = None

            self.emit_event(
                "pattern_detection.tr_signals",
                {"price": current_price},
            )

            return signals
        except Exception as e:
            self._last_error = str(e)
            logger.error("获取TR信号失败: %s", e)
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """获取插件统计信息

        Returns:
            Dict: 统计信息
        """
        stats: Dict[str, Any] = {
            "tr_detect_count": self._tr_detect_count,
            "phase_detect_count": self._phase_detect_count,
            "boundary_fit_count": self._boundary_fit_count,
            "last_error": self._last_error,
        }

        if self._tr_detector is not None:
            try:
                stats["tr_statistics"] = (
                    self._tr_detector.get_statistics()
                )
            except Exception:
                stats["tr_statistics"] = {}

        return stats
