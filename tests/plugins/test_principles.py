"""Phase 1 单元测试 — 三大原则打分器

覆盖：
- BarFeatures 数据类字段和不可变性
- StructureContext 数据类字段
- WyckoffPrinciplesScorer 单K线特征计算
- WyckoffPrinciplesScorer 集成三大原则子分析器
- supply_demand 子分析器
- cause_effect 子分析器
- effort_result 子分析器
"""

import pytest
from collections import deque

from src.plugins.wyckoff_state_machine.principles.bar_features import (
    BarFeatures,
    StructureContext,
    WyckoffPrinciplesScorer,
)
from src.plugins.wyckoff_state_machine.principles.supply_demand import (
    calc_supply_demand,
)
from src.plugins.wyckoff_state_machine.principles.cause_effect import (
    calc_cause_effect,
)
from src.plugins.wyckoff_state_machine.principles.effort_result import (
    calc_effort_result,
)


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def _candle(open_=100.0, high=105.0, low=95.0, close=103.0, volume=1000.0):
    """创建标准K线字典"""
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _fill_history(scorer, n=25, base_price=100.0, volume=1000.0):
    """填充N根平稳K线历史，返回最后一根的 BarFeatures"""
    result = None
    for i in range(n):
        c = _candle(
            open_=base_price,
            high=base_price + 5,
            low=base_price - 5,
            close=base_price + 1,
            volume=volume,
        )
        result = scorer.score(c)
    return result


def _context(**overrides):
    """创建 StructureContext，默认值为中性"""
    defaults = dict(
        current_phase="B",
        last_confirmed_event="ST",
        position_in_tr=0.5,
        distance_to_support=0.5,
        distance_to_resistance=0.5,
        test_quality=0.5,
        recovery_speed=0.5,
        swing_context="unknown",
        direction_bias=0.0,
        boundaries={"SC_LOW": {}, "AR_HIGH": {}},
    )
    defaults.update(overrides)
    return StructureContext(**defaults)


# ---------------------------------------------------------------------------
# BarFeatures 测试
# ---------------------------------------------------------------------------


class TestBarFeatures:
    """BarFeatures 数据类"""

    def test_all_fields_present(self):
        bf = BarFeatures(
            supply_demand=0.5,
            cause_effect=0.3,
            effort_result=-0.2,
            volume_ratio=1.1,
            price_range_ratio=0.9,
            body_ratio=0.6,
            is_stopping_action=False,
            spread_vs_volume_divergence=0.2,
        )
        assert bf.supply_demand == 0.5
        assert bf.effort_result == -0.2
        assert bf.is_stopping_action is False

    def test_frozen_immutable(self):
        bf = BarFeatures(0, 0, 0, 1, 1, 0.5, False, 0)
        with pytest.raises(AttributeError):
            bf.supply_demand = 999  # type: ignore[misc]

    def test_field_count(self):
        """8个字段"""
        import dataclasses

        assert len(dataclasses.fields(BarFeatures)) == 8


class TestStructureContext:
    """StructureContext 数据类"""

    def test_all_fields(self):
        ctx = _context()
        assert ctx.current_phase == "B"
        assert ctx.direction_bias == 0.0
        assert isinstance(ctx.boundaries, dict)

    def test_field_count(self):
        import dataclasses

        assert len(dataclasses.fields(StructureContext)) == 11


# ---------------------------------------------------------------------------
# WyckoffPrinciplesScorer 测试
# ---------------------------------------------------------------------------


class TestScorerBasics:
    """打分器基本功能"""

    def test_first_candle_returns_features(self):
        scorer = WyckoffPrinciplesScorer()
        result = scorer.score(_candle())
        assert isinstance(result, BarFeatures)

    def test_first_candle_defaults(self):
        """首根K线：volume_ratio=1.0, 三原则=0"""
        scorer = WyckoffPrinciplesScorer()
        bf = scorer.score(_candle())
        assert bf.volume_ratio == 1.0
        assert bf.price_range_ratio == 1.0

    def test_history_grows(self):
        scorer = WyckoffPrinciplesScorer()
        for _ in range(5):
            scorer.score(_candle())
        assert len(scorer._history) == 5

    def test_history_maxlen(self):
        scorer = WyckoffPrinciplesScorer()
        for _ in range(60):
            scorer.score(_candle())
        assert len(scorer._history) == 50


class TestScorerCandle:
    """单K线特征计算"""

    def test_body_ratio_bullish(self):
        scorer = WyckoffPrinciplesScorer()
        c = _candle(open_=95, high=105, low=95, close=105)
        bf = scorer.score(c)
        assert bf.body_ratio == pytest.approx(1.0)

    def test_body_ratio_doji(self):
        scorer = WyckoffPrinciplesScorer()
        c = _candle(open_=100, high=105, low=95, close=100)
        bf = scorer.score(c)
        assert bf.body_ratio == pytest.approx(0.0)

    def test_body_ratio_zero_range(self):
        scorer = WyckoffPrinciplesScorer()
        c = _candle(open_=100, high=100, low=100, close=100)
        bf = scorer.score(c)
        assert bf.body_ratio == 0.0

    def test_volume_ratio_high_volume(self):
        scorer = WyckoffPrinciplesScorer()
        _fill_history(scorer, n=25, volume=1000)
        high_vol = _candle(volume=3000)
        bf = scorer.score(high_vol)
        assert bf.volume_ratio > 2.5

    def test_stopping_action_detection(self):
        scorer = WyckoffPrinciplesScorer()
        _fill_history(scorer, n=25, volume=1000)
        # 高量(>1.5x) + 小实体(<0.3)
        stop_candle = _candle(open_=100, high=110, low=90, close=101, volume=2000)
        bf = scorer.score(stop_candle)
        assert bf.is_stopping_action is True

    def test_non_stopping_action(self):
        scorer = WyckoffPrinciplesScorer()
        _fill_history(scorer, n=25, volume=1000)
        normal = _candle(volume=1000)
        bf = scorer.score(normal)
        assert bf.is_stopping_action is False


# ---------------------------------------------------------------------------
# 供需分析器测试
# ---------------------------------------------------------------------------


class TestSupplyDemand:
    """supply_demand 子分析器"""

    def _hist(self, candles):
        h = deque(maxlen=50)
        for c in candles:
            h.append(c)
        return h

    def test_bullish_positive(self):
        """放量上涨 → 正分（需求）"""
        base = [_candle(volume=1000) for _ in range(20)]
        bull = _candle(open_=95, close=105, volume=2000)
        score = calc_supply_demand(bull, self._hist(base + [bull]))
        assert score > 0

    def test_bearish_negative(self):
        """放量下跌 → 负分（供应）"""
        base = [_candle(volume=1000) for _ in range(20)]
        bear = _candle(open_=105, close=95, volume=2000)
        score = calc_supply_demand(bear, self._hist(base + [bear]))
        assert score < 0

    def test_near_support_positive(self):
        ctx = _context(position_in_tr=0.1)
        h = self._hist([_candle() for _ in range(5)])
        assert calc_supply_demand(_candle(), h, ctx) > 0

    def test_near_resistance_negative(self):
        ctx = _context(position_in_tr=0.9)
        # 用中性K线（open==close）使量价方向为零，凸显位置负分
        neutral = _candle(open_=100, close=100, volume=1000)
        h = self._hist([neutral for _ in range(5)])
        assert calc_supply_demand(neutral, h, ctx) < 0

    def test_clamped(self):
        base = [_candle(volume=1000) for _ in range(20)]
        extreme = _candle(open_=50, close=150, volume=10000)
        s = calc_supply_demand(extreme, self._hist(base + [extreme]))
        assert -1.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# 因果分析器测试
# ---------------------------------------------------------------------------


class TestCauseEffect:
    def test_no_context_zero(self):
        h = deque([_candle() for _ in range(5)], maxlen=50)
        assert calc_cause_effect(_candle(), h, None) == 0.0

    def test_idle_zero(self):
        ctx = _context(current_phase="IDLE")
        h = deque([_candle() for _ in range(5)], maxlen=50)
        assert calc_cause_effect(_candle(), h, ctx) == 0.0

    def test_later_phase_higher(self):
        h = deque([_candle() for _ in range(25)], maxlen=50)
        a = calc_cause_effect(_candle(), h, _context(current_phase="A"))
        c = calc_cause_effect(_candle(), h, _context(current_phase="C"))
        assert c > a

    def test_clamped(self):
        h = deque([_candle() for _ in range(25)], maxlen=50)
        s = calc_cause_effect(_candle(), h, _context())
        assert 0.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# 努力结果分析器测试
# ---------------------------------------------------------------------------


class TestEffortResult:
    def test_first_candle_zero(self):
        h = deque([_candle()], maxlen=50)
        assert calc_effort_result(_candle(), h) == 0.0

    def test_clamped(self):
        base = [_candle(volume=1000) for _ in range(20)]
        c = _candle(volume=5000)
        h = deque(base + [c], maxlen=50)
        s = calc_effort_result(c, h)
        assert -1.0 <= s <= 1.0

    def test_returns_float(self):
        h = deque([_candle() for _ in range(10)], maxlen=50)
        assert isinstance(calc_effort_result(_candle(), h), float)


# ---------------------------------------------------------------------------
# 集成测试：Scorer 调用所有子分析器
# ---------------------------------------------------------------------------


class TestScorerIntegration:
    def test_full_pipeline(self):
        """25根K线后，三原则分数不全为零"""
        scorer = WyckoffPrinciplesScorer()
        _fill_history(scorer, n=25)
        bf = scorer.score(
            _candle(open_=95, close=108, volume=2000),
            prev_context=_context(),
        )
        assert isinstance(bf, BarFeatures)
        # 至少有一个原则分数非零
        assert bf.supply_demand != 0 or bf.effort_result != 0

    def test_with_context(self):
        scorer = WyckoffPrinciplesScorer()
        _fill_history(scorer, n=25)
        ctx = _context(position_in_tr=0.1, current_phase="C")
        bf = scorer.score(_candle(), ctx)
        assert bf.cause_effect > 0
