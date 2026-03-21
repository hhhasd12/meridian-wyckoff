"""
统一信号引擎 v3 — 实盘和进化的唯一信号来源

从旧版 engine.py 重建，关键变更：
1. 每TF独立 WyckoffStateMachineV2 实例（不再共享单一 legacy 状态机）
2. 类型化接口 — PerceptionResult / FusionResult / WyckoffStateResult（不再散装 Dict）
3. 新增 process_bar() → BarSignal（进化回测逐bar调用）
4. 优雅降级 — 每个阶段的 try/except 返回类型安全的默认值（不再返回 None）

架构流程：
    数据输入 → _run_perception()  → PerceptionResult
             → _run_fusion()      → FusionResult
             → _run_state_machine() → WyckoffStateResult
             → _generate_decision() → TradingDecision
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.kernel.types import (
    AnomalyEvent,
    BarSignal,
    BreakoutInfo,
    CandlePhysicalStats,
    DecisionContext,
    EntryValidation,
    FusionResult,
    FVGSignal,
    PerceptionResult,
    PinBodySummary,
    StateConfig,
    StateDirection,
    StateEvidence,
    TimeframeConflict,
    TradingDecision,
    TradingRangeInfo,
    TradingSignal,
    WyckoffSignal,
    WyckoffStateResult,
)
from src.plugins.market_regime.detector import RegimeDetector
from src.plugins.pattern_detection.curve_boundary import CurveBoundaryFitter
from src.plugins.pattern_detection.tr_detector import TRDetector
from src.plugins.perception.candle_physical import (
    create_candle_from_dataframe_row,
)
from src.plugins.perception.fvg_detector import FVGDetector
from src.plugins.perception.pin_body_analyzer import (
    AnalysisContext,
    MarketRegimeType,
    analyze_pin_vs_body,
)
from src.plugins.risk_management.anomaly_validator import AnomalyValidator
from src.plugins.risk_management.circuit_breaker import CircuitBreaker
from src.plugins.signal_validation.breakout_validator import BreakoutValidator
from src.plugins.signal_validation.conflict_resolver import (
    ConflictResolutionManager,
)
from src.plugins.signal_validation.micro_entry_validator import MicroEntryValidator
from src.plugins.weight_system.period_weight_filter import (
    PeriodWeightFilter,
    Timeframe,
)
from src.plugins.wyckoff_state_machine.state_machine_v2 import (
    WyckoffStateMachineV2,
)

logger = logging.getLogger(__name__)

# 默认时间框架列表
_DEFAULT_TIMEFRAMES = ["H4", "H1", "M15"]

# 时间框架优先级（高→低）
_TF_PRIORITY = {"D1": 0, "H4": 1, "H1": 2, "M15": 3, "M5": 4}


@dataclass
class EngineEvents:
    """引擎产生的副作用事件，由调用方处理"""

    tr_detected: bool = False
    tr_data: Optional[Dict[str, Any]] = None
    state_changed: bool = False
    old_state: Optional[str] = None
    new_state: Optional[str] = None
    low_confidence_signal: bool = False
    conflicts_detected: bool = False
    conflict_details: Optional[Dict[str, Any]] = None


def _default_perception() -> PerceptionResult:
    """类型安全的感知层降级默认值"""
    return PerceptionResult(
        market_regime="UNKNOWN",
        regime_confidence=0.0,
        trading_range=None,
        fvg_signals=[],
        breakout_status=None,
        pin_body_summary=None,
        candle_physical=None,
        anomaly_events=[],
    )


def _default_fusion() -> FusionResult:
    """类型安全的融合层降级默认值"""
    return FusionResult(
        timeframe_weights={"H4": 0.5, "H1": 0.3, "M15": 0.2},
        conflicts=[],
        resolved_bias="NEUTRAL",
        entry_validation=None,
    )


def _default_state_result() -> WyckoffStateResult:
    """类型安全的状态机降级默认值"""
    return WyckoffStateResult(
        current_state="IDLE",
        phase="IDLE",
        direction=StateDirection.IDLE,
        confidence=0.0,
        intensity=0.0,
        evidences=[],
        signal=WyckoffSignal.NO_SIGNAL,
        signal_strength="none",
        state_changed=False,
        previous_state=None,
        heritage_score=0.0,
    )


class WyckoffEngine:
    """统一信号引擎 v3 — 纯信号处理，无副作用

    设计原则：
    1. 纯信号逻辑 — 无文件I/O、无可视化、无MistakeBook
    2. 每TF独立 WyckoffStateMachineV2 — 不再共享单一状态机
    3. 类型化接口 — PerceptionResult/FusionResult/WyckoffStateResult
    4. 实盘和进化使用完全相同的逻辑 — 相同上下文、相同决策
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self._timeframes = self.config.get("timeframes", _DEFAULT_TIMEFRAMES)

        # 感知层模块
        self.regime_detector = RegimeDetector(self.config.get("market_regime", {}))
        self.tr_detector = TRDetector(self.config.get("tr_detector", {}))
        self.curve_analyzer = CurveBoundaryFitter(self.config.get("curve_boundary", {}))
        self.fvg_detector = FVGDetector(self.config.get("fvg_detector", {}))
        self.breakout_validator = BreakoutValidator(
            self.config.get("breakout_validator", {})
        )
        self.anomaly_validator = AnomalyValidator(
            self.config.get("anomaly_validator", {})
        )
        self.circuit_breaker = CircuitBreaker(self.config.get("circuit_breaker", {}))

        # 融合层模块
        self.period_filter = PeriodWeightFilter(
            self.config.get("period_weight_filter", {})
        )
        self.conflict_resolver = ConflictResolutionManager(
            self.config.get("conflict_resolver", {})
        )
        self.entry_validator = MicroEntryValidator(
            self.config.get("micro_entry_validator", {})
        )

        # 状态机 — 每TF独立实例
        sm_config = StateConfig()
        sm_dict = self.config.get("state_machine", {})
        if sm_dict:
            sm_config.update_from_dict(sm_dict)
        self._sm_config = sm_config
        self._state_machines: Dict[str, WyckoffStateMachineV2] = {}
        for tf in self._timeframes:
            self._state_machines[tf] = WyckoffStateMachineV2(tf, sm_config)

        # 引擎状态
        self.last_processed_candle_time: Optional[Any] = None
        self.previous_state: Optional[str] = None
        self._bar_index: int = 0

    def reset(self) -> None:
        """重置所有状态（进化层在每个评估窗口间调用）"""
        sm_config = StateConfig()
        sm_dict = self.config.get("state_machine", {})
        if sm_dict:
            sm_config.update_from_dict(sm_dict)
        self._sm_config = sm_config
        self._state_machines = {}
        for tf in self._timeframes:
            self._state_machines[tf] = WyckoffStateMachineV2(tf, sm_config)
        self.last_processed_candle_time = None
        self.previous_state = None
        self._bar_index = 0

    # ================================================================
    # 辅助方法：K线统计
    # ================================================================

    def _calculate_candle_statistics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """计算K线统计数据，供针vs实体分析使用"""
        if len(data) < 20:
            return {"volatility_index": 1.0, "volume_ma20": 1.0, "avg_body_size": 1.0}

        try:
            high_low = data["high"] - data["low"]
            high_close = abs(data["high"] - data["close"].shift(1))
            low_close = abs(data["low"] - data["close"].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

            # 注意：pd.concat().max(axis=1) 返回值 pyright 推断为 ndarray，
            # 因此 rolling().mean() 的结果也被推断为 ndarray。
            # 使用 pd.Series() 包装并通过 iat 取值确保类型安全。
            tr_series = pd.Series(tr)
            tr_r14 = pd.Series(tr_series.rolling(14).mean())
            atr14 = float(tr_r14.iat[-1]) if len(tr_r14) > 0 else 1.0

            tr_r50 = pd.Series(tr_series.rolling(50).mean())
            avg_atr = (
                float(tr_r50.iat[-1]) if len(data) >= 50 and len(tr_r50) > 0 else atr14
            )

            volatility_index = atr14 / avg_atr if avg_atr > 0 else 1.0

            vol_rolled = pd.Series(pd.Series(data["volume"]).rolling(20).mean())
            volume_ma20 = float(vol_rolled.iat[-1]) if len(vol_rolled) > 0 else 1.0

            body_sizes = abs(data["close"] - data["open"])
            avg_body_size = float(body_sizes.mean())

            if len(data) >= 50:
                close_series = pd.Series(data["close"])
                ma50 = pd.Series(close_series.rolling(50).mean())
                current_close = float(close_series.iat[-1]) if len(data) > 0 else 0.0
                ma50_last = float(ma50.iat[-1]) if len(ma50) > 0 else current_close
                trend = "UPTREND" if current_close > ma50_last else "DOWNTREND"
                trend_strength = (
                    abs(current_close - ma50_last) / ma50_last if ma50_last > 0 else 0.0
                )
            else:
                trend = "NEUTRAL"
                trend_strength = 0.0

            return {
                "volatility_index": volatility_index,
                "volume_ma20": volume_ma20,
                "avg_body_size": avg_body_size,
                "atr14": atr14,
                "previous_close": float(data["close"].iloc[-2])
                if len(data) >= 2
                else None,
                "trend": trend,
                "trend_strength": trend_strength,
            }
        except Exception as e:
            logger.warning("计算K线统计数据失败: %s", e)
            return {"volatility_index": 1.0, "volume_ma20": 1.0, "avg_body_size": 1.0}

    def _summarize_pin_body_analysis(
        self, results: List[Dict[str, Any]]
    ) -> PinBodySummary:
        """汇总针vs实体分析结果，返回 PinBodySummary"""
        if not results:
            return PinBodySummary(
                dominant_pattern="NEUTRAL",
                avg_pin_strength=0.0,
                avg_body_strength=0.0,
                avg_confidence=0.0,
            )

        pin_dominant_count = sum(1 for r in results if r.get("is_pin_dominant", False))
        body_dominant_count = sum(
            1 for r in results if r.get("is_body_dominant", False)
        )

        avg_pin_strength = float(
            np.mean(
                [
                    r.get("pin_strength", 0)
                    for r in results
                    if r.get("is_pin_dominant", False)
                ]
                or [0]
            )
        )
        avg_body_strength = float(
            np.mean(
                [
                    r.get("body_strength", 0)
                    for r in results
                    if r.get("is_body_dominant", False)
                ]
                or [0]
            )
        )
        avg_confidence = float(np.mean([r.get("confidence", 0) for r in results]))

        if pin_dominant_count > body_dominant_count:
            dominant = "PIN"
        elif body_dominant_count > pin_dominant_count:
            dominant = "BODY"
        else:
            dominant = "NEUTRAL"

        return PinBodySummary(
            dominant_pattern=dominant,
            avg_pin_strength=avg_pin_strength,
            avg_body_strength=avg_body_strength,
            avg_confidence=avg_confidence,
        )

    def _calculate_candle_physical_stats(
        self, data: pd.DataFrame
    ) -> Optional[CandlePhysicalStats]:
        """计算K线物理属性统计，返回 CandlePhysicalStats"""
        if len(data) < 10:
            return None

        try:
            candles = []
            for _, row in data.iloc[-10:].iterrows():
                candle = create_candle_from_dataframe_row(row)
                candles.append(candle)

            body_sizes = [c.body for c in candles]
            shadow_sizes = [c.total_shadow for c in candles]
            body_ratios = [c.body_ratio for c in candles]

            doji_count = sum(1 for c in candles if c.is_doji)
            hammer_count = sum(1 for c in candles if c.is_hammer)
            shooting_star_count = sum(1 for c in candles if c.is_shooting_star)

            return CandlePhysicalStats(
                avg_body_size=float(np.mean(body_sizes)) if body_sizes else 0.0,
                avg_shadow_size=float(np.mean(shadow_sizes)) if shadow_sizes else 0.0,
                avg_body_ratio=float(np.mean(body_ratios)) if body_ratios else 0.0,
                doji_pct=doji_count / len(candles) * 100,
                hammer_pct=hammer_count / len(candles) * 100,
                shooting_star_pct=shooting_star_count / len(candles) * 100,
            )
        except Exception as e:
            logger.warning("计算K线物理属性统计失败: %s", e)
            return None

    # ================================================================
    # 阶段1：感知层
    # ================================================================

    def _get_primary_tf(self, data_dict: Dict[str, pd.DataFrame]) -> str:
        """选择主时间框架（优先H4，否则取第一个可用TF）"""
        if "H4" in data_dict:
            return "H4"
        return next(iter(data_dict.keys()))

    def _run_perception(
        self,
        symbol: str,
        data_dict: Dict[str, pd.DataFrame],
    ) -> Tuple[PerceptionResult, EngineEvents]:
        """运行物理感知层分析，返回类型安全的 PerceptionResult

        Args:
            symbol: 交易对符号
            data_dict: {时间框架: DataFrame} 数据字典

        Returns:
            (PerceptionResult, EngineEvents) 元组
        """
        events = EngineEvents()

        primary_tf = self._get_primary_tf(data_dict)
        primary_data = data_dict[primary_tf]

        # 初始化各分析结果变量
        market_regime = "UNKNOWN"
        regime_confidence = 0.0
        trading_range: Optional[TradingRangeInfo] = None
        fvg_signals: List[FVGSignal] = []
        breakout_status: Optional[BreakoutInfo] = None
        pin_body_summary: Optional[PinBodySummary] = None
        candle_physical: Optional[CandlePhysicalStats] = None
        anomaly_events: List[AnomalyEvent] = []

        try:
            # 1. 市场体制检测
            try:
                regime_result = self.regime_detector.detect_regime(primary_data)
                regime_enum = regime_result.get("regime")
                if regime_enum is not None and hasattr(regime_enum, "value"):
                    market_regime = str(regime_enum.value)
                elif regime_enum is not None:
                    market_regime = str(regime_enum)
                regime_confidence = float(regime_result.get("confidence", 0.0))
            except Exception as e:
                logger.warning("市场体制检测失败: %s", e)

            # 2. K线统计（供后续分析使用）
            stats = self._calculate_candle_statistics(primary_data)

            # 3. TR识别
            try:
                tr_result = self.tr_detector.detect_trading_range(primary_data)
                if tr_result is not None:
                    bd = tr_result.breakout_direction
                    bd_str = bd.value if bd is not None else None
                    trading_range = TradingRangeInfo(
                        has_range=True,
                        support=tr_result.lower_boundary,
                        resistance=tr_result.upper_boundary,
                        confidence=tr_result.confidence,
                        breakout_direction=bd_str,
                    )
                    events.tr_detected = True
                    events.tr_data = {
                        "detected": True,
                        "support": tr_result.lower_boundary,
                        "resistance": tr_result.upper_boundary,
                        "breakout_direction": bd_str,
                        "confidence": tr_result.confidence,
                    }
            except Exception as e:
                logger.warning("TR识别失败: %s", e)

            # 3.5 多周期TR共振检测
            try:
                self._detect_tr_resonance(data_dict, primary_tf, trading_range)
            except Exception as e:
                logger.warning("多周期TR共振检测失败（跳过）: %s", e)

            # 4. 曲线边界拟合（保留原逻辑，但不存入结果 — 供状态机上下文使用）
            try:
                if len(primary_data) >= 20:
                    self.curve_analyzer.detect_trading_range(
                        pd.Series(primary_data["high"]),
                        pd.Series(primary_data["low"]),
                        pd.Series(primary_data["close"]),
                    )
            except Exception as e:
                logger.warning("曲线边界拟合失败: %s", e)

            # 5. FVG检测
            try:
                raw_fvg = self.fvg_detector.detect_fvg_gaps(primary_data)
                for fvg in raw_fvg:
                    fvg_signals.append(
                        FVGSignal(
                            direction=fvg.direction.value
                            if hasattr(fvg.direction, "value")
                            else str(fvg.direction),
                            gap_top=float(fvg.max_price),
                            gap_bottom=float(fvg.min_price),
                            fill_ratio=0.0,  # FVGGap 没有 fill_ratio 字段
                        )
                    )
            except Exception as e:
                logger.warning("FVG检测失败: %s", e)

            # 6. 突破验证
            try:
                support_level = (
                    trading_range.support
                    if trading_range and trading_range.support is not None
                    else 0.0
                )
                resistance_level = (
                    trading_range.resistance
                    if trading_range and trading_range.resistance is not None
                    else 0.0
                )
                latest_prices = (
                    primary_data.iloc[-30:] if len(primary_data) >= 30 else primary_data
                )
                raw_breakout = self.breakout_validator.detect_initial_breakout(
                    df=latest_prices,
                    support_level=support_level,
                    resistance_level=resistance_level,
                    current_atr=stats.get("atr14", 1.0),
                )
                if raw_breakout:
                    breakout_status = BreakoutInfo(
                        is_valid=raw_breakout.get("is_valid", False),
                        direction=raw_breakout.get("direction", 0),
                        breakout_level=float(raw_breakout.get("breakout_level", 0.0)),
                        breakout_strength=float(
                            raw_breakout.get("breakout_strength", 0.0)
                        ),
                        volume_confirmation=raw_breakout.get(
                            "volume_confirmation", False
                        ),
                    )
            except Exception as e:
                logger.warning("突破验证失败: %s", e)

            # 7. 针vs实体分析
            try:
                pin_body_summary = self._analyze_pin_body(
                    primary_data, stats, trading_range, market_regime
                )
            except Exception as e:
                logger.warning("针vs实体分析失败: %s", e)

            # 8. K线物理属性统计
            try:
                candle_physical = self._calculate_candle_physical_stats(primary_data)
            except Exception as e:
                logger.warning("K线物理属性统计失败: %s", e)

        except Exception:
            logger.exception("物理感知层分析整体失败")

        result = PerceptionResult(
            market_regime=market_regime,
            regime_confidence=regime_confidence,
            trading_range=trading_range,
            fvg_signals=fvg_signals,
            breakout_status=breakout_status,
            pin_body_summary=pin_body_summary,
            candle_physical=candle_physical,
            anomaly_events=anomaly_events,
        )
        return result, events

    def _detect_tr_resonance(
        self,
        data_dict: Dict[str, pd.DataFrame],
        primary_tf: str,
        trading_range: Optional[TradingRangeInfo],
    ) -> None:
        """多周期TR共振检测 — 更新 trading_range 的 resonance_score"""
        tr_by_timeframe: Dict[str, Dict[str, Any]] = {}
        for tf, tf_data in data_dict.items():
            if tf == primary_tf or len(tf_data) < 50:
                continue
            try:
                tf_tr = self.tr_detector.detect_trading_range(tf_data)
                if tf_tr is not None:
                    tr_by_timeframe[tf] = {
                        "support": tf_tr.lower_boundary,
                        "resistance": tf_tr.upper_boundary,
                        "confidence": tf_tr.confidence,
                    }
            except Exception:
                pass

        if not tr_by_timeframe or trading_range is None:
            return

        all_supports = [
            v["support"] for v in tr_by_timeframe.values() if v["support"] is not None
        ]
        all_resistances = [
            v["resistance"]
            for v in tr_by_timeframe.values()
            if v["resistance"] is not None
        ]
        if trading_range.support is not None:
            all_supports.append(trading_range.support)
        if trading_range.resistance is not None:
            all_resistances.append(trading_range.resistance)

        resonance_score = 0.0
        if len(all_supports) >= 2:
            support_mean = float(np.mean(all_supports))
            support_spread = (
                float(np.std(all_supports)) / support_mean if support_mean > 0 else 1.0
            )
            if support_spread < 0.05:
                resonance_score += 0.5

        if len(all_resistances) >= 2:
            resistance_mean = float(np.mean(all_resistances))
            resistance_spread = (
                float(np.std(all_resistances)) / resistance_mean
                if resistance_mean > 0
                else 1.0
            )
            if resistance_spread < 0.05:
                resonance_score += 0.5

        trading_range.resonance_score = resonance_score

    def _analyze_pin_body(
        self,
        primary_data: pd.DataFrame,
        stats: Dict[str, Any],
        trading_range: Optional[TradingRangeInfo],
        market_regime_str: str,
    ) -> Optional[PinBodySummary]:
        """分析针vs实体，返回 PinBodySummary"""
        if len(primary_data) < 3:
            return None

        recent_candles = primary_data.iloc[-3:]
        pin_body_results: List[Dict[str, Any]] = []

        market_regime_enum = MarketRegimeType.UNKNOWN
        if market_regime_str and market_regime_str != "unknown":
            try:
                market_regime_enum = MarketRegimeType(market_regime_str.upper())
            except ValueError:
                market_regime_enum = MarketRegimeType.UNKNOWN

        tr_support = trading_range.support if trading_range else None
        tr_resistance = trading_range.resistance if trading_range else None

        for _, row in recent_candles.iterrows():
            candle = create_candle_from_dataframe_row(row)
            context = AnalysisContext(
                volatility_index=stats.get("volatility_index", 1.0),
                market_regime=market_regime_enum,
                volume_moving_avg=stats.get("volume_ma20", 1.0),
                avg_body_size=stats.get("avg_body_size", 1.0),
                previous_close=stats.get("previous_close"),
                atr14=stats.get("atr14", 1.0),
                tr_support=tr_support,
                tr_resistance=tr_resistance,
                trend=stats.get("trend", "NEUTRAL"),
                trend_strength=stats.get("trend_strength", 0.0),
            )
            result = analyze_pin_vs_body(candle, context)
            pin_body_results.append(
                {
                    "is_pin_dominant": result.is_pin_dominant,
                    "is_body_dominant": result.is_body_dominant,
                    "pin_strength": result.pin_strength,
                    "body_strength": result.body_strength,
                    "confidence": result.confidence,
                }
            )

        return self._summarize_pin_body_analysis(pin_body_results)

    # ================================================================
    # 阶段2：多周期融合
    # ================================================================

    def _run_fusion(
        self,
        data_dict: Dict[str, pd.DataFrame],
        perception: PerceptionResult,
    ) -> FusionResult:
        """运行多周期融合分析，返回类型安全的 FusionResult

        Args:
            data_dict: {时间框架: DataFrame} 数据字典
            perception: 感知层输出

        Returns:
            FusionResult 包含权重、冲突、偏向、入场验证
        """
        regime = perception.market_regime

        # 1. 动态权重
        try:
            raw_weights = self.period_filter.get_weights(regime)
            available_tfs = set(data_dict.keys())
            timeframe_weights = {
                tf.value: w
                for tf, w in raw_weights.items()
                if tf.value in available_tfs
            }
            total_w = sum(timeframe_weights.values())
            if total_w > 0:
                timeframe_weights = {
                    k: v / total_w for k, v in timeframe_weights.items()
                }
        except Exception as e:
            logger.warning("PeriodWeightFilter调用失败: %s", e)
            timeframe_weights = {"H4": 0.5, "H1": 0.3, "M15": 0.2}

        # 2. 各TF趋势状态
        timeframe_states: Dict[str, Dict[str, Any]] = {}
        for tf, df in data_dict.items():
            state_label, tf_conf = self._tf_trend_state(df)
            timeframe_states[tf] = {"state": state_label, "confidence": tf_conf}

        # 3. 冲突解决
        conflicts: List[TimeframeConflict] = []
        resolved_bias = "NEUTRAL"
        try:
            h4_df = data_dict.get("H4") or data_dict.get(next(iter(data_dict)))
            correction_depth = 0.0
            volume_on_correction = "NORMAL"
            if h4_df is not None and len(h4_df) >= 10:
                recent = h4_df.iloc[-10:]
                high_max = float(recent["high"].max())
                low_min = float(recent["low"].min())
                last_close = float(recent["close"].iloc[-1])
                if high_max > low_min:
                    correction_depth = (high_max - last_close) / (high_max - low_min)
                avg_vol = float(recent["volume"].mean())
                last_vol = float(recent["volume"].iloc[-1])
                if avg_vol > 0:
                    vol_ratio = last_vol / avg_vol
                    volume_on_correction = (
                        "LOW_VOLUME"
                        if vol_ratio < 0.7
                        else ("HIGH_VOLUME" if vol_ratio > 1.5 else "NORMAL")
                    )

            market_context = {
                "regime": regime,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "correction_depth": correction_depth,
                "volume_on_correction": volume_on_correction,
            }
            conflict_resolution = self.conflict_resolver.resolve_conflict(
                timeframe_states, market_context
            )
            conflict_type = conflict_resolution.get("conflict_type", "NO_CONFLICT")
            if conflict_type != "NO_CONFLICT":
                primary_bias = conflict_resolution.get("primary_bias", "NEUTRAL")
                if hasattr(primary_bias, "value"):
                    primary_bias = primary_bias.value
                conflicts.append(
                    TimeframeConflict(
                        higher_tf=conflict_resolution.get("higher_tf", "H4"),
                        higher_bias=conflict_resolution.get("higher_bias", "NEUTRAL"),
                        lower_tf=conflict_resolution.get("lower_tf", "M15"),
                        lower_bias=conflict_resolution.get("lower_bias", "NEUTRAL"),
                        resolution=conflict_resolution.get(
                            "resolution", "follow_higher"
                        ),
                        confidence_penalty=conflict_resolution.get(
                            "confidence_penalty", 0.0
                        ),
                    )
                )
            resolved_bias = conflict_resolution.get("primary_bias", "NEUTRAL")
            if hasattr(resolved_bias, "value"):
                resolved_bias = resolved_bias.value
            if resolved_bias not in ("BULLISH", "BEARISH", "NEUTRAL"):
                resolved_bias = "NEUTRAL"
        except Exception as e:
            logger.warning("ConflictResolutionManager调用失败: %s", e)

        # 4. 微观入场验证
        entry_validation = self._validate_micro_entry(
            data_dict, perception, resolved_bias, regime
        )

        return FusionResult(
            timeframe_weights=timeframe_weights,
            conflicts=conflicts,
            resolved_bias=resolved_bias,
            entry_validation=entry_validation,
        )

    @staticmethod
    def _tf_trend_state(df: pd.DataFrame) -> Tuple[str, float]:
        """计算单个TF的趋势状态"""
        try:
            if df is None or len(df) < 20:
                return "NEUTRAL", 0.4
            close = pd.Series(df["close"])
            if close is None or len(close) < 20:
                return "NEUTRAL", 0.4
            ma20_s = pd.Series(close.rolling(20).mean())
            ma50_s = pd.Series(close.rolling(min(50, len(df))).mean())
            ma20 = float(ma20_s.iat[-1])
            ma50 = float(ma50_s.iat[-1])
            last_close = float(close.iat[-1])
            if ma20 > ma50 and last_close > ma20:
                gap = (ma20 - ma50) / ma50 if ma50 > 0 else 0
                return "BULLISH", min(0.9, 0.5 + gap * 10)
            elif ma20 < ma50 and last_close < ma20:
                gap = (ma50 - ma20) / ma50 if ma50 > 0 else 0
                return "BEARISH", min(0.9, 0.5 + gap * 10)
            else:
                return "NEUTRAL", 0.4
        except Exception:
            return "NEUTRAL", 0.4

    def _validate_micro_entry(
        self,
        data_dict: Dict[str, pd.DataFrame],
        perception: PerceptionResult,
        resolved_bias: str,
        regime: str,
    ) -> Optional[EntryValidation]:
        """微观入场验证"""
        try:
            m15_data = data_dict.get("M15")
            breakout = perception.breakout_status
            if (
                m15_data is None
                or len(m15_data) < 10
                or breakout is None
                or breakout.direction not in (1, -1)
                or breakout.breakout_level <= 0
            ):
                return None

            structure_direction = "RESISTANCE" if breakout.direction == 1 else "SUPPORT"
            structure_type = "CREEK" if breakout.breakout_strength >= 1.0 else "PIVOT"
            confidence = min(
                0.95,
                0.6
                + breakout.breakout_strength * 0.1
                + (0.1 if breakout.volume_confirmation else 0.0),
            )
            h4_structure = {
                "type": structure_type,
                "price_level": float(breakout.breakout_level),
                "direction": structure_direction,
                "confidence": confidence,
            }

            macro_bias = resolved_bias
            if macro_bias not in ("BULLISH", "BEARISH", "NEUTRAL"):
                macro_bias = "NEUTRAL"

            raw_validation = self.entry_validator.validate_entry(
                h4_structure=h4_structure,
                m15_data=m15_data,
                m5_data=data_dict.get("M5"),
                macro_bias=macro_bias,
                market_context={
                    "regime": regime,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            if raw_validation:
                return EntryValidation(
                    is_valid=raw_validation.get("is_valid", False),
                    entry_grade=raw_validation.get("entry_grade", "D"),
                    m15_confirmation=raw_validation.get("m15_confirmation", False),
                    m5_confirmation=raw_validation.get("m5_confirmation", False),
                    optimal_entry_zone=raw_validation.get("optimal_entry_zone"),
                )
        except Exception as e:
            logger.warning("MicroEntryValidator调用失败: %s", e)
        return None

    # ================================================================
    # 阶段3：状态机决策
    # ================================================================

    def _ensure_state_machine(self, tf: str) -> WyckoffStateMachineV2:
        """确保指定TF的状态机实例存在"""
        if tf not in self._state_machines:
            self._state_machines[tf] = WyckoffStateMachineV2(tf, self._sm_config)
        return self._state_machines[tf]

    def _run_state_machine(
        self,
        data_dict: Dict[str, pd.DataFrame],
        perception: PerceptionResult,
        fusion: FusionResult,
    ) -> WyckoffStateResult:
        """运行状态机决策层 — 每TF独立实例，选取主TF结果

        对每个TF喂入最后一根K线到对应的 WyckoffStateMachineV2 实例，
        取主时间框架（通常H4）的结果作为引擎输出。

        Args:
            data_dict: {时间框架: DataFrame} 数据字典
            perception: 感知层输出
            fusion: 融合层输出

        Returns:
            WyckoffStateResult 主TF的状态机结果
        """
        primary_tf = self._get_primary_tf(data_dict)
        primary_result: Optional[WyckoffStateResult] = None

        # 构建状态机上下文
        sm_context: Dict[str, Any] = {
            "market_regime": perception.market_regime,
            "regime_confidence": perception.regime_confidence,
        }
        if perception.trading_range:
            sm_context["tr_support"] = perception.trading_range.support
            sm_context["tr_resistance"] = perception.trading_range.resistance
        if perception.breakout_status:
            sm_context["breakout_direction"] = perception.breakout_status.direction
            sm_context["breakout_strength"] = (
                perception.breakout_status.breakout_strength
            )

        # 按优先级排序TF（高TF先处理）
        sorted_tfs = sorted(
            data_dict.keys(),
            key=lambda t: _TF_PRIORITY.get(t, 99),
        )

        for tf in sorted_tfs:
            df = data_dict[tf]
            if df is None or df.empty:
                continue

            try:
                sm = self._ensure_state_machine(tf)
                last_candle = df.iloc[-1]
                tf_result = sm.process_candle(last_candle, sm_context)

                if tf == primary_tf:
                    primary_result = tf_result
            except Exception as e:
                logger.warning("状态机处理TF=%s失败: %s", tf, e)

        if primary_result is None:
            return _default_state_result()

        # 更新引擎级别状态跟踪
        if primary_result.state_changed:
            self.previous_state = primary_result.previous_state

        return primary_result

    # ================================================================
    # 阶段4：交易决策生成
    # ================================================================

    def _generate_decision(
        self,
        perception: PerceptionResult,
        fusion: FusionResult,
        state: WyckoffStateResult,
    ) -> TradingDecision:
        """生成最终交易决策（纯逻辑，无MistakeBook/叙事日志）

        Args:
            perception: 感知层输出
            fusion: 融合层输出
            state: 状态机输出

        Returns:
            TradingDecision 交易决策
        """
        context = DecisionContext(
            timestamp=datetime.now(timezone.utc),
            market_regime=perception.market_regime,
            regime_confidence=perception.regime_confidence,
            timeframe_weights=fusion.timeframe_weights,
            detected_conflicts=[
                {
                    "higher_tf": c.higher_tf,
                    "higher_bias": c.higher_bias,
                    "lower_tf": c.lower_tf,
                    "lower_bias": c.lower_bias,
                    "resolution": c.resolution,
                }
                for c in fusion.conflicts
            ],
            wyckoff_state=state.current_state,
            wyckoff_confidence=state.confidence,
            breakout_status={
                "is_valid": perception.breakout_status.is_valid,
                "direction": perception.breakout_status.direction,
                "breakout_level": perception.breakout_status.breakout_level,
            }
            if perception.breakout_status
            else None,
            fvg_signals=[
                {
                    "direction": f.direction,
                    "gap_top": f.gap_top,
                    "gap_bottom": f.gap_bottom,
                }
                for f in perception.fvg_signals
            ],
        )

        signal = TradingSignal.NEUTRAL
        confidence = 0.0
        reasoning: List[str] = []

        trading_mode = self.config.get("trading_mode", "spot")
        leverage = self.config.get("leverage", 1)
        allow_shorting = self.config.get("allow_shorting", False)

        # 基于威科夫状态机信号
        if state.signal == WyckoffSignal.BUY_SIGNAL:
            signal = (
                TradingSignal.STRONG_BUY
                if state.signal_strength == "strong"
                else TradingSignal.BUY
            )
            confidence = state.confidence
            reasoning.append(
                f"Wyckoff {state.current_state} buy signal "
                f"(confidence: {state.confidence:.2f}, "
                f"strength: {state.signal_strength})"
            )
            if trading_mode == "futures":
                reasoning.append(f"使用杠杆倍数: {leverage}x")

        elif state.signal == WyckoffSignal.SELL_SIGNAL:
            signal = (
                TradingSignal.STRONG_SELL
                if state.signal_strength == "strong"
                else TradingSignal.SELL
            )
            confidence = state.confidence
            reasoning.append(
                f"Wyckoff {state.current_state} sell signal "
                f"(confidence: {state.confidence:.2f}, "
                f"strength: {state.signal_strength})"
            )
            if trading_mode == "futures":
                reasoning.append(f"使用杠杆倍数: {leverage}x")

        # 合约做空逻辑
        if allow_shorting and trading_mode == "futures":
            if state.direction == StateDirection.DISTRIBUTION:
                distribution_structures = {"UT", "UTAD", "ST_DIST", "LPSY"}
                if state.current_state in distribution_structures:
                    market_regime = perception.market_regime
                    if (
                        "BEARISH" in market_regime.upper()
                        or "DOWN" in market_regime.upper()
                        or state.direction == StateDirection.DISTRIBUTION
                    ):
                        short_conf = min(0.9, state.confidence * 1.2)
                        if signal not in [
                            TradingSignal.SELL,
                            TradingSignal.STRONG_SELL,
                        ]:
                            signal = (
                                TradingSignal.SELL
                                if short_conf < 0.8
                                else TradingSignal.STRONG_SELL
                            )
                            confidence = max(confidence, short_conf)
                            reasoning.append(
                                f"合约做空信号：检测到派发阶段小结构 "
                                f"{state.current_state} "
                                f"(置信度: {short_conf:.2f})"
                            )
                            reasoning.append(f"使用杠杆倍数: {leverage}x")

        # 突破确认
        bs = perception.breakout_status
        if bs and bs.is_valid:
            if bs.direction == 1 and signal in [
                TradingSignal.BUY,
                TradingSignal.STRONG_BUY,
            ]:
                confidence = min(1.0, confidence + 0.1)
                reasoning.append("Confirmed bullish breakout")
            elif bs.direction == -1 and signal in [
                TradingSignal.SELL,
                TradingSignal.STRONG_SELL,
            ]:
                confidence = min(1.0, confidence + 0.1)
                reasoning.append("Confirmed bearish breakout")

        # 冲突解决结果应用
        for conflict in fusion.conflicts:
            if conflict.resolution == "follow_higher":
                reasoning.append("Following larger timeframe direction")
            elif conflict.resolution == "reduce_size":
                reasoning.append("Reducing position size due to conflict")

        # 低置信度 → 中性
        if confidence < 0.6:
            signal = TradingSignal.NEUTRAL
            reasoning.append(
                f"Low confidence ({confidence:.2f}), maintaining neutral position"
            )

        return TradingDecision(
            signal=signal,
            confidence=confidence,
            context=context,
            reasoning=reasoning,
        )

    # ================================================================
    # 主入口1：逐bar处理（进化回测用）
    # ================================================================

    def process_bar(
        self,
        symbol: str,
        data_dict: Dict[str, pd.DataFrame],
    ) -> BarSignal:
        """逐bar处理 — 进化回测器的唯一接口

        每次调用处理当前bar位置的数据，产出一个 BarSignal。
        引擎内部状态（状态机、计数器）在调用间保持。

        Args:
            symbol: 交易对符号
            data_dict: {时间框架: DataFrame}，
                       每个DataFrame截止到当前bar位置

        Returns:
            BarSignal 包含信号、状态、证据链
        """
        self._bar_index += 1

        try:
            # 四阶段流水线
            perception, _ = self._run_perception(symbol, data_dict)
            fusion = self._run_fusion(data_dict, perception)
            state = self._run_state_machine(data_dict, perception, fusion)
            decision = self._generate_decision(perception, fusion, state)

            # 提取最后一根K线的时间戳和价格
            primary_tf = self._get_primary_tf(data_dict)
            primary_data = data_dict[primary_tf]
            last_candle = primary_data.iloc[-1] if len(primary_data) > 0 else None

            timestamp = None
            entry_price = None
            if last_candle is not None:
                if hasattr(last_candle, "name"):
                    ts = last_candle.name
                    if isinstance(ts, datetime):
                        timestamp = ts
                entry_price = float(last_candle["close"])

            # 计算止损（基于ATR）
            stop_loss = None
            if entry_price is not None and decision.signal != TradingSignal.NEUTRAL:
                stats = self._calculate_candle_statistics(primary_data)
                atr = stats.get("atr14", 0.0)
                if atr > 0:
                    if decision.signal in (
                        TradingSignal.BUY,
                        TradingSignal.STRONG_BUY,
                    ):
                        stop_loss = entry_price - 2.0 * atr
                    elif decision.signal in (
                        TradingSignal.SELL,
                        TradingSignal.STRONG_SELL,
                    ):
                        stop_loss = entry_price + 2.0 * atr

            return BarSignal(
                bar_index=self._bar_index,
                timestamp=timestamp,
                signal=decision.signal,
                confidence=decision.confidence,
                wyckoff_state=state.current_state,
                phase=state.phase,
                evidences=state.evidences,
                entry_price=entry_price,
                stop_loss=stop_loss,
            )

        except Exception as e:
            logger.exception("process_bar失败: %s", e)
            return BarSignal(
                bar_index=self._bar_index,
                timestamp=None,
                signal=TradingSignal.NEUTRAL,
                confidence=0.0,
                wyckoff_state="IDLE",
                phase="IDLE",
                evidences=[],
            )

    # ================================================================
    # 主入口2：完整市场数据处理（实盘用）
    # ================================================================

    def process_market_data(
        self,
        symbol: str,
        timeframes: List[str],
        data_dict: Dict[str, pd.DataFrame],
    ) -> Tuple[TradingDecision, EngineEvents]:
        """主入口 — 处理所有时间框架数据并返回决策和事件

        Args:
            symbol: 交易对符号
            timeframes: 时间框架列表
            data_dict: {时间框架: DataFrame} 数据字典

        Returns:
            (TradingDecision, EngineEvents) 元组
        """
        all_events = EngineEvents()

        try:
            # 阶段1：感知层
            perception, perception_events = self._run_perception(symbol, data_dict)
            if perception_events.tr_detected:
                all_events.tr_detected = True
                all_events.tr_data = perception_events.tr_data

            # 阶段2：融合层
            fusion = self._run_fusion(data_dict, perception)
            if fusion.conflicts:
                all_events.conflicts_detected = True
                all_events.conflict_details = {
                    "higher_tf": fusion.conflicts[0].higher_tf,
                    "higher_bias": fusion.conflicts[0].higher_bias,
                    "lower_tf": fusion.conflicts[0].lower_tf,
                    "lower_bias": fusion.conflicts[0].lower_bias,
                    "resolution": fusion.conflicts[0].resolution,
                }

            # 阶段3：状态机决策
            state = self._run_state_machine(data_dict, perception, fusion)
            if state.state_changed:
                all_events.state_changed = True
                all_events.old_state = state.previous_state
                all_events.new_state = state.current_state

            # 阶段4：交易决策
            decision = self._generate_decision(perception, fusion, state)
            if decision.confidence < 0.6:
                all_events.low_confidence_signal = True

            return decision, all_events

        except Exception as e:
            logger.exception("process_market_data整体失败: %s", e)
            # 优雅降级 — 返回中性决策
            default_context = DecisionContext(
                timestamp=datetime.now(timezone.utc),
                market_regime="UNKNOWN",
                regime_confidence=0.0,
                timeframe_weights={"H4": 0.5, "H1": 0.3, "M15": 0.2},
                detected_conflicts=[],
            )
            return (
                TradingDecision(
                    signal=TradingSignal.NEUTRAL,
                    confidence=0.0,
                    context=default_context,
                    reasoning=["Engine error: graceful degradation"],
                ),
                all_events,
            )
