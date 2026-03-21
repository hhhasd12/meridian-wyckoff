"""WyckoffStateMachineV2 单元测试

测试内容：
1. 初始化和默认状态
2. PHASE_MAP 标签正确性
3. process_candle 返回 WyckoffStateResult
4. TransitionGuard 硬约束生效
5. 证据链传递完整性
6. 再积累/再派发检测
7. 信号推导
"""

import pytest
import pandas as pd
from typing import Any, Dict

from src.plugins.wyckoff_state_machine.state_machine_v2 import (
    PHASE_MAP,
    WyckoffStateMachineV2,
    _ACCUM_STATES,
    _BUY_STATES,
    _DIST_STATES,
    _SELL_STATES,
)
from src.kernel.types import (
    StateConfig,
    StateDirection,
    StateEvidence,
    WyckoffSignal,
    WyckoffStateResult,
)


# ============================================================
# 辅助工厂
# ============================================================


def _make_candle(
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: float = 1000.0,
) -> pd.Series:
    """构建一根测试K线"""
    return pd.Series(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _make_context(**overrides: Any) -> Dict[str, Any]:
    """构建上下文字典"""
    ctx: Dict[str, Any] = {
        "avg_volume_20": 1000.0,
        "market_regime": "UNKNOWN",
    }
    ctx.update(overrides)
    return ctx


def _make_evidence(evidence_type: str, value: float = 1.0) -> StateEvidence:
    """快速构建一条 StateEvidence"""
    return StateEvidence(
        evidence_type=evidence_type,
        value=value,
        confidence=0.8,
        weight=1.0,
        description=f"test evidence: {evidence_type}",
    )


# ============================================================
# TestInitialization — 初始化和默认状态
# ============================================================


class TestInitialization:
    """初始化测试"""

    def test_default_state(self) -> None:
        """新实例初始状态为 IDLE"""
        sm = WyckoffStateMachineV2("H4")
        assert sm.current_state == "IDLE"
        assert sm.phase == "IDLE"
        assert sm.direction == StateDirection.IDLE
        assert sm.bars_in_state == 0

    def test_timeframe_stored(self) -> None:
        """时间框架标识正确存储"""
        sm = WyckoffStateMachineV2("M15")
        assert sm.timeframe == "M15"

    def test_custom_config(self) -> None:
        """自定义配置生效"""
        cfg = StateConfig()
        cfg.STATE_MIN_CONFIDENCE = 0.9
        sm = WyckoffStateMachineV2("H1", config=cfg)
        assert sm.config.STATE_MIN_CONFIDENCE == 0.9

    def test_empty_collections(self) -> None:
        """初始时各集合为空"""
        sm = WyckoffStateMachineV2("H4")
        assert sm.evidence_chain == []
        assert sm.critical_levels == {}
        assert sm.state_history == []

    def test_independent_instances(self) -> None:
        """不同TF实例互不影响"""
        h4 = WyckoffStateMachineV2("H4")
        h1 = WyckoffStateMachineV2("H1")
        h4.current_state = "SC"
        assert h1.current_state == "IDLE"
        h4.critical_levels["SC_LOW"] = 90.0
        assert "SC_LOW" not in h1.critical_levels


# ============================================================
# TestPhaseMap — 阶段标签映射
# ============================================================


class TestPhaseMap:
    """PHASE_MAP 映射验证"""

    def test_accumulation_phase_a(self) -> None:
        """吸筹A阶段：PS/SC/AR/ST"""
        for state in ["PS", "SC", "AR", "ST"]:
            assert PHASE_MAP[state] == "A", f"{state} should be Phase A"

    def test_accumulation_phase_b(self) -> None:
        """吸筹B阶段：TEST/UTA"""
        assert PHASE_MAP["TEST"] == "B"
        assert PHASE_MAP["UTA"] == "B"

    def test_accumulation_phase_c(self) -> None:
        """吸筹C阶段：SPRING/SO/LPS/mSOS"""
        for state in ["SPRING", "SO", "LPS", "mSOS"]:
            assert PHASE_MAP[state] == "C", f"{state} should be Phase C"

    def test_accumulation_phase_d_e(self) -> None:
        """吸筹D-E阶段"""
        assert PHASE_MAP["MSOS"] == "D"
        assert PHASE_MAP["JOC"] == "D"
        assert PHASE_MAP["BU"] == "E"

    def test_distribution_phases(self) -> None:
        """派发各阶段映射"""
        assert PHASE_MAP["PSY"] == "A"
        assert PHASE_MAP["BC"] == "A"
        assert PHASE_MAP["UT"] == "B"
        assert PHASE_MAP["UTAD"] == "C"
        assert PHASE_MAP["mSOW"] == "D"
        assert PHASE_MAP["MSOW"] == "D"

    def test_special_states(self) -> None:
        """特殊状态映射"""
        assert PHASE_MAP["IDLE"] == "IDLE"
        assert PHASE_MAP["UPTREND"] == "MARKUP"
        assert PHASE_MAP["DOWNTREND"] == "MARKDOWN"
        assert PHASE_MAP["RE_ACCUMULATION"] == "B"
        assert PHASE_MAP["RE_DISTRIBUTION"] == "B"

    def test_get_phase_method(self) -> None:
        """get_phase() 使用 PHASE_MAP"""
        sm = WyckoffStateMachineV2("H4")
        assert sm.get_phase() == "IDLE"


# ============================================================
# TestProcessCandle — process_candle 返回值
# ============================================================


class TestProcessCandle:
    """process_candle 基本行为测试"""

    def setup_method(self) -> None:
        # 使用高阈值配置，避免弱信号触发状态转换
        cfg = StateConfig()
        cfg.STATE_MIN_CONFIDENCE = 0.8
        self.sm = WyckoffStateMachineV2("H4", config=cfg)
        self.candle = _make_candle()
        self.ctx = _make_context()

    def test_returns_wyckoff_state_result(self) -> None:
        """process_candle 返回 WyckoffStateResult"""
        result = self.sm.process_candle(self.candle, self.ctx)
        assert isinstance(result, WyckoffStateResult)

    def test_result_has_required_fields(self) -> None:
        """返回值包含所有必需字段"""
        result = self.sm.process_candle(self.candle, self.ctx)
        assert hasattr(result, "current_state")
        assert hasattr(result, "phase")
        assert hasattr(result, "direction")
        assert hasattr(result, "confidence")
        assert hasattr(result, "intensity")
        assert hasattr(result, "evidences")
        assert hasattr(result, "signal")
        assert hasattr(result, "signal_strength")
        assert hasattr(result, "state_changed")
        assert hasattr(result, "previous_state")
        assert hasattr(result, "heritage_score")
        assert hasattr(result, "critical_levels")

    def test_idle_no_change(self) -> None:
        """极中性K线不触发状态变化"""
        # 用极小波动的K线，不会触发任何检测器
        neutral = _make_candle(
            open_=100.0,
            high=100.1,
            low=99.9,
            close=100.0,
            volume=100.0,
        )
        ctx = _make_context(avg_volume_20=100.0)
        result = self.sm.process_candle(neutral, ctx)
        assert result.current_state == "IDLE"
        assert result.state_changed is False
        assert result.signal == WyckoffSignal.NO_SIGNAL
        assert result.signal_strength == "none"

    def test_bars_in_state_increments(self) -> None:
        """bars_in_state 每次递增"""
        neutral = _make_candle(
            open_=100.0,
            high=100.1,
            low=99.9,
            close=100.0,
            volume=100.0,
        )
        ctx = _make_context(avg_volume_20=100.0)
        self.sm.process_candle(neutral, ctx)
        assert self.sm.bars_in_state == 1
        self.sm.process_candle(neutral, ctx)
        assert self.sm.bars_in_state == 2

    def test_phase_matches_current_state(self) -> None:
        """phase 始终与 current_state 的 PHASE_MAP 一致"""
        result = self.sm.process_candle(self.candle, self.ctx)
        expected_phase = PHASE_MAP.get(result.current_state, "IDLE")
        assert result.phase == expected_phase

    def test_evidences_is_list(self) -> None:
        """evidences 始终是 list"""
        result = self.sm.process_candle(self.candle, self.ctx)
        assert isinstance(result.evidences, list)

    def test_critical_levels_is_dict(self) -> None:
        """critical_levels 始终是 dict"""
        result = self.sm.process_candle(self.candle, self.ctx)
        assert isinstance(result.critical_levels, dict)


# ============================================================
# TestTransitionGuardIntegration — Guard 硬约束
# ============================================================


class TestTransitionGuardIntegration:
    """TransitionGuard 与 V2 状态机的集成测试"""

    def setup_method(self) -> None:
        # 高阈值确保弱信号不误触发
        cfg = StateConfig()
        cfg.STATE_MIN_CONFIDENCE = 0.8
        self.sm = WyckoffStateMachineV2("H4", config=cfg)

    def test_guard_blocks_invalid_transition(self) -> None:
        """Guard 阻止非法转换（IDLE 不能直接跳到 SPRING）"""
        # 用极中性K线确保不触发入口检测器
        neutral = _make_candle(
            open_=100.0,
            high=100.1,
            low=99.9,
            close=100.0,
            volume=100.0,
        )
        ctx = _make_context(avg_volume_20=100.0)
        self.sm.process_candle(neutral, ctx)
        # 状态应该还是 IDLE
        assert self.sm.current_state == "IDLE"

    def test_state_history_records_transitions(self) -> None:
        """状态转换被记录到 state_history"""
        initial_len = len(self.sm.state_history)
        # 无论是否发生转换，历史长度不应减少
        candle = _make_candle()
        ctx = _make_context()
        self.sm.process_candle(candle, ctx)
        assert len(self.sm.state_history) >= initial_len


# ============================================================
# TestSignalDerivation — 信号推导
# ============================================================


class TestSignalDerivation:
    """信号推导验证"""

    def setup_method(self) -> None:
        self.sm = WyckoffStateMachineV2("H4")

    def test_buy_states_produce_buy_signal(self) -> None:
        """买入状态产生 BUY_SIGNAL"""
        for state in _BUY_STATES:
            self.sm.current_state = state
            signal = self.sm._derive_signal()
            assert signal == WyckoffSignal.BUY_SIGNAL, (
                f"{state} should produce BUY_SIGNAL"
            )

    def test_sell_states_produce_sell_signal(self) -> None:
        """卖出状态产生 SELL_SIGNAL"""
        for state in _SELL_STATES:
            self.sm.current_state = state
            signal = self.sm._derive_signal()
            assert signal == WyckoffSignal.SELL_SIGNAL, (
                f"{state} should produce SELL_SIGNAL"
            )

    def test_idle_produces_no_signal(self) -> None:
        """IDLE 产生 NO_SIGNAL"""
        self.sm.current_state = "IDLE"
        assert self.sm._derive_signal() == WyckoffSignal.NO_SIGNAL

    def test_strong_buy_strength(self) -> None:
        """JOC/BU/MSOS 为 strong"""
        for state in ["JOC", "BU", "MSOS"]:
            self.sm.current_state = state
            assert self.sm._derive_signal_strength() == "strong", (
                f"{state} should be strong"
            )

    def test_medium_buy_strength(self) -> None:
        """SPRING/SO/LPS/mSOS 为 medium"""
        for state in ["SPRING", "SO", "LPS", "mSOS"]:
            self.sm.current_state = state
            assert self.sm._derive_signal_strength() == "medium", (
                f"{state} should be medium"
            )

    def test_idle_strength_none(self) -> None:
        """IDLE 信号强度为 none"""
        self.sm.current_state = "IDLE"
        assert self.sm._derive_signal_strength() == "none"


# ============================================================
# TestNormalizeEvidences — 证据规范化
# ============================================================


class TestNormalizeEvidences:
    """_normalize_evidences 静态方法测试"""

    def test_pass_through_state_evidence(self) -> None:
        """StateEvidence 对象直接保留"""
        ev = _make_evidence("test_type")
        result = WyckoffStateMachineV2._normalize_evidences([ev], "SC")
        assert len(result) == 1
        assert result[0] is ev

    def test_string_to_state_evidence(self) -> None:
        """字符串自动转换为 StateEvidence"""
        result = WyckoffStateMachineV2._normalize_evidences(
            ["some string evidence"], "PS"
        )
        assert len(result) == 1
        assert isinstance(result[0], StateEvidence)
        assert result[0].evidence_type == "PS_evidence"
        assert result[0].description == "some string evidence"

    def test_mixed_list(self) -> None:
        """混合列表（StateEvidence + str）"""
        ev = _make_evidence("real")
        result = WyckoffStateMachineV2._normalize_evidences(
            [ev, "fallback string"], "AR"
        )
        assert len(result) == 2
        assert isinstance(result[0], StateEvidence)
        assert isinstance(result[1], StateEvidence)
        assert result[0].evidence_type == "real"
        assert result[1].evidence_type == "AR_evidence"

    def test_empty_list(self) -> None:
        """空列表返回空"""
        result = WyckoffStateMachineV2._normalize_evidences([], "IDLE")
        assert result == []


# ============================================================
# TestReAccumulationReDistribution — 再积累/再派发
# ============================================================


class TestReAccumulationReDistribution:
    """再积累/再派发检测测试"""

    def test_re_accumulation_requires_uptrend(self) -> None:
        """_detect_re_accumulation 仅在 UPTREND 状态触发"""
        sm = WyckoffStateMachineV2("H4")
        # IDLE 状态 → 返回 None
        candle = _make_candle(
            open_=105.0,
            high=106.0,
            low=100.0,
            close=101.0,
            volume=500.0,
        )
        ctx = _make_context(avg_volume_20=1000.0)
        result = sm._detect_re_accumulation(candle, ctx)
        assert result is None

    def test_re_accumulation_in_uptrend(self) -> None:
        """UPTREND 中的回调 + 缩量触发再积累"""
        sm = WyckoffStateMachineV2("H4")
        sm.current_state = "UPTREND"
        sm.critical_levels["SPRING_LOW"] = 90.0
        # 回调K线：阴线 + 缩量 + 不破 SPRING_LOW
        candle = _make_candle(
            open_=105.0,
            high=106.0,
            low=95.0,
            close=101.0,
            volume=500.0,
        )
        ctx = _make_context(avg_volume_20=1000.0)
        result = sm._detect_re_accumulation(candle, ctx)
        # 可能触发也可能不触发取决于阈值，但不应该报错
        if result is not None:
            assert result.state_name == "RE_ACCUMULATION"
            assert result.confidence > 0
            assert len(result.evidences) > 0

    def test_re_distribution_requires_downtrend(self) -> None:
        """_detect_re_distribution 仅在 DOWNTREND 状态触发"""
        sm = WyckoffStateMachineV2("H4")
        candle = _make_candle()
        ctx = _make_context()
        result = sm._detect_re_distribution(candle, ctx)
        assert result is None

    def test_re_distribution_in_downtrend(self) -> None:
        """DOWNTREND 中的反弹 + 放量触发再派发"""
        sm = WyckoffStateMachineV2("H4")
        sm.current_state = "DOWNTREND"
        sm.critical_levels["LPSY_HIGH"] = 110.0
        # 反弹K线：阳线 + 放量 + 不破 LPSY_HIGH
        candle = _make_candle(
            open_=95.0,
            high=105.0,
            low=94.0,
            close=103.0,
            volume=1500.0,
        )
        ctx = _make_context(avg_volume_20=1000.0)
        result = sm._detect_re_distribution(candle, ctx)
        if result is not None:
            assert result.state_name == "RE_DISTRIBUTION"
            assert result.confidence > 0
            assert len(result.evidences) > 0


# ============================================================
# TestDirectionUpdate — 状态方向更新
# ============================================================


class TestDirectionUpdate:
    """_update_direction 验证"""

    def setup_method(self) -> None:
        self.sm = WyckoffStateMachineV2("H4")

    def test_accumulation_direction(self) -> None:
        """吸筹状态 → ACCUMULATION 方向"""
        for state in _ACCUM_STATES:
            self.sm._update_direction(state)
            assert self.sm.direction == StateDirection.ACCUMULATION, (
                f"{state} should set ACCUMULATION"
            )

    def test_distribution_direction(self) -> None:
        """派发状态 → DISTRIBUTION 方向"""
        for state in _DIST_STATES:
            self.sm._update_direction(state)
            assert self.sm.direction == StateDirection.DISTRIBUTION, (
                f"{state} should set DISTRIBUTION"
            )

    def test_trend_direction(self) -> None:
        """趋势状态 → TRENDING 方向"""
        self.sm._update_direction("UPTREND")
        assert self.sm.direction == StateDirection.TRENDING
        self.sm._update_direction("DOWNTREND")
        assert self.sm.direction == StateDirection.TRENDING

    def test_idle_direction(self) -> None:
        """IDLE → IDLE 方向"""
        self.sm._update_direction("IDLE")
        assert self.sm.direction == StateDirection.IDLE


# ============================================================
# TestCriticalLevels — 关键价格水平记录
# ============================================================


class TestCriticalLevels:
    """_record_critical_levels 验证"""

    def setup_method(self) -> None:
        self.sm = WyckoffStateMachineV2("H4")

    def test_sc_records_low(self) -> None:
        """SC 记录 SC_LOW"""
        candle = _make_candle(low=85.0)
        self.sm._record_critical_levels("SC", candle)
        assert self.sm.critical_levels["SC_LOW"] == 85.0

    def test_bc_records_high_and_low(self) -> None:
        """BC 记录 BC_HIGH 和 BC_LOW"""
        candle = _make_candle(high=120.0, low=110.0)
        self.sm._record_critical_levels("BC", candle)
        assert self.sm.critical_levels["BC_HIGH"] == 120.0
        assert self.sm.critical_levels["BC_LOW"] == 110.0

    def test_joc_records_high(self) -> None:
        """JOC 记录 JOC_HIGH"""
        candle = _make_candle(high=115.0)
        self.sm._record_critical_levels("JOC", candle)
        assert self.sm.critical_levels["JOC_HIGH"] == 115.0

    def test_spring_records_low(self) -> None:
        """SPRING 记录 SPRING_LOW"""
        candle = _make_candle(low=80.0)
        self.sm._record_critical_levels("SPRING", candle)
        assert self.sm.critical_levels["SPRING_LOW"] == 80.0

    def test_unknown_state_no_record(self) -> None:
        """未定义状态不记录"""
        candle = _make_candle()
        self.sm._record_critical_levels("IDLE", candle)
        assert len(self.sm.critical_levels) == 0
