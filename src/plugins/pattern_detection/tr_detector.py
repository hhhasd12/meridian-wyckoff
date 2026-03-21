"""
交易区间（TR）识别器
整合曲线边界拟合，识别非线性TR边界，区分趋势和盘整市场
解决TR区间识别模糊性：增加"区间稳定性锁定机制"
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd

# 导入曲线边界拟合模块
try:
    from .curve_boundary import BoundaryType, CurveBoundaryFitter
except ImportError:
    # 如果直接运行，使用相对导入
    from curve_boundary import BoundaryType, CurveBoundaryFitter  # type: ignore


class TRStatus(Enum):
    """交易区间状态枚举"""

    CONSOLIDATION = "CONSOLIDATION"  # 盘整（明确TR）
    TRENDING = "TRENDING"  # 趋势（无明确TR）
    TRANSITION = "TRANSITION"  # 过渡期（TR形成或突破中）
    UNKNOWN = "UNKNOWN"  # 未知


class BreakoutDirection(Enum):
    """突破方向枚举"""

    UP = "UP"  # 向上突破
    DOWN = "DOWN"  # 向下跌破
    NONE = "NONE"  # 无突破


@dataclass
class TradingRange:
    """交易区间数据结构"""

    tr_id: str
    upper_boundary: float  # 上边界
    lower_boundary: float  # 下边界
    upper_confidence: float  # 上边界置信度
    lower_confidence: float  # 下边界置信度
    boundary_type: BoundaryType  # 边界类型
    timestamp: datetime  # 检测时间
    status: TRStatus  # TR状态
    confidence: float  # TR整体置信度 [0, 1]
    stability_score: float  # 稳定性评分 [0, 1]
    price_position: float  # 当前价格在TR中的位置 [0, 1]
    breakout_direction: BreakoutDirection  # 突破方向
    breakout_strength: float  # 突破强度 [0, 1]

    # 统计信息
    age_bars: int = 0  # TR年龄（K线数）
    test_count: int = 0  # 边界测试次数
    successful_tests: int = 0  # 成功测试次数（价格从边界反弹）

    # 几何特征
    width_pct: float = 0.0  # TR宽度百分比
    aspect_ratio: float = 0.0  # 高宽比
    curvature: float = 0.0  # 边界曲率

    # 上下文信息
    market_regime: Optional[str] = None  # 市场体制
    volatility_index: float = 1.0  # 波动率指数
    volume_profile: Optional[dict[str, Any]] = None  # 成交量分布


class TRDetector:
    """
    交易区间识别器

    功能：
    1. 整合曲线边界拟合识别非线性TR边界
    2. TR稳定性锁定机制（防抖动）
    3. 突破检测与验证
    4. TR质量评估与置信度计算
    5. 多时间框架TR分析

    设计原则：
    1. 稳定性优先：TR锁定后需有效突破N%并保持M根K线才改变
    2. 渐进式解锁：突破尝试需要连续确认
    3. 动态参数：所有阈值可配置，纳入自动进化
    4. 多证据融合：结合价格行为、成交量、波动率判断TR
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        初始化TR识别器

        Args:
            config: 配置字典，包含以下参数：
                - min_tr_width_pct: 最小TR宽度百分比（默认1.0%）
                - min_tr_bars: 最小TR持续时间（K线数，默认10）
                - stability_lock_bars: 稳定性锁定K线数（默认5）
                - breakout_confirmation_bars: 突破确认K线数（默认3）
                - breakout_threshold_pct: 突破阈值百分比（默认1.0%）
                - max_test_failure_ratio: 最大边界测试失败率（默认0.3）
                - curve_fit_smoothness: 曲线拟合平滑度（默认0.7）
                - require_volume_confirmation: 是否需要成交量确认（默认False）
                - enable_stability_lock: 启用稳定性锁定（默认True）
                - volatility_adjustment: 波动率调整系数（默认True）
        """
        self.config = config or {}
        self.min_tr_width_pct = self.config.get("min_tr_width_pct", 1.0)
        self.min_tr_bars = self.config.get("min_tr_bars", 10)
        self.stability_lock_bars = self.config.get("stability_lock_bars", 5)
        self.breakout_confirmation_bars = self.config.get(
            "breakout_confirmation_bars", 3
        )
        self.breakout_threshold_pct = self.config.get("breakout_threshold_pct", 1.0)
        self.max_test_failure_ratio = self.config.get("max_test_failure_ratio", 0.3)
        self.curve_fit_smoothness = self.config.get("curve_fit_smoothness", 0.7)
        self.require_volume_confirmation = self.config.get(
            "require_volume_confirmation", False
        )
        self.enable_stability_lock = self.config.get("enable_stability_lock", True)
        self.volatility_adjustment = self.config.get("volatility_adjustment", True)

        # 曲线边界拟合器
        self.boundary_fitter = CurveBoundaryFitter(
            {
                "pivot_window": 5,
                "min_pivot_distance": 10,
                "spline_smoothness": self.curve_fit_smoothness,
                "min_boundary_points": 8,
            }
        )

        # TR状态跟踪
        self.active_tr: Optional[TradingRange] = None
        self.tr_history: list[TradingRange] = []
        self.next_tr_id = 1

        # 突破跟踪
        self.breakout_attempts: list[dict[str, Any]] = []

        # 统计信息
        self.stats = {
            "tr_detections": 0,
            "tr_confirmations": 0,
            "breakouts_detected": 0,
            "false_breakouts": 0,
            "avg_tr_width_pct": 0.0,
            "avg_tr_lifetime_bars": 0.0,
            "success_rate": 0.0,  # TR内高空低多成功率
        }

        # 稳定性锁定状态
        self.stability_lock: dict[str, Any] = {
            "locked": False,
            "lock_start_time": None,
            "lock_bars_count": 0,
            "pending_breakout": None,  # 待确认的突破
            "confirmation_bars": 0,
        }

    def detect_trading_range(
        self,
        df: pd.DataFrame,
        market_regime: Optional[str] = None,
        volatility_index: float = 1.0,
    ) -> Optional[TradingRange]:
        """
        检测交易区间

        Args:
            df: OHLCV数据
            market_regime: 市场体制（来自RegimeDetector）
            volatility_index: 波动率指数

        Returns:
            检测到的交易区间，或None（无有效TR）
        """
        if len(df) < 20:  # 需要足够数据检测TR
            return None

        # 使用曲线边界拟合器检测TR边界
        tr_result = self.boundary_fitter.detect_trading_range(
            df["high"], df["low"], df["close"]
        )

        if not tr_result:
            return None

        # 检查TR有效性
        is_valid, validation_result = self._validate_tr_result(
            tr_result, df, volatility_index
        )

        if not is_valid:
            return None

        # 计算TR置信度
        confidence = self._calculate_tr_confidence(tr_result, validation_result, df)

        # 计算稳定性评分
        stability_score = self._calculate_stability_score(tr_result, df)

        # 确定TR状态
        status = self._determine_tr_status(tr_result, confidence, stability_score)

        # 检查突破
        breakout_direction, breakout_strength = self._detect_breakout(tr_result, df)

        # 创建TR记录
        # 修复：时间戳可能是int64类型，需要转换为datetime对象
        last_timestamp = df.index[-1]
        if isinstance(last_timestamp, (int, np.integer)):
            # 如果是整数时间戳（Unix毫秒），转换为datetime
            timestamp_dt = datetime.fromtimestamp(float(last_timestamp) / 1000.0)
            time_str = timestamp_dt.strftime("%Y%m%d_%H%M")
        else:
            # 如果是datetime对象，直接格式化
            time_str = last_timestamp.strftime("%Y%m%d_%H%M")

        tr_id = f"tr_{self.next_tr_id}_{time_str}"
        self.next_tr_id += 1

        # 计算几何特征
        width_pct = tr_result["boundary_distance"]
        upper_curve = tr_result["upper_boundary"]["curvature"]
        lower_curve = tr_result["lower_boundary"]["curvature"]
        avg_curvature = (abs(upper_curve) + abs(lower_curve)) / 2

        # 计算高宽比（简化）
        tr_duration = len(df)
        aspect_ratio = tr_duration / (width_pct + 0.1)  # 避免除零

        # 修复：时间戳可能是int64类型，需要转换为datetime对象
        last_timestamp = df.index[-1]
        if isinstance(last_timestamp, (int, np.integer)):
            # 如果是整数时间戳（Unix毫秒），转换为datetime
            # 使用datetime.fromtimestamp，注意需要除以1000转换为秒
            timestamp_dt = datetime.fromtimestamp(float(last_timestamp) / 1000.0)
        else:
            # 如果是datetime对象，直接使用
            timestamp_dt = last_timestamp

        tr = TradingRange(
            tr_id=tr_id,
            upper_boundary=tr_result["upper_price"],
            lower_boundary=tr_result["lower_price"],
            upper_confidence=tr_result["upper_boundary"]["confidence"],
            lower_confidence=tr_result["lower_boundary"]["confidence"],
            boundary_type=tr_result["upper_boundary"][
                "boundary_type"
            ],  # 使用上边界类型
            timestamp=timestamp_dt,
            status=status,
            confidence=confidence,
            stability_score=stability_score,
            price_position=tr_result["price_position"],
            breakout_direction=breakout_direction,
            breakout_strength=breakout_strength,
            age_bars=tr_duration,
            width_pct=width_pct,
            curvature=avg_curvature,
            aspect_ratio=aspect_ratio,
            market_regime=market_regime,
            volatility_index=volatility_index,
        )

        # 更新稳定性锁定
        self._update_stability_lock(tr, df)

        # 如果启用了稳定性锁定且TR已锁定，检查是否应该替换当前TR
        if self.enable_stability_lock and self.stability_lock["locked"]:
            # 只有在当前TR明显不同或质量更高时才替换
            if self.active_tr:
                should_replace = self._should_replace_active_tr(self.active_tr, tr)
                if should_replace:
                    self.active_tr = tr
                    self.tr_history.append(tr)
                    self.stats["tr_detections"] += 1
                    if confidence > 0.7:
                        self.stats["tr_confirmations"] += 1
            else:
                self.active_tr = tr
                self.tr_history.append(tr)
                self.stats["tr_detections"] += 1
                if confidence > 0.7:
                    self.stats["tr_confirmations"] += 1
        else:
            # 未启用稳定性锁定，直接更新
            self.active_tr = tr
            self.tr_history.append(tr)
            self.stats["tr_detections"] += 1
            if confidence > 0.7:
                self.stats["tr_confirmations"] += 1

        # 限制历史记录长度
        if len(self.tr_history) > 1000:
            self.tr_history = self.tr_history[-1000:]

        # 更新统计信息
        self._update_stats()

        return tr

    def _validate_tr_result(
        self, tr_result: dict[str, Any], df: pd.DataFrame, volatility_index: float
    ) -> tuple[bool, dict[str, Any]]:
        """验证TR结果有效性"""
        validation = {
            "width_valid": False,
            "duration_valid": False,
            "boundary_valid": False,
            "price_position_valid": False,
            "volume_valid": True,
        }

        # 1. 检查TR宽度
        width_pct = tr_result["boundary_distance"]
        min_width = self.min_tr_width_pct

        # 根据波动率调整最小宽度
        if self.volatility_adjustment:
            min_width *= volatility_index

        validation["width_valid"] = width_pct >= min_width

        # 2. 检查TR持续时间（通过边界拟合点数估算）
        upper_points = tr_result["upper_boundary"]["num_points"]
        lower_points = tr_result["lower_boundary"]["num_points"]
        avg_points = (upper_points + lower_points) / 2

        # 根据点数估算持续时间
        estimated_bars = avg_points * 3  # 每个枢轴点大约3根K线

        validation["duration_valid"] = estimated_bars >= self.min_tr_bars

        # 3. 检查边界有效性
        upper_confidence = tr_result["upper_boundary"]["confidence"]
        lower_confidence = tr_result["lower_boundary"]["confidence"]
        avg_confidence = (upper_confidence + lower_confidence) / 2

        validation["boundary_valid"] = avg_confidence >= 0.5

        # 4. 检查价格位置（不应在边界极端位置）
        price_position = tr_result["price_position"]
        validation["price_position_valid"] = 0.1 <= price_position <= 0.9

        # 5. 检查成交量确认（可选）
        if self.require_volume_confirmation and "volume" in df.columns:
            # 检查TR内部成交量是否相对较低（盘整特征）
            recent_volume = df["volume"].iloc[-10:].mean()
            older_volume = df["volume"].iloc[-30:-10].mean()

            if older_volume > 0:
                volume_ratio = recent_volume / older_volume
                validation["volume_valid"] = volume_ratio < 1.5  # TR内成交量不应过高

        # 综合有效性
        is_valid = (
            validation["width_valid"]
            and validation["duration_valid"]
            and validation["boundary_valid"]
            and validation["price_position_valid"]
            and validation["volume_valid"]
        )

        return is_valid, validation

    def _calculate_tr_confidence(
        self,
        tr_result: dict[str, Any],
        validation_result: dict[str, Any],
        df: pd.DataFrame,
    ) -> float:
        """计算TR置信度"""
        confidence_factors = []

        # 1. 边界拟合置信度（40%权重）
        upper_conf = tr_result["upper_boundary"]["confidence"]
        lower_conf = tr_result["lower_boundary"]["confidence"]
        boundary_confidence = (upper_conf + lower_conf) / 2
        confidence_factors.append(("boundary", boundary_confidence, 0.4))

        # 2. TR宽度因子（20%权重）
        width_pct = tr_result["boundary_distance"]
        min_width = self.min_tr_width_pct
        width_factor = min(
            width_pct / (min_width * 2), 1.0
        )  # 2倍最小宽度达到最大置信度
        confidence_factors.append(("width", width_factor, 0.2))

        # 3. 价格位置因子（15%权重）
        price_position = tr_result["price_position"]
        # 价格在TR中部时置信度最高
        position_factor = 1.0 - 2 * abs(price_position - 0.5)
        confidence_factors.append(("position", position_factor, 0.15))

        # 4. 波动率因子（15%权重）
        if "volume" in df.columns and len(df) >= 20:
            # 计算TR内波动率（价格变化/ATR）
            recent_prices = df["close"].iloc[-10:]
            price_range = recent_prices.max() - recent_prices.min()
            atr = self._calculate_atr(df["high"], df["low"], df["close"])

            if atr > 0:
                volatility_ratio = price_range / atr
                # 波动率较低时置信度较高（盘整特征）
                volatility_factor = max(
                    0, 1.0 - volatility_ratio / 5.0
                )  # 5倍ATR时降为0
                confidence_factors.append(("volatility", volatility_factor, 0.15))
            else:
                confidence_factors.append(("volatility", 0.5, 0.15))
        else:
            confidence_factors.append(("volatility", 0.5, 0.15))

        # 5. 边界类型因子（10%权重）
        upper_type = tr_result["upper_boundary"]["boundary_type"]
        lower_type = tr_result["lower_boundary"]["boundary_type"]

        # 某些边界类型组合更可能是TR
        type_score = 0.5  # 默认

        # 理想TR边界：矩形、通道、对称三角形
        ideal_types = {
            BoundaryType.RECTANGLE,
            BoundaryType.CHANNEL_UP,
            BoundaryType.CHANNEL_DOWN,
            BoundaryType.TRIANGLE_SYMMETRICAL,
        }

        if upper_type in ideal_types and lower_type in ideal_types:
            type_score = 0.9
        elif BoundaryType.UNKNOWN in (upper_type, lower_type):
            type_score = 0.3

        confidence_factors.append(("type", type_score, 0.1))

        # 计算加权置信度
        total_weight = 0.0
        weighted_sum = 0.0

        for name, score, weight in confidence_factors:
            weighted_sum += score * weight
            total_weight += weight

        confidence = weighted_sum / total_weight if total_weight > 0 else 0.0

        return max(0.0, min(1.0, confidence))

    def _calculate_stability_score(
        self, tr_result: dict[str, Any], df: pd.DataFrame
    ) -> float:
        """计算TR稳定性评分"""
        if len(df) < 10:
            return 0.0

        stability_factors = []

        # 1. 边界测试历史（如果可用）
        if self.active_tr:
            test_ratio = self.active_tr.successful_tests / max(
                self.active_tr.test_count, 1
            )
            stability_factors.append(("test_history", test_ratio, 0.3))
        else:
            stability_factors.append(("test_history", 0.5, 0.3))

        # 2. 价格在TR内的持续时间
        # 检查最近价格是否在TR内稳定
        recent_prices = df["close"].iloc[-5:]
        upper = tr_result["upper_price"]
        lower = tr_result["lower_price"]

        in_tr_count = sum((lower <= price <= upper) for price in recent_prices)
        in_tr_ratio = in_tr_count / len(recent_prices)

        stability_factors.append(("price_stability", in_tr_ratio, 0.3))

        # 3. 成交量稳定性（可选）
        if "volume" in df.columns:
            recent_volume = df["volume"].iloc[-10:]
            volume_std = recent_volume.std()
            volume_mean = recent_volume.mean()

            if volume_mean > 0:
                volume_cv = volume_std / volume_mean  # 变异系数
                volume_stability = max(0, 1.0 - volume_cv)  # 变异系数越小越稳定
                stability_factors.append(("volume_stability", volume_stability, 0.2))
            else:
                stability_factors.append(("volume_stability", 0.5, 0.2))
        else:
            stability_factors.append(("volume_stability", 0.5, 0.2))

        # 4. 波动率稳定性
        if len(df) >= 20:
            # 计算最近波动率变化
            recent_atr = self._calculate_atr(
                df["high"].iloc[-10:], df["low"].iloc[-10:], df["close"].iloc[-10:]
            )

            older_atr = self._calculate_atr(
                df["high"].iloc[-20:-10],
                df["low"].iloc[-20:-10],
                df["close"].iloc[-20:-10],
            )

            if older_atr > 0:
                atr_change = abs(recent_atr - older_atr) / older_atr
                volatility_stability = max(0, 1.0 - atr_change)
                stability_factors.append(
                    ("volatility_stability", volatility_stability, 0.2)
                )
            else:
                stability_factors.append(("volatility_stability", 0.5, 0.2))
        else:
            stability_factors.append(("volatility_stability", 0.5, 0.2))

        # 计算加权稳定性评分
        total_weight = 0.0
        weighted_sum = 0.0

        for name, score, weight in stability_factors:
            weighted_sum += score * weight
            total_weight += weight

        stability = weighted_sum / total_weight if total_weight > 0 else 0.0

        return max(0.0, min(1.0, stability))

    def _determine_tr_status(
        self, tr_result: dict[str, Any], confidence: float, stability_score: float
    ) -> TRStatus:
        """确定TR状态"""
        if confidence < 0.4:
            return TRStatus.UNKNOWN

        # 检查突破强度
        breakout_strength = tr_result["breakout_strength"]

        if breakout_strength > 0.5:
            # 强突破，可能是趋势或过渡
            return TRStatus.TRANSITION
        if breakout_strength > 0.2:
            # 弱突破，过渡期
            return TRStatus.TRANSITION
        if confidence > 0.6 and stability_score > 0.5:
            # 高置信度且稳定，明确盘整
            return TRStatus.CONSOLIDATION
        # 其他情况，可能是弱趋势或形成中的TR
        return TRStatus.TRENDING

    def _detect_breakout(
        self, tr_result: dict[str, Any], df: pd.DataFrame
    ) -> tuple[BreakoutDirection, float]:
        """检测突破"""
        breakout_direction = BreakoutDirection.NONE
        breakout_strength = 0.0

        direction_code = tr_result["breakout_direction"]
        strength = tr_result["breakout_strength"]

        if direction_code == 1 and strength > 0:
            breakout_direction = BreakoutDirection.UP
            breakout_strength = strength
        elif direction_code == -1 and strength > 0:
            breakout_direction = BreakoutDirection.DOWN
            breakout_strength = strength

        # 如果需要，进行额外验证
        if breakout_direction != BreakoutDirection.NONE and self.enable_stability_lock:
            # 检查突破确认
            is_confirmed = self._confirm_breakout(breakout_direction, tr_result, df)

            if not is_confirmed:
                breakout_strength *= 0.5  # 降低未确认突破的强度

        return breakout_direction, breakout_strength

    def _confirm_breakout(
        self, direction: BreakoutDirection, tr_result: dict[str, Any], df: pd.DataFrame
    ) -> bool:
        """确认突破有效性"""
        if len(df) < 3:
            return False

        upper = tr_result["upper_price"]
        lower = tr_result["lower_price"]

        # 检查最近3根K线
        df["high"].iloc[-3:]
        df["low"].iloc[-3:]
        recent_closes = df["close"].iloc[-3:]

        if direction == BreakoutDirection.UP:
            # 向上突破确认：收盘价持续在阻力上方
            above_resistance: int = sum(close > upper for close in recent_closes)
            return above_resistance >= 2  # 至少2根K线确认
        if direction == BreakoutDirection.DOWN:
            # 向下跌破确认：收盘价持续在支撑下方
            below_support: int = sum(close < lower for close in recent_closes)
            return below_support >= 2  # 至少2根K线确认

        return False

    def _update_stability_lock(self, tr: TradingRange, df: pd.DataFrame) -> None:
        """更新稳定性锁定状态"""
        if not self.enable_stability_lock:
            return

        # 如果当前没有锁定，且TR置信度高，开始锁定
        if not self.stability_lock["locked"]:
            if tr.confidence > 0.7 and tr.stability_score > 0.6:
                self.stability_lock["locked"] = True
                self.stability_lock["lock_start_time"] = df.index[-1]
                self.stability_lock["lock_bars_count"] = 0
                self.stability_lock["pending_breakout"] = None
                self.stability_lock["confirmation_bars"] = 0
        else:
            # 已锁定，更新锁定计数
            self.stability_lock["lock_bars_count"] += 1

            # 检查突破尝试
            if tr.breakout_direction != BreakoutDirection.NONE:
                if self.stability_lock["pending_breakout"] is None:
                    # 新突破尝试
                    self.stability_lock["pending_breakout"] = {
                        "direction": tr.breakout_direction,
                        "strength": tr.breakout_strength,
                        "start_time": df.index[-1],
                    }
                    self.stability_lock["confirmation_bars"] = 1
                else:
                    # 继续现有突破尝试
                    pending = self.stability_lock["pending_breakout"]
                    if pending is None:
                        return
                    # 此时pending不是None，进行类型检查
                    if not isinstance(pending, dict):
                        return
                    # 类型提示：此时pending是dict类型
                    pending_dict: dict[str, Any] = pending
                    if pending_dict["direction"] == tr.breakout_direction:
                        self.stability_lock["confirmation_bars"] += 1

                        # 检查是否达到确认条件
                        if (
                            self.stability_lock["confirmation_bars"]
                            >= self.breakout_confirmation_bars
                        ):
                            # 突破确认，解除锁定
                            self.stability_lock["locked"] = False
                            self.stability_lock["pending_breakout"] = None

                            # 记录突破
                            self.breakout_attempts.append(
                                {
                                    "direction": tr.breakout_direction,
                                    "strength": tr.breakout_strength,
                                    "confirmed": True,
                                    "timestamp": df.index[-1],
                                }
                            )

                            self.stats["breakouts_detected"] += 1
                    else:
                        # 突破方向改变，重置
                        self.stability_lock["pending_breakout"] = None
                        self.stability_lock["confirmation_bars"] = 0

            # 检查锁定是否过期（太久没有突破）
            max_lock_bars = self.stability_lock_bars * 3  # 最长锁定时间
            if self.stability_lock["lock_bars_count"] > max_lock_bars:
                self.stability_lock["locked"] = False
                self.stability_lock["pending_breakout"] = None

    def _should_replace_active_tr(
        self, active_tr: TradingRange, new_tr: TradingRange
    ) -> bool:
        """判断是否应该替换当前活跃TR"""
        # 1. 如果新TR置信度明显更高（>0.2差异）
        if new_tr.confidence - active_tr.confidence > 0.2:
            return True

        # 2. 如果新TR明显更宽（>50%差异）
        width_diff = (new_tr.width_pct - active_tr.width_pct) / active_tr.width_pct
        if width_diff > 0.5:
            return True

        # 3. 如果当前TR已过期（年龄太大）
        if active_tr.age_bars > 100:
            return True

        # 4. 如果当前TR稳定性差且新TR稳定性好
        return bool(active_tr.stability_score < 0.4 and new_tr.stability_score > 0.6)

    def _calculate_atr(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> float:
        """计算平均真实波幅（简化版）"""
        if len(close) < period + 1:
            return 0.0

        try:
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))

            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean().iloc[-1]

            return atr if not np.isnan(atr) else 0.0
        except Exception:
            return 0.0

    def _update_stats(self) -> None:
        """更新统计信息"""
        if self.tr_history:
            # 计算平均TR宽度
            widths = [tr.width_pct for tr in self.tr_history[-20:]]
            self.stats["avg_tr_width_pct"] = float(np.mean(widths)) if widths else 0.0

            # 计算平均TR生命周期（简化）
            if len(self.tr_history) >= 2:
                lifetimes = []
                for i in range(1, len(self.tr_history)):
                    if (
                        self.tr_history[i].timestamp
                        and self.tr_history[i - 1].timestamp
                    ):
                        lifetime = (
                            self.tr_history[i].timestamp
                            - self.tr_history[i - 1].timestamp
                        ).total_seconds() / 3600
                        lifetimes.append(lifetime)

                if lifetimes:
                    self.stats["avg_tr_lifetime_bars"] = float(np.mean(lifetimes))

            # 计算成功率（简化）
            total_tests = sum(tr.test_count for tr in self.tr_history[-10:])
            successful_tests = sum(tr.successful_tests for tr in self.tr_history[-10:])

            if total_tests > 0:
                self.stats["success_rate"] = successful_tests / total_tests

    def get_tr_signals(self, current_price: float) -> dict[str, Any]:
        """
        获取TR交易信号

        Args:
            current_price: 当前价格

        Returns:
            交易信号字典
        """
        if not self.active_tr:
            return {
                "tr_status": "NO_TR",
                "signals": [],
                "support": None,
                "resistance": None,
                "position": 0.5,
                "confidence": 0.0,
            }

        tr = self.active_tr
        signals = []

        # 根据TR状态和价格位置生成信号
        if tr.status == TRStatus.CONSOLIDATION:
            # 盘整市：高空低多

            # 计算边界区域（支撑/阻力区域）
            support_zone = tr.lower_boundary * 1.01  # 支撑区域上边界
            resistance_zone = tr.upper_boundary * 0.99  # 阻力区域下边界

            # 接近支撑区域：买入信号
            if (
                current_price <= support_zone
                and current_price > tr.lower_boundary * 0.99
            ):
                signals.append(
                    {
                        "type": "BUY_SUPPORT",
                        "entry_price": current_price,
                        "target_price": tr.upper_boundary,
                        "stop_loss": tr.lower_boundary * 0.98,
                        "confidence": tr.confidence
                        * (1.0 - tr.price_position),  # 越接近支撑置信度越高
                        "reason": "TR支撑区域买入",
                    }
                )

            # 接近阻力区域：卖出信号
            elif (
                current_price >= resistance_zone
                and current_price < tr.upper_boundary * 1.01
            ):
                signals.append(
                    {
                        "type": "SELL_RESISTANCE",
                        "entry_price": current_price,
                        "target_price": tr.lower_boundary,
                        "stop_loss": tr.upper_boundary * 1.02,
                        "confidence": tr.confidence
                        * tr.price_position,  # 越接近阻力置信度越高
                        "reason": "TR阻力区域卖出",
                    }
                )

            # TR中部：观望或小仓位
            elif 0.4 <= tr.price_position <= 0.6:
                signals.append(
                    {
                        "type": "HOLD",
                        "confidence": tr.confidence * 0.5,
                        "reason": "TR中部，等待边界测试",
                    }
                )

        elif tr.status == TRStatus.TRENDING:
            # 趋势市：顺势交易
            if tr.breakout_direction == BreakoutDirection.UP:
                signals.append(
                    {
                        "type": "BUY_TREND",
                        "entry_price": current_price,
                        "target_price": current_price * 1.03,  # 3%目标
                        "stop_loss": tr.lower_boundary,
                        "confidence": tr.confidence * tr.breakout_strength,
                        "reason": "向上突破趋势",
                    }
                )
            elif tr.breakout_direction == BreakoutDirection.DOWN:
                signals.append(
                    {
                        "type": "SELL_TREND",
                        "entry_price": current_price,
                        "target_price": current_price * 0.97,  # 3%目标
                        "stop_loss": tr.upper_boundary,
                        "confidence": tr.confidence * tr.breakout_strength,
                        "reason": "向下突破趋势",
                    }
                )

        elif tr.status == TRStatus.TRANSITION:
            # 过渡期：谨慎交易或等待
            signals.append(
                {
                    "type": "WAIT",
                    "confidence": tr.confidence,
                    "reason": "TR突破过渡期，等待确认",
                }
            )

        # 排序信号（按置信度）
        signals.sort(key=lambda x: float(x["confidence"]), reverse=True)  # type: ignore

        return {
            "tr_status": tr.status.value,
            "signals": signals[:3],  # 最多3个信号
            "support": tr.lower_boundary,
            "resistance": tr.upper_boundary,
            "position": tr.price_position,
            "confidence": tr.confidence,
            "stability": tr.stability_score,
            "breakout_direction": tr.breakout_direction.value,
            "breakout_strength": tr.breakout_strength,
            "tr_id": tr.tr_id,
        }

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()

        # 添加当前状态信息
        stats["active_tr"] = self.active_tr is not None
        stats["stability_locked"] = self.stability_lock["locked"]
        stats["pending_breakout"] = self.stability_lock["pending_breakout"] is not None
        stats["tr_history_count"] = len(self.tr_history)
        stats["breakout_attempts"] = len(self.breakout_attempts)

        if self.active_tr:
            stats["current_tr_confidence"] = self.active_tr.confidence
            stats["current_tr_width_pct"] = self.active_tr.width_pct
            stats["current_tr_age_bars"] = self.active_tr.age_bars

        return stats


# 简单使用示例
if __name__ == "__main__":

    # 创建模拟数据（盘整市）
    np.random.seed(42)
    n_bars = 100

    # 生成盘整价格序列
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="H")

    base_price = 100.0
    tr_width = 5.0  # TR宽度5%

    prices = []
    highs = []
    lows = []
    volumes = []

    for i in range(n_bars):
        # 在TR内随机波动
        if i < 30:
            # 前30根K线形成TR
            price = base_price + np.random.randn() * (tr_width / 3)
        elif i < 70:
            # 中间40根K线在TR内
            price = base_price + (np.random.rand() - 0.5) * tr_width
        # 后30根K线尝试突破
        elif i % 3 == 0:
            price = base_price + tr_width * 1.2  # 向上突破尝试
        else:
            price = base_price + (np.random.rand() - 0.5) * tr_width

        high = price + abs(np.random.randn() * 1.5)
        low = price - abs(np.random.randn() * 1.5)
        volume = 1000 + np.random.rand() * 500

        prices.append(price)
        highs.append(high)
        lows.append(low)
        volumes.append(volume)

    df = pd.DataFrame(
        {
            "open": prices,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": volumes,
        },
        index=dates,
    )

    # 创建TR识别器
    detector = TRDetector(
        {
            "min_tr_width_pct": 2.0,
            "min_tr_bars": 8,
            "stability_lock_bars": 3,
            "breakout_confirmation_bars": 2,
            "breakout_threshold_pct": 1.5,
            "enable_stability_lock": True,
        }
    )

    # 模拟实时检测

    detected_trs = []

    for i in range(20, len(df)):
        current_df = df.iloc[: i + 1]

        # 检测TR
        tr = detector.detect_trading_range(
            current_df, market_regime="RANGING", volatility_index=1.0
        )

        if tr and tr not in detected_trs:
            detected_trs.append(tr)


    # 获取交易信号

    current_price = df["close"].iloc[-1]
    signals = detector.get_tr_signals(current_price)


    if signals["signals"]:
        for signal in signals["signals"]:
            if signal["type"] != "HOLD" and signal["type"] != "WAIT":
                pass
    else:
        pass

    # 获取统计信息
    stats = detector.get_statistics()

