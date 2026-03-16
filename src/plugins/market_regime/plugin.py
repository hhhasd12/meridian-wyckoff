"""市场体制检测插件

将 RegimeDetector 包装为标准插件，提供：
1. 生命周期管理（on_load / on_unload）
2. 事件驱动：订阅 data_pipeline.ohlcv_ready，发布 market_regime.detected
3. 配置热更新
4. 健康检查
"""

import logging
from typing import Any, Dict, Optional

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus
from src.plugins.market_regime.detector import (
    MarketRegime,
    RegimeDetector,
)

logger = logging.getLogger(__name__)


class MarketRegimePlugin(BasePlugin):
    """市场体制检测插件

    封装 RegimeDetector，通过事件总线与其他插件通信。
    当收到 OHLCV 数据就绪事件时自动执行体制检测，
    并将结果通过 market_regime.detected 事件广播。

    Attributes:
        detector: RegimeDetector 实例
        _last_regime: 上一次检测到的体制
    """

    def __init__(
        self,
        name: str = "market_regime",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name=name, config=config)
        self.detector: Optional[RegimeDetector] = None
        self._last_regime: Optional[MarketRegime] = None

    def on_load(self) -> None:
        """加载插件：初始化 RegimeDetector 并订阅事件"""
        self.detector = RegimeDetector(config=self._config)
        self._last_regime = None

        # 订阅数据就绪事件
        self.subscribe_event(
            "data_pipeline.ohlcv_ready",
            self._on_ohlcv_ready,
        )

        self._logger.info(
            "MarketRegimePlugin 已加载，配置: "
            "atr_period=%s, adx_period=%s, "
            "trending_threshold=%s",
            self._config.get("atr_period", 14),
            self._config.get("adx_period", 14),
            self._config.get("trending_threshold", 25.0),
        )

    def on_unload(self) -> None:
        """卸载插件：清理资源"""
        self.detector = None
        self._last_regime = None
        self._logger.info("MarketRegimePlugin 已卸载")

    def on_config_update(
        self, new_config: Dict[str, Any]
    ) -> None:
        """配置热更新：重新创建 RegimeDetector"""
        self._config = new_config
        if self.detector is not None:
            self.detector = RegimeDetector(config=new_config)
            self._logger.info(
                "MarketRegimePlugin 配置已热更新"
            )

    def health_check(self) -> HealthCheckResult:
        """健康检查：验证 detector 是否正常"""
        base_check = super().health_check()
        if base_check.status != HealthStatus.HEALTHY:
            return base_check

        if self.detector is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="RegimeDetector 未初始化",
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message=(
                f"运行正常，当前体制: "
                f"{self._last_regime.value if self._last_regime else 'N/A'}"
            ),
        )

    # ---- 公共 API ----

    def detect(self, df: pd.DataFrame) -> Dict:
        """手动触发体制检测

        Args:
            df: 包含OHLCV数据的DataFrame

        Returns:
            检测结果字典

        Raises:
            RuntimeError: 当插件未加载时
        """
        if self.detector is None:
            raise RuntimeError(
                "MarketRegimePlugin 未加载，无法执行检测"
            )

        result = self.detector.detect_regime(df)
        self._publish_result(result)
        return result

    def get_current_regime(self) -> Dict:
        """获取当前体制状态"""
        if self.detector is None:
            return {
                "regime": MarketRegime.UNKNOWN,
                "confidence": 0.0,
                "timestamp": None,
            }
        return self.detector.get_current_regime()

    def get_regime_history(
        self, n: int = 50
    ) -> list:
        """获取体制历史"""
        if self.detector is None:
            return []
        return self.detector.get_regime_history(n)

    # ---- 事件处理 ----

    def _on_ohlcv_ready(
        self,
        event_name: str,
        data: Dict[str, Any],
    ) -> None:
        """处理 OHLCV 数据就绪事件

        Args:
            event_name: 事件名称
            data: 事件数据，应包含 'df' 键
        """
        df = data.get("df")
        if df is None or not isinstance(df, pd.DataFrame):
            self._logger.warning(
                "收到 ohlcv_ready 事件但缺少有效的 DataFrame"
            )
            return

        if self.detector is None:
            self._logger.warning(
                "detector 未初始化，跳过检测"
            )
            return

        try:
            result = self.detector.detect_regime(df)
            self._publish_result(result)
        except (ValueError, KeyError) as e:
            self._logger.error(
                "体制检测失败: %s", e
            )

    def _publish_result(self, result: Dict) -> None:
        """发布检测结果事件"""
        # 发布检测完成事件
        self.emit_event(
            "market_regime.detected",
            {
                "regime": result["regime"].value,
                "confidence": result["confidence"],
                "reasons": result.get("reasons", []),
                "timestamp": str(
                    result.get("timestamp", "")
                ),
            },
        )

        # 如果体制发生变化，额外发布变化事件
        new_regime = result["regime"]
        if (
            self._last_regime is not None
            and new_regime != self._last_regime
        ):
            self.emit_event(
                "market_regime.changed",
                {
                    "old_regime": self._last_regime.value,
                    "new_regime": new_regime.value,
                    "confidence": result["confidence"],
                },
            )
            self._logger.info(
                "市场体制变化: %s -> %s (置信度: %.2f)",
                self._last_regime.value,
                new_regime.value,
                result["confidence"],
            )

        self._last_regime = new_regime
