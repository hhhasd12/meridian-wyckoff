"""
K线物理属性模型（CandlePhysical类）
实现计划书第2.1节的K线物理属性定义模型

设计原则：
1. 非指标化识别：基于K线原始OHLCV数据计算物理属性
2. 数学精确：所有属性计算基于严格的数学定义
3. 类型安全：完整类型提示和输入验证
4. 高性能：属性使用@property装饰器，延迟计算
5. 可扩展：支持自定义属性和计算方法

核心属性：
- 实体（body）：控制力度，|close - open|
- 上影线（upper_shadow）：向上试探力度，high - max(open, close)
- 下影线（lower_shadow）：向下试探力度，min(open, close) - low
- 总影线（total_shadow）：针的极限力度，upper_shadow + lower_shadow
- 实体占比（body_ratio）：实体 / (high - low)
- 影线占比（shadow_ratio）：影线 / (high - low)
- 强度评分（intensity_score）：影线占比 * 成交量系数

使用示例：
    candle = CandlePhysical(open=100, high=110, low=95, close=105, volume=1000)
    print(f"实体: {candle.body:.2f}")
    print(f"上影线: {candle.upper_shadow:.2f}")
    print(f"实体占比: {candle.body_ratio:.2%}")
    print(f"强度评分: {candle.get_intensity_score(volume_moving_avg=800):.2f}")
"""

import warnings
from dataclasses import dataclass
from typing import Any


@dataclass
class CandlePhysical:
    """
    K线物理属性模型

    基于威科夫方法的K线物理属性分析，专注于针（影线）与实体（蜡烛主体）的对比分析。
    所有属性均为计算属性，确保数据一致性和计算效率。

    Attributes:
        open (float): 开盘价
        high (float): 最高价
        low (float): 最低价
        close (float): 收盘价
        volume (float): 成交量
    """

    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self):
        """数据验证"""
        self._validate_data()

    def _validate_data(self):
        """验证K线数据有效性"""
        if not (
            self.low <= self.open <= self.high and self.low <= self.close <= self.high
        ):
            warnings.warn(
                f"K线数据异常: O={self.open}, H={self.high}, L={self.low}, C={self.close}. "
                f"确保 low <= open/close <= high"
            )

        if self.volume < 0:
            raise ValueError(f"成交量不能为负数: {self.volume}")

        if self.high - self.low <= 0:
            raise ValueError(f"价格范围无效: high={self.high}, low={self.low}")

    @property
    def body(self) -> float:
        """
        实体（控制力度）

        定义：|close - open|
        意义：表示多空双方的实际控制范围，实体越大表示趋势力度越强

        Returns:
            float: 实体绝对值
        """
        return abs(self.close - self.open)

    @property
    def body_direction(self) -> int:
        """
        实体方向

        Returns:
            int: 1表示阳线（收盘>开盘），-1表示阴线（收盘<开盘），0表示平盘
        """
        if self.close > self.open:
            return 1
        if self.close < self.open:
            return -1
        return 0

    @property
    def upper_shadow(self) -> float:
        """
        上影线长度

        定义：high - max(open, close)
        意义：表示向上试探的力度，长上影线可能表示上方阻力或抛压

        Returns:
            float: 上影线长度
        """
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        """
        下影线长度

        定义：min(open, close) - low
        意义：表示向下试探的力度，长下影线可能表示下方支撑或买盘

        Returns:
            float: 下影线长度
        """
        return min(self.open, self.close) - self.low

    @property
    def total_shadow(self) -> float:
        """
        总影线长度（针的极限力度）

        定义：upper_shadow + lower_shadow
        意义：表示K线总体试探力度，影线越长表示市场犹豫度越高

        Returns:
            float: 总影线长度
        """
        return self.upper_shadow + self.lower_shadow

    @property
    def total_range(self) -> float:
        """
        K线总范围

        定义：high - low
        意义：K线的整体波动范围

        Returns:
            float: 价格总范围
        """
        return self.high - self.low

    @property
    def body_ratio(self) -> float:
        """
        实体占比

        定义：实体 / (实体+影线) = body / total_range
        意义：表示实体在整根K线中的比例，用于判断趋势力度
              - >0.7: 强实体主导（趋势明显）
              - 0.3-0.7: 平衡状态
              - <0.3: 影线主导（市场犹豫）

        Returns:
            float: 实体占比 [0, 1]，当total_range=0时返回0
        """
        if self.total_range == 0:
            return 0.0
        return self.body / self.total_range

    @property
    def shadow_ratio(self) -> float:
        """
        影线占比

        定义：影线 / (实体+影线) = total_shadow / total_range
        意义：表示影线在整根K线中的比例，用于判断市场犹豫度
              - >0.7: 强影线主导（市场极度犹豫）
              - 0.3-0.7: 平衡状态
              - <0.3: 实体主导（趋势明确）

        Returns:
            float: 影线占比 [0, 1]，当total_range=0时返回0
        """
        if self.total_range == 0:
            return 0.0
        return self.total_shadow / self.total_range

    @property
    def is_doji(self) -> bool:
        """
        是否十字星

        定义：实体占比 < 0.1（实体极小）
        意义：表示市场极度犹豫，多空力量平衡

        Returns:
            bool: 是否为十字星
        """
        return self.body_ratio < 0.1

    @property
    def is_marubozu(self) -> bool:
        """
        是否光头光脚线（Marubozu）

        定义：影线占比 < 0.1（影线极小）
        意义：表示趋势强烈，无反向试探

        Returns:
            bool: 是否为光头光脚线
        """
        return self.shadow_ratio < 0.1

    @property
    def is_hammer(self) -> bool:
        """
        是否锤子线（需结合上下文判断）

        定义：下影线 > 2倍实体 且 上影线很小
        意义：可能表示底部反转信号

        Returns:
            bool: 是否为锤子线形态
        """
        return (
            self.lower_shadow > 2 * self.body
            and self.upper_shadow < 0.1 * self.total_range
        )

    @property
    def is_shooting_star(self) -> bool:
        """
        是否射击之星（需结合上下文判断）

        定义：上影线 > 2倍实体 且 下影线很小
        意义：可能表示顶部反转信号

        Returns:
            bool: 是否为射击之星形态
        """
        return (
            self.upper_shadow > 2 * self.body
            and self.lower_shadow < 0.1 * self.total_range
        )

    def get_intensity_score(self, volume_moving_avg: float) -> float:
        """
        强度评分 = 影线占比 * 成交量系数

        定义：shadow_ratio * min(volume_factor, 3.0)
             其中 volume_factor = volume / volume_moving_avg

        意义：综合考虑影线力度和成交量异常，用于评估K线的市场影响力
              - 高影线占比 + 高成交量 = 强市场事件
              - 低影线占比 + 高成交量 = 趋势确认
              - 高影线占比 + 低成交量 = 假突破可能

        Args:
            volume_moving_avg (float): 成交量移动平均值，用于归一化

        Returns:
            float: 强度评分 [0, 3]，值越高表示K线影响力越大

        Raises:
            ValueError: 如果volume_moving_avg <= 0
        """
        if volume_moving_avg <= 0:
            raise ValueError(f"成交量移动平均值必须为正数: {volume_moving_avg}")

        # 影线重要性加权（根据计划书公式）
        shadow_importance = self.shadow_ratio * 2.0

        # 成交量系数（限制在合理范围）
        volume_factor = self.volume / volume_moving_avg
        volume_factor = min(volume_factor, 3.0)  # 限制最大3倍

        intensity = shadow_importance * volume_factor
        return min(intensity, 3.0)  # 确保不超过3.0

    def get_pin_dominant_score(self) -> float:
        """
        针主导评分

        定义：total_shadow / max(body, 0.001)  # 避免除零
        意义：评估影线相对于实体的优势程度
              - >2.0: 强针主导（长影线）
              - 1.5-2.0: 中等针主导
              - <1.5: 实体主导

        Returns:
            float: 针主导评分
        """
        return self.total_shadow / max(self.body, 0.001)

    def get_body_dominant_score(self) -> float:
        """
        实体主导评分

        定义：body / max(total_shadow, 0.001)  # 避免除零
        意义：评估实体相对于影线的优势程度
              - >2.0: 强实体主导（大实体）
              - 1.5-2.0: 中等实体主导
              - <1.5: 针主导

        Returns:
            float: 实体主导评分
        """
        return self.body / max(self.total_shadow, 0.001)

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典格式

        Returns:
            Dict: 包含所有K线属性的字典
        """
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "body": self.body,
            "body_direction": self.body_direction,
            "upper_shadow": self.upper_shadow,
            "lower_shadow": self.lower_shadow,
            "total_shadow": self.total_shadow,
            "total_range": self.total_range,
            "body_ratio": self.body_ratio,
            "shadow_ratio": self.shadow_ratio,
            "is_doji": self.is_doji,
            "is_marubozu": self.is_marubozu,
            "is_hammer": self.is_hammer,
            "is_shooting_star": self.is_shooting_star,
        }

    def get_summary(self) -> str:
        """
        获取K线摘要文本

        Returns:
            str: 格式化的K线摘要
        """
        direction = (
            "阳线"
            if self.body_direction == 1
            else "阴线"
            if self.body_direction == -1
            else "平盘"
        )

        summary = [
            "K线物理属性摘要:",
            f"  方向: {direction} (O={self.open:.2f}, H={self.high:.2f}, L={self.low:.2f}, C={self.close:.2f})",
            f"  实体: {self.body:.2f} ({self.body_ratio:.1%})",
            f"  影线: 上={self.upper_shadow:.2f}, 下={self.lower_shadow:.2f}, 总={self.total_shadow:.2f} ({self.shadow_ratio:.1%})",
            f"  形态: {'十字星' if self.is_doji else ''}{'光头光脚' if self.is_marubozu else ''}{'锤子线' if self.is_hammer else ''}{'射击之星' if self.is_shooting_star else ''}",
            f"  主导: {'针主导' if self.get_pin_dominant_score() > 1.5 else '实体主导' if self.get_body_dominant_score() > 1.5 else '平衡'}",
        ]

        return "\n".join(summary)


# 工具函数
_REQUIRED_CANDLE_FIELDS = ("open", "high", "low", "close")


def create_candle_from_series(series: dict[str, float]) -> CandlePhysical:
    """
    从数据序列创建CandlePhysical对象

    Args:
        series: 包含'open','high','low','close','volume'键的字典

    Returns:
        CandlePhysical: K线物理属性对象

    Raises:
        KeyError: 如果缺少必要的OHLC字段
    """
    missing = [f for f in _REQUIRED_CANDLE_FIELDS if f not in series]
    if missing:
        raise KeyError(f"K线数据缺少必要字段: {', '.join(missing)}")

    return CandlePhysical(
        open=series["open"],
        high=series["high"],
        low=series["low"],
        close=series["close"],
        volume=series.get("volume", 0),
    )


def create_candle_from_dataframe_row(df_row) -> CandlePhysical:
    """
    从DataFrame行创建CandlePhysical对象

    Args:
        df_row: pandas DataFrame行，需包含'open','high','low','close','volume'列

    Returns:
        CandlePhysical: K线物理属性对象
    """
    return CandlePhysical(
        open=float(df_row["open"]),
        high=float(df_row["high"]),
        low=float(df_row["low"]),
        close=float(df_row["close"]),
        volume=float(df_row.get("volume", 0)),
    )


# 测试代码
if __name__ == "__main__":
    # 测试示例1：正常K线
    candle1 = CandlePhysical(open=100, high=110, low=95, close=105, volume=1000)

    # 测试示例2：十字星
    candle2 = CandlePhysical(open=100, high=101, low=99, close=100, volume=500)

    # 测试示例3：大实体（close必须在low和high之间）
    candle3 = CandlePhysical(open=100, high=108, low=98, close=108, volume=2000)

    # 测试示例4：锤子线
    candle4 = CandlePhysical(open=105, high=106, low=95, close=104, volume=1500)

    # 测试字典转换
    candle_dict = candle1.to_dict()
