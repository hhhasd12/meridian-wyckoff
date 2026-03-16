"""
周期权重过滤器模块
实现多周期融合中的时间框架权重分配算法

设计原则：
1. 默认权重分配：周线(25%)→日线(20%)→4小时(18%)→1小时(15%)→15分钟(12%)→5分钟(10%)
2. 动态调整：根据市场体制（趋势/盘整）调整权重分布
3. 冲突解决：为冲突检测模块提供权重基础
4. 可配置：所有权重可通过配置调整，纳入自动进化范围
"""

from enum import Enum
from typing import Any, Optional


class Timeframe(Enum):
    """时间框架枚举"""

    WEEKLY = "W"  # 周线
    DAILY = "D"  # 日线
    H8 = "H8"  # 8小时
    H4 = "H4"  # 4小时
    H1 = "H1"  # 1小时
    M15 = "M15"  # 15分钟
    M5 = "M5"  # 5分钟

    @classmethod
    def get_all(cls) -> list["Timeframe"]:
        """获取所有时间框架（按周期从大到小排序）"""
        return [cls.WEEKLY, cls.DAILY, cls.H8, cls.H4, cls.H1, cls.M15, cls.M5]

    @classmethod
    def get_timeframe_order(cls) -> list[str]:
        """获取时间框架顺序列表（字符串形式）"""
        return [tf.value for tf in cls.get_all()]

    @classmethod
    def from_string(cls, tf_str: str) -> "Timeframe":
        """从字符串转换为Timeframe枚举"""
        tf_str_upper = tf_str.upper()
        for tf in cls.get_all():
            if tf.value == tf_str_upper:
                return tf
        raise ValueError(f"未知的时间框架: {tf_str}")


class PeriodWeightFilter:
    """
    周期权重过滤器

    功能：
    1. 管理各时间框架的默认权重
    2. 根据市场体制动态调整权重
    3. 计算多周期加权分数
    4. 提供冲突解决中的权重基础
    """

    # 默认权重配置（合计100%）
    DEFAULT_WEIGHTS = {
        Timeframe.WEEKLY: 0.22,  # 22% - 战略方向
        Timeframe.DAILY: 0.18,  # 18% - 战术背景
        Timeframe.H8: 0.15,  # 15% - 中期趋势
        Timeframe.H4: 0.14,  # 14% - 中期动量
        Timeframe.H1: 0.12,  # 12% - 短期结构
        Timeframe.M15: 0.10,  # 10% - 入场时机
        Timeframe.M5: 0.09,  # 9% - 精确点位
    }

    # 市场体制权重调整系数
    # 趋势市：加大大周期权重，减小小周期权重
    # 盘整市：均衡各周期权重，侧重中短周期
    # 高波动市：减小大周期权重，加大短周期权重（快速反应）
    REGIME_ADJUSTMENTS = {
        "TRENDING": {
            Timeframe.WEEKLY: 1.2,  # +20%
            Timeframe.DAILY: 1.15,  # +15%
            Timeframe.H8: 1.1,  # +10%
            Timeframe.H4: 1.0,  # 不变
            Timeframe.H1: 0.9,  # -10%
            Timeframe.M15: 0.8,  # -20%
            Timeframe.M5: 0.7,  # -30%
        },
        "RANGING": {
            Timeframe.WEEKLY: 0.8,  # -20%
            Timeframe.DAILY: 0.85,  # -15%
            Timeframe.H8: 0.95,  # -5%
            Timeframe.H4: 1.1,  # +10%
            Timeframe.H1: 1.2,  # +20%
            Timeframe.M15: 1.15,  # +15%
            Timeframe.M5: 1.0,  # 不变
        },
        "VOLATILE": {
            Timeframe.WEEKLY: 0.7,  # -30%
            Timeframe.DAILY: 0.75,  # -25%
            Timeframe.H8: 0.85,  # -15%
            Timeframe.H4: 1.0,  # 不变
            Timeframe.H1: 1.1,  # +10%
            Timeframe.M15: 1.2,  # +20%
            Timeframe.M5: 1.3,  # +30%
        },
        "UNKNOWN": {
            # 未知市场体制时使用默认权重（无调整）
            Timeframe.WEEKLY: 1.0,
            Timeframe.DAILY: 1.0,
            Timeframe.H8: 1.0,
            Timeframe.H4: 1.0,
            Timeframe.H1: 1.0,
            Timeframe.M15: 1.0,
            Timeframe.M5: 1.0,
        },
    }

    def __init__(self, config: Optional[dict] = None):
        """
        初始化周期权重过滤器

        Args:
            config: 配置字典，包含以下参数：
                - weights: 自定义权重字典，覆盖默认权重
                - regime_adjustments: 自定义市场体制调整系数
                - normalize: 是否归一化权重（默认True）
                - min_weight: 最小权重限制（默认0.05）
        """
        self.config = config or {}

        # 加载权重配置
        self.weights = self.DEFAULT_WEIGHTS.copy()
        if "weights" in self.config:
            custom_weights = self.config["weights"]
            for tf_str, weight in custom_weights.items():
                tf = Timeframe.from_string(tf_str)
                self.weights[tf] = weight

        # 加载市场体制调整系数
        self.regime_adjustments = self.REGIME_ADJUSTMENTS.copy()
        if "regime_adjustments" in self.config:
            self.regime_adjustments.update(self.config["regime_adjustments"])

        # 其他配置
        self.normalize = self.config.get("normalize", True)
        self.min_weight = self.config.get("min_weight", 0.05)

        # 验证权重
        self._validate_weights()

    def _validate_weights(self) -> None:
        """验证权重配置的合理性"""
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01 and self.normalize:
            # 自动归一化
            self._normalize_weights()

        # 检查权重范围
        for tf, weight in self.weights.items():
            if weight < 0:
                raise ValueError(f"时间框架 {tf.value} 的权重不能为负: {weight}")
            if weight < self.min_weight:
                self.weights[tf] = self.min_weight

    def _normalize_weights(self) -> None:
        """归一化权重，使总和为1"""
        total = sum(self.weights.values())
        if total > 0:
            for tf in self.weights:
                self.weights[tf] /= total

    def get_weights(self, regime: str = "UNKNOWN") -> dict[Timeframe, float]:
        """
        获取指定市场体制下的权重

        Args:
            regime: 市场体制，可选值: "TRENDING", "RANGING", "VOLATILE", "UNKNOWN"

        Returns:
            各时间框架的权重字典
        """
        if regime not in self.regime_adjustments:
            regime = "UNKNOWN"

        adjustments = self.regime_adjustments[regime]
        adjusted_weights = {}

        for tf in Timeframe.get_all():
            base_weight = self.weights.get(tf, 0.0)
            adjustment = adjustments.get(tf, 1.0)
            adjusted_weight = base_weight * adjustment
            adjusted_weights[tf] = max(adjusted_weight, self.min_weight)

        # 归一化
        if self.normalize:
            total = sum(adjusted_weights.values())
            if total > 0:
                for tf in adjusted_weights:
                    adjusted_weights[tf] /= total

        # 归一化后再次确保最小权重（防止归一化后权重低于最小权重）
        # 使用更稳健的算法：对于任何低于最小权重的权重，设置为最小值，然后按比例调整其他权重
        if self.normalize:
            # 检查哪些权重需要调整
            underweight_timeframes = []
            for tf in adjusted_weights:
                if adjusted_weights[tf] < self.min_weight:
                    underweight_timeframes.append(tf)

            if underweight_timeframes:
                # 计算需要增加的总权重
                total_increase = 0
                for tf in underweight_timeframes:
                    total_increase += self.min_weight - adjusted_weights[tf]

                # 从其他权重中按比例扣除
                overweight_timeframes = [
                    tf for tf in adjusted_weights if tf not in underweight_timeframes
                ]
                if overweight_timeframes:
                    # 计算超重权重的总和
                    overweight_total = sum(
                        adjusted_weights[tf] for tf in overweight_timeframes
                    )
                    if overweight_total > 0:
                        # 按比例减少超重权重
                        for tf in overweight_timeframes:
                            adjusted_weights[tf] -= total_increase * (
                                adjusted_weights[tf] / overweight_total
                            )

                # 设置权重为最小值
                for tf in underweight_timeframes:
                    adjusted_weights[tf] = self.min_weight

                # 最终归一化以确保总和为1（由于浮点精度）
                total = sum(adjusted_weights.values())
                if abs(total - 1.0) > 1e-12:
                    for tf in adjusted_weights:
                        adjusted_weights[tf] /= total

        return adjusted_weights

    def calculate_weighted_score(
        self, timeframe_scores: dict[str, float], regime: str = "UNKNOWN"
    ) -> float:
        """
        计算多周期加权分数

        Args:
            timeframe_scores: 各时间框架的分数字典，键为时间框架字符串（如"W", "D", "H4"等）
            regime: 市场体制

        Returns:
            加权总分（0-1范围）
        """
        weights = self.get_weights(regime)
        total_weight = 0.0
        weighted_sum = 0.0

        for tf_str, score in timeframe_scores.items():
            try:
                tf = Timeframe.from_string(tf_str)
                weight = weights.get(tf, 0.0)
                weighted_sum += score * weight
                total_weight += weight
            except ValueError:
                # 忽略未知时间框架
                continue

        if total_weight > 0:
            return weighted_sum / total_weight
        return 0.0

    def get_weighted_decision(
        self, timeframe_decisions: dict[str, dict[str, Any]], regime: str = "UNKNOWN"
    ) -> dict[str, Any]:
        """
        生成加权决策

        Args:
            timeframe_decisions: 各时间框架的决策字典
                                键为时间框架字符串，值为包含'state'和'confidence'的字典
            regime: 市场体制

        Returns:
            加权决策字典，包含：
                - primary_bias: 主要偏向（"BULLISH", "BEARISH", "NEUTRAL"）
                - confidence: 置信度（0-1）
                - timeframe_contributions: 各时间框架贡献度
                - regime: 使用的市场体制
        """
        weights = self.get_weights(regime)

        # 收集各时间框架的状态和置信度
        bullish_weight = 0.0
        bearish_weight = 0.0
        total_weight = 0.0
        timeframe_contributions = {}

        for tf_str, decision in timeframe_decisions.items():
            try:
                tf = Timeframe.from_string(tf_str)
                weight = weights.get(tf, 0.0)

                state = decision.get("state", "NEUTRAL")
                confidence = decision.get("confidence", 0.0)

                if state == "BULLISH":
                    bullish_weight += weight * confidence
                elif state == "BEARISH":
                    bearish_weight += weight * confidence
                else:
                    # 中性状态，权重平均分配
                    bullish_weight += weight * confidence * 0.5
                    bearish_weight += weight * confidence * 0.5

                total_weight += weight

                # 记录贡献度
                timeframe_contributions[tf_str] = {
                    "weight": weight,
                    "state": state,
                    "confidence": confidence,
                    "contribution": weight * confidence,
                }

            except ValueError:
                continue

        # 计算主要偏向和置信度
        if total_weight > 0:
            bullish_score = bullish_weight / total_weight
            bearish_score = bearish_weight / total_weight

            if bullish_score > bearish_score + 0.1:  # 10%阈值
                primary_bias = "BULLISH"
                confidence = bullish_score
            elif bearish_score > bullish_score + 0.1:
                primary_bias = "BEARISH"
                confidence = bearish_score
            else:
                primary_bias = "NEUTRAL"
                confidence = (bullish_score + bearish_score) / 2
        else:
            primary_bias = "NEUTRAL"
            confidence = 0.0

        return {
            "primary_bias": primary_bias,
            "confidence": confidence,
            "timeframe_contributions": timeframe_contributions,
            "regime": regime,
            "weights_used": {tf.value: w for tf, w in weights.items()},
        }

    def recommend_timeframe_focus(
        self, regime: str = "UNKNOWN", bias: str = "NEUTRAL"
    ) -> list[tuple[str, float]]:
        """
        推荐应关注的时间框架（按重要性排序）

        Args:
            regime: 市场体制
            bias: 交易偏向（"BULLISH", "BEARISH", "NEUTRAL"）

        Returns:
            时间框架和权重列表，按权重降序排列
        """
        weights = self.get_weights(regime)

        # 根据交易偏向调整推荐
        # 在趋势市中，如果偏向与趋势一致，则推荐关注趋势时间框架
        if regime == "TRENDING":
            if bias in ["BULLISH", "BEARISH"]:
                # 趋势市中，大周期更重要
                sorted_tfs = sorted(weights.items(), key=lambda x: x[1], reverse=True)
            else:
                # 中性偏向时，关注所有时间框架
                sorted_tfs = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        else:
            # 非趋势市，按权重排序
            sorted_tfs = sorted(weights.items(), key=lambda x: x[1], reverse=True)

        return [(tf.value, weight) for tf, weight in sorted_tfs]

    def get_config_report(self) -> dict[str, Any]:
        """获取配置报告"""
        return {
            "base_weights": {tf.value: w for tf, w in self.weights.items()},
            "regime_adjustments": {
                regime: {tf.value: adj for tf, adj in adjustments.items()}
                for regime, adjustments in self.regime_adjustments.items()
            },
            "normalize": self.normalize,
            "min_weight": self.min_weight,
        }


# 使用示例
if __name__ == "__main__":
    # 创建过滤器
    filter = PeriodWeightFilter()

    # 获取不同市场体制下的权重
    for regime in ["TRENDING", "RANGING", "VOLATILE", "UNKNOWN"]:
        weights = filter.get_weights(regime)
        for tf, w in weights.items():
            pass

    # 计算加权分数示例
    timeframe_scores = {
        "W": 0.8,  # 周线看涨
        "D": 0.6,  # 日线中性偏多
        "H4": 0.4,  # 4小时看跌
        "H1": 0.5,  # 1小时中性
        "M15": 0.7,  # 15分钟看涨
        "M5": 0.9,  # 5分钟看涨
    }

    for regime in ["TRENDING", "RANGING"]:
        score = filter.calculate_weighted_score(timeframe_scores, regime)

    # 加权决策示例
    timeframe_decisions = {
        "W": {"state": "BULLISH", "confidence": 0.8},
        "D": {"state": "NEUTRAL", "confidence": 0.6},
        "H4": {"state": "BEARISH", "confidence": 0.7},
        "H1": {"state": "NEUTRAL", "confidence": 0.5},
        "M15": {"state": "BULLISH", "confidence": 0.9},
        "M5": {"state": "BULLISH", "confidence": 0.8},
    }

    decision = filter.get_weighted_decision(timeframe_decisions, "TRENDING")
    for tf, contrib in decision["timeframe_contributions"].items():
        pass
