"""修改建议管理 (SuggestionManager) 测试

覆盖:
- 从 AI 输出创建建议
- ParamChange 数据类字段验证
- JSONL 持久化（保存+加载）
- 应用参数修改到 mock registry
- 拒绝建议
- 获取待处理建议筛选
- 格式化人类可读报告
"""

import json
import os
import tempfile

import pytest

from src.plugins.annotation.suggestion import (
    LogicChange,
    ParamChange,
    Suggestion,
    SuggestionManager,
)


@pytest.fixture
def tmp_dir():
    """临时数据目录"""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_ai_output():
    """模拟 AI 诊断输出"""
    return {
        "diagnosis": "SC检测器volume_threshold过高，导致漏检弱成交量SC事件",
        "evidence": "标注SC共5次，检测器仅命中2次，3次漏检均为volume_ratio<1.5",
        "confidence": 0.85,
        "param_changes": [
            {
                "detector": "SC",
                "param": "volume_threshold",
                "from": 2.0,
                "to": 1.5,
                "reason": "降低阈值以捕获弱SC事件",
            },
            {
                "detector": "SC",
                "param": "price_drop_pct",
                "current_value": 0.03,
                "suggested_value": 0.025,
                "reason": "放宽价格下跌幅度要求",
            },
        ],
        "logic_changes": [
            {
                "detector": "SC",
                "description": "增加针体比例作为辅助判断条件",
                "file": "src/plugins/wyckoff_state_machine/detectors/accumulation.py",
                "method": "evaluate",
                "priority": "high",
            }
        ],
    }


class TestParamChangeDataclass:
    """参数修改数据类测试"""

    def test_basic_fields(self):
        pc = ParamChange(
            detector="SC",
            param="volume_threshold",
            current_value=2.0,
            suggested_value=1.5,
            reason="降低阈值",
        )
        assert pc.detector == "SC"
        assert pc.param == "volume_threshold"
        assert pc.current_value == 2.0
        assert pc.suggested_value == 1.5
        assert pc.reason == "降低阈值"

    def test_default_reason(self):
        pc = ParamChange(
            detector="AR",
            param="min_bounce",
            current_value=0.5,
            suggested_value=0.4,
        )
        assert pc.reason == ""


class TestLogicChangeDataclass:
    """逻辑修改数据类测试"""

    def test_basic_fields(self):
        lc = LogicChange(
            detector="SC",
            description="增加针体判断",
            file="accumulation.py",
            method="evaluate",
            priority="high",
        )
        assert lc.detector == "SC"
        assert lc.priority == "high"

    def test_defaults(self):
        lc = LogicChange(detector="AR", description="test")
        assert lc.file == ""
        assert lc.method == ""
        assert lc.priority == "medium"


class TestCreateFromAiResponse:
    """从 AI 输出创建建议"""

    def test_creates_suggestion_with_correct_fields(self, tmp_dir, sample_ai_output):
        mgr = SuggestionManager(data_dir=tmp_dir)
        s = mgr.create_from_ai_response(sample_ai_output)

        assert s.id  # UUID 非空
        assert s.diagnosis == sample_ai_output["diagnosis"]
        assert s.evidence == sample_ai_output["evidence"]
        assert s.confidence == 0.85
        assert s.status == "pending"
        assert s.created_at  # 非空时间戳

    def test_param_changes_parsed(self, tmp_dir, sample_ai_output):
        mgr = SuggestionManager(data_dir=tmp_dir)
        s = mgr.create_from_ai_response(sample_ai_output)

        assert len(s.param_changes) == 2
        # 第一个用 from/to 格式
        pc0 = s.param_changes[0]
        assert pc0.detector == "SC"
        assert pc0.param == "volume_threshold"
        assert pc0.current_value == 2.0
        assert pc0.suggested_value == 1.5
        # 第二个用 current_value/suggested_value 格式
        pc1 = s.param_changes[1]
        assert pc1.current_value == 0.03
        assert pc1.suggested_value == 0.025

    def test_logic_changes_parsed(self, tmp_dir, sample_ai_output):
        mgr = SuggestionManager(data_dir=tmp_dir)
        s = mgr.create_from_ai_response(sample_ai_output)

        assert len(s.logic_changes) == 1
        lc = s.logic_changes[0]
        assert lc.detector == "SC"
        assert lc.priority == "high"
        assert "accumulation.py" in lc.file

    def test_empty_ai_output(self, tmp_dir):
        """空 AI 输出也能安全创建"""
        mgr = SuggestionManager(data_dir=tmp_dir)
        s = mgr.create_from_ai_response({})
        assert s.diagnosis == ""
        assert s.confidence == 0.0
        assert len(s.param_changes) == 0
        assert len(s.logic_changes) == 0


class TestSuggestionPersistence:
    """JSONL 持久化测试"""

    def test_save_and_reload(self, tmp_dir, sample_ai_output):
        """保存建议后重新加载应完整恢复"""
        mgr1 = SuggestionManager(data_dir=tmp_dir)
        s = mgr1.create_from_ai_response(sample_ai_output)
        original_id = s.id

        # 创建新实例，从文件加载
        mgr2 = SuggestionManager(data_dir=tmp_dir)
        all_suggestions = mgr2.get_all_suggestions()

        assert len(all_suggestions) == 1
        loaded = all_suggestions[0]
        assert loaded["id"] == original_id
        assert loaded["diagnosis"] == sample_ai_output["diagnosis"]
        assert len(loaded["param_changes"]) == 2
        assert len(loaded["logic_changes"]) == 1

    def test_multiple_suggestions_persist(self, tmp_dir):
        """多个建议均能正确持久化"""
        mgr = SuggestionManager(data_dir=tmp_dir)
        mgr.create_from_ai_response({"diagnosis": "issue 1", "confidence": 0.5})
        mgr.create_from_ai_response({"diagnosis": "issue 2", "confidence": 0.7})

        mgr2 = SuggestionManager(data_dir=tmp_dir)
        assert len(mgr2.get_all_suggestions()) == 2

    def test_jsonl_file_format(self, tmp_dir, sample_ai_output):
        """验证 JSONL 文件格式正确"""
        mgr = SuggestionManager(data_dir=tmp_dir)
        mgr.create_from_ai_response(sample_ai_output)

        path = os.path.join(tmp_dir, "suggestions.jsonl")
        assert os.path.exists(path)

        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert "id" in data
        assert "param_changes" in data


class TestApplyParamChanges:
    """应用参数修改测试"""

    def test_apply_to_mock_registry(self, tmp_dir, sample_ai_output):
        """mock registry 验证参数应用"""

        class MockDetector:
            def __init__(self):
                self._params = {"volume_threshold": 2.0, "price_drop_pct": 0.03}

            def set_params(self, params):
                for k, v in params.items():
                    if k in self._params:
                        self._params[k] = v

        class MockRegistry:
            def __init__(self):
                self._detectors = {"SC": MockDetector()}

            def get(self, name):
                return self._detectors.get(name)

        mgr = SuggestionManager(data_dir=tmp_dir)
        s = mgr.create_from_ai_response(sample_ai_output)
        registry = MockRegistry()

        result = mgr.apply_param_changes(s.id, registry)

        assert result["applied"] == 2
        assert result["skipped"] == 0
        assert len(result["errors"]) == 0

        # 验证参数确实被修改
        det = registry.get("SC")
        assert det._params["volume_threshold"] == 1.5
        assert det._params["price_drop_pct"] == 0.025

        # 验证状态变更
        loaded = mgr.get_suggestion(s.id)
        assert loaded is not None
        assert loaded.status == "applied"
        assert loaded.applied_at is not None

    def test_apply_missing_detector(self, tmp_dir):
        """目标检测器不存在时跳过"""

        class MockRegistry:
            def get(self, name):
                return None

        mgr = SuggestionManager(data_dir=tmp_dir)
        s = mgr.create_from_ai_response(
            {
                "param_changes": [
                    {"detector": "NONEXISTENT", "param": "x", "from": 1, "to": 2}
                ]
            }
        )

        result = mgr.apply_param_changes(s.id, MockRegistry())
        assert result["applied"] == 0
        assert result["skipped"] == 1
        assert "NONEXISTENT" in result["errors"][0]

    def test_apply_not_found(self, tmp_dir):
        """建议 ID 不存在"""
        mgr = SuggestionManager(data_dir=tmp_dir)
        result = mgr.apply_param_changes("nonexistent-id", None)
        assert "error" in result


class TestRejectSuggestion:
    """拒绝建议测试"""

    def test_reject_changes_status(self, tmp_dir, sample_ai_output):
        mgr = SuggestionManager(data_dir=tmp_dir)
        s = mgr.create_from_ai_response(sample_ai_output)

        result = mgr.reject_suggestion(s.id)
        assert result is True

        loaded = mgr.get_suggestion(s.id)
        assert loaded is not None
        assert loaded.status == "rejected"

    def test_reject_nonexistent(self, tmp_dir):
        mgr = SuggestionManager(data_dir=tmp_dir)
        result = mgr.reject_suggestion("does-not-exist")
        assert result is False


class TestGetPending:
    """获取待处理建议测试"""

    def test_filter_by_status(self, tmp_dir):
        mgr = SuggestionManager(data_dir=tmp_dir)
        s1 = mgr.create_from_ai_response({"diagnosis": "issue 1"})
        mgr.create_from_ai_response({"diagnosis": "issue 2"})
        mgr.reject_suggestion(s1.id)

        pending = mgr.get_pending_suggestions()
        assert len(pending) == 1
        assert pending[0]["diagnosis"] == "issue 2"

        all_suggestions = mgr.get_all_suggestions()
        assert len(all_suggestions) == 2


class TestFormatReport:
    """格式化报告测试"""

    def test_report_contains_key_info(self, tmp_dir, sample_ai_output):
        mgr = SuggestionManager(data_dir=tmp_dir)
        s = mgr.create_from_ai_response(sample_ai_output)
        report = mgr.format_report(s.id)

        assert "修改建议" in report
        assert "volume_threshold" in report
        assert "2.0" in report
        assert "1.5" in report
        assert "参数修改" in report
        assert "逻辑修改" in report
        assert "85.0%" in report

    def test_report_not_found(self, tmp_dir):
        mgr = SuggestionManager(data_dir=tmp_dir)
        report = mgr.format_report("nonexistent")
        assert "not found" in report
