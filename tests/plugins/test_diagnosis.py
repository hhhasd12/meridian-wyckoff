"""诊断顾问测试 — AIResponse + DiagnosisAdvisor"""

from unittest.mock import AsyncMock, patch

import pytest

from src.plugins.annotation.diagnosis import AIResponse, DiagnosisAdvisor


class TestAIResponse:
    """AIResponse 数据类测试"""

    def test_ai_response_dataclass(self) -> None:
        """验证 AIResponse 字段默认值"""
        resp = AIResponse(text="test diagnosis")
        assert resp.text == "test diagnosis"
        assert resp.suggested_params == []
        assert resp.highlighted_bars == []
        assert resp.follow_up_question is None
        assert resp.confidence == 0.0

    def test_ai_response_full_fields(self) -> None:
        """验证 AIResponse 全字段赋值"""
        resp = AIResponse(
            text="分析结果",
            suggested_params=[
                {"detector": "SC", "param": "vol_thr", "from": 1.5, "to": 2.0}
            ],
            highlighted_bars=[10, 15, 20],
            follow_up_question="这个区间是否有 Spring？",
            confidence=0.85,
        )
        assert len(resp.suggested_params) == 1
        assert resp.suggested_params[0]["detector"] == "SC"
        assert resp.highlighted_bars == [10, 15, 20]
        assert resp.follow_up_question is not None
        assert resp.confidence == 0.85


class TestDiagnosisAdvisorInit:
    """DiagnosisAdvisor 初始化测试"""

    def test_default_init(self) -> None:
        """无配置初始化不报错"""
        advisor = DiagnosisAdvisor()
        assert advisor.provider == "openai"
        assert advisor.model == "gpt-4o-mini"
        assert advisor._conversation_history == []

    def test_custom_config(self) -> None:
        """自定义配置"""
        config = {
            "llm": {
                "provider": "ollama",
                "model": "qwen2.5",
                "ollama_url": "http://myhost:11434",
            }
        }
        advisor = DiagnosisAdvisor(config)
        assert advisor.provider == "ollama"
        assert advisor.model == "qwen2.5"
        assert advisor.ollama_url == "http://myhost:11434"


class TestDiagnoseChat:
    """DiagnosisAdvisor.diagnose_chat 测试"""

    def test_diagnose_chat_mock(self) -> None:
        """mock LLM 调用，验证对话流"""
        advisor = DiagnosisAdvisor()
        mock_response = (
            "SC 检测器的 volume_threshold 过低，"
            "导致普通放量也被识别为 SC。\n"
            "建议将阈值从 1.5 提高到 2.0。\n"
            "```json\n"
            '{"param_changes": [{"detector": "SC", '
            '"param": "volume_threshold", "from": 1.5, "to": 2.0}], '
            '"highlighted_bars": [42, 43], "confidence": 0.8}\n'
            "```"
        )

        with patch.object(
            advisor,
            "_diagnose_chat_async",
            new_callable=AsyncMock,
        ) as mock_async:
            mock_async.return_value = advisor._format_response(mock_response)
            result = advisor.diagnose_chat(
                "为什么 bar 42 被检测为 SC？",
                context={"match_report": "SC mismatch at bar 42"},
            )

        assert "volume_threshold" in result.text
        assert len(result.suggested_params) == 1
        assert result.suggested_params[0]["to"] == 2.0
        assert 42 in result.highlighted_bars
        assert result.confidence == 0.8

    def test_conversation_history(self) -> None:
        """多轮对话上下文保持"""
        advisor = DiagnosisAdvisor()

        # 模拟两轮对话
        with patch.object(
            advisor,
            "_diagnose_chat_async",
            new_callable=AsyncMock,
        ) as mock_async:
            mock_async.return_value = AIResponse(text="第一轮回复")
            advisor.diagnose_chat("第一个问题", context={"focus_items": "SC"})

            mock_async.return_value = AIResponse(text="第二轮回复")
            advisor.diagnose_chat("追问")

        # _diagnose_chat_async 被 mock 了不会写历史，
        # 但 mock 调用了两次
        assert mock_async.call_count == 2


class TestFormatResponse:
    """结构化输出解析测试"""

    def test_parse_structured_output(self) -> None:
        """JSON 代码块解析"""
        advisor = DiagnosisAdvisor()
        raw = (
            "分析结果：SC 阈值偏低。\n\n"
            "```json\n"
            '{"param_changes": ['
            '{"detector": "SC_ACC", "param": "threshold", '
            '"from": 0.3, "to": 0.5}], '
            '"highlighted_bars": [10, 11], '
            '"confidence": 0.9}\n'
            "```"
        )
        result = advisor._format_response(raw)
        assert "SC 阈值偏低" in result.text
        assert len(result.suggested_params) == 1
        assert result.suggested_params[0]["detector"] == "SC_ACC"
        assert result.highlighted_bars == [10, 11]
        assert result.confidence == 0.9

    def test_parse_plain_text(self) -> None:
        """纯文本降级（无 JSON 块）"""
        advisor = DiagnosisAdvisor()
        raw = "检测器逻辑有问题，需要修改代码而非调参。"
        result = advisor._format_response(raw)
        assert result.text == raw
        assert result.suggested_params == []
        assert result.highlighted_bars == []
        assert result.confidence == 0.0

    def test_parse_follow_up_question(self) -> None:
        """追问检测"""
        advisor = DiagnosisAdvisor()
        raw = "信息不足。\n这个区间的 ST 是否有放量？"
        result = advisor._format_response(raw)
        assert result.follow_up_question is not None
        assert "ST" in result.follow_up_question

    def test_parse_chinese_question(self) -> None:
        """中文问号追问检测"""
        advisor = DiagnosisAdvisor()
        raw = "需要更多信息。\n你能提供 bar 50-60 的成交量数据吗？"
        result = advisor._format_response(raw)
        assert result.follow_up_question is not None


class TestConversationManagement:
    """对话管理测试"""

    def test_reset_conversation(self) -> None:
        """清空历史"""
        advisor = DiagnosisAdvisor()
        advisor._conversation_history.append({"role": "user", "content": "test"})
        advisor._current_context = {"foo": "bar"}

        advisor.reset_conversation()

        assert advisor._conversation_history == []
        assert advisor._current_context == {}

    def test_get_conversation_history(self) -> None:
        """返回历史副本"""
        advisor = DiagnosisAdvisor()
        advisor._conversation_history.append({"role": "user", "content": "q1"})
        advisor._conversation_history.append({"role": "assistant", "content": "a1"})

        history = advisor.get_conversation_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        # 确认是副本不是引用
        history.clear()
        assert len(advisor._conversation_history) == 2
