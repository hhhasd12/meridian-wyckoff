"""
冲突解决管理器单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from src.plugins.signal_validation.conflict_resolver import (
    ConflictResolutionManager,
    ConflictType,
    ResolutionBias,
)


class TestConflictResolutionManager:
    """测试冲突解决管理器"""

    def test_initialization(self):
        """测试初始化"""
        resolver = ConflictResolutionManager()
        assert resolver is not None
        assert resolver.conflict_threshold == 0.3
        assert resolver.resolution_threshold == 0.1
        assert resolver.max_position_size == 0.5
        assert resolver.require_micro_confirmation is True
        assert len(resolver.resolution_history) == 0

    def test_detect_conflict_no_conflict(self):
        """测试无冲突检测"""
        resolver = ConflictResolutionManager()

        # 一致的多头信号
        timeframe_states = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BULLISH", "confidence": 0.7},
            "H4": {"state": "BULLISH", "confidence": 0.6},
            "H1": {"state": "BULLISH", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.9},
            "M5": {"state": "BULLISH", "confidence": 0.8},
        }

        conflict_type, detail = resolver.detect_conflict(timeframe_states)
        assert conflict_type == ConflictType.NO_CONFLICT
        assert "timeframe_states" in detail

    def test_detect_distribution_accumulation_conflict(self):
        """测试日线派发 vs 4小时吸筹冲突检测"""
        resolver = ConflictResolutionManager()

        # 日线派发，4小时吸筹
        timeframe_states = {
            "W": {"state": "NEUTRAL", "confidence": 0.5},
            "D": {"state": "BEARISH", "confidence": 0.8},  # 日线派发
            "H4": {"state": "BULLISH", "confidence": 0.7},  # 4小时吸筹
            "H1": {"state": "NEUTRAL", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.6},
            "M5": {"state": "BULLISH", "confidence": 0.7},
        }

        conflict_type, detail = resolver.detect_conflict(timeframe_states)
        assert conflict_type == ConflictType.DISTRIBUTION_ACCUMULATION
        assert detail["d1_state"] == "BEARISH"
        assert detail["h4_state"] == "BULLISH"
        assert "confidence_gap" in detail

    def test_detect_trend_correction_conflict(self):
        """测试趋势 vs 回调冲突检测"""
        resolver = ConflictResolutionManager()

        # 周线多头，但小周期空头
        timeframe_states = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BEARISH", "confidence": 0.6},  # 日线回调
            "H4": {"state": "BEARISH", "confidence": 0.7},  # 4小时回调
            "H1": {"state": "NEUTRAL", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.6},
            "M5": {"state": "BULLISH", "confidence": 0.7},
        }

        conflict_type, detail = resolver.detect_conflict(timeframe_states)
        assert conflict_type == ConflictType.TREND_CORRECTION
        assert detail["weekly_state"] == "BULLISH"
        assert len(detail["conflicting_timeframes"]) >= 2

    def test_detect_multi_timeframe_conflict(self):
        """测试多时间框架混合冲突检测"""
        resolver = ConflictResolutionManager()

        # 多头空头混合
        timeframe_states = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BEARISH", "confidence": 0.7},
            "H4": {"state": "BULLISH", "confidence": 0.6},
            "H1": {"state": "BEARISH", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.9},
            "M5": {"state": "BEARISH", "confidence": 0.8},
        }

        conflict_type, detail = resolver.detect_conflict(timeframe_states)
        assert conflict_type == ConflictType.MULTI_TIMEFRAME_CONFLICT
        assert detail["bull_count"] > 0
        assert detail["bear_count"] > 0
        assert detail["total_timeframes"] == 6

    def test_resolve_no_conflict(self):
        """测试无冲突解决"""
        resolver = ConflictResolutionManager()

        timeframe_states = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BULLISH", "confidence": 0.7},
            "H4": {"state": "BULLISH", "confidence": 0.6},
            "H1": {"state": "BULLISH", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.9},
            "M5": {"state": "BULLISH", "confidence": 0.8},
        }

        market_context = {"regime": "TRENDING", "timestamp": "2024-01-20 10:00:00"}

        resolution = resolver.resolve_conflict(timeframe_states, market_context)
        assert resolution["conflict_type"] == "NO_CONFLICT"
        assert resolution["primary_bias"] == ResolutionBias.BULLISH
        assert resolution["confidence"] > 0.5
        assert "NORMAL_TRADING" in resolution["allowed_actions"]

    def test_resolve_distribution_accumulation_conflict_d1_dominant(self):
        """测试日线派发主导的冲突解决"""
        resolver = ConflictResolutionManager()

        timeframe_states = {
            "W": {"state": "NEUTRAL", "confidence": 0.5},
            "D": {"state": "BEARISH", "confidence": 0.8},
            "H4": {"state": "BULLISH", "confidence": 0.3},  # 置信度低
            "H1": {"state": "NEUTRAL", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.6},
            "M5": {"state": "BULLISH", "confidence": 0.7},
        }

        market_context = {
            "regime": "RANGING",
            "timestamp": "2024-01-20 10:00:00",
            "volume_analysis": {"distribution_pattern": True},
            "price_action": {"lower_highs_lower_lows": True},
            "market_position": "HIGH",
        }

        resolution = resolver.resolve_conflict(timeframe_states, market_context)
        assert resolution["conflict_type"] == "DISTRIBUTION_ACCUMULATION"
        assert resolution["primary_bias"] in [
            ResolutionBias.BEARISH,
            ResolutionBias.NEUTRAL,
            ResolutionBias.DEFERRED,
        ]
        assert "confidence" in resolution
        assert "allowed_actions" in resolution

    def test_resolve_distribution_accumulation_conflict_h4_dominant(self):
        """测试4小时吸筹主导的冲突解决"""
        resolver = ConflictResolutionManager()

        timeframe_states = {
            "W": {"state": "NEUTRAL", "confidence": 0.5},
            "D": {"state": "BEARISH", "confidence": 0.4},  # 置信度低
            "H4": {"state": "BULLISH", "confidence": 0.8},
            "H1": {"state": "NEUTRAL", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.9},
            "M5": {"state": "BULLISH", "confidence": 0.8},
        }

        market_context = {
            "regime": "RANGING",
            "timestamp": "2024-01-20 10:00:00",
            "volume_analysis": {"accumulation_pattern": True},
            "price_action": {"higher_lows": True},
            "market_position": "MID",
        }

        resolution = resolver.resolve_conflict(timeframe_states, market_context)
        assert resolution["conflict_type"] == "DISTRIBUTION_ACCUMULATION"
        assert resolution["primary_bias"] in [
            ResolutionBias.BULLISH,
            ResolutionBias.NEUTRAL,
        ]
        assert "confidence" in resolution

    def test_resolve_trend_correction_conflict(self):
        """测试趋势 vs 回调冲突解决"""
        resolver = ConflictResolutionManager()

        timeframe_states = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BEARISH", "confidence": 0.6},
            "H4": {"state": "BEARISH", "confidence": 0.7},
            "H1": {"state": "NEUTRAL", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.6},
            "M5": {"state": "BULLISH", "confidence": 0.7},
        }

        market_context = {
            "regime": "TRENDING",
            "timestamp": "2024-01-20 10:00:00",
            "correction_depth": 0.2,  # 20%回调
            "volume_on_correction": "LOW_VOLUME",
        }

        resolution = resolver.resolve_conflict(timeframe_states, market_context)
        assert resolution["conflict_type"] == "TREND_CORRECTION"
        assert resolution["primary_bias"] in [
            ResolutionBias.BULLISH,
            ResolutionBias.NEUTRAL,
        ]
        assert "correction_depth" in resolution
        assert "volume_on_correction" in resolution

    def test_resolve_multi_timeframe_conflict(self):
        """测试多时间框架混合冲突解决"""
        resolver = ConflictResolutionManager()

        timeframe_states = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BEARISH", "confidence": 0.7},
            "H4": {"state": "BULLISH", "confidence": 0.6},
            "H1": {"state": "BEARISH", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.9},
            "M5": {"state": "BEARISH", "confidence": 0.8},
        }

        market_context = {"regime": "RANGING", "timestamp": "2024-01-20 10:00:00"}

        resolution = resolver.resolve_conflict(timeframe_states, market_context)
        assert resolution["conflict_type"] == "MULTI_TIMEFRAME_CONFLICT"
        assert "weighted_decision" in resolution
        assert "confidence" in resolution
        assert resolution["confidence"] >= 0.0

    def test_resolution_history(self):
        """测试解决历史记录"""
        resolver = ConflictResolutionManager()

        # 执行几次冲突解决
        timeframe_states = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BEARISH", "confidence": 0.7},
            "H4": {"state": "BULLISH", "confidence": 0.6},
            "H1": {"state": "NEUTRAL", "confidence": 0.5},
            "M15": {"state": "BULLISH", "confidence": 0.9},
            "M5": {"state": "BULLISH", "confidence": 0.8},
        }

        market_context = {"regime": "RANGING", "timestamp": "2024-01-20 10:00:00"}

        # 第一次解决
        resolution1 = resolver.resolve_conflict(timeframe_states, market_context)

        # 修改状态，第二次解决
        timeframe_states2 = timeframe_states.copy()
        timeframe_states2["D"]["state"] = "BULLISH"
        resolution2 = resolver.resolve_conflict(timeframe_states2, market_context)

        # 检查历史记录
        history = resolver.get_resolution_history()
        assert len(history) == 2
        assert history[0]["conflict_type"] == resolution1["conflict_type"]
        assert history[1]["conflict_type"] == resolution2["conflict_type"]

    def test_clear_history(self):
        """测试清空历史记录"""
        resolver = ConflictResolutionManager()

        # 添加一些历史记录
        timeframe_states = {
            "W": {"state": "BULLISH", "confidence": 0.8},
            "D": {"state": "BEARISH", "confidence": 0.7},
            "H4": {"state": "BULLISH", "confidence": 0.6},
        }

        market_context = {"regime": "RANGING", "timestamp": "2024-01-20 10:00:00"}
        resolver.resolve_conflict(timeframe_states, market_context)

        assert len(resolver.resolution_history) == 1

        # 清空历史
        resolver.clear_history()
        assert len(resolver.resolution_history) == 0

    def test_custom_config(self):
        """测试自定义配置"""
        custom_config = {
            "conflict_threshold": 0.2,
            "resolution_threshold": 0.05,
            "max_position_size": 0.3,
            "require_micro_confirmation": False,
        }

        resolver = ConflictResolutionManager(custom_config)
        assert resolver.conflict_threshold == 0.2
        assert resolver.resolution_threshold == 0.05
        assert resolver.max_position_size == 0.3
        assert resolver.require_micro_confirmation is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
