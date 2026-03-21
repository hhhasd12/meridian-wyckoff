"""威科夫状态机 V2 — 每个时间框架拥有独立实例

设计原则：
1. 每TF独立实例 — H4/H1/M15 各自拥有独立的状态机
2. TransitionGuard 硬约束 — 只允许合法的父→子转换
3. 证据链全流程保持 — 每次 process_candle 产出完整 WyckoffStateResult
4. PHASE_MAP 标签 — 所有状态映射到 Phase A-E
5. 再积累/再派发检测 — UPTREND/DOWNTREND 中的横盘检测

从 system-architecture-v3.md §4.2 ~ §4.6 实现。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.kernel.types import (
    StateConfig,
    StateDetectionResult,
    StateDirection,
    StateEvidence,
    StateTransition,
    StateTransitionType,
    WyckoffSignal,
    WyckoffStateResult,
)
from src.plugins.wyckoff_state_machine.transition_guard import TransitionGuard

logger = logging.getLogger(__name__)


# ============================================================
# 阶段标签映射 (§4.2)
# ============================================================

PHASE_MAP: Dict[str, str] = {
    # 吸筹阶段
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
    # 派发阶段
    "PSY": "A",
    "BC": "A",
    "AR_DIST": "A",
    "ST_DIST": "A",
    "UT": "B",
    "UTAD": "C",
    "LPSY": "C",
    "mSOW": "D",
    "MSOW": "D",
    # 特殊状态
    "IDLE": "IDLE",
    "UPTREND": "MARKUP",
    "DOWNTREND": "MARKDOWN",
    "RE_ACCUMULATION": "B",
    "RE_DISTRIBUTION": "B",
}

# 信号映射：状态 → WyckoffSignal
_BUY_STATES = {"SPRING", "SO", "LPS", "mSOS", "MSOS", "JOC", "BU", "UPTREND"}
_SELL_STATES = {"UT", "UTAD", "LPSY", "mSOW", "MSOW", "DOWNTREND"}

# 信号强度映射
_STRONG_BUY = {"JOC", "BU", "MSOS"}
_MEDIUM_BUY = {"SPRING", "SO", "LPS", "mSOS", "UPTREND"}
_STRONG_SELL = {"MSOW", "DOWNTREND"}
_MEDIUM_SELL = {"UTAD", "LPSY", "mSOW"}
_WEAK_SELL = {"UT"}

# 吸筹/派发状态集合（用于 direction 判断）
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

# 检测器方法名映射
_ACCUM_DETECTORS: Dict[str, str] = {
    "PS": "detect_ps",
    "SC": "detect_sc",
    "AR": "detect_ar",
    "ST": "detect_st",
    "TEST": "detect_test",
    "UTA": "detect_uta",
    "SPRING": "detect_spring",
    "SO": "detect_so",
    "LPS": "detect_lps",
    "mSOS": "detect_minor_sos",
    "MSOS": "detect_msos",
    "JOC": "detect_joc",
    "BU": "detect_bu",
}
_DIST_DETECTORS: Dict[str, str] = {
    "PSY": "detect_psy",
    "BC": "detect_bc",
    "AR_DIST": "detect_ar_dist",
    "ST_DIST": "detect_st_dist",
    "UT": "detect_ut",
    "UTAD": "detect_utad",
    "LPSY": "detect_lpsy",
    "mSOW": "detect_minor_sow",
    "MSOW": "detect_msow",
}


# ============================================================
# WyckoffStateMachineV2 类
# ============================================================


class WyckoffStateMachineV2:
    """每个时间框架拥有独立的状态机实例

    使用 TransitionGuard 作为硬约束，只允许合法的父→子转换。
    证据链从检测器一直传递到 WyckoffStateResult 输出。

    Attributes:
        timeframe: 时间框架标识（如 "H4", "H1", "M15"）
        config: 状态机配置
        current_state: 当前状态名
        phase: 当前阶段标签 (A-E / IDLE / MARKUP / MARKDOWN)
        direction: 状态方向
        evidence_chain: 累积证据链（最近 N 条）
        critical_levels: 关键价格水平
        state_history: 状态转换历史
        bars_in_state: 当前状态持续K线数
    """

    # 证据链最大长度
    _MAX_EVIDENCE_CHAIN = 50

    def __init__(self, timeframe: str, config: Optional[StateConfig] = None) -> None:
        self.timeframe = timeframe
        self.config = config or StateConfig()

        # 当前状态
        self.current_state: str = "IDLE"
        self.phase: str = "IDLE"
        self.direction: StateDirection = StateDirection.IDLE

        # 证据链 & 关键水平
        self.evidence_chain: List[StateEvidence] = []
        self.critical_levels: Dict[str, float] = {}

        # 历史记录
        self.state_history: List[StateTransition] = []
        self.bars_in_state: int = 0

        # 状态置信度/强度缓存
        self._state_confidences: Dict[str, float] = {}
        self._state_intensities: Dict[str, float] = {}

        # 内部标记
        self._state_changed_this_bar: bool = False
        self._previous_state: Optional[str] = None
        self._heritage_score: float = 0.0

        # 延迟初始化的检测器 Mixin 实例
        self._accum_detector: Optional[Any] = None
        self._dist_detector: Optional[Any] = None

    # --------------------------------------------------------
    # 公共接口
    # --------------------------------------------------------

    def process_candle(
        self, candle: pd.Series, context: Dict[str, Any]
    ) -> WyckoffStateResult:
        """处理单根K线，返回完整的 WyckoffStateResult

        Args:
            candle: 单根K线（open/high/low/close/volume）
            context: 上下文信息（市场体制、TR边界等）

        Returns:
            WyckoffStateResult 包含状态、阶段、证据链等
        """
        self._state_changed_this_bar = False
        self._previous_state = self.current_state

        # 1. 运行所有检测器
        candidates = self._detect_all_states(candle, context)

        # 2. 过滤：只保留合法转换 + 前置证据检查
        valid: List[StateDetectionResult] = []
        for c in candidates:
            if not TransitionGuard.is_valid_transition(
                self.current_state, c.state_name
            ):
                continue
            if not TransitionGuard.check_prerequisite_evidence(
                c.state_name, self.evidence_chain, self.critical_levels
            ):
                continue
            valid.append(c)

        # 3. 选择最佳候选
        if valid:
            best = max(valid, key=lambda c: c.confidence)
            if best.confidence > self.config.STATE_MIN_CONFIDENCE:
                self._transition_to(best, candle)

        # 4. 更新计数器
        self.bars_in_state += 1

        # 5. 构建并返回结果
        return self._build_result()

    def get_phase(self) -> str:
        """获取当前阶段标签"""
        return PHASE_MAP.get(self.current_state, "IDLE")

    def get_evidence_chain(self) -> List[StateEvidence]:
        """获取当前累积证据链"""
        return list(self.evidence_chain)

    # --------------------------------------------------------
    # 结果构建
    # --------------------------------------------------------

    def _build_result(self) -> WyckoffStateResult:
        """构建 WyckoffStateResult"""
        return WyckoffStateResult(
            current_state=self.current_state,
            phase=PHASE_MAP.get(self.current_state, "IDLE"),
            direction=self.direction,
            confidence=self._state_confidences.get(self.current_state, 0.0),
            intensity=self._state_intensities.get(self.current_state, 0.0),
            evidences=self.evidence_chain[-20:],
            signal=self._derive_signal(),
            signal_strength=self._derive_signal_strength(),
            state_changed=self._state_changed_this_bar,
            previous_state=self._previous_state,
            heritage_score=self._heritage_score,
            critical_levels=dict(self.critical_levels),
        )

    def _derive_signal(self) -> WyckoffSignal:
        """根据当前状态推导交易信号"""
        if self.current_state in _BUY_STATES:
            return WyckoffSignal.BUY_SIGNAL
        if self.current_state in _SELL_STATES:
            return WyckoffSignal.SELL_SIGNAL
        return WyckoffSignal.NO_SIGNAL

    def _derive_signal_strength(self) -> str:
        """根据当前状态推导信号强度"""
        st = self.current_state
        if st in _STRONG_BUY or st in _STRONG_SELL:
            return "strong"
        if st in _MEDIUM_BUY or st in _MEDIUM_SELL:
            return "medium"
        if st in _WEAK_SELL:
            return "weak"
        return "none"

    # --------------------------------------------------------
    # 状态转换
    # --------------------------------------------------------

    def _transition_to(self, result: StateDetectionResult, candle: pd.Series) -> None:
        """执行状态转换

        Args:
            result: 检测结果（包含目标状态、置信度、证据）
            candle: 当前K线
        """
        from_state = self.current_state
        to_state = result.state_name

        # 记录转换
        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.now(),
            confidence=result.confidence,
            transition_type=StateTransitionType.NONLINEAR,
            evidences=list(result.evidences),
            heritage_transfer=self._heritage_score * 0.8,
        )
        self.state_history.append(transition)
        # 限制历史长度
        if len(self.state_history) > 100:
            self.state_history = self.state_history[-100:]

        # 更新状态
        self.current_state = to_state
        self.phase = PHASE_MAP.get(to_state, "IDLE")
        self._state_changed_this_bar = True
        self.bars_in_state = 0

        # 更新置信度/强度
        self._state_confidences[to_state] = result.confidence
        self._state_intensities[to_state] = result.intensity

        # 更新方向
        self._update_direction(to_state)

        # 追加证据到链
        self.evidence_chain.extend(result.evidences)
        if len(self.evidence_chain) > self._MAX_EVIDENCE_CHAIN:
            self.evidence_chain = self.evidence_chain[-self._MAX_EVIDENCE_CHAIN :]

        # 遗产传递
        old_intensity = self._state_intensities.get(from_state, 0.0)
        self._heritage_score = old_intensity * 0.8

        # 记录关键价格水平
        self._record_critical_levels(to_state, candle)

        logger.debug(
            "[%s] 状态转换: %s → %s (置信度=%.2f, 阶段=%s)",
            self.timeframe,
            from_state,
            to_state,
            result.confidence,
            self.phase,
        )

    def _update_direction(self, state: str) -> None:
        """更新状态方向"""
        if state in _ACCUM_STATES:
            self.direction = StateDirection.ACCUMULATION
        elif state in _DIST_STATES:
            self.direction = StateDirection.DISTRIBUTION
        elif state in ("UPTREND", "DOWNTREND"):
            self.direction = StateDirection.TRENDING
        elif state in ("RE_ACCUMULATION", "RE_DISTRIBUTION"):
            self.direction = StateDirection.TRENDING
        elif state == "IDLE":
            self.direction = StateDirection.IDLE

    def _record_critical_levels(self, state: str, candle: pd.Series) -> None:
        """记录关键价格水平"""
        high = float(candle["high"])
        low = float(candle["low"])

        level_map: Dict[str, Dict[str, float]] = {
            "SC": {"SC_LOW": low},
            "AR": {"AR_HIGH": high},
            "SPRING": {"SPRING_LOW": low},
            "JOC": {"JOC_HIGH": high},
            "BC": {"BC_HIGH": high, "BC_LOW": low},
            "PSY": {"PSY_HIGH": high},
            "LPSY": {"LPSY_HIGH": high},
        }
        levels = level_map.get(state)
        if levels:
            self.critical_levels.update(levels)

    # --------------------------------------------------------
    # 检测器管理
    # --------------------------------------------------------

    def _ensure_detectors(self) -> None:
        """延迟初始化检测器 Mixin 实例

        将 critical_price_levels 和 state_history 注入到 Mixin 实例中，
        使其能正常访问这些共享状态。
        """
        if self._accum_detector is None:
            from src.plugins.wyckoff_state_machine.accumulation_detectors import (
                AccumulationDetectorMixin,
            )

            self._accum_detector = AccumulationDetectorMixin()
            # 注入共享状态
            self._accum_detector.critical_price_levels = self.critical_levels
            self._accum_detector.state_history = self.state_history

        if self._dist_detector is None:
            from src.plugins.wyckoff_state_machine.distribution_detectors import (
                DistributionDetectorMixin,
            )

            self._dist_detector = DistributionDetectorMixin()
            self._dist_detector.critical_price_levels = self.critical_levels
            self._dist_detector.state_history = self.state_history

        # 每次调用时同步引用（因为 dict/list 是引用类型，
        # 只有在重新赋值时才需要更新）
        self._accum_detector.critical_price_levels = self.critical_levels
        self._accum_detector.state_history = self.state_history
        self._dist_detector.critical_price_levels = self.critical_levels
        self._dist_detector.state_history = self.state_history

    # --------------------------------------------------------
    # 状态检测
    # --------------------------------------------------------

    def _detect_all_states(
        self, candle: pd.Series, context: Dict[str, Any]
    ) -> List[StateDetectionResult]:
        """运行所有检测器，返回候选状态列表"""
        self._ensure_detectors()
        candidates: List[StateDetectionResult] = []

        # 获取当前状态的合法目标
        valid_targets = TransitionGuard.get_valid_targets(self.current_state)
        if not valid_targets:
            return candidates

        # 吸筹检测器
        for state_name, method_name in _ACCUM_DETECTORS.items():
            if state_name not in valid_targets:
                continue
            self._run_detector(
                self._accum_detector,
                state_name,
                method_name,
                candle,
                context,
                candidates,
            )

        # 派发检测器
        for state_name, method_name in _DIST_DETECTORS.items():
            if state_name not in valid_targets:
                continue
            self._run_detector(
                self._dist_detector,
                state_name,
                method_name,
                candle,
                context,
                candidates,
            )

        # 再积累/再派发检测
        if "RE_ACCUMULATION" in valid_targets:
            re_accum = self._detect_re_accumulation(candle, context)
            if re_accum is not None:
                candidates.append(re_accum)
        if "RE_DISTRIBUTION" in valid_targets:
            re_dist = self._detect_re_distribution(candle, context)
            if re_dist is not None:
                candidates.append(re_dist)

        # 趋势恢复检测
        if "UPTREND" in valid_targets:
            trend_up = self._detect_trend_resumption(candle, context, "UPTREND")
            if trend_up is not None:
                candidates.append(trend_up)
        if "DOWNTREND" in valid_targets:
            trend_down = self._detect_trend_resumption(candle, context, "DOWNTREND")
            if trend_down is not None:
                candidates.append(trend_down)

        return candidates

    def _run_detector(
        self,
        detector: Any,
        state_name: str,
        method_name: str,
        candle: pd.Series,
        context: Dict[str, Any],
        candidates: List[StateDetectionResult],
    ) -> None:
        """运行单个检测器并将结果追加到候选列表"""
        method = getattr(detector, method_name, None)
        if method is None:
            return
        try:
            result = method(candle, context)
        except Exception:
            logger.debug(
                "[%s] 检测器 %s 执行异常",
                self.timeframe,
                method_name,
                exc_info=True,
            )
            return

        confidence = result.get("confidence", 0.0)
        if confidence <= self.config.STATE_MIN_CONFIDENCE:
            return

        raw_evidences = result.get("evidences", [])
        evidences = self._normalize_evidences(raw_evidences, state_name)

        candidates.append(
            StateDetectionResult(
                state_name=state_name,
                confidence=confidence,
                intensity=result.get("intensity", 0.0),
                evidences=evidences,
            )
        )

    @staticmethod
    def _normalize_evidences(raw: List[Any], state_name: str) -> List[StateEvidence]:
        """将检测器输出的证据统一为 List[StateEvidence]

        兼容旧版检测器返回 List[str] 的情况。
        """
        evidences: List[StateEvidence] = []
        for item in raw:
            if isinstance(item, StateEvidence):
                evidences.append(item)
            elif isinstance(item, str):
                # 旧版兼容：字符串证据 → StateEvidence
                evidences.append(
                    StateEvidence(
                        evidence_type=f"{state_name}_evidence",
                        value=1.0,
                        confidence=0.5,
                        weight=0.3,
                        description=item,
                    )
                )
        return evidences

    # --------------------------------------------------------
    # 再积累/再派发检测 (§4.6)
    # --------------------------------------------------------

    def _detect_re_accumulation(
        self, candle: pd.Series, context: Dict[str, Any]
    ) -> Optional[StateDetectionResult]:
        """在上升趋势中检测再积累

        条件：
        1. 当前处于 UPTREND
        2. 价格回调但不跌破前一波 LPS
        3. 成交量收缩
        4. 形成更高的支撑
        """
        if self.current_state != "UPTREND":
            return None

        required = ["open", "high", "low", "close", "volume"]
        if not all(f in candle for f in required):
            return None

        close = float(candle["close"])
        low = float(candle["low"])
        open_price = float(candle["open"])
        volume = float(candle["volume"])

        evidences: List[StateEvidence] = []
        scores: List[float] = []

        # 条件1：价格回调（阴线或小阳线，非强势上涨）
        is_pullback = close < open_price or (close - open_price) / open_price < 0.005
        if is_pullback:
            scores.append(0.3)
            evidences.append(
                StateEvidence(
                    evidence_type="price_pullback",
                    value=1.0,
                    confidence=0.6,
                    weight=0.4,
                    description=f"上升趋势中价格回调 close={close:.2f}",
                )
            )

        # 条件2：不跌破前一波 LPS 或 SPRING_LOW
        lps_low = self.critical_levels.get("SPRING_LOW")
        sc_low = self.critical_levels.get("SC_LOW")
        ref_low = lps_low or sc_low
        if ref_low is not None and low > ref_low:
            scores.append(0.3)
            evidences.append(
                StateEvidence(
                    evidence_type="higher_support",
                    value=low - ref_low,
                    confidence=0.7,
                    weight=0.5,
                    description=(f"保持更高支撑 low={low:.2f} > ref={ref_low:.2f}"),
                )
            )

        # 条件3：成交量收缩
        avg_vol = context.get("avg_volume_20", volume * 1.5)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1.0
        if vol_ratio < 0.8:
            scores.append(0.2)
            evidences.append(
                StateEvidence(
                    evidence_type="volume_contraction",
                    value=vol_ratio,
                    confidence=0.6,
                    weight=0.4,
                    description=f"成交量收缩 vol_ratio={vol_ratio:.2f}",
                )
            )

        confidence = min(1.0, sum(scores))
        if confidence < self.config.STATE_MIN_CONFIDENCE:
            return None

        return StateDetectionResult(
            state_name="RE_ACCUMULATION",
            confidence=confidence,
            intensity=vol_ratio,
            evidences=evidences,
        )

    def _detect_re_distribution(
        self, candle: pd.Series, context: Dict[str, Any]
    ) -> Optional[StateDetectionResult]:
        """在下降趋势中检测再派发

        条件：
        1. 当前处于 DOWNTREND
        2. 价格反弹但不突破前一波 LPSY
        3. 成交量放大
        4. 形成更低的阻力
        """
        if self.current_state != "DOWNTREND":
            return None

        required = ["open", "high", "low", "close", "volume"]
        if not all(f in candle for f in required):
            return None

        close = float(candle["close"])
        high = float(candle["high"])
        open_price = float(candle["open"])
        volume = float(candle["volume"])

        evidences: List[StateEvidence] = []
        scores: List[float] = []

        # 条件1：价格反弹（阳线或小阴线，非强势下跌）
        is_bounce = close > open_price or (open_price - close) / open_price < 0.005
        if is_bounce:
            scores.append(0.3)
            evidences.append(
                StateEvidence(
                    evidence_type="price_bounce",
                    value=1.0,
                    confidence=0.6,
                    weight=0.4,
                    description=f"下降趋势中价格反弹 close={close:.2f}",
                )
            )

        # 条件2：不突破前一波 LPSY 或 BC_HIGH
        lpsy_high = self.critical_levels.get("LPSY_HIGH")
        bc_high = self.critical_levels.get("BC_HIGH")
        ref_high = lpsy_high or bc_high
        if ref_high is not None and high < ref_high:
            scores.append(0.3)
            evidences.append(
                StateEvidence(
                    evidence_type="lower_resistance",
                    value=ref_high - high,
                    confidence=0.7,
                    weight=0.5,
                    description=(f"保持更低阻力 high={high:.2f} < ref={ref_high:.2f}"),
                )
            )

        # 条件3：成交量放大
        avg_vol = context.get("avg_volume_20", volume * 1.5)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1.0
        if vol_ratio > 1.2:
            scores.append(0.2)
            evidences.append(
                StateEvidence(
                    evidence_type="volume_expansion",
                    value=vol_ratio,
                    confidence=0.6,
                    weight=0.4,
                    description=f"成交量放大 vol_ratio={vol_ratio:.2f}",
                )
            )

        confidence = min(1.0, sum(scores))
        if confidence < self.config.STATE_MIN_CONFIDENCE:
            return None

        return StateDetectionResult(
            state_name="RE_DISTRIBUTION",
            confidence=confidence,
            intensity=vol_ratio,
            evidences=evidences,
        )

    def _detect_trend_resumption(
        self, candle: pd.Series, context: Dict[str, Any], target: str
    ) -> Optional[StateDetectionResult]:
        """检测趋势恢复（从 RE_ACCUMULATION→UPTREND
        或 RE_DISTRIBUTION→DOWNTREND）

        Args:
            candle: 当前K线
            context: 上下文
            target: "UPTREND" 或 "DOWNTREND"
        """
        required = ["open", "high", "low", "close", "volume"]
        if not all(f in candle for f in required):
            return None

        close = float(candle["close"])
        open_price = float(candle["open"])
        volume = float(candle["volume"])

        evidences: List[StateEvidence] = []
        scores: List[float] = []

        avg_vol = context.get("avg_volume_20", volume * 1.5)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1.0

        if target == "UPTREND":
            # 从 RE_ACCUMULATION 恢复上涨
            # 条件：强阳线 + 成交量放大
            body_pct = (close - open_price) / open_price if open_price > 0 else 0
            if body_pct > 0.01:
                scores.append(0.4)
                evidences.append(
                    StateEvidence(
                        evidence_type="bullish_resumption",
                        value=body_pct,
                        confidence=0.7,
                        weight=0.6,
                        description=f"强阳线确认上涨恢复 body={body_pct:.3f}",
                    )
                )
            if vol_ratio > 1.3:
                scores.append(0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="volume_confirmation",
                        value=vol_ratio,
                        confidence=0.6,
                        weight=0.5,
                        description=f"成交量确认 vol_ratio={vol_ratio:.2f}",
                    )
                )
        elif target == "DOWNTREND":
            # 从 RE_DISTRIBUTION 恢复下跌
            body_pct = (open_price - close) / open_price if open_price > 0 else 0
            if body_pct > 0.01:
                scores.append(0.4)
                evidences.append(
                    StateEvidence(
                        evidence_type="bearish_resumption",
                        value=body_pct,
                        confidence=0.7,
                        weight=0.6,
                        description=f"强阴线确认下跌恢复 body={body_pct:.3f}",
                    )
                )
            if vol_ratio > 1.3:
                scores.append(0.3)
                evidences.append(
                    StateEvidence(
                        evidence_type="volume_confirmation",
                        value=vol_ratio,
                        confidence=0.6,
                        weight=0.5,
                        description=f"成交量确认 vol_ratio={vol_ratio:.2f}",
                    )
                )

        confidence = min(1.0, sum(scores))
        if confidence < self.config.STATE_MIN_CONFIDENCE:
            return None

        return StateDetectionResult(
            state_name=target,
            confidence=confidence,
            intensity=vol_ratio,
            evidences=evidences,
        )
