"""
自我修正工作流 (SelfCorrectionWorkflow) 单元测试

测试 GeneticAlgorithm + WFAValidator + StandardEvaluator 集成
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from src.plugins.self_correction.workflow import (
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

    def _make_config(self, **overrides):
        """创建标准测试配置"""
        config = {
            "initial_config": {
                "period_weight_filter": {
                    "weights": {
                        "W": 0.25,
                        "D": 0.20,
                        "H4": 0.18,
                        "H1": 0.15,
                        "M15": 0.12,
                        "M5": 0.10,
                    },
                },
                "threshold_parameters": {
                    "confidence_threshold": 0.7,
                    "volume_threshold": 1.5,
                },
            },
            "min_errors_for_correction": 5,
            "ga_generations": 2,
            "ga_config": {
                "population_size": 6,
                "max_generations": 3,
            },
            "cycle_interval_hours": 1,
            "mistake_book_config": {
                "max_records": 100,
                "auto_cleanup_days": 7,
            },
        }
        config.update(overrides)
        return config

    def test_initialization(self):
        """测试初始化"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)
        assert workflow is not None
        assert hasattr(workflow, "config")
        assert hasattr(workflow, "genetic_algorithm")
        assert hasattr(workflow, "wfa_validator")
        assert hasattr(workflow, "evaluator")

    def test_initialization_with_custom_modules(self):
        """测试自定义模块初始化"""
        config = self._make_config()
        mock_mistake_book = Mock()
        mock_ga = Mock()
        mock_wfa = Mock()
        mock_evaluator = Mock()

        workflow = SelfCorrectionWorkflow(
            config=config,
            mistake_book=mock_mistake_book,
            genetic_algorithm=mock_ga,
            wfa_validator=mock_wfa,
            evaluator=mock_evaluator,
        )
        assert workflow is not None
        assert workflow.mistake_book is mock_mistake_book
        assert workflow.genetic_algorithm is mock_ga
        assert workflow.wfa_validator is mock_wfa
        assert workflow.evaluator is mock_evaluator

    def test_config_values(self):
        """测试配置值"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)
        assert workflow.config["min_errors_for_correction"] == 5
        assert workflow.ga_generations == 2

    def test_baseline_config_is_deep_copy(self):
        """测试 baseline_config 是深拷贝"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)
        # 修改 current_config 不应影响 baseline
        workflow.current_config["new_key"] = "test"
        assert "new_key" not in workflow.baseline_config

    def test_set_historical_data_dict(self):
        """测试设置多TF历史数据"""
        import pandas as pd

        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)

        data = {"H4": pd.DataFrame({"close": [1, 2, 3]})}
        workflow.set_historical_data(data)
        assert workflow.historical_data is not None
        assert "H4" in workflow.historical_data

    def test_set_historical_data_single_df(self):
        """测试设置单个DataFrame（向后兼容）"""
        import pandas as pd

        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)

        df = pd.DataFrame({"close": [1, 2, 3]})
        workflow.set_historical_data(df)
        assert workflow.historical_data is not None
        assert "H4" in workflow.historical_data

    def test_get_workflow_status(self):
        """测试获取工作流状态"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)
        status = workflow.get_workflow_status()

        assert "is_running" in status
        assert "current_stage" in status
        assert "current_config" in status
        assert status["is_running"] is False
        assert status["current_stage"] == "ERROR_ANALYSIS"

    def test_reset_workflow(self):
        """测试重置工作流"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)

        # 修改一些状态
        workflow.current_config["new_key"] = "test"
        workflow.is_running = True

        # 重置
        workflow.reset_workflow()

        assert workflow.is_running is False
        assert "new_key" not in workflow.current_config
        assert workflow.current_stage == CorrectionStage.ERROR_ANALYSIS

    def test_stage_enum_access(self):
        """测试阶段枚举访问"""
        stages = list(CorrectionStage)
        assert CorrectionStage.ERROR_ANALYSIS in stages
        assert CorrectionStage.MUTATION_GENERATION in stages
        assert CorrectionStage.WFA_VALIDATION in stages
        assert CorrectionStage.CONFIG_UPDATE in stages
        assert CorrectionStage.EVALUATION in stages

    def test_run_error_analysis_insufficient_errors(self):
        """测试错误不足时的分析阶段"""
        config = self._make_config(min_errors_for_correction=100)
        mock_mb = Mock()
        mock_mb.get_statistics.return_value = {"total_errors": 3}

        workflow = SelfCorrectionWorkflow(
            config=config,
            mistake_book=mock_mb,
        )

        result = workflow._run_error_analysis()
        assert result.success is True
        assert result.details["mode"] == "random_mutation"
        assert result.details["total_errors"] == 3

    def test_generate_mutations_no_ga(self):
        """测试 GA 不可用时的变异生成"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)
        workflow.genetic_algorithm = None

        result = workflow._generate_mutations({"weight_adjustments": []})
        assert result.success is False
        assert result.error_message is not None

    def test_generate_mutations_no_data(self):
        """测试无历史数据时的变异生成"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)
        workflow.historical_data = None

        result = workflow._generate_mutations({"weight_adjustments": []})
        assert result.success is False

    def test_validate_mutations_no_wfa(self):
        """测试 WFA 不可用时的验证"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)
        workflow.wfa_validator = None

        result = workflow._validate_mutations({"mutation_details": []})
        assert result.success is False
        assert result.error_message is not None

    def test_validate_mutations_no_candidates(self):
        """测试无候选配置时的验证（需要设置历史数据）"""
        import pandas as pd

        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)

        # 设置历史数据，否则会因缺少数据而报错
        workflow.historical_data = {"H4": pd.DataFrame({"close": range(100)})}

        result = workflow._validate_mutations({"mutation_details": []})
        assert result.success is True
        assert result.details["has_best_config"] is False

    def test_summarize_config(self):
        """测试配置摘要生成"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)

        test_config = {
            "period_weight_filter": {"weights": {"H4": 0.5}},
            "threshold_parameters": {"confidence_threshold": 0.7},
            "score": 0.85,
            "nested_dict": {"a": 1, "b": 2, "c": 3, "d": 4},
        }

        summary = workflow._summarize_config(test_config)
        assert "period_weight_filter" in summary
        assert "threshold_parameters" in summary
        assert summary["score"] == 0.85
        assert summary["nested_dict"]["type"] == "dict"

    def test_compare_configs(self):
        """测试配置比较"""
        config = self._make_config()
        workflow = SelfCorrectionWorkflow(config=config)

        old = {"a": 1.0, "b": 2.0}
        new = {"a": 1.5, "b": 2.0, "c": 3.0}

        changes = workflow._compare_configs(old, new)
        assert "a" in changes
        assert changes["a"]["old"] == 1.0
        assert changes["a"]["new"] == 1.5
        assert "c" in changes
        assert "b" not in changes  # 没变化

    def test_correction_result_to_dict_complete(self):
        """测试 CorrectionResult.to_dict 完整性"""
        result = CorrectionResult(
            stage=CorrectionStage.EVALUATION,
            timestamp=datetime(2026, 1, 1),
            success=True,
            details={"key": "value"},
            metrics={"score": 0.9},
            error_message=None,
            duration_seconds=1.5,
        )
        d = result.to_dict()
        assert d["stage"] == "EVALUATION"
        assert d["success"] is True
        assert d["details"] == {"key": "value"}
        assert d["metrics"] == {"score": 0.9}
        assert d["error_message"] is None
        assert d["duration_seconds"] == 1.5
