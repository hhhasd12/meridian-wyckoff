#!/usr/bin/env python3
"""
CandlePhysical类测试脚本
验证K线物理属性模型的所有功能
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from perception.candle_physical import (
    CandlePhysical,
    create_candle_from_series,
    create_candle_from_dataframe_row,
)


def test_basic_properties():
    """测试基本属性"""
    print("=== 测试1: 基本属性 ===")
    candle = CandlePhysical(open=100, high=110, low=95, close=105, volume=1000)

    # 验证基本属性
    assert candle.open == 100, f"开盘价错误: {candle.open}"
    assert candle.high == 110, f"最高价错误: {candle.high}"
    assert candle.low == 95, f"最低价错误: {candle.low}"
    assert candle.close == 105, f"收盘价错误: {candle.close}"
    assert candle.volume == 1000, f"成交量错误: {candle.volume}"

    # 验证计算属性
    assert candle.body == 5.0, f"实体错误: {candle.body}"
    assert candle.body_direction == 1, f"实体方向错误: {candle.body_direction}"
    assert candle.upper_shadow == 5.0, f"上影线错误: {candle.upper_shadow}"
    assert candle.lower_shadow == 5.0, f"下影线错误: {candle.lower_shadow}"
    assert candle.total_shadow == 10.0, f"总影线错误: {candle.total_shadow}"
    assert candle.total_range == 15.0, f"总范围错误: {candle.total_range}"

    # 验证比例
    assert abs(candle.body_ratio - 0.3333) < 0.001, f"实体占比错误: {candle.body_ratio}"
    assert abs(candle.shadow_ratio - 0.6667) < 0.001, (
        f"影线占比错误: {candle.shadow_ratio}"
    )

    print("[OK] 基本属性测试通过")
    return True


def test_candle_types():
    """测试K线类型识别"""
    print("\n=== 测试2: K线类型识别 ===")

    # 测试十字星
    doji = CandlePhysical(open=100, high=101, low=99, close=100, volume=500)
    assert doji.is_doji, "十字星识别失败"
    print("[OK] 十字星识别通过")

    # 测试光头光脚线
    marubozu = CandlePhysical(open=100, high=105, low=100, close=105, volume=1000)
    assert marubozu.is_marubozu, "光头光脚线识别失败"
    print("[OK] 光头光脚线识别通过")

    # 测试锤子线
    hammer = CandlePhysical(open=105, high=106, low=95, close=104, volume=1500)
    assert hammer.is_hammer, "锤子线识别失败"
    print("[OK] 锤子线识别通过")

    # 测试射击之星
    shooting_star = CandlePhysical(open=104, high=115, low=103, close=105, volume=1200)
    assert shooting_star.is_shooting_star, "射击之星识别失败"
    print("[OK] 射击之星识别通过")

    return True


def test_intensity_score():
    """测试强度评分"""
    print("\n=== 测试3: 强度评分 ===")

    candle = CandlePhysical(open=100, high=110, low=95, close=105, volume=1000)

    # 测试正常情况
    score = candle.get_intensity_score(800)  # 成交量是平均的1.25倍
    expected = 0.6667 * 2.0 * min(1.25, 3.0)  # shadow_ratio * 2.0 * volume_factor
    expected = min(expected, 3.0)

    assert abs(score - expected) < 0.001, f"强度评分错误: {score}, 期望: {expected}"
    print(f"[OK] 强度评分测试通过: {score:.2f}")

    # 测试高成交量情况
    high_volume_candle = CandlePhysical(
        open=100, high=110, low=95, close=105, volume=3000
    )
    score2 = high_volume_candle.get_intensity_score(800)
    assert score2 <= 3.0, f"强度评分超过上限: {score2}"
    print(f"[OK] 高成交量强度评分测试通过: {score2:.2f}")

    return True


def test_dominant_scores():
    """测试主导评分"""
    print("\n=== 测试4: 主导评分 ===")

    # 针主导的K线
    pin_dominant = CandlePhysical(open=100, high=110, low=90, close=101, volume=1000)
    pin_score = pin_dominant.get_pin_dominant_score()
    body_score = pin_dominant.get_body_dominant_score()

    assert pin_score > body_score, "针主导评分错误"
    print(f"[OK] 针主导评分: {pin_score:.2f}, 实体主导评分: {body_score:.2f}")

    # 实体主导的K线
    body_dominant = CandlePhysical(open=100, high=102, low=98, close=108, volume=2000)
    pin_score2 = body_dominant.get_pin_dominant_score()
    body_score2 = body_dominant.get_body_dominant_score()

    assert body_score2 > pin_score2, "实体主导评分错误"
    print(f"[OK] 实体主导评分: {body_score2:.2f}, 针主导评分: {pin_score2:.2f}")

    return True


def test_utility_functions():
    """测试工具函数"""
    print("\n=== 测试5: 工具函数 ===")

    # 测试从字典创建
    series_data = {"open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000}
    candle1 = create_candle_from_series(series_data)
    assert candle1.open == 100, "从字典创建失败"
    print("[OK] 从字典创建测试通过")

    # 测试字典转换
    candle_dict = candle1.to_dict()
    assert "body" in candle_dict, "字典转换缺少body"
    assert "body_ratio" in candle_dict, "字典转换缺少body_ratio"
    assert "shadow_ratio" in candle_dict, "字典转换缺少shadow_ratio"
    print(f"[OK] 字典转换测试通过，包含{len(candle_dict)}个属性")

    # 测试摘要输出
    summary = candle1.get_summary()
    assert "K线物理属性摘要" in summary, "摘要格式错误"
    assert "实体" in summary, "摘要缺少实体信息"
    assert "影线" in summary, "摘要缺少影线信息"
    print("[OK] 摘要输出测试通过")

    return True


def test_error_handling():
    """测试错误处理"""
    print("\n=== 测试6: 错误处理 ===")

    try:
        # 测试无效价格范围
        CandlePhysical(open=100, high=90, low=95, close=105, volume=1000)
        assert False, "应该抛出警告"
    except Exception as e:
        print(f"[OK] 价格范围验证: {type(e).__name__}")

    try:
        # 测试负成交量
        CandlePhysical(open=100, high=110, low=95, close=105, volume=-1000)
        assert False, "应该抛出ValueError"
    except ValueError as e:
        print(f"[OK] 负成交量验证: {e}")

    try:
        # 测试零价格范围
        CandlePhysical(open=100, high=100, low=100, close=100, volume=1000)
        assert False, "应该抛出ValueError"
    except ValueError as e:
        print(f"[OK] 零价格范围验证: {e}")

    return True


def main():
    """主测试函数"""
    print("开始CandlePhysical类测试...")

    tests = [
        test_basic_properties,
        test_candle_types,
        test_intensity_score,
        test_dominant_scores,
        test_utility_functions,
        test_error_handling,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"[FAIL] {test_func.__name__} 失败: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"测试完成: {passed}通过, {failed}失败")

    if failed == 0:
        print("[SUCCESS] 所有测试通过！CandlePhysical类功能完整。")
        return 0
    else:
        print("[ERROR] 有测试失败，请检查代码。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
