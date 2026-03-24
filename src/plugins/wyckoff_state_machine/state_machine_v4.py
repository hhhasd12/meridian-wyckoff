"""威科夫状态机 V4 — 基于三大原则的序列化推进器

核心设计（取代 V2 的22检测器并行竞争）：
1. 内部三层语义（AD-1）：current_phase / last_confirmed_event / active_hypothesis
2. BarFeatures + StructureContext 分离（AD-2）
3. 检测器只举证，推进权在主干（AD-3）
4. 对外 WyckoffStateResult 接口不变

数据流：
  K线 → WyckoffPrinciplesScorer → BarFeatures
       → 主干裁决（检测器举证 + 原则分数 + 确认质量）
       → 推进/维持/否定 → WyckoffStateResult
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from src.kernel.types import (
    StateConfig,
    StateDirection,
    StateEvidence,
    WyckoffSignal,
    WyckoffStateResult,
)

from .principles.bar_features import (
    BarFeatures,
    StructureContext,
    WyckoffPrinciplesScorer,
)
from .boundary_manager import BoundaryManager, BoundaryStatus
from .transition_guard import TransitionGuard
from .detector_registry import DetectorRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AD-1 内部状态类型
# ---------------------------------------------------------------------------


class MarketMode(Enum):
    """市场运行模式 — 控制检测器调度（CD-1: 内部类型，不进types.py）"""

    TRENDING = "trending"  # 趋势中，只允许停止行为检测
    TRANSITIONING = "transitioning"  # 过渡中，允许AR/ST检测
    RANGING = "ranging"  # 区间内，允许全部检测器


class StateStatus(Enum):
    """假设生命周期状态"""

    HYPOTHETICAL = "hypothetical"
    TESTING = "testing"
    REJECTED = "rejected"
    EXHAUSTED = "exhausted"


@dataclass
class StructureHypothesis:
    """结构级假设 — 独立于事件级Hypothesis（CD-2）

    跟踪整个威科夫结构（吸筹/派发）的生命周期，
    从第一个停止行为开始，到趋势确认或结构失败结束。
    """

    direction: str  # "ACCUM" / "DIST" / "UNKNOWN"
    confidence: float  # 0.0~1.0 随事件推进递增
    created_at_bar: int
    events_confirmed: List[str] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)


@dataclass
class Hypothesis:
    """状态机对某个威科夫事件的假设（AD-1）"""

    event_name: str
    status: StateStatus
    confidence: float
    proposed_at_bar: int
    bars_held: int = 0
    supporting_evidence: list = field(default_factory=list)
    contradicting_evidence: list = field(default_factory=list)
    confirmation_quality: float = 0.0
    rejection_reason: Optional[str] = None
    bar_range: Optional[Tuple[int, int]] = None  # (proposed_at_bar, confirmed_at_bar)


# ---------------------------------------------------------------------------
# 状态→阶段/信号/方向 映射表（复用 V2 的映射）
# ---------------------------------------------------------------------------

PHASE_MAP: Dict[str, str] = {
    "PS": "A",
    "SC": "A",
    "AR": "A",
    "ST": "A",
    "TEST": "B",
    "UTA": "B",
    "SPRING": "C",
    "SO": "C",
    "LPS": "C",
    "mSOS": "C",
    "MSOS": "D",
    "JOC": "D",
    "BU": "E",
    "PSY": "A",
    "BC": "A",
    "AR_DIST": "A",
    "ST_DIST": "A",
    "UT": "B",
    "UTAD": "C",
    "LPSY": "C",
    "mSOW": "D",
    "MSOW": "D",
    "IDLE": "IDLE",
    "UPTREND": "MARKUP",
    "DOWNTREND": "MARKDOWN",
    "RE_ACCUMULATION": "B",
    "RE_DISTRIBUTION": "B",
}

_BUY_STATES = {"SPRING", "SO", "LPS", "mSOS", "MSOS", "JOC", "BU", "UPTREND"}
_SELL_STATES = {"UT", "UTAD", "LPSY", "mSOW", "MSOW", "DOWNTREND"}
_STRONG_BUY = {"JOC", "BU", "MSOS"}
_MEDIUM_BUY = {"SPRING", "SO", "LPS", "mSOS", "UPTREND"}
_STRONG_SELL = {"MSOW", "DOWNTREND"}
_MEDIUM_SELL = {"UTAD", "LPSY", "mSOW"}

_ACCUM_STATES = {
    "PS",
    "SC",
    "AR",
    "ST",
    "TEST",
    "UTA",
    "SPRING",
    "SO",
    "LPS",
    "mSOS",
    "MSOS",
    "JOC",
    "BU",
}
_DIST_STATES = {
    "PSY",
    "BC",
    "AR_DIST",
    "ST_DIST",
    "UT",
    "UTAD",
    "LPSY",
    "mSOW",
    "MSOW",
}

# 边界记录规则：哪些事件产生哪些关键价位
_BOUNDARY_EVENTS: Dict[str, str] = {
    "SC": "SC_LOW",
    "BC": "BC_HIGH",
    "AR": "AR_HIGH",
    "AR_DIST": "AR_LOW",
    "SPRING": "SPRING_LOW",
    "UTAD": "UTAD_HIGH",
    "JOC": "JOC_HIGH",
}


# ---------------------------------------------------------------------------
# WyckoffStateMachineV4
# ---------------------------------------------------------------------------


class WyckoffStateMachineV4:
    """威科夫状态机 V4 — 序列化推进，三大原则打分

    对外接口与 V2 完全兼容：
      process_candle(candle, context) → WyckoffStateResult
    """

    def __init__(
        self,
        timeframe: str = "H4",
        config: Optional[StateConfig] = None,
    ) -> None:
        self.timeframe = timeframe
        self.config = config or StateConfig()

        # AD-1 三层语义
        self.current_phase: str = "IDLE"
        self.last_confirmed_event: str = "IDLE"
        self.active_hypothesis: Optional[Hypothesis] = None

        # 认知层：市场模式 + 结构假设
        self.market_mode: MarketMode = MarketMode.TRENDING
        self.structure_hypothesis: Optional[StructureHypothesis] = None

        # 方向与状态
        self.direction: StateDirection = StateDirection.IDLE
        self.bars_processed: int = 0
        self.heritage_score: float = 0.0

        # 证据链
        self.evidence_chain: List[StateEvidence] = []

        # 关键价位（BoundaryManager 管理生命周期，critical_levels 保持兼容）
        self.critical_levels: Dict[str, float] = {}
        self._boundary_manager = BoundaryManager()

        # 打分器
        self._scorer = WyckoffPrinciplesScorer()
        self._prev_context: Optional[StructureContext] = None

        # 检测器注册表
        self._registry = DetectorRegistry()
        self._register_all_detectors()

        # 状态转换历史
        self._transition_history: List[Dict[str, Any]] = []
        self._confidence_cache: float = 0.0
        self._intensity_cache: float = 0.0
        # V2 兼容：engine plugin 访问此字典
        self._state_confidences: Dict[str, float] = {}

        # W3: 近期价格历史（用于计算 swing_context / recovery_speed）
        self._recent_closes: List[float] = []
        self._recent_highs: List[float] = []
        self._recent_lows: List[float] = []
        _PRICE_HISTORY_LEN = 20  # 保留最近20根K线
        self._price_history_len = _PRICE_HISTORY_LEN

        # 无假设持续bar计数（用于结构超时重置）
        self._idle_bars: int = 0

        # Wave 3: 事件成交量记录（供检测器做跨事件量比较）
        self._event_volumes: Dict[str, float] = {}

        # T1.1: 最近确认事件的bar范围（用于填充 WyckoffStateResult.event_window）
        self._last_confirmed_bar_range: Optional[Tuple[int, int]] = None

    @property
    def current_state(self) -> str:
        """V2 兼容属性 — 对外状态"""
        return self._current_state_for_output()

    # ------------------------------------------------------------------
    # 核心入口 — 与 V2 接口兼容
    # ------------------------------------------------------------------

    def process_candle(
        self, candle: dict, context: Dict[str, Any]
    ) -> WyckoffStateResult:
        """处理单根K线，返回状态评估结果。

        Args:
            candle: K线数据（open/high/low/close/volume）
            context: 外部上下文（market_regime, tr_support 等）

        Returns:
            WyckoffStateResult — 接口与 V2 完全兼容
        """
        self.bars_processed += 1
        old_state = self._current_state_for_output()

        # 0. 累积价格历史 + 冷却递减
        self._recent_closes.append(candle["close"])
        self._recent_highs.append(candle["high"])
        self._recent_lows.append(candle["low"])
        if len(self._recent_closes) > self._price_history_len:
            self._recent_closes.pop(0)
            self._recent_highs.pop(0)
            self._recent_lows.pop(0)

        if self._registry:
            self._registry.tick_cooldowns()

        # 1. 三大原则打分（AD-2: 滞后一拍依赖）
        features = self._scorer.score(candle, self._prev_context)

        # 2. 构建当前结构上下文
        struct_ctx = self._build_structure_context(candle, context)

        # 3. 主干裁决（AD-3）
        self._run_progression(candle, features, struct_ctx)

        # 4. 更新上下文供下轮使用
        self._prev_context = struct_ctx

        # 5. 构建输出
        new_state = self._current_state_for_output()
        state_changed = new_state != old_state

        return self._build_result(state_changed, old_state)

    # ------------------------------------------------------------------
    # AD-1: 对外状态映射
    # ------------------------------------------------------------------

    def _current_state_for_output(self) -> str:
        """AD-1 映射：内部三层语义 → 对外 current_state"""
        if (
            self.active_hypothesis is not None
            and self.active_hypothesis.status == StateStatus.TESTING
        ):
            return self.active_hypothesis.event_name
        return self.last_confirmed_event

    # ------------------------------------------------------------------
    # AD-3: 主干裁决 — 检测器只举证，推进权在这里
    # ------------------------------------------------------------------

    def _run_progression(
        self,
        candle: dict,
        features: BarFeatures,
        context: StructureContext,
    ) -> None:
        """主干推进逻辑（AD-3）"""
        max_hyp_bars = getattr(self.config, "MAX_HYPOTHESIS_BARS", 25)
        confirm_threshold = getattr(self.config, "CONFIRMATION_THRESHOLD", 0.8)

        # --- 情况1: 无活跃假设 → 尝试产生新假设 ---
        if self.active_hypothesis is None:
            self._try_new_hypothesis(candle, features, context)
            if self.active_hypothesis is not None:
                # 新假设产生，重置idle计数
                self._idle_bars = 0
            else:
                self._idle_bars += 1
                # 结构超时重置：连续40根bar无法产生任何假设 → 回IDLE重新开始
                # （当前结构已失去动能，需要重新寻找新的PS/SC等入口事件）
                structure_timeout = (
                    getattr(self.config, "STATE_TIMEOUT_BARS", 20) * 2
                )  # 默认40根
                if (
                    self._idle_bars >= structure_timeout
                    and self.last_confirmed_event != "IDLE"
                ):
                    logger.debug(
                        "结构超时重置: %s → IDLE (连续%d根无假设)",
                        self.last_confirmed_event,
                        self._idle_bars,
                    )
                    self._reset_to_idle()
            return

        # --- 情况2: 有活跃假设 → 推进/否定/超时 ---
        self._idle_bars = 0
        hyp = self.active_hypothesis
        hyp.bars_held += 1

        # 检查否定条件
        rejection = self._check_rejection(hyp, candle, features, context)
        if rejection:
            hyp.status = StateStatus.REJECTED
            hyp.rejection_reason = rejection
            self.active_hypothesis = None
            return

        # 检查超时
        if hyp.bars_held > max_hyp_bars:
            hyp.status = StateStatus.EXHAUSTED
            hyp.rejection_reason = f"超过{max_hyp_bars}根K线未确认"
            self.active_hypothesis = None
            return

        # 累积确认质量
        quality = self._calc_confirmation_quality(hyp, candle, features, context)
        hyp.confirmation_quality += quality

        # 检查确认
        if hyp.confirmation_quality >= confirm_threshold:
            self._confirm_and_advance(hyp, candle)
            return

        # 升级：HYPOTHETICAL → TESTING（持续2根以上未否定）
        if hyp.status == StateStatus.HYPOTHETICAL and hyp.bars_held >= 2:
            hyp.status = StateStatus.TESTING

    def _reset_to_idle(self) -> None:
        """重置状态机到IDLE，准备检测新结构"""
        self.last_confirmed_event = "IDLE"
        self.current_phase = "IDLE"
        self.direction = StateDirection.IDLE
        self.active_hypothesis = None
        self.critical_levels.clear()
        self._boundary_manager = BoundaryManager()
        self._idle_bars = 0
        self.heritage_score = 0.0
        self._confidence_cache = 0.0
        self._intensity_cache = 0.0
        self.market_mode = MarketMode.TRENDING
        self.structure_hypothesis = None
        self._event_volumes.clear()

    # 假设产生
    # ------------------------------------------------------------------

    def _try_new_hypothesis(
        self,
        candle: dict,
        features: BarFeatures,
        context: StructureContext,
    ) -> None:
        """尝试基于期待列表产生新假设"""
        current = self._current_state_for_output()
        expected = TransitionGuard.get_valid_targets(
            current, mode=self.market_mode.value
        )
        if not expected:
            return

        # 对期待列表中每个目标评估适配度
        best_event: Optional[str] = None
        best_score: float = 0.0

        # 优先使用 DetectorRegistry（Phase 3 检测器）
        if self._registry and self._registry.list_names():
            node_scores = self._registry.evaluate_expected(
                list(expected),
                candle,
                features,
                context,
            )
            for ns in node_scores:
                if ns.confidence > best_score:
                    best_score = ns.confidence
                    best_event = ns.event_name

        # 兜底：如果检测器没有产出，用简化评分
        if best_event is None:
            for event in expected:
                if not TransitionGuard.check_prerequisite_evidence(
                    event, self.evidence_chain, self.critical_levels
                ):
                    continue
                score = self._score_event_fit(event, candle, features, context)
                if score > best_score:
                    best_score = score
                    best_event = event

        threshold = self.config.STATE_MIN_CONFIDENCE
        if best_event and best_score >= threshold:
            self.active_hypothesis = Hypothesis(
                event_name=best_event,
                status=StateStatus.HYPOTHETICAL,
                confidence=best_score,
                proposed_at_bar=self.bars_processed,
            )

    def _score_event_fit(
        self,
        event: str,
        candle: dict,
        features: BarFeatures,
        context: StructureContext,
    ) -> float:
        """评估某事件与当前K线特征的匹配度（简化版）

        Phase 3 接入检测器后，此方法将委托 DetectorRegistry。
        当前使用 BarFeatures 做基础评估。
        """
        score = 0.0

        # --- 趋势确认事件 ---
        if event == "UPTREND":
            # 吸筹结构完成后进入上升趋势：价格在TR上方+需求主导
            if features.supply_demand > 0:
                score += 0.2
            if features.effort_result > 0:
                score += 0.15
            if context.swing_context == "higher_lows":
                score += 0.15
            # 从BU/JOC来的，结构已确认，给基础分
            score += 0.1
            return min(score, 1.0)

        if event == "DOWNTREND":
            # 派发结构完成后进入下降趋势
            if features.supply_demand < 0:
                score += 0.2
            if features.effort_result > 0:
                score += 0.15
            if context.swing_context == "lower_highs":
                score += 0.15
            score += 0.1
            return min(score, 1.0)

        if event in ("RE_ACCUMULATION", "RE_DISTRIBUTION"):
            # 趋势中出现停顿 → 再积累/再派发
            if features.is_stopping_action:
                score += 0.3
            if abs(features.supply_demand) < 0.2:
                score += 0.1  # 供需平衡 = 盘整信号
            score += features.cause_effect * 0.1
            return min(score, 1.0)

        if event == "IDLE":
            # 从趋势/结构状态回到IDLE — 停止行为+供需转向
            if features.is_stopping_action:
                score += 0.3
            # 趋势反向信号
            if self.direction == StateDirection.ACCUMULATION:
                if features.supply_demand < -0.2:
                    score += 0.2  # 吸筹中出现供应 → 可能要重新评估
            elif self.direction == StateDirection.DISTRIBUTION:
                if features.supply_demand > 0.2:
                    score += 0.2
            return min(score, 1.0)

        # --- 停止行为事件（PS/SC/BC）---
        if event in ("PS", "SC", "BC") and features.is_stopping_action:
            score += 0.4
        elif event in ("PS", "SC", "BC"):
            score += 0.1

        # 高量事件
        if event in ("SC", "BC", "SPRING", "UTAD"):
            score += min(features.volume_ratio / 3.0, 0.3)

        # 供需方向匹配
        if event in _ACCUM_STATES and features.supply_demand > 0:
            score += features.supply_demand * 0.2
        elif event in _DIST_STATES and features.supply_demand < 0:
            score += abs(features.supply_demand) * 0.2

        # 因果累积
        score += features.cause_effect * 0.1

        return min(score, 1.0)

    # ------------------------------------------------------------------
    # 否定与确认
    # ------------------------------------------------------------------

    def _check_rejection(
        self,
        hyp: Hypothesis,
        candle: dict,
        features: BarFeatures,
        context: StructureContext,
    ) -> Optional[str]:
        """检查假设是否被当前K线否定。返回否定原因或 None"""
        # 努力结果强烈背离 → 否定
        if features.effort_result < -0.7:
            return "努力结果强烈背离"

        # 边界破坏检查
        if hyp.event_name in ("ST", "TEST", "LPS"):
            sc_low = self.critical_levels.get("SC_LOW")
            if sc_low and candle["close"] < sc_low * 0.97:
                return f"收盘跌破SC_LOW({sc_low:.2f})3%"

        if hyp.event_name in ("UT", "UTAD", "LPSY"):
            bc_high = self.critical_levels.get("BC_HIGH")
            if bc_high and candle["close"] > bc_high * 1.03:
                return f"收盘突破BC_HIGH({bc_high:.2f})3%"

        return None

    def _calc_confirmation_quality(
        self,
        hyp: Hypothesis,
        candle: dict,
        features: BarFeatures,
        context: StructureContext,
    ) -> float:
        """计算当前K线对假设的确认质量增量

        设计目标：典型K线增量 0.15-0.3，3-5根好K线可确认（阈值0.8）
        单根最大增量 0.5，避免 1 根完美K线直接确认
        """
        quality = 0.0

        # 三大原则和谐度
        if features.effort_result > 0.3:
            quality += 0.15
        if abs(features.supply_demand) > 0.3:
            quality += 0.15

        # 价格在合理位置
        if 0.2 < context.position_in_tr < 0.8:
            quality += 0.05

        # 量能配合
        if 0.7 < features.volume_ratio < 2.0:
            quality += 0.1

        # 因果累积奖励（cause_effect > 0.3 说明形态在发展）
        if features.cause_effect > 0.3:
            quality += 0.05

        # 单根增量上限 0.5（保证至少2根K线才能确认）
        quality = min(quality, 0.5)

        # 更新假设置信度
        hyp.confidence = min(hyp.confidence + quality * 0.1, 1.0)

        return quality

    def _confirm_and_advance(self, hyp: Hypothesis, candle: dict) -> None:
        """确认假设并推进到新状态"""
        old_intensity = self._intensity_cache
        self.heritage_score = old_intensity * 0.8

        # 保存旧事件用于 transition_history
        old_event = self.last_confirmed_event

        # 更新三层语义
        self.last_confirmed_event = hyp.event_name
        self.current_phase = PHASE_MAP.get(hyp.event_name, "IDLE")
        self._update_direction(hyp.event_name)

        # 确认IDLE时清理关键价位（新结构从零开始）
        if hyp.event_name == "IDLE":
            self.critical_levels.clear()
            self._boundary_manager = BoundaryManager()
            self._event_volumes.clear()

        # 记录关键价位（通过 BoundaryManager 管理生命周期）
        boundary_key = _BOUNDARY_EVENTS.get(hyp.event_name)
        if boundary_key:
            price = candle["low"] if "LOW" in boundary_key else candle["high"]
            self._boundary_manager.propose(boundary_key, price, self.bars_processed)

        # 锁定逻辑：ST/TEST确认 → lock SC_LOW, ST_DIST确认 → lock BC_HIGH
        if hyp.event_name in {"ST", "TEST"} and self._boundary_manager.get("SC_LOW"):
            try:
                self._boundary_manager.lock("SC_LOW", self.bars_processed)
            except (KeyError, ValueError):
                pass  # 已锁定或不存在，忽略
        if hyp.event_name == "ST_DIST" and self._boundary_manager.get("BC_HIGH"):
            try:
                self._boundary_manager.lock("BC_HIGH", self.bars_processed)
            except (KeyError, ValueError):
                pass

        # 同步 critical_levels 用于兼容（其他代码可能读 self.critical_levels）
        self.critical_levels = self._boundary_manager.to_critical_levels()

        # 更新缓存
        self._confidence_cache = hyp.confidence
        self._intensity_cache = hyp.confidence * 0.8
        self._state_confidences[hyp.event_name] = hyp.confidence

        # 记录事件成交量（供检测器做跨事件量比较）
        self._event_volumes[hyp.event_name] = candle["volume"]

        # 记录转换历史
        self._transition_history.append(
            {
                "from": old_event,
                "to": hyp.event_name,
                "bar": self.bars_processed,
                "confidence": hyp.confidence,
            }
        )

        # 证据链追加
        self.evidence_chain.append(
            StateEvidence(
                evidence_type="state_transition",
                value=hyp.confidence,
                confidence=hyp.confidence,
                weight=1.0,
                description=f"{hyp.event_name} confirmed",
            )
        )
        if len(self.evidence_chain) > 50:
            self.evidence_chain = self.evidence_chain[-50:]

        # T1.1: 记录事件的bar范围
        hyp.bar_range = (hyp.proposed_at_bar, self.bars_processed)
        self._last_confirmed_bar_range = hyp.bar_range

        # 清除假设
        self.active_hypothesis = None

        # 模式转换
        self._update_market_mode(hyp.event_name)

        # 结构假设生命周期
        self._update_structure_hypothesis(hyp.event_name)

    def _update_market_mode(self, confirmed_event: str) -> None:
        """根据确认的事件更新市场模式

        TRENDING → TRANSITIONING: PS/SC/PSY/BC 确认（需≥5根K线滞后）
        TRANSITIONING → RANGING: ST/ST_DIST 确认
        RANGING → TRENDING: UPTREND/DOWNTREND 确认
        """
        if self.market_mode == MarketMode.TRENDING:
            if confirmed_event in {"PS", "SC", "PSY", "BC"}:
                if self.bars_processed >= 5:  # hysteresis
                    self.market_mode = MarketMode.TRANSITIONING
        elif self.market_mode == MarketMode.TRANSITIONING:
            if confirmed_event in {"ST", "ST_DIST"}:
                self.market_mode = MarketMode.RANGING
        elif self.market_mode == MarketMode.RANGING:
            if confirmed_event in {"UPTREND", "DOWNTREND"}:
                self.market_mode = MarketMode.TRENDING
                # 结构完成，清理边界和事件量记录，为新结构做准备
                self._boundary_manager = BoundaryManager()
                self.critical_levels.clear()
                self._event_volumes.clear()

    def _update_structure_hypothesis(self, event: str) -> None:
        """根据确认事件更新结构假设

        生命周期：
        - 创建：PS/SC/PSY/BC（停止行为入口）→ confidence=0.2, direction=UNKNOWN
        - 方向设定：AR→ACCUM, AR_DIST→DIST, confidence+=0.15
        - 巩固：ST/ST_DIST → confidence+=0.15
        - C阶段方向确认：SPRING/SO/UTAD → confidence+=0.2
        - D阶段力量展示：mSOS/MSOS/JOC/LPS/mSOW/MSOW/LPSY → confidence+=0.2
        - 完成：UPTREND/DOWNTREND → structure_hypothesis=None
        - 维持：BU/TEST/UTA/UT → confidence+=0.05
        """
        # 创建：停止行为入口
        if event in {"PS", "SC", "PSY", "BC"}:
            if self.structure_hypothesis is None:
                self.structure_hypothesis = StructureHypothesis(
                    direction="UNKNOWN",
                    confidence=0.2,
                    created_at_bar=self.bars_processed,
                    events_confirmed=[event],
                )
            else:
                self.structure_hypothesis.events_confirmed.append(event)
                self.structure_hypothesis.confidence = min(
                    self.structure_hypothesis.confidence + 0.1, 1.0
                )
            return

        # 无结构假设时后续事件无意义
        if self.structure_hypothesis is None:
            return

        sh = self.structure_hypothesis
        sh.events_confirmed.append(event)

        # 方向设定
        if event == "AR":
            sh.direction = "ACCUM"
            sh.confidence = min(sh.confidence + 0.15, 1.0)
        elif event == "AR_DIST":
            sh.direction = "DIST"
            sh.confidence = min(sh.confidence + 0.15, 1.0)
        # ST 巩固
        elif event in {"ST", "ST_DIST"}:
            sh.confidence = min(sh.confidence + 0.15, 1.0)
        # C 阶段方向确认
        elif event in {"SPRING", "SO"}:
            sh.confidence = min(sh.confidence + 0.2, 1.0)
        elif event == "UTAD":
            sh.confidence = min(sh.confidence + 0.2, 1.0)
        # D 阶段力量展示
        elif event in {"mSOS", "MSOS", "JOC", "LPS"}:
            sh.confidence = min(sh.confidence + 0.2, 1.0)
        elif event in {"mSOW", "MSOW", "LPSY"}:
            sh.confidence = min(sh.confidence + 0.2, 1.0)
        # 结构完成
        elif event in {"UPTREND", "DOWNTREND"}:
            self.structure_hypothesis = None
        # BU/TEST 等维持
        elif event in {"BU", "TEST", "UTA", "UT"}:
            sh.confidence = min(sh.confidence + 0.05, 1.0)

    def _update_direction(self, state: str) -> None:
        """根据状态更新方向"""
        if state in _ACCUM_STATES:
            self.direction = StateDirection.ACCUMULATION
        elif state in _DIST_STATES:
            self.direction = StateDirection.DISTRIBUTION
        elif state in ("UPTREND", "DOWNTREND"):
            self.direction = StateDirection.TRENDING
        else:
            self.direction = StateDirection.IDLE

    # ------------------------------------------------------------------
    # 结构上下文构建
    # ------------------------------------------------------------------

    def _build_structure_context(
        self, candle: dict, context: Dict[str, Any]
    ) -> StructureContext:
        """构建当前结构上下文（W3: 填充实际计算值）

        position_in_tr 优先级:
        1. 内部边界（BoundaryManager SC_LOW + AR_HIGH，非 INVALIDATED）
        2. 外部 TR（sm_context 的 tr_support/tr_resistance）
        3. 默认 0.5 中性
        """
        tr_sup = 0.0
        tr_res = 0.0
        pos = 0.5  # 默认中性

        # 优先使用内部边界（BoundaryManager）
        sc_low_info = self._boundary_manager.get("SC_LOW")
        ar_high_info = self._boundary_manager.get("AR_HIGH")

        used_internal = False
        if (
            sc_low_info
            and ar_high_info
            and sc_low_info.status != BoundaryStatus.INVALIDATED
            and ar_high_info.status != BoundaryStatus.INVALIDATED
        ):
            internal_sup = sc_low_info.price
            internal_res = ar_high_info.price
            internal_range = internal_res - internal_sup
            if internal_sup > 0 and internal_range > internal_sup * 0.01:
                pos = (candle["close"] - internal_sup) / internal_range
                pos = max(0.0, min(1.0, pos))
                tr_sup = internal_sup
                tr_res = internal_res
                used_internal = True

        # 回退到外部 TR（原逻辑）
        if not used_internal:
            ext_sup = context.get("tr_support", 0.0)
            ext_res = context.get("tr_resistance", 0.0)
            ext_range = ext_res - ext_sup
            if ext_sup > 0 and ext_range > ext_sup * 0.01:
                pos = (candle["close"] - ext_sup) / ext_range
                pos = max(0.0, min(1.0, pos))
                tr_sup = ext_sup
                tr_res = ext_res

        # --- W3: test_quality — 关键价位被测试的次数越多质量越高 ---
        test_quality = self._calc_test_quality()

        # --- W3: recovery_speed — SC/BC 后反弹速度 ---
        recovery_speed = self._calc_recovery_speed()

        # --- W3: swing_context — 近期高低点模式 ---
        swing_context = self._calc_swing_context()

        # --- W3: direction_bias — 从状态机方向和阶段累积 ---
        direction_bias = self._calc_direction_bias()

        return StructureContext(
            current_phase=self.current_phase,
            last_confirmed_event=self.last_confirmed_event,
            position_in_tr=pos,
            distance_to_support=(candle["close"] - tr_sup if tr_sup else 0),
            distance_to_resistance=(tr_res - candle["close"] if tr_res else 0),
            test_quality=test_quality,
            recovery_speed=recovery_speed,
            swing_context=swing_context,
            direction_bias=direction_bias,
            boundaries=self._boundary_manager.to_critical_levels(),
            event_volumes=dict(self._event_volumes),
        )

    def _calc_test_quality(self) -> float:
        """从关键价位测试次数计算测试质量 (0~1)

        逻辑：SC_LOW / BC_HIGH 存在且近期K线有接近（±3%）的记录，
        每次接近算一次 test，3次测试=1.0 满质量。
        """
        if not self._recent_lows or not self.critical_levels:
            return 0.5

        test_count = 0
        sc_low = self.critical_levels.get("SC_LOW")
        bc_high = self.critical_levels.get("BC_HIGH")

        if sc_low and sc_low > 0:
            for low in self._recent_lows:
                if abs(low - sc_low) / sc_low < 0.03:
                    test_count += 1
        if bc_high and bc_high > 0:
            for high in self._recent_highs:
                if abs(high - bc_high) / bc_high < 0.03:
                    test_count += 1

        return min(test_count / 3.0, 1.0)

    def _calc_recovery_speed(self) -> float:
        """从SC/BC后的收盘恢复计算反弹速度 (0~1)

        逻辑：最近5根K线的收盘价变化方向与 SC→AR 反弹方向一致的比例。
        """
        if len(self._recent_closes) < 3:
            return 0.5

        recent = self._recent_closes[-5:]
        if len(recent) < 2:
            return 0.5

        # 计算连续上涨/下跌比例
        ups = sum(1 for j in range(1, len(recent)) if recent[j] > recent[j - 1])
        ratio = ups / (len(recent) - 1)

        # 根据方向调整：吸筹阶段上涨=恢复，派发阶段下跌=恢复
        if self.direction == StateDirection.DISTRIBUTION:
            ratio = 1.0 - ratio

        return ratio

    def _calc_swing_context(self) -> str:
        """从近期高低点序列判断摆动模式

        Returns:
            "higher_lows" — 底部抬升（吸筹信号）
            "lower_highs" — 顶部压低（派发信号）
            "sideways" — 横盘
            "unknown" — 数据不足
        """
        if len(self._recent_highs) < 6:
            return "unknown"

        # 取前半和后半对比
        mid = len(self._recent_lows) // 2
        first_lows = self._recent_lows[:mid]
        second_lows = self._recent_lows[mid:]
        first_highs = self._recent_highs[:mid]
        second_highs = self._recent_highs[mid:]

        avg_low_1 = sum(first_lows) / len(first_lows)
        avg_low_2 = sum(second_lows) / len(second_lows)
        avg_high_1 = sum(first_highs) / len(first_highs)
        avg_high_2 = sum(second_highs) / len(second_highs)

        # 比较均值变化（阈值 0.5% 避免噪声）
        low_rising = avg_low_2 > avg_low_1 * 1.005
        high_falling = avg_high_2 < avg_high_1 * 0.995

        if low_rising and not high_falling:
            return "higher_lows"
        if high_falling and not low_rising:
            return "lower_highs"
        return "sideways"

    def _calc_direction_bias(self) -> float:
        """从状态机方向和阶段计算方向偏向 (-1~+1)

        A-B阶段逐步积累，C阶段明确方向，D-E阶段强方向。
        """
        phase = self.current_phase
        direction = self.direction

        # 基础偏向
        if direction == StateDirection.ACCUMULATION:
            base = 0.3
        elif direction == StateDirection.DISTRIBUTION:
            base = -0.3
        else:
            return 0.0

        # 阶段放大
        phase_mult = {
            "A": 0.3,
            "B": 0.5,
            "C": 0.8,
            "D": 1.0,
            "E": 1.0,
            "IDLE": 0.0,
            "MARKUP": 1.0,
            "MARKDOWN": 1.0,
        }
        mult = phase_mult.get(phase, 0.3)

        return max(-1.0, min(1.0, base * mult / 0.3))

    # ------------------------------------------------------------------
    # 结果构建 — 与 V2 接口完全兼容
    # ------------------------------------------------------------------

    def _build_result(
        self, state_changed: bool, previous_state: str
    ) -> WyckoffStateResult:
        """构建 WyckoffStateResult（接口不变）"""
        current = self._current_state_for_output()
        signal = self._derive_signal(current)
        strength = self._derive_strength(current)

        confidence = self._confidence_cache
        if self.active_hypothesis:
            confidence = self.active_hypothesis.confidence

        # 结构假设置信度增强
        if self.structure_hypothesis is not None:
            confidence = max(confidence, self.structure_hypothesis.confidence)

        return WyckoffStateResult(
            current_state=current,
            phase=self.current_phase,
            direction=self.direction,
            confidence=confidence,
            intensity=self._intensity_cache,
            evidences=self.evidence_chain[-20:],
            signal=signal,
            signal_strength=strength,
            state_changed=state_changed,
            previous_state=previous_state,
            heritage_score=self.heritage_score,
            critical_levels=self._boundary_manager.to_critical_levels(),
            event_window=self._last_confirmed_bar_range,
        )

    @staticmethod
    def _derive_signal(state: str) -> WyckoffSignal:
        if state in _BUY_STATES:
            return WyckoffSignal.BUY_SIGNAL
        if state in _SELL_STATES:
            return WyckoffSignal.SELL_SIGNAL
        return WyckoffSignal.NO_SIGNAL

    @staticmethod
    def _derive_strength(state: str) -> str:
        if state in _STRONG_BUY or state in _STRONG_SELL:
            return "strong"
        if state in _MEDIUM_BUY or state in _MEDIUM_SELL:
            return "medium"
        if state == "UT":
            return "weak"
        return "none"

    # ------------------------------------------------------------------
    # 检测器注册（T3.4）
    # ------------------------------------------------------------------

    def _register_all_detectors(self) -> None:
        """注册所有吸筹和派发检测器"""
        try:
            from .detectors.accumulation import (
                PSDetector,
                SCDetector,
                ARDetector,
                STDetector,
                TestDetector,
                UTADetector,
                SpringDetector,
                SODetector,
                LPSDetector,
                MinorSOSDetector,
                MSOSDetector,
                JOCDetector,
                BUDetector,
            )

            for det_cls in (
                PSDetector,
                SCDetector,
                ARDetector,
                STDetector,
                TestDetector,
                UTADetector,
                SpringDetector,
                SODetector,
                LPSDetector,
                MinorSOSDetector,
                MSOSDetector,
                JOCDetector,
                BUDetector,
            ):
                self._registry.register(det_cls())
        except ImportError:
            logger.warning("吸筹检测器导入失败，跳过注册")

        try:
            from .detectors.distribution import (
                PSYDetector,
                BCDetector,
                ARDistDetector,
                STDistDetector,
                UTDetector,
                UTADDetector,
                LPSYDetector,
                MinorSOWDetector,
                MSOWDetector,
            )

            for det_cls in (
                PSYDetector,
                BCDetector,
                ARDistDetector,
                STDistDetector,
                UTDetector,
                UTADDetector,
                LPSYDetector,
                MinorSOWDetector,
                MSOWDetector,
            ):
                self._registry.register(det_cls())
        except ImportError:
            logger.warning("派发检测器导入失败，跳过注册")
