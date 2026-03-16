"""
周期权重系统插件

封装 PeriodWeightFilter，提供多时间框架权重分配与加权决策功能。
通过插件架构实现事件驱动和配置热更新。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class WeightSystemPlugin(BasePlugin):
    """周期权重系统插件

    封装 PeriodWeightFilter，提供以下功能：
    1. 获取指定市场体制下的时间框架权重
    2. 计算多周期加权分数
    3. 生成加权决策
    4. 推荐关注的时间框架
    5. 获取配置报告
    """

    def __init__(self, name: str = "weight_system") -> None:
        super().__init__(name)
        self._weight_filter = None
        self._weights_calc_count: int = 0
        self._score_calc_count: int = 0
        self._decision_count: int = 0
        self._recommend_count: int = 0
        self._last_error: Optional[str] = None

    def on_load(self) -> None:
        """加载插件，初始化 PeriodWeightFilter"""
        from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter

        config = self._config or {}
        filter_config = {}

        # 传递权重配置
        if "weights" in config:
            filter_config["weights"] = config["weights"]
        if "regime_adjustments" in config:
            filter_config["regime_adjustments"] = config["regime_adjustments"]
        if "normalize" in config:
            filter_config["normalize"] = config["normalize"]
        if "min_weight" in config:
            filter_config["min_weight"] = config["min_weight"]

        self._weight_filter = PeriodWeightFilter(
            config=filter_config if filter_config else None
        )

        logger.info("WeightSystemPlugin 加载完成")

    def on_unload(self) -> None:
        """卸载插件，清理资源"""
        self._weight_filter = None
        self._weights_calc_count = 0
        self._score_calc_count = 0
        self._decision_count = 0
        self._recommend_count = 0
        self._last_error = None
        logger.info("WeightSystemPlugin 已卸载")

    def on_config_update(self, new_config: Dict[str, Any]) -> None:
        """配置更新时重新创建 PeriodWeightFilter

        Args:
            new_config: 新的配置字典
        """
        if self._weight_filter is not None:
            from src.plugins.weight_system.period_weight_filter import PeriodWeightFilter

            filter_config = {}
            if "weights" in new_config:
                filter_config["weights"] = new_config["weights"]
            if "regime_adjustments" in new_config:
                filter_config["regime_adjustments"] = (
                    new_config["regime_adjustments"]
                )
            if "normalize" in new_config:
                filter_config["normalize"] = new_config["normalize"]
            if "min_weight" in new_config:
                filter_config["min_weight"] = new_config["min_weight"]

            self._weight_filter = PeriodWeightFilter(
                config=filter_config if filter_config else None
            )
            logger.info("WeightSystemPlugin 配置已更新")

    def health_check(self) -> HealthCheckResult:
        """健康检查

        Returns:
            HealthCheckResult: 健康检查结果
        """
        from src.kernel.types import PluginState

        if self._state != PluginState.ACTIVE:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"插件状态异常: {self._state}",
            )

        if self._weight_filter is None:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="PeriodWeightFilter 未初始化",
            )

        if self._last_error is not None:
            return HealthCheckResult(
                status=HealthStatus.DEGRADED,
                message=f"最近发生错误: {self._last_error}",
                details={
                    "weights_calc_count": self._weights_calc_count,
                    "score_calc_count": self._score_calc_count,
                    "decision_count": self._decision_count,
                    "recommend_count": self._recommend_count,
                    "last_error": self._last_error,
                },
            )

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="周期权重系统运行正常",
            details={
                "weights_calc_count": self._weights_calc_count,
                "score_calc_count": self._score_calc_count,
                "decision_count": self._decision_count,
                "recommend_count": self._recommend_count,
            },
        )

    def get_weights(
        self, regime: str = "UNKNOWN"
    ) -> Dict[str, float]:
        """获取指定市场体制下的权重

        Args:
            regime: 市场体制字符串

        Returns:
            各时间框架的权重字典（键为字符串形式）

        Raises:
            RuntimeError: 当插件未加载时
        """
        if self._weight_filter is None:
            raise RuntimeError("WeightSystemPlugin 未加载，无法获取权重")

        try:
            raw_weights = self._weight_filter.get_weights(regime)
            # 转换 Timeframe 枚举键为字符串
            result = {tf.value: w for tf, w in raw_weights.items()}
            self._weights_calc_count += 1

            self.emit_event("weights_calculated", {
                "regime": regime,
                "weights": result,
            })

            return result
        except Exception as e:
            self._last_error = str(e)
            logger.error("获取权重失败: %s", e)
            raise

    def calculate_weighted_score(
        self,
        timeframe_scores: Dict[str, float],
        regime: str = "UNKNOWN",
    ) -> float:
        """计算多周期加权分数

        Args:
            timeframe_scores: 各时间框架的分数字典
            regime: 市场体制

        Returns:
            加权总分（0-1范围）

        Raises:
            RuntimeError: 当插件未加载时
        """
        if self._weight_filter is None:
            raise RuntimeError(
                "WeightSystemPlugin 未加载，无法计算加权分数"
            )

        try:
            score = self._weight_filter.calculate_weighted_score(
                timeframe_scores, regime
            )
            self._score_calc_count += 1

            self.emit_event("weighted_score_calculated", {
                "regime": regime,
                "score": score,
                "input_count": len(timeframe_scores),
            })

            return score
        except Exception as e:
            self._last_error = str(e)
            logger.error("计算加权分数失败: %s", e)
            raise

    def get_weighted_decision(
        self,
        timeframe_decisions: Dict[str, Dict[str, Any]],
        regime: str = "UNKNOWN",
    ) -> Dict[str, Any]:
        """生成加权决策

        Args:
            timeframe_decisions: 各时间框架的决策字典
            regime: 市场体制

        Returns:
            加权决策字典

        Raises:
            RuntimeError: 当插件未加载时
        """
        if self._weight_filter is None:
            raise RuntimeError(
                "WeightSystemPlugin 未加载，无法生成加权决策"
            )

        try:
            decision = self._weight_filter.get_weighted_decision(
                timeframe_decisions, regime
            )
            self._decision_count += 1

            self.emit_event("weighted_decision_made", {
                "regime": regime,
                "primary_bias": decision.get("primary_bias"),
                "confidence": decision.get("confidence"),
            })

            return decision
        except Exception as e:
            self._last_error = str(e)
            logger.error("生成加权决策失败: %s", e)
            raise

    def recommend_timeframe_focus(
        self,
        regime: str = "UNKNOWN",
        bias: str = "NEUTRAL",
    ) -> List[Tuple[str, float]]:
        """推荐应关注的时间框架

        Args:
            regime: 市场体制
            bias: 交易偏向

        Returns:
            时间框架和权重列表，按权重降序排列

        Raises:
            RuntimeError: 当插件未加载时
        """
        if self._weight_filter is None:
            raise RuntimeError(
                "WeightSystemPlugin 未加载，无法推荐时间框架"
            )

        try:
            recommendations = (
                self._weight_filter.recommend_timeframe_focus(
                    regime, bias
                )
            )
            self._recommend_count += 1

            self.emit_event("timeframe_focus_recommended", {
                "regime": regime,
                "bias": bias,
                "top_timeframe": (
                    recommendations[0][0]
                    if recommendations
                    else None
                ),
            })

            return recommendations
        except Exception as e:
            self._last_error = str(e)
            logger.error("推荐时间框架失败: %s", e)
            raise

    def get_config_report(self) -> Dict[str, Any]:
        """获取配置报告

        Returns:
            配置报告字典

        Raises:
            RuntimeError: 当插件未加载时
        """
        if self._weight_filter is None:
            raise RuntimeError(
                "WeightSystemPlugin 未加载，无法获取配置报告"
            )

        return self._weight_filter.get_config_report()

    def get_statistics(self) -> Dict[str, Any]:
        """获取插件统计信息

        Returns:
            统计信息字典
        """
        return {
            "weights_calc_count": self._weights_calc_count,
            "score_calc_count": self._score_calc_count,
            "decision_count": self._decision_count,
            "recommend_count": self._recommend_count,
            "last_error": self._last_error,
            "filter_loaded": self._weight_filter is not None,
        }
