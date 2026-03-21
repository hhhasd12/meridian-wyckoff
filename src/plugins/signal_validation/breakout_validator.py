"""
突破验证器（回踩测试逻辑）
解决三根K线伪确认问题：使用"突破+回踩不破"逻辑替代简单横盘计数
防止SFP（摆动失败模式）欺骗
"""

from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class BreakoutStatus(Enum):
    """突破状态枚举"""

    NO_BREAKOUT = "NO_BREAKOUT"  # 无突破
    INITIAL_BREAKOUT = "INITIAL_BREAKOUT"  # 初始突破
    RETEST_IN_PROGRESS = "RETEST_IN_PROGRESS"  # 回踩进行中
    RETEST_SUCCESS = "RETEST_SUCCESS"  # 回踩成功（不破支撑/阻力）
    RETEST_FAILED = "RETEST_FAILED"  # 回踩失败（跌破支撑/突破阻力）
    CONFIRMED = "CONFIRMED"  # 突破确认
    FALSE_BREAKOUT = "FALSE_BREAKOUT"  # 假突破


class BreakoutValidator:
    """
    突破验证器 - 回踩测试逻辑

    功能：
    1. 检测初始突破
    2. 监控回踩过程
    3. 验证回踩不破关键位
    4. 识别假突破（SFP欺骗）
    5. 提供突破确认信号

    核心逻辑：
    - 向上突破：突破阻力 → 回踩不破原阻力（现支撑）→ 确认上涨
    - 向下跌破：跌破支撑 → 回弹不破原支撑（现阻力）→ 确认下跌

    设计原则：
    1. 结构优先：关注价格行为结构而非简单K线数量
    2. 动态阈值：根据波动率调整验证标准
    3. 多时间框架：结合高低时间框架确认
    4. 实时监控：持续跟踪突破进展
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化突破验证器

        Args:
            config: 配置字典，包含以下参数：
                - atr_multiplier: ATR突破倍数（默认1.0）
                - retest_depth_pct: 回踩深度百分比（默认30%）
                - max_retest_bars: 最大回踩K线数（默认20）
                - confirmation_bars: 确认所需K线数（默认3）
                - volume_threshold: 成交量阈值（默认1.2倍平均）
                - support_resistance_zone: 支撑阻力区域宽度（默认0.5%）
                - use_wick_break: 是否使用影线突破（默认False）
        """
        self.config = config or {}
        self.atr_multiplier = self.config.get("atr_multiplier", 1.0)
        self.retest_depth_pct = self.config.get("retest_depth_pct", 30.0)
        self.max_retest_bars = self.config.get("max_retest_bars", 20)
        self.confirmation_bars = self.config.get("confirmation_bars", 3)
        self.volume_threshold = self.config.get("volume_threshold", 1.2)
        self.support_resistance_zone = self.config.get(
            "support_resistance_zone", 0.005
        )  # 0.5%
        self.use_wick_break = self.config.get("use_wick_break", False)

        # 状态跟踪
        self.active_breakouts: dict[str, dict] = {}
        self.breakout_history: list[dict] = []
        self.next_breakout_id = 1

        # 统计信息
        self.stats = {
            "total_breakouts": 0,
            "confirmed_breakouts": 0,
            "false_breakouts": 0,
            "retest_success_rate": 0.0,
        }

    def detect_initial_breakout(
        self,
        df: pd.DataFrame,
        resistance_level: float,
        support_level: float,
        current_atr: float,
    ) -> Optional[dict]:
        """
        检测初始突破

        Args:
            df: 包含OHLCV数据的DataFrame（最近N根K线）
            resistance_level: 阻力位
            support_level: 支撑位
            current_atr: 当前ATR值

        Returns:
            Dict包含突破信息，或None（无突破）
        """
        if len(df) < 5:
            return None

        latest = df.iloc[-1]
        # df.iloc[-2] 已移除（死代码，赋值后未使用）

        # 计算突破阈值（基于ATR）
        breakout_threshold = current_atr * self.atr_multiplier

        # 检查向上突破
        if resistance_level is not None and resistance_level > 0:
            # 确定突破价格（收盘价或最高价）
            break_price = latest["high"] if self.use_wick_break else latest["close"]

            # 检查是否突破阻力
            if break_price > resistance_level:
                # 计算突破强度
                breakout_strength = (
                    break_price - resistance_level
                ) / breakout_threshold

                # 检查成交量确认
                volume_confirmation = self._check_volume_confirmation(df, direction=1)

                if (
                    breakout_strength > 0.5 or volume_confirmation
                ):  # 突破至少0.5倍ATR或有成交量确认
                    return self._create_breakout_record(
                        direction=1,
                        breakout_price=break_price,
                        breakout_level=resistance_level,
                        breakout_strength=breakout_strength,
                        volume_confirmation=volume_confirmation,
                        timestamp=latest.name,
                        atr=current_atr,
                    )

        # 检查向下跌破
        if support_level is not None and support_level > 0:
            # 确定突破价格
            break_price = latest["low"] if self.use_wick_break else latest["close"]

            # 检查是否跌破支撑
            if break_price < support_level:
                # 计算突破强度
                breakout_strength = (support_level - break_price) / breakout_threshold

                # 检查成交量确认
                volume_confirmation = self._check_volume_confirmation(df, direction=-1)

                if breakout_strength > 0.5 or volume_confirmation:
                    return self._create_breakout_record(
                        direction=-1,
                        breakout_price=break_price,
                        breakout_level=support_level,
                        breakout_strength=breakout_strength,
                        volume_confirmation=volume_confirmation,
                        timestamp=latest.name,
                        atr=current_atr,
                    )

        return None

    def _create_breakout_record(
        self,
        direction: int,
        breakout_price: float,
        breakout_level: float,
        breakout_strength: float,
        volume_confirmation: bool,
        timestamp: pd.Timestamp,
        atr: float,
    ) -> dict:
        """创建突破记录"""
        breakout_id = f"breakout_{self.next_breakout_id}"
        self.next_breakout_id += 1

        record = {
            "breakout_id": breakout_id,
            "direction": direction,  # 1: 向上, -1: 向下
            "status": BreakoutStatus.INITIAL_BREAKOUT,
            "breakout_price": breakout_price,
            "breakout_level": breakout_level,
            "breakout_strength": breakout_strength,
            "volume_confirmation": volume_confirmation,
            "atr": atr,
            "timestamp": timestamp,
            "retest_data": {
                "retest_start_time": None,
                "retest_lowest_price": breakout_price
                if direction == 1
                else float("inf"),
                "retest_highest_price": breakout_price if direction == -1 else 0.0,
                "retest_bars_count": 0,
                "retest_depth_pct": 0.0,
                "support_resistance_flipped": breakout_level,  # 原阻力变支撑，或原支撑变阻力
            },
            "confirmation_data": {
                "confirmation_bars_count": 0,
                "confirmation_price": breakout_price,
                "confirmed": False,
            },
            "statistics": {
                "max_retracement": 0.0,
                "retest_success": None,
                "time_to_confirmation": None,
            },
        }

        # 设置回踩目标（原阻力变支撑，或原支撑变阻力）
        if direction == 1:
            # 向上突破：原阻力变支撑
            record["retest_data"]["support_level"] = breakout_level
            record["retest_data"]["resistance_level"] = None
        else:
            # 向下跌破：原支撑变阻力
            record["retest_data"]["support_level"] = None
            record["retest_data"]["resistance_level"] = breakout_level

        self.active_breakouts[breakout_id] = record
        self.stats["total_breakouts"] += 1

        return record

    def _check_volume_confirmation(self, df: pd.DataFrame, direction: int) -> bool:
        """
        检查成交量确认

        Args:
            df: 最近N根K线数据
            direction: 突破方向（1: 向上, -1: 向下）

        Returns:
            是否有成交量确认
        """
        if len(df) < 10:
            return False

        latest_volume = df.iloc[-1]["volume"]
        avg_volume = df["volume"].iloc[-10:-1].mean()

        if avg_volume > 0:
            volume_ratio = latest_volume / avg_volume
            return volume_ratio > self.volume_threshold

        return False

    def update_breakout_status(
        self,
        breakout_id: str,
        current_price: float,
        current_low: float,
        current_high: float,
        current_time: pd.Timestamp,
    ) -> dict:
        """
        更新突破状态（每根新K线调用）

        Args:
            breakout_id: 突破ID
            current_price: 当前收盘价
            current_low: 当前最低价
            current_high: 当前最高价
            current_time: 当前时间

        Returns:
            更新后的突破状态
        """
        if breakout_id not in self.active_breakouts:
            return {"error": "Breakout ID not found"}

        breakout = self.active_breakouts[breakout_id]
        direction = breakout["direction"]

        # 更新回踩数据
        retest_data = breakout["retest_data"]

        if breakout["status"] == BreakoutStatus.INITIAL_BREAKOUT:
            # 初始突破阶段，等待回踩开始
            if direction == 1:
                # 向上突破：价格开始回落
                if current_price < breakout["breakout_price"]:
                    retest_data["retest_start_time"] = current_time
                    retest_data["retest_lowest_price"] = current_low
                    breakout["status"] = BreakoutStatus.RETEST_IN_PROGRESS
            # 向下跌破：价格开始反弹
            elif current_price > breakout["breakout_price"]:
                retest_data["retest_start_time"] = current_time
                retest_data["retest_highest_price"] = current_high
                breakout["status"] = BreakoutStatus.RETEST_IN_PROGRESS

        elif breakout["status"] == BreakoutStatus.RETEST_IN_PROGRESS:
            # 回踩进行中
            retest_data["retest_bars_count"] += 1

            # 更新回踩极值
            if direction == 1:
                retest_data["retest_lowest_price"] = min(
                    retest_data["retest_lowest_price"], current_low
                )

                # 计算回踩深度百分比
                breakout_price = breakout["breakout_price"]
                support_level = retest_data["support_level"]

                if support_level is not None and breakout_price > support_level:
                    retest_depth = (
                        breakout_price - retest_data["retest_lowest_price"]
                    ) / (breakout_price - support_level)
                    retest_data["retest_depth_pct"] = retest_depth * 100

                    # 检查回踩是否成功（不破支撑）
                    if retest_data["retest_lowest_price"] > support_level * (
                        1 - self.support_resistance_zone
                    ):
                        # 回踩不破支撑，开始确认
                        breakout["status"] = BreakoutStatus.RETEST_SUCCESS
                        retest_data["retest_success"] = True
                    elif retest_data["retest_lowest_price"] < support_level * (
                        1 - self.support_resistance_zone
                    ):
                        # 跌破支撑，回踩失败
                        breakout["status"] = BreakoutStatus.RETEST_FAILED
                        retest_data["retest_success"] = False
                        self.stats["false_breakouts"] += 1

                # 检查是否超过最大回踩K线数
                if retest_data["retest_bars_count"] > self.max_retest_bars:
                    breakout["status"] = BreakoutStatus.FALSE_BREAKOUT
                    retest_data["retest_success"] = False
                    self.stats["false_breakouts"] += 1

            else:  # direction == -1
                retest_data["retest_highest_price"] = max(
                    retest_data["retest_highest_price"], current_high
                )

                # 计算回弹深度百分比
                breakout_price = breakout["breakout_price"]
                resistance_level = retest_data["resistance_level"]

                if resistance_level is not None and resistance_level > breakout_price:
                    retest_depth = (
                        retest_data["retest_highest_price"] - breakout_price
                    ) / (resistance_level - breakout_price)
                    retest_data["retest_depth_pct"] = retest_depth * 100

                    # 检查回弹是否成功（不破阻力）
                    if retest_data["retest_highest_price"] < resistance_level * (
                        1 + self.support_resistance_zone
                    ):
                        # 回弹不破阻力，开始确认
                        breakout["status"] = BreakoutStatus.RETEST_SUCCESS
                        retest_data["retest_success"] = True
                    elif retest_data["retest_highest_price"] > resistance_level * (
                        1 + self.support_resistance_zone
                    ):
                        # 突破阻力，回踩失败
                        breakout["status"] = BreakoutStatus.RETEST_FAILED
                        retest_data["retest_success"] = False
                        self.stats["false_breakouts"] += 1

                # 检查是否超过最大回踩K线数
                if retest_data["retest_bars_count"] > self.max_retest_bars:
                    breakout["status"] = BreakoutStatus.FALSE_BREAKOUT
                    retest_data["retest_success"] = False
                    self.stats["false_breakouts"] += 1

        elif breakout["status"] == BreakoutStatus.RETEST_SUCCESS:
            # 回踩成功，等待确认
            confirmation_data = breakout["confirmation_data"]
            confirmation_data["confirmation_bars_count"] += 1

            # 更新确认价格
            if direction == 1:
                # 向上突破：跟踪高点
                confirmation_data["confirmation_price"] = max(
                    confirmation_data["confirmation_price"], current_high
                )
            else:
                # 向下跌破：跟踪低点
                confirmation_data["confirmation_price"] = min(
                    confirmation_data["confirmation_price"], current_low
                )

            # 检查是否达到确认条件
            if confirmation_data["confirmation_bars_count"] >= self.confirmation_bars:
                breakout["status"] = BreakoutStatus.CONFIRMED
                confirmation_data["confirmed"] = True

                # 计算统计信息
                breakout["statistics"]["time_to_confirmation"] = (
                    current_time - breakout["timestamp"]
                ).total_seconds() / 3600  # 转换为小时

                self.stats["confirmed_breakouts"] += 1

                # 移动到历史记录
                self.breakout_history.append(breakout.copy())
                del self.active_breakouts[breakout_id]

        # 更新统计信息
        if retest_data.get("retest_success") is not None:
            successful_retests = sum(
                1
                for b in self.breakout_history
                if b["retest_data"].get("retest_success") is True
            )
            total_retests = sum(
                1
                for b in self.breakout_history
                if b["retest_data"].get("retest_success") is not None
            )

            if total_retests > 0:
                self.stats["retest_success_rate"] = successful_retests / total_retests

        return breakout

    def get_breakout_signal(self, breakout_id: str) -> dict:
        """
        获取突破交易信号

        Args:
            breakout_id: 突破ID

        Returns:
            交易信号字典
        """
        if breakout_id not in self.active_breakouts:
            return {"signal": "NO_SIGNAL", "reason": "Breakout not found"}

        breakout = self.active_breakouts[breakout_id]
        status = breakout["status"]
        direction = breakout["direction"]

        signal_map = {
            BreakoutStatus.INITIAL_BREAKOUT: "WATCH",
            BreakoutStatus.RETEST_IN_PROGRESS: "WAIT",
            BreakoutStatus.RETEST_SUCCESS: "PREPARE",
            BreakoutStatus.RETEST_FAILED: "AVOID",
            BreakoutStatus.CONFIRMED: "ENTER",
            BreakoutStatus.FALSE_BREAKOUT: "AVOID",
        }

        signal = signal_map.get(status, "WAIT")

        if signal == "ENTER":
            # 生成入场信号
            if direction == 1:
                entry_price = breakout["breakout_price"]
                support_level = breakout["retest_data"]["support_level"]
                if support_level is not None:
                    stop_loss = support_level * (1 - self.support_resistance_zone)
                    take_profit = (
                        entry_price + (entry_price - stop_loss) * 2
                    )  # 1:2风险回报比
                else:
                    # 如果没有支撑位，使用保守止损
                    stop_loss = entry_price * 0.98  # 2%止损
                    take_profit = entry_price * 1.04  # 4%止盈
            else:
                entry_price = breakout["breakout_price"]
                resistance_level = breakout["retest_data"]["resistance_level"]
                if resistance_level is not None:
                    stop_loss = resistance_level * (1 + self.support_resistance_zone)
                    take_profit = entry_price - (stop_loss - entry_price) * 2
                else:
                    # 如果没有阻力位，使用保守止损
                    stop_loss = entry_price * 1.02  # 2%止损
                    take_profit = entry_price * 0.96  # 4%止盈

            return {
                "signal": "ENTER",
                "direction": "LONG" if direction == 1 else "SHORT",
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward_ratio": 2.0,
                "confidence": min(
                    breakout["breakout_strength"] * 0.5
                    + breakout["retest_data"]["retest_depth_pct"] / 100,
                    1.0,
                ),
                "breakout_id": breakout_id,
            }

        return {
            "signal": signal,
            "status": status.value,
            "direction": "LONG" if direction == 1 else "SHORT",
            "confidence": breakout.get("breakout_strength", 0.0),
            "breakout_id": breakout_id,
        }

    def cleanup_old_breakouts(self, max_age_hours: int = 24):
        """清理过期的突破记录"""
        current_time = pd.Timestamp.now()
        expired_ids = []

        for breakout_id, breakout in self.active_breakouts.items():
            breakout_time = breakout["timestamp"]
            age_hours = (current_time - breakout_time).total_seconds() / 3600

            if age_hours > max_age_hours:
                # 标记为过期
                if breakout["status"] not in [
                    BreakoutStatus.CONFIRMED,
                    BreakoutStatus.FALSE_BREAKOUT,
                ]:
                    breakout["status"] = BreakoutStatus.FALSE_BREAKOUT
                    self.stats["false_breakouts"] += 1

                # 移动到历史记录
                self.breakout_history.append(breakout.copy())
                expired_ids.append(breakout_id)

        # 删除过期记录
        for breakout_id in expired_ids:
            del self.active_breakouts[breakout_id]

    def get_statistics(self) -> dict:
        """获取统计信息"""
        total_confirmed = self.stats["confirmed_breakouts"]
        total_false = self.stats["false_breakouts"]
        total = total_confirmed + total_false

        success_rate = total_confirmed / total if total > 0 else 0.0

        return {
            **self.stats,
            "success_rate": success_rate,
            "active_breakouts": len(self.active_breakouts),
            "total_history": len(self.breakout_history),
        }


# 简单使用示例
if __name__ == "__main__":
    # 创建模拟数据
    np.random.seed(42)
    n_bars = 100

    # 模拟价格突破阻力位
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="H")

    # 创建价格序列：前80根K线在区间内，后20根突破
    base_price = 100.0
    resistance = 105.0
    support = 95.0

    prices = []
    highs = []
    lows = []
    volumes = []

    for i in range(n_bars):
        if i < 80:
            # 区间内震荡
            price = base_price + np.random.randn() * 3
            price = max(support, min(resistance, price))
        # 突破阶段
        elif i == 80:
            # 初始突破
            price = resistance + 2.0
        elif i < 90:
            # 回踩
            price = resistance - 1.0 + np.random.rand() * 2
        else:
            # 确认上涨
            price = resistance + 3.0 + np.random.randn() * 1.5

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

    # 创建突破验证器
    validator = BreakoutValidator(
        {
            "atr_multiplier": 1.0,
            "retest_depth_pct": 30.0,
            "max_retest_bars": 15,
            "confirmation_bars": 3,
        }
    )

    # 计算ATR（简化）
    atr = 2.0  # 假设ATR为2.0

    # 模拟实时检测

    breakout_record = None

    for i in range(70, n_bars):
        current_df = df.iloc[: i + 1]

        # 检测初始突破
        if breakout_record is None:
            breakout = validator.detect_initial_breakout(
                current_df.tail(20),
                resistance_level=resistance,
                support_level=support,
                current_atr=atr,
            )

            if breakout:
                breakout_record = breakout

        # 更新突破状态
        if breakout_record:
            current_bar = current_df.iloc[-1]

            updated = validator.update_breakout_status(
                breakout_record["breakout_id"],
                current_price=current_bar["close"],
                current_low=current_bar["low"],
                current_high=current_bar["high"],
                current_time=current_bar.name,
            )

            if "status" in updated and updated["status"] != breakout_record["status"]:

                if updated["status"] == BreakoutStatus.CONFIRMED:
                    signal = validator.get_breakout_signal(
                        breakout_record["breakout_id"]
                    )

                breakout_record = updated

    # 打印统计信息
    stats = validator.get_statistics()
