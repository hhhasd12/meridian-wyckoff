"""
自我修正工作流 (SelfCorrectionWorkflow) 单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from unittest.mock import Mock
from datetime import datetime
from src.core.self_correction_workflow import (
    SelfCorrectionWorkflow,
    CorrectionResult,
    CorrectionStage,
)


class TestCorrectionStage:
    """测试修正阶段枚举"""

    def test_stage_values(self):
        """测试枚举值"""
        assert CorrectionStage.ERROR_ANALYSIS.value == "ERROR_ANALYSIS"
        assert CorrectionStage.MUTATION_GENERATION.value == "MUTATION_GENERATION"
        assert CorrectionStage.WFA_VALIDATION.value == "WFA_VALIDATION"
        assert CorrectionStage.CONFIG_UPDATE.value == "CONFIG_UPDATE"
        assert CorrectionStage.EVALUATION.value == "EVALUATION"

    def test_stage_members(self):
        """测试枚举成员数量"""
        assert len(list(CorrectionStage)) == 5


class TestCorrectionResult:
    """测试修正结果数据类"""

    def test_correction_result_creation(self):
        """测试创建修正结果"""
        result = CorrectionResult(
            stage=CorrectionStage.ERROR_ANALYSIS,
            timestamp=datetime.now(),
            success=True,
            details={"errors_found": 5, "patterns_identified": 2},
            metrics={"accuracy": 0.85},
        )
        assert result.stage == CorrectionStage.ERROR_ANALYSIS
        assert result.success is True
        assert result.details["errors_found"] == 5

    def test_to_dict(self):
        """测试转换为字典"""
        result = CorrectionResult(
            stage=CorrectionStage.MUTATION_GENERATION,
            timestamp=datetime.now(),
            success=True,
            details={"mutations_generated": 10},
            metrics={"diversity": 0.7},
        )
        result_dict = result.to_dict()
        assert result_dict["stage"] == "MUTATION_GENERATION"
        assert result_dict["success"] is True
        assert "timestamp" in result_dict

    def test_with_error_message(self):
        """测试带错误消息的结果"""
        result = CorrectionResult(
            stage=CorrectionStage.WFA_VALIDATION,
            timestamp=datetime.now(),
            success=False,
            details={},
            error_message="Insufficient data for validation",
        )
        assert result.success is False
        assert result.error_message == "Insufficient data for validation"

    def test_with_duration(self):
        """测试带执行时间的结果"""
        result = CorrectionResult(
            stage=CorrectionStage.CONFIG_UPDATE,
            timestamp=datetime.now(),
            success=True,
            details={},
            duration_seconds=2.5,
        )
        assert result.duration_seconds == 2.5


class TestSelfCorrectionWorkflow:
    """测试自我修正工作流"""

    def test_initialization(self):
        """测试初始化"""
        config = {"evolution_enabled": True, "max_mutations": 10}
        workflow = SelfCorrectionWorkflow(config=config)
        assert workflow is not None
        assert hasattr(workflow, "config")

    def test_initialization_with_custom_modules(self):
        """测试自定义模块初始化"""
        config = {"evolution_enabled": True}
        # 创建 mock 模块
        mock_mistake_book = Mock()
        mock_weight_variator = Mock()
        mock_wfa = Mock()

        workflow = SelfCorrectionWorkflow(
            config=config,
            mistake_book=mock_mistake_book,
            weight_variator=mock_weight_variator,
            wfa_backtester=mock_wfa,
        )
        assert workflow is not None

    def test_config_values(self):
        """测试配置值"""
        config = {
            "evolution_enabled": True,
            "max_mutations": 20,
            "min_improvement_threshold": 0.05,
        }
        workflow = SelfCorrectionWorkflow(config=config)
        assert workflow.config["evolution_enabled"] is True
        assert workflow.config["max_mutations"] == 20

    def test_stage_enum_access(self):
        """测试阶段枚举访问"""
        # 验证所有阶段都可以访问
        stages = list(CorrectionStage)
        assert CorrectionStage.ERROR_ANALYSIS in stages
        assert CorrectionStage.MUTATION_GENERATION in stages
        assert CorrectionStage.WFA_VALIDATION in stages
        assert CorrectionStage.CONFIG_UPDATE in stages
        assert CorrectionStage.EVALUATION in stages
