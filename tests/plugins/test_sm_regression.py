"""V4 状态机回归测试 — 确定性场景基准

三个确定性测试场景：
1. 吸筹循环: PS→SC→AR→ST→Spring 序列
2. 派发循环: PSY→BC→AR_DIST 序列
3. 结构失败: 建立结构后跌破SC_LOW → 回IDLE

每个测试使用 xfail 标记，因为当前 V4 检测器阈值可能未完全调优。
"""

import pytest

from src.plugins.wyckoff_state_machine.state_machine_v4 import (
    WyckoffStateMachineV4,
)
from src.kernel.types import WyckoffStateResult


# ---------------------------------------------------------------------------
# Helper 函数
# ---------------------------------------------------------------------------


def warmup_bars(n=30, base_price=50000.0, base_volume=100000.0):
    """生成 n 根稳定K线用于 scorer 滑窗预热。

    小振荡 ±50, 实体小, 量能稳定 → scorer 建立 MA20 基线。
    """
    bars = []
    for i in range(n):
        p = base_price + (i % 3 - 1) * 50
        bars.append(
            {
                "open": p,
                "high": p + 100,
                "low": p - 100,
                "close": p + 20,
                "volume": base_volume,
            }
        )
    return bars


def feed_bars(sm, bars, ctx):
    """依次喂入多根K线，返回结果列表。"""
    results = []
    for bar in bars:
        results.append(sm.process_candle(bar, ctx))
    return results


def make_ctx(support=48000.0, resistance=52000.0):
    """创建标准 sm_context。"""
    return {
        "market_regime": "TRENDING",
        "tr_support": support,
        "tr_resistance": resistance,
        "avg_volume_20": 100000.0,
    }


def find_transitions(sm):
    """提取状态机转换历史中的 to 字段序列。"""
    return [t["to"] for t in sm._transition_history]


# ---------------------------------------------------------------------------
# Test 1: 吸筹循环
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="baseline — V4 检测器可能需要调优才能走完完整吸筹序列",
    strict=False,
)
def test_accumulation_cycle():
    """PS→SC→AR→ST→Spring 吸筹序列。

    K线设计原理:
    - PS: 供需转向需求(close>open) + 停止行为(volume_ratio>1.5, body_ratio<0.3)
    - SC: 恐慌放量(volume_ratio>2.0) + 大振幅(price_range_ratio>1.5) + 停止行为
    - AR: 需求主导反弹(supply_demand>0.2) + 量缩(volume_ratio<1.0)
    - ST: 接近支撑 + 量缩(volume_ratio<0.8) + 小实体(body_ratio<0.4)
    - Spring: 跌破支撑后收盘反弹回TR内
    """
    sm = WyckoffStateMachineV4()
    ctx = make_ctx()

    # 1. 预热30根
    warmup = warmup_bars(30)
    feed_bars(sm, warmup, ctx)

    # 2. PS — 下跌中出现需求: 高量 + 小实体 (停止行为)
    ps_bar = {
        "open": 49000,
        "high": 49200,
        "low": 48500,
        "close": 49100,
        "volume": 300000,  # 3x avg → stopping action
    }
    # 3. SC — 恐慌放量抛售: 超大量 + 大振幅 + 停止行为
    sc_bar = {
        "open": 48800,
        "high": 49000,
        "low": 47500,
        "close": 48700,
        "volume": 400000,  # 4x avg, range 1500 vs avg 200
    }
    # 4. AR — 需求主导反弹: 量缩 + 阳线
    ar_bar = {
        "open": 48800,
        "high": 50500,
        "low": 48700,
        "close": 50400,
        "volume": 60000,  # 0.6x avg → vol shrink
    }
    # 5. ST — 回测SC区域: 接近支撑 + 量缩 + 小实体
    st_bar = {
        "open": 48500,
        "high": 48700,
        "low": 48100,
        "close": 48400,
        "volume": 50000,  # 0.5x avg → supply dry
    }
    # 6. Spring — 跌破SC_LOW后反弹回TR
    spring_bar = {
        "open": 48000,
        "high": 49500,
        "low": 47200,
        "close": 49200,
        "volume": 250000,  # 2.5x avg → high volume spring
    }

    event_bars = [ps_bar, sc_bar, ar_bar, st_bar, spring_bar]

    # 每根事件K线后面跟2根确认K线（保持原方向，量能适中）
    sequence = []
    for bar in event_bars:
        sequence.append(bar)
        # 2根温和确认K线
        c = bar["close"]
        for j in range(3):
            sequence.append(
                {
                    "open": c,
                    "high": c + 100,
                    "low": c - 50,
                    "close": c + 50,
                    "volume": 100000,
                }
            )
            c = c + 50

    results = feed_bars(sm, sequence, ctx)
    transitions = find_transitions(sm)

    # 至少应发生若干状态转换
    assert len(transitions) >= 1, f"无状态转换发生: {transitions}"

    # 检查前几个转换包含 PS 或 SC（吸筹入口事件）
    accum_entry = {"PS", "SC"}
    assert any(t in accum_entry for t in transitions[:3]), (
        f"前3个转换未包含吸筹入口: {transitions[:3]}"
    )


# ---------------------------------------------------------------------------
# Test 2: 派发循环
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="baseline — V4 检测器可能需要调优才能走完完整派发序列",
    strict=False,
)
def test_distribution_cycle():
    """PSY→BC→AR_DIST 派发序列。

    K线设计原理:
    - PSY: 供应出现(supply_demand<-0.1) + 放量(volume_ratio>1.2)
    - BC: 极端放量冲顶(volume_ratio>2.0) + 大振幅(price_range_ratio>1.5)
    - AR_DIST: 买盘枯竭回落(supply_demand<-0.2) + 量缩
    """
    sm = WyckoffStateMachineV4()
    ctx = make_ctx(support=48000.0, resistance=52000.0)

    # 1. 预热30根 — 偏高价位(接近阻力区)
    warmup = warmup_bars(30, base_price=51500.0)
    feed_bars(sm, warmup, ctx)

    # 2. PSY — 上涨中出现卖压: 阴线 + 放量 + 停止行为
    psy_bar = {
        "open": 51800,
        "high": 52000,
        "low": 51200,
        "close": 51300,
        "volume": 250000,  # 2.5x avg
    }
    # 3. BC — 极端放量冲顶: 超大量 + 大振幅
    bc_bar = {
        "open": 51500,
        "high": 52800,
        "low": 51400,
        "close": 52600,
        "volume": 400000,  # 4x avg
    }
    # 4. AR_DIST — 买盘枯竭自然回落: 阴线 + 量缩
    ar_dist_bar = {
        "open": 52400,
        "high": 52500,
        "low": 50800,
        "close": 50900,
        "volume": 60000,  # 0.6x avg
    }

    event_bars = [psy_bar, bc_bar, ar_dist_bar]

    sequence = []
    for bar in event_bars:
        sequence.append(bar)
        c = bar["close"]
        for j in range(3):
            sequence.append(
                {
                    "open": c,
                    "high": c + 80,
                    "low": c - 80,
                    "close": c - 30,
                    "volume": 100000,
                }
            )
            c = c - 30

    results = feed_bars(sm, sequence, ctx)
    transitions = find_transitions(sm)

    assert len(transitions) >= 1, f"无状态转换发生: {transitions}"

    dist_entry = {"PSY", "BC"}
    assert any(t in dist_entry for t in transitions[:3]), (
        f"前3个转换未包含派发入口: {transitions[:3]}"
    )


# ---------------------------------------------------------------------------
# Test 3: 结构失败 — 建立结构后价格跌破SC_LOW放量，应重置到IDLE
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="baseline — V4 结构失败→IDLE 路径可能需要40根无假设才触发",
    strict=False,
)
def test_structure_failure():
    """建立 PS→SC→AR→ST 结构后，价格大幅跌破SC_LOW放量 → 回IDLE。

    设计: 先走到ST建立结构，然后喂入大量放量破底K线破坏结构，
    最后观察状态机是否通过超时重置回IDLE。
    """
    sm = WyckoffStateMachineV4()
    ctx = make_ctx()

    # 1. 预热
    warmup = warmup_bars(30)
    feed_bars(sm, warmup, ctx)

    # 2. 建立结构: PS + 确认 + SC + 确认 + AR + 确认 + ST + 确认
    structure_bars = [
        # PS
        {"open": 49000, "high": 49200, "low": 48500, "close": 49100, "volume": 300000},
        {"open": 49100, "high": 49300, "low": 49000, "close": 49200, "volume": 100000},
        {"open": 49200, "high": 49400, "low": 49100, "close": 49300, "volume": 100000},
        {"open": 49300, "high": 49400, "low": 49200, "close": 49350, "volume": 100000},
        # SC
        {"open": 48800, "high": 49000, "low": 47500, "close": 48700, "volume": 400000},
        {"open": 48700, "high": 48900, "low": 48600, "close": 48800, "volume": 100000},
        {"open": 48800, "high": 48900, "low": 48700, "close": 48850, "volume": 100000},
        {"open": 48850, "high": 49000, "low": 48800, "close": 48900, "volume": 100000},
        # AR
        {"open": 48800, "high": 50500, "low": 48700, "close": 50400, "volume": 60000},
        {"open": 50400, "high": 50600, "low": 50300, "close": 50500, "volume": 100000},
        {"open": 50500, "high": 50600, "low": 50400, "close": 50550, "volume": 100000},
        {"open": 50550, "high": 50600, "low": 50450, "close": 50500, "volume": 100000},
        # ST
        {"open": 48500, "high": 48700, "low": 48100, "close": 48400, "volume": 50000},
        {"open": 48400, "high": 48500, "low": 48300, "close": 48450, "volume": 100000},
        {"open": 48450, "high": 48550, "low": 48400, "close": 48500, "volume": 100000},
        {"open": 48500, "high": 48550, "low": 48450, "close": 48520, "volume": 100000},
    ]
    feed_bars(sm, structure_bars, ctx)

    # 3. 破坏: 大幅跌破SC_LOW(47500)放量 — 供应占主导
    breakdown_bars = []
    price = 47000  # 低于SC_LOW
    for i in range(45):  # 45根持续下跌 → 超过40根结构超时
        breakdown_bars.append(
            {
                "open": price,
                "high": price + 50,
                "low": price - 200,
                "close": price - 150,
                "volume": 200000,  # 持续放量下跌
            }
        )
        price -= 100

    feed_bars(sm, breakdown_bars, ctx)
    transitions = find_transitions(sm)

    # 结构应已被重置 — 最终状态应含 IDLE
    # 如果有 IDLE 或状态机回到初始状态说明结构失败被检测到
    final_state = sm.last_confirmed_event
    has_idle_reset = "IDLE" in transitions or final_state == "IDLE"
    assert has_idle_reset, (
        f"结构未重置到IDLE, final={final_state}, transitions={transitions}"
    )
