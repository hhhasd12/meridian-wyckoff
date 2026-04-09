"""模板6：供需力量对比检测器 — SOS/SOW/LPSY/LPS/MSOS/MSOW/mSOS/mSOW

统一检测器，多种事件。
检测统一模式："方向移动 → 弱反向运动 → 窄幅横盘"
产出通用 SUPPLY_DEMAND_SIGNAL 事件，由规则引擎根据阶段+位置命名。
状态机：IDLE → MOVE_DETECTED → EVALUATING_RESPONSE → CANDIDATE
"""

from __future__ import annotations

import logging
import uuid

import numpy as np

from ..models import (
    Event,
    EventType,
    EventResult,
    RangeContext,
    EngineState,
    Range,
    Phase,
)
from ..params import EventEngineParams
from .base_detector import BaseDetector

logger = logging.getLogger(__name__)

# 状态机常量
_IDLE = "IDLE"
_MOVE_DETECTED = "MOVE_DETECTED"
_EVALUATING_RESPONSE = "EVALUATING_RESPONSE"
_CANDIDATE = "CANDIDATE"

# 方向常量
_BULLISH = "BULLISH"
_BEARISH = "BEARISH"


class SupplyDemandDetector(BaseDetector):
    """
    供需力量对比检测器 — 统一检测 SOS/SOW/LPSY/LPS/MSOS/MSOW/mSOS/mSOW。

    检测器不命名事件，只产出通用 SUPPLY_DEMAND_SIGNAL。
    命名由规则引擎根据阶段+位置完成。

    状态机流程：
        IDLE → 检测到方向移动（幅度 > move_threshold）
        MOVE_DETECTED → 方向移动结束，反向运动开始
        EVALUATING_RESPONSE → 评估反向运动质量
            - 反向运动强（retracement > strong_threshold）→ IDLE
            - 反向运动弱 + 窄幅横盘 → CANDIDATE → 产出事件 → IDLE
            - 超时 → IDLE
    """

    def __init__(self):
        self._state: str = _IDLE

        # 方向移动追踪
        self._move_direction: str = ""  # BULLISH / BEARISH
        self._move_start_bar: int = 0
        self._move_start_price: float = 0.0
        self._move_end_price: float = 0.0
        self._move_bars: list[dict] = []
        self._move_avg_volume: float = 0.0

        # 反向运动追踪
        self._response_start_bar: int = 0
        self._response_bars: list[dict] = []
        self._response_peak: float = 0.0  # 反向运动的极端价格
        self._response_trough: float = 0.0

        # 横盘追踪
        self._consolidation_bars: list[dict] = []

        # 量价窗口
        self._recent_volumes: list[float] = []

        # W1修复：价格历史用于多K线窗口方向检测
        self._price_history: list[float] = []

    def process_bar(
        self,
        candle: dict,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        engine_state: EngineState,
    ) -> list[Event]:
        """每根K线调用一次，返回事件或空列表"""
        if not range_ctx.has_active_range:
            return []
        active = range_ctx.active_range
        if active is None:
            return []

        close = candle.get("close", 0)
        volume = candle.get("volume", 0)

        # 更新量价窗口
        self._recent_volumes.append(float(volume))
        if len(self._recent_volumes) > params.supply_demand.move_window * 2:
            self._recent_volumes.pop(0)

        # 更新价格历史（用于多K线窗口方向检测）
        self._price_history.append(float(close))
        if len(self._price_history) > params.supply_demand.move_window * 2:
            self._price_history.pop(0)

        # 区间宽度（用于归一化）
        channel_width = self._get_channel_width(active)
        if channel_width <= 0:
            return []

        events: list[Event] = []

        if self._state == _IDLE:
            events = self._handle_idle(
                candle,
                active,
                range_ctx,
                bar_index,
                params,
                channel_width,
                engine_state,
            )
        elif self._state == _MOVE_DETECTED:
            events = self._handle_move_detected(
                candle,
                active,
                range_ctx,
                bar_index,
                params,
                channel_width,
                engine_state,
            )
        elif self._state == _EVALUATING_RESPONSE:
            events = self._handle_evaluating_response(
                candle,
                active,
                range_ctx,
                bar_index,
                params,
                channel_width,
                engine_state,
            )
        elif self._state == _CANDIDATE:
            events = self._handle_candidate(
                candle,
                active,
                range_ctx,
                bar_index,
                params,
                channel_width,
                engine_state,
            )

        return events

    # ═══ 状态处理 ═══

    def _handle_idle(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        channel_width: float,
        engine_state: EngineState,
    ) -> list[Event]:
        """IDLE状态：检测方向移动的起点"""
        sdp = params.supply_demand
        close = candle.get("close", 0)

        # 需要足够的K线窗口来判断方向移动
        if len(self._recent_volumes) < 2:
            return []

        # 计算近期价格变化
        move_pct = self._detect_move(candle, sdp)

        if move_pct is not None:
            direction, magnitude, start_price = move_pct

            if abs(magnitude) >= sdp.move_threshold:
                # 检测到方向移动
                self._state = _MOVE_DETECTED
                self._move_direction = direction
                self._move_start_bar = bar_index
                self._move_start_price = start_price
                self._move_end_price = close
                self._move_bars = [candle.copy()]
                self._move_avg_volume = self._avg_volume()

                logger.debug(
                    "方向移动检测: direction=%s, magnitude=%.4f, bar=%d",
                    direction,
                    magnitude,
                    bar_index,
                )

        return []

    def _handle_move_detected(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        channel_width: float,
        engine_state: EngineState,
    ) -> list[Event]:
        """MOVE_DETECTED：追踪方向移动，判断是否结束"""
        sdp = params.supply_demand
        close = candle.get("close", 0)
        open_ = candle.get("open", 0)

        self._move_bars.append(candle.copy())

        # 判断方向移动是否还在继续
        still_moving = self._is_move_continuing(candle, sdp)

        if still_moving:
            # 更新移动终点
            self._move_end_price = close

            # 移动窗口超时保护
            if len(self._move_bars) > sdp.move_window * 2:
                self._state = _IDLE
                self._clear_tracking()
                logger.debug("方向移动超时，重置")
            return []

        # 方向移动结束 → 进入反向运动评估
        self._state = _EVALUATING_RESPONSE
        self._response_start_bar = bar_index
        self._response_bars = [candle.copy()]
        self._response_peak = candle.get("high", 0)
        self._response_trough = candle.get("low", 0)

        logger.debug(
            "方向移动结束，进入反向评估: direction=%s, bars=%d",
            self._move_direction,
            len(self._move_bars),
        )

        return []

    def _handle_evaluating_response(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        channel_width: float,
        engine_state: EngineState,
    ) -> list[Event]:
        """EVALUATING_RESPONSE：评估反向运动质量"""
        sdp = params.supply_demand
        close = candle.get("close", 0)
        high = candle.get("high", 0)
        low = candle.get("low", 0)

        self._response_bars.append(candle.copy())

        # 更新反向运动的极值
        if high > self._response_peak:
            self._response_peak = high
        if low < self._response_trough:
            self._response_trough = low

        # 计算回撤比率
        move_magnitude = abs(self._move_end_price - self._move_start_price)
        if move_magnitude <= 0:
            self._state = _IDLE
            self._clear_tracking()
            return []

        retracement = self._calc_retracement(close)
        response_quality = self._evaluate_response(
            self._move_bars, self._response_bars, sdp
        )

        # 反向运动强（回撤超过阈值）→ 不是供需信号，重置
        if retracement > sdp.strong_retracement:
            logger.debug(
                "反向运动过强（retracement=%.2f > threshold=%.2f），重置",
                retracement,
                sdp.strong_retracement,
            )
            self._state = _IDLE
            self._clear_tracking()
            return []

        # 检查是否进入窄幅横盘
        consolidation = self._detect_consolidation(
            self._response_bars, sdp, channel_width
        )

        if (
            consolidation is not None
            and len(self._response_bars) >= sdp.min_consolidation_bars
        ):
            # 反向运动弱 + 窄幅横盘 → CANDIDATE
            self._state = _CANDIDATE
            self._consolidation_bars = self._response_bars.copy()

            # 提取特征
            features = self._extract_features(
                candle,
                active,
                range_ctx,
                bar_index,
                channel_width,
                engine_state,
                response_quality,
                consolidation,
                retracement,
                sdp,
            )

            # 产出通用供需信号事件
            event = self._make_event(bar_index, candle, active, features)

            logger.info(
                "供需信号检测: direction=%s, retracement=%.2f, evr=%.2f, position=%.2f",
                self._move_direction,
                retracement,
                response_quality.get("effort_vs_result", 0.0),
                features.get("position_in_range", 0.0),
            )

            # 产出事件后重置
            self._state = _IDLE
            self._clear_tracking()
            return [event]

        # 超时保护：反向评估持续太久
        response_duration = bar_index - self._response_start_bar
        if response_duration > sdp.move_window * 3:
            logger.debug("反向评估超时（%d bars），重置", response_duration)
            self._state = _IDLE
            self._clear_tracking()

        return []

    def _handle_candidate(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        params: EventEngineParams,
        channel_width: float,
        engine_state: EngineState,
    ) -> list[Event]:
        """CANDIDATE：实际上事件已在 EVALUATING_RESPONSE 中产出并重置。此状态作为安全兜底。"""
        self._state = _IDLE
        self._clear_tracking()
        return []

    # ═══ 方向移动检测 ═══

    def _detect_move(self, candle: dict, sdp) -> tuple[str, float, float] | None:
        """
        检测方向移动。

        使用 move_window 根K线的价格变化判断方向和幅度。
        对比当前K线收盘价与窗口起始前一根K线的收盘价（如果有缓存），
        或使用单根K线作为最小触发条件。

        W1修复：不再仅用单根K线 open/close，而是用累积窗口的价格变化。

        返回 (direction, magnitude, start_price) 或 None。
        """
        if len(self._recent_volumes) < 2:
            return None

        close = candle.get("close", 0)
        open_ = candle.get("open", 0)

        if close <= 0:
            return None

        # 尝试多K线窗口检测：对比当前 close 与 window 长度前的价格
        # 使用 _price_history 追踪历史收盘价
        window_size = min(sdp.move_window, len(self._price_history))
        if window_size >= 2 and self._price_history:
            start_price = self._price_history[-window_size]
            magnitude = (close - start_price) / start_price if start_price > 0 else 0.0
            if abs(magnitude) >= sdp.move_threshold:
                direction = _BULLISH if magnitude > 0 else _BEARISH
                return direction, magnitude, start_price

        # 兜底：单根K线检测（窗口数据不足时）
        if open_ <= 0:
            return None

        if close > open_:
            direction = _BULLISH
            magnitude = (close - open_) / open_
            start_price = open_
        elif close < open_:
            direction = _BEARISH
            magnitude = (open_ - close) / open_
            start_price = open_
        else:
            return None

        return direction, magnitude, start_price

    def _is_move_continuing(self, candle: dict, sdp) -> bool:
        """判断方向移动是否仍在继续"""
        close = candle.get("close", 0)
        open_ = candle.get("open", 0)
        move_magnitude = abs(self._move_end_price - self._move_start_price)

        if self._move_direction == _BULLISH:
            # 上涨移动：阳线或十字星继续，阴线但幅度小也继续
            bar_body = close - open_
            if bar_body >= 0:
                return True
            # 小幅阴线（回调不到移动幅度的 strong_retracement）也算继续
            if (
                move_magnitude > 0
                and abs(bar_body) < move_magnitude * sdp.strong_retracement
            ):
                return True
            return False
        else:
            # 下跌移动：阴线继续
            bar_body = close - open_
            if bar_body <= 0:
                return True
            if (
                move_magnitude > 0
                and abs(bar_body) < move_magnitude * sdp.strong_retracement
            ):
                return True
            return False

    # ═══ 反向运动评估 ═══

    def _calc_retracement(self, current_close: float) -> float:
        """
        计算回撤比率：反向运动幅度 / 方向移动幅度。

        BULLISH移动后的回撤 = (move_end - current) / (move_end - move_start)
        BEARISH移动后的反弹 = (current - move_end) / (move_start - move_end)
        """
        move_magnitude = abs(self._move_end_price - self._move_start_price)
        if move_magnitude <= 0:
            return 0.0

        if self._move_direction == _BULLISH:
            # 上涨后被回撤
            retracement = (self._move_end_price - current_close) / move_magnitude
        else:
            # 下跌后反弹
            retracement = (current_close - self._move_end_price) / move_magnitude

        return max(0.0, min(1.0, retracement))

    def _evaluate_response(
        self, move_bars: list[dict], response_bars: list[dict], sdp
    ) -> dict:
        """
        评估反向运动质量。

        返回特征字典：
        - effort_vs_result: effort与结果的比值（越低=越弱=供需信号越强）
        - retracement_ratio: 回撤比率
        - bar_type_shift: 阴阳线比率变化
        - volume_decay: 成交量衰减趋势
        """
        result: dict = {}

        # 1. effort_vs_result: 反向运动的成交量投入 vs 价格效果
        result["effort_vs_result"] = self._calc_effort_vs_result(
            move_bars, response_bars
        )

        # 2. bar_type_shift: 反向运动中阴阳线比例变化
        result["bar_type_shift"] = self._calc_bar_type_shift(move_bars, response_bars)

        # 3. volume_decay: 反向运动中的量能衰减
        result["volume_decay"] = self._calc_volume_decay(move_bars, response_bars)

        return result

    def _calc_effort_vs_result(
        self, move_bars: list[dict], response_bars: list[dict]
    ) -> float:
        """
        effort_vs_result = price_change / (volume_ratio × avg_change)

        低值 = 努力但没结果 = 弱势反向运动 = 供需信号强
        高值 = 轻松推动价格 = 强势反向运动 = 非供需信号
        """
        if not move_bars or not response_bars:
            return 1.0

        # 方向移动的均量和价格变化
        move_volumes = [b.get("volume", 0) for b in move_bars]
        move_avg_vol = sum(move_volumes) / len(move_volumes) if move_volumes else 1.0

        # 反向运动的均量和价格变化
        resp_volumes = [b.get("volume", 0) for b in response_bars]
        resp_avg_vol = sum(resp_volumes) / len(resp_volumes) if resp_volumes else 1.0

        # 反向运动的价格变化
        if len(response_bars) >= 2:
            resp_start = response_bars[0].get("close", 0)
            resp_end = response_bars[-1].get("close", 0)
            resp_price_change = abs(resp_end - resp_start)
        else:
            resp_price_change = 0.0

        # 方向移动的价格变化
        move_start = move_bars[0].get("close", 0)
        move_end = move_bars[-1].get("close", 0)
        move_price_change = abs(move_end - move_start)

        if move_price_change <= 0 or move_avg_vol <= 0:
            return 1.0

        volume_ratio = resp_avg_vol / move_avg_vol
        avg_change = move_price_change / len(move_bars)

        if volume_ratio <= 0 or avg_change <= 0:
            return 1.0

        evr = resp_price_change / (volume_ratio * avg_change)

        # 归一化到 [-1, 1]，低值=弱势（供需信号强）
        return max(-1.0, min(1.0, evr - 1.0))

    def _calc_bar_type_shift(
        self, move_bars: list[dict], response_bars: list[dict]
    ) -> float:
        """
        阴阳线比率的滑动窗口变化。

        返回 [-1, 1]：
        - 正值 = 阳线占比增加（买方增强）
        - 负值 = 阴线占比增加（卖方增强）
        """
        if not move_bars or not response_bars:
            return 0.0

        def bullish_ratio(bars: list[dict]) -> float:
            if not bars:
                return 0.5
            bullish = sum(1 for b in bars if b.get("close", 0) >= b.get("open", 0))
            return bullish / len(bars)

        move_br = bullish_ratio(move_bars)
        resp_br = bullish_ratio(response_bars)

        return resp_br - move_br

    def _calc_volume_decay(
        self, move_bars: list[dict], response_bars: list[dict]
    ) -> float:
        """
        反向运动中的成交量衰减趋势。

        返回比率：< 1 表示缩量，> 1 表示放量。
        """
        if not move_bars or not response_bars:
            return 1.0

        move_volumes = [b.get("volume", 0) for b in move_bars]
        move_avg = sum(move_volumes) / len(move_volumes) if move_volumes else 1.0

        if len(response_bars) < 2:
            return 1.0

        # 反向运动前半段 vs 后半段的量
        half = len(response_bars) // 2
        first_half = [b.get("volume", 0) for b in response_bars[:half]]
        second_half = [b.get("volume", 0) for b in response_bars[half:]]

        avg_first = sum(first_half) / len(first_half) if first_half else 1.0
        avg_second = sum(second_half) / len(second_half) if second_half else 1.0

        if avg_first <= 0:
            return 1.0

        return avg_second / avg_first

    # ═══ 窄幅横盘检测 ═══

    def _detect_consolidation(
        self, bars: list[dict], sdp, channel_width: float
    ) -> dict | None:
        """
        检测窄幅横盘。

        W2修复：只使用最近 min_consolidation_bars 根K线的高低点，
        避免早期大波动导致全量 consolidation_range 过大而漏检。

        返回横盘特征字典或 None（未检测到横盘）。
        """
        if len(bars) < sdp.min_consolidation_bars:
            return None

        # W2修复：只用最近 min_consolidation_bars 根K线
        recent_bars = bars[-sdp.min_consolidation_bars :]

        highs = [b.get("high", 0) for b in recent_bars]
        lows = [b.get("low", 0) for b in recent_bars]

        max_high = max(highs)
        min_low = min(lows)
        consolidation_range = max_high - min_low

        # 归一化到区间宽度
        if channel_width <= 0:
            return None

        relative_range = consolidation_range / channel_width

        # 横盘条件：价格波动范围 < consolidation_threshold × channel_width
        if relative_range > sdp.consolidation_threshold:
            return None

        # 计算一致性（标准差越小=越一致）
        low_consistency = float(np.std(lows)) if len(lows) >= 2 else 0.0
        high_consistency = float(np.std(highs)) if len(highs) >= 2 else 0.0

        return {
            "consolidation_range": consolidation_range,
            "consolidation_range_relative": relative_range,
            "low_consistency": low_consistency,
            "high_consistency": high_consistency,
            "consolidation_bars": len(bars),
            "max_high": max_high,
            "min_low": min_low,
        }

    # ═══ 特征提取 ═══

    def _extract_features(
        self,
        candle: dict,
        active: Range,
        range_ctx: RangeContext,
        bar_index: int,
        channel_width: float,
        engine_state: EngineState,
        response_quality: dict,
        consolidation: dict,
        retracement: float,
        sdp,
    ) -> dict:
        """
        提取全部特征给进化系统（设计文档 §4）。

        五大类：
        1. 方向移动特征
        2. 反向运动质量
        3. 窄幅横盘特征
        4. 量价转变
        5. 位置特征
        """
        close = candle.get("close", 0)
        features: dict = {}

        # ─── 方向移动特征 ───
        features["direction"] = self._move_direction
        move_magnitude = abs(self._move_end_price - self._move_start_price)
        features["move_magnitude"] = (
            move_magnitude / self._move_start_price
            if self._move_start_price > 0
            else 0.0
        )
        features["move_bars"] = len(self._move_bars)
        features["move_start_price"] = self._move_start_price
        features["move_end_price"] = self._move_end_price
        features["move_start_bar"] = self._move_start_bar

        # W4配套：将 boundary_proximity 写入 features，供 rule_engine 读取
        features["boundary_proximity"] = sdp.boundary_proximity

        # 移动过程的成交量分布
        move_volumes = [b.get("volume", 0) for b in self._move_bars]
        features["move_avg_volume"] = (
            sum(move_volumes) / len(move_volumes) if move_volumes else 0.0
        )
        features["move_volume_profile"] = (
            "expanding" if self._is_volume_expanding(move_volumes) else "drying"
        )

        # ─── 反向运动质量 ───
        features["retracement_ratio"] = retracement
        features["effort_vs_result"] = response_quality.get("effort_vs_result", 0.0)
        features["bar_type_shift"] = response_quality.get("bar_type_shift", 0.0)
        features["volume_decay"] = response_quality.get("volume_decay", 1.0)
        features["response_bars"] = len(self._response_bars)

        # ─── 窄幅横盘特征 ───
        features["consolidation_range"] = consolidation.get("consolidation_range", 0.0)
        features["consolidation_range_relative"] = consolidation.get(
            "consolidation_range_relative", 0.0
        )
        features["low_consistency"] = consolidation.get("low_consistency", 0.0)
        features["high_consistency"] = consolidation.get("high_consistency", 0.0)
        features["consolidation_bars"] = consolidation.get("consolidation_bars", 0)

        # ─── 量价转变 ───
        resp_volumes = [b.get("volume", 0) for b in self._response_bars]
        resp_avg = sum(resp_volumes) / len(resp_volumes) if resp_volumes else 0.0
        move_avg = features["move_avg_volume"]
        features["buy_sell_volume_ratio"] = resp_avg / move_avg if move_avg > 0 else 1.0
        features["volume_trend"] = (
            "drying" if response_quality.get("volume_decay", 1.0) < 0.7 else "stable"
        )

        # ─── 位置特征 ───
        features["position_in_range"] = range_ctx.position_in_range
        features["distance_to_lower"] = range_ctx.distance_to_lower
        features["distance_to_upper"] = range_ctx.distance_to_upper
        features["distance_to_boundary"] = min(
            range_ctx.distance_to_lower, range_ctx.distance_to_upper
        )

        # ─── 上下文 ───
        features["current_phase"] = (
            active.current_phase.value if active.current_phase else ""
        )
        features["range_id"] = active.range_id
        features["prior_events"] = self._get_prior_events(engine_state)

        return features

    def _get_prior_events(self, engine_state: EngineState) -> list[str]:
        """EVD-10: 从事件历史中提取已发生事件类型列表"""
        seen: set[str] = set()
        result: list[str] = []
        for event in engine_state.recent_events:
            et = event.event_type.value
            if et not in seen:
                seen.add(et)
                result.append(et)
        return result

    def _is_volume_expanding(self, volumes: list[float]) -> bool:
        """判断成交量是否递增"""
        if len(volumes) < 2:
            return False
        half = len(volumes) // 2
        first = sum(volumes[:half]) / half if half > 0 else 0
        second = (
            sum(volumes[half:]) / (len(volumes) - half) if len(volumes) > half else 0
        )
        return second > first if first > 0 else False

    def _avg_volume(self) -> float:
        """近期平均成交量"""
        if not self._recent_volumes:
            return 1.0
        return sum(self._recent_volumes) / len(self._recent_volumes)

    # ═══ 区间宽度 ═══

    def _get_channel_width(self, active: Range) -> float:
        """获取区间宽度"""
        if active.channel_width > 0:
            return active.channel_width
        # 兜底：从锚点计算
        lower = active.primary_anchor_1
        upper = active.opposite_anchor
        if lower is not None and upper is not None:
            return abs(upper.extreme_price - lower.extreme_price)
        return 0.0

    # ═══ 事件构造 ═══

    def _make_event(
        self,
        bar_index: int,
        candle: dict,
        active: Range,
        features: dict,
    ) -> Event:
        """构造通用供需信号事件"""
        close = candle.get("close", 0)

        return Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SUPPLY_DEMAND_SIGNAL,
            event_result=EventResult.SUCCESS,
            sequence_start_bar=features.get("move_start_bar", bar_index),
            sequence_end_bar=bar_index,
            sequence_length=bar_index - features.get("move_start_bar", bar_index) + 1,
            volume_ratio=features.get("volume_decay", 1.0),
            volume_pattern=features.get("volume_trend", "normal"),
            effort_vs_result=features.get("effort_vs_result", 0.0),
            price_extreme=candle.get(
                "high" if self._move_direction == _BULLISH else "low", 0
            ),
            price_body=close,
            position_in_range=features.get("position_in_range", 0.0),
            range_id=active.range_id,
            phase=active.current_phase,
            variant_tag=self._move_direction,
            variant_features=features,
        )

    # ═══ 状态管理 ═══

    def _clear_tracking(self) -> None:
        """清理追踪数据"""
        self._move_direction = ""
        self._move_start_bar = 0
        self._move_start_price = 0.0
        self._move_end_price = 0.0
        self._move_bars = []
        self._move_avg_volume = 0.0
        self._response_start_bar = 0
        self._response_bars = []
        self._response_peak = 0.0
        self._response_trough = 0.0
        self._consolidation_bars = []

    def reset(self) -> None:
        """重置状态机"""
        self._state = _IDLE
        self._clear_tracking()
        self._recent_volumes = []
        self._price_history = []
