"""威科夫三大原则打分 + 单K线特征

提供三个核心数据类和打分器入口：
- BarFeatures: 三大原则分数 + 单K线/滚动窗口特征（AD-2: 纯特征层，无状态机依赖）
- StructureContext: 结构上下文 — 状态机维护的当前结构认知（AD-2）
- WyckoffPrinciplesScorer: 打分器入口，维护滑窗历史，委托子分析器
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BarFeatures:
    """三大原则打分 + 单K线/滚动窗口特征（AD-2: 纯特征层，无状态机依赖）

    三大原则核心分数由子分析器计算（T1.2-T1.4），
    单K线特征由打分器直接计算。
    """

    # 三大原则核心分数
    supply_demand: float
    """供需原则分数。-1(纯供应) ~ +1(纯需求)"""

    cause_effect: float
    """因果原则分数。0~1 因的累积程度"""

    effort_result: float
    """努力与结果原则分数。-1(完全背离) ~ +1(完全和谐)"""

    # 单K线特征
    volume_ratio: float
    """当前量/MA20量"""

    price_range_ratio: float
    """当前振幅/MA20振幅"""

    body_ratio: float
    """实体/全长（0~1）"""

    is_stopping_action: bool
    """是否为停止行为（高量 + 小实体）"""

    spread_vs_volume_divergence: float
    """努力结果背离强度。正值 = 高努力低结果"""


@dataclass
class StructureContext:
    """结构上下文 — 状态机维护的当前结构认知（AD-2）

    由状态机在每根K线处理后更新，供下一轮打分器使用。
    数据流：StructureContext(t-1) → BarFeatures(t) → StructureContext(t)
    """

    current_phase: str
    """当前阶段。A/B/C/D/E/IDLE/MARKUP/MARKDOWN"""

    last_confirmed_event: str
    """最近确认的结构事件。PS/SC/AR/ST/Spring/UTAD..."""

    position_in_tr: float
    """当前价格在TR中的位置。0~1"""

    distance_to_support: float
    """距支撑位距离（标准化）"""

    distance_to_resistance: float
    """距阻力位距离（标准化）"""

    test_quality: float
    """最近测试的质量"""

    recovery_speed: float
    """反弹速度"""

    swing_context: str
    """当前摆动上下文。"impulse" | "test" | "unknown" """

    direction_bias: float
    """方向偏向。-1 ~ +1, A-B阶段逐步积累"""

    boundaries: Dict[str, Any]
    """关键价位信息。Phase 2 定义 BoundaryInfo 后类型为 Dict[str, 'BoundaryInfo']"""

    event_volumes: Dict[str, float] = field(default_factory=dict)
    """已确认事件的成交量。{事件名: volume} — 供检测器做跨事件量比较"""


# ---------------------------------------------------------------------------
# 滑窗历史中存储的K线数据类型
# ---------------------------------------------------------------------------
_CandleDict = Dict[str, float]

# 默认滑窗大小
_DEFAULT_WINDOW = 50

# MA 窗口大小
_MA_WINDOW = 20


class WyckoffPrinciplesScorer:
    """威科夫三大原则打分器入口

    维护滑窗历史，委托三个子分析器计算各原则分数。
    接收上一轮 StructureContext（滞后一拍依赖，AD-2数据流设计）。
    """

    def __init__(self) -> None:
        self._history: deque = deque(maxlen=_DEFAULT_WINDOW)
        self._last_features: Optional[BarFeatures] = None

    def score(
        self,
        candle: dict,
        prev_context: Optional[StructureContext] = None,
    ) -> BarFeatures:
        """对当前K线进行三大原则评估。

        Args:
            candle: K线数据字典，必须包含 open/high/low/close/volume
            prev_context: 上一轮状态机产出的结构上下文。
                         首根K线时为 None，位置相关分数默认为 0（中性）。

        Returns:
            BarFeatures: 三大原则分数 + 单K线特征
        """
        # 1. 将当前K线加入滑窗历史
        self._history.append(candle)

        # 2. 计算单K线特征
        volume_ratio = self._calc_volume_ratio(candle)
        price_range_ratio = self._calc_price_range_ratio(candle)
        body_ratio = self._calc_body_ratio(candle)
        is_stopping_action = volume_ratio > 1.5 and body_ratio < 0.3
        spread_vs_volume_divergence = volume_ratio - price_range_ratio

        # 3. 三大原则分数 — 尝试导入子分析器，不存在则用中性默认值
        supply_demand = self._calc_supply_demand(candle, prev_context)
        cause_effect = self._calc_cause_effect(candle, prev_context)
        effort_result = self._calc_effort_result(candle, prev_context)

        features = BarFeatures(
            supply_demand=supply_demand,
            cause_effect=cause_effect,
            effort_result=effort_result,
            volume_ratio=volume_ratio,
            price_range_ratio=price_range_ratio,
            body_ratio=body_ratio,
            is_stopping_action=is_stopping_action,
            spread_vs_volume_divergence=spread_vs_volume_divergence,
        )
        self._last_features = features
        return features

    @property
    def last_features(self) -> Optional[BarFeatures]:
        """最近一次 score() 产出的 BarFeatures，供 API 层读取"""
        return self._last_features

    # ------------------------------------------------------------------
    # 单K线特征计算
    # ------------------------------------------------------------------

    def _calc_volume_ratio(self, candle: dict) -> float:
        """计算成交量比率：当前量 / MA20量

        Args:
            candle: 当前K线数据

        Returns:
            成交量比率，历史不足时返回 1.0
        """
        if len(self._history) < 2:
            return 1.0

        window = min(len(self._history) - 1, _MA_WINDOW)
        # 取历史中倒数第2条到倒数第(window+1)条（不含当前K线）
        recent = list(self._history)[-window - 1 : -1]
        avg_volume = sum(c["volume"] for c in recent) / len(recent)
        if avg_volume <= 0:
            return 1.0
        return candle["volume"] / avg_volume

    def _calc_price_range_ratio(self, candle: dict) -> float:
        """计算价格振幅比率：当前振幅 / MA20振幅

        Args:
            candle: 当前K线数据

        Returns:
            振幅比率，历史不足时返回 1.0
        """
        current_range = candle["high"] - candle["low"]
        if len(self._history) < 2:
            return 1.0

        window = min(len(self._history) - 1, _MA_WINDOW)
        recent = list(self._history)[-window - 1 : -1]
        avg_range = sum(c["high"] - c["low"] for c in recent) / len(recent)
        if avg_range <= 0:
            return 1.0
        return current_range / avg_range

    @staticmethod
    def _calc_body_ratio(candle: dict) -> float:
        """计算实体比率：abs(close-open) / (high-low)

        Args:
            candle: 当前K线数据

        Returns:
            实体比率。high==low 时返回 0.0
        """
        full_range = candle["high"] - candle["low"]
        if full_range <= 0:
            return 0.0
        return abs(candle["close"] - candle["open"]) / full_range

    # ------------------------------------------------------------------
    # 三大原则分数（子分析器委托 / 默认中性值）
    # ------------------------------------------------------------------

    def _calc_supply_demand(
        self,
        candle: dict,
        prev_context: Optional[StructureContext],
    ) -> float:
        """供需原则分数。

        尝试导入 supply_demand 子分析器。
        子分析器不存在时返回中性值 0.0。

        Args:
            candle: 当前K线数据
            prev_context: 上一轮结构上下文

        Returns:
            供需分数 -1 ~ +1
        """
        try:
            from .supply_demand import calc_supply_demand

            return calc_supply_demand(candle, self._history, prev_context)
        except ImportError:
            return 0.0

    def _calc_cause_effect(
        self,
        candle: dict,
        prev_context: Optional[StructureContext],
    ) -> float:
        """因果原则分数。

        尝试导入 cause_effect 子分析器。
        子分析器不存在时返回中性值 0.0。

        Args:
            candle: 当前K线数据
            prev_context: 上一轮结构上下文

        Returns:
            因果分数 0 ~ 1
        """
        try:
            from .cause_effect import calc_cause_effect

            return calc_cause_effect(candle, self._history, prev_context)
        except ImportError:
            return 0.0

    def _calc_effort_result(
        self,
        candle: dict,
        prev_context: Optional[StructureContext],
    ) -> float:
        """努力与结果原则分数。

        尝试导入 effort_result 子分析器。
        子分析器不存在时返回中性值 0.0。

        Args:
            candle: 当前K线数据
            prev_context: 上一轮结构上下文

        Returns:
            努力结果分数 -1 ~ +1
        """
        try:
            from .effort_result import calc_effort_result

            return calc_effort_result(candle, self._history, prev_context)
        except ImportError:
            return 0.0
