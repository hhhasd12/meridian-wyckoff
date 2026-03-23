"""共享测试工厂函数 — 状态机检测器测试用

提供 make_candle / make_features / make_context 三个工厂函数，
用于快速构造检测器测试所需的输入数据。
"""

from typing import Any, Dict

from src.plugins.wyckoff_state_machine.principles.bar_features import (
    BarFeatures,
    StructureContext,
)


def make_candle(
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 103.0,
    volume: float = 1000.0,
) -> Dict[str, float]:
    """创建标准K线字典

    Args:
        open_: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量

    Returns:
        K线字典，包含 open/high/low/close/volume
    """
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def make_features(**overrides: Any) -> BarFeatures:
    """创建 BarFeatures 实例，未指定字段使用中性默认值

    默认值说明:
        supply_demand=0.0: 供需中性
        cause_effect=0.0: 无因累积
        effort_result=0.0: 努力结果中性
        volume_ratio=1.0: 成交量等于均值
        price_range_ratio=1.0: 振幅等于均值
        body_ratio=0.5: 实体占全长50%
        is_stopping_action=False: 非停止行为
        spread_vs_volume_divergence=0.0: 无背离

    Args:
        **overrides: 覆盖默认值的关键字参数

    Returns:
        BarFeatures 实例
    """
    defaults = dict(
        supply_demand=0.0,
        cause_effect=0.0,
        effort_result=0.0,
        volume_ratio=1.0,
        price_range_ratio=1.0,
        body_ratio=0.5,
        is_stopping_action=False,
        spread_vs_volume_divergence=0.0,
    )
    defaults.update(overrides)
    return BarFeatures(**defaults)


def make_context(**overrides: Any) -> StructureContext:
    """创建 StructureContext 实例，未指定字段使用中性默认值

    默认值说明:
        current_phase="B": B阶段（震荡区间）
        last_confirmed_event="ST": 最近确认事件为二次测试
        position_in_tr=0.5: 价格在TR中间
        distance_to_support=0.5: 距支撑中等距离
        distance_to_resistance=0.5: 距阻力中等距离
        test_quality=0.5: 测试质量中等
        recovery_speed=0.5: 反弹速度中等
        swing_context="unknown": 摆动上下文未知
        direction_bias=0.0: 方向中性
        boundaries={"SC_LOW": {}, "AR_HIGH": {}}: 空边界

    Args:
        **overrides: 覆盖默认值的关键字参数

    Returns:
        StructureContext 实例
    """
    defaults: Dict[str, Any] = dict(
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


__all__ = ["make_candle", "make_features", "make_context"]
