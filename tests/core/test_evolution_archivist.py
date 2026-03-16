"""
进化档案员 (EvolutionArchivist) 单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from datetime import datetime
from src.plugins.evolution.archivist import (
    EvolutionArchivist,
    EvolutionLog,
    EvolutionEventType,
    EmbeddingProvider,
)


class TestEvolutionEventType:
    """测试进化事件类型枚举"""

    def test_event_type_values(self):
        """测试枚举值"""
        assert EvolutionEventType.WEIGHT_ADJUSTMENT.value == "weight_adjustment"
        assert EvolutionEventType.THRESHOLD_CHANGE.value == "threshold_change"
        assert EvolutionEventType.PARAMETER_TUNING.value == "parameter_tuning"
        assert EvolutionEventType.ERROR_CORRECTION.value == "error_correction"
        assert (
            EvolutionEventType.PERFORMANCE_IMPROVEMENT.value
            == "performance_improvement"
        )
        assert EvolutionEventType.SYSTEM_ADAPTATION.value == "system_adaptation"

    def test_event_type_members(self):
        """测试枚举成员数量"""
        assert len(list(EvolutionEventType)) == 6


class TestEvolutionLog:
    """测试进化日志数据类"""

    def test_evolution_log_creation(self):
        """测试创建进化日志"""
        log = EvolutionLog(
            timestamp=datetime.now(),
            event_type=EvolutionEventType.WEIGHT_ADJUSTMENT,
            module="period_weight_filter",
            parameter="RSI_threshold",
            old_value=0.7,
            new_value=0.65,
            change_percent=-7.14,
            reason="降低假阳性率",
        )
        assert log.module == "period_weight_filter"
        assert log.parameter == "RSI_threshold"
        assert log.old_value == 0.7
        assert log.new_value == 0.65

    def test_to_dict(self):
        """测试转换为字典"""
        log = EvolutionLog(
            timestamp=datetime.now(),
            event_type=EvolutionEventType.THRESHOLD_CHANGE,
            module="breakout_validator",
            parameter="min_volume",
            old_value=1000,
            new_value=1200,
            change_percent=20.0,
            reason="提高入场门槛",
        )
        result = log.to_dict()
        assert "timestamp" in result
        assert result["event_type"] == "threshold_change"
        assert result["module"] == "breakout_validator"

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "timestamp": "2026-01-20T12:00:00",
            "event_type": "weight_adjustment",
            "module": "test_module",
            "parameter": "test_param",
            "old_value": 0.5,
            "new_value": 0.6,
            "change_percent": 20.0,
            "reason": "test reason",
            "context": {},
            "performance_impact": None,
            "embedding": [],
        }
        log = EvolutionLog.from_dict(data)
        assert log.module == "test_module"
        assert log.event_type == EvolutionEventType.WEIGHT_ADJUSTMENT


class TestEmbeddingProvider:
    """测试嵌入提供者"""

    def test_mock_provider_initialization(self):
        """测试 Mock 提供者初始化"""
        provider = EmbeddingProvider(provider_type="mock")
        assert provider is not None
        assert provider.provider_type == "mock"

    def test_provider_with_config(self):
        """测试带配置的提供者"""
        config = {"dimension": 512, "model": "test-model"}
        provider = EmbeddingProvider(provider_type="mock", config=config)
        assert provider.config.get("dimension") == 512


class TestEvolutionArchivist:
    """测试进化档案员"""

    def test_initialization(self):
        """测试初始化"""
        archivist = EvolutionArchivist()
        assert archivist is not None
        # 验证必要的属性存在
        assert hasattr(archivist, "config") or hasattr(archivist, "_config")

    def test_initialization_with_config(self, tmp_path):
        """测试自定义配置初始化"""
        custom_dir = tmp_path / "evolution_logs"
        config = {
            "log_dir": str(custom_dir),
            "provider_type": "mock",
        }
        archivist = EvolutionArchivist(config=config)
        assert archivist is not None

    def test_record_log_basic(self):
        """测试记录日志基本功能"""
        archivist = EvolutionArchivist()
        assert hasattr(archivist, "record_log") or hasattr(
            archivist, "add_log"
        ) or hasattr(archivist, "log_event")
