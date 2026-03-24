"""诊断顾问 — 威科夫状态机差异诊断的对话式 AI

支持两种 LLM 后端（复用 evolution_advisor 配置）：
- OpenAI (GPT-4o-mini): 推荐，API调用
- Ollama (本地): 免费，需要 GPU

核心功能：
1. 多轮对话保持上下文
2. 结构化输出（参数建议 + 高亮K线）
3. 降级处理（LLM 不可用时返回纯文本）
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.plugins.annotation.prompts import (
    DIAGNOSIS_PROMPT,
    FOLLOWUP_PROMPT,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class AIResponse:
    """诊断 AI 的结构化回复

    Attributes:
        text: 诊断文本（Markdown格式）
        suggested_params: 建议修改的参数列表
        highlighted_bars: 建议高亮的bar序号
        follow_up_question: AI的追问（如果有歧义）
        confidence: 诊断置信度 [0, 1]
    """

    text: str
    suggested_params: List[Dict[str, Any]] = field(default_factory=list)
    highlighted_bars: List[int] = field(default_factory=list)
    follow_up_question: Optional[str] = None
    confidence: float = 0.0


class DiagnosisAdvisor:
    """对话式诊断顾问 — 分析用户标注与机器检测的差异

    复用 evolution_advisor 的 LLM 调用模式（httpx + 双后端）。

    Attributes:
        provider: LLM 提供者 ("openai" 或 "ollama")
        model: 模型名称
        api_key: OpenAI API Key
        ollama_url: Ollama 服务地址
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        config = config or {}
        # 从 annotation 配置中读取 LLM 设置，
        # 如果没有则 fallback 到环境变量
        llm_config = config.get("llm", {})
        self.provider: str = llm_config.get("provider", "openai")
        self.model: str = llm_config.get("model", "gpt-4o-mini")
        self.api_key: str = llm_config.get(
            "api_key", os.environ.get("OPENAI_API_KEY", "")
        )
        self.base_url: str = llm_config.get("base_url", "https://api.openai.com/v1")
        self.ollama_url: str = llm_config.get("ollama_url", "http://localhost:11434")

        # 对话历史
        self._conversation_history: List[Dict[str, str]] = []
        self._current_context: Dict[str, Any] = {}

        logger.info(
            "诊断顾问初始化: provider=%s, model=%s",
            self.provider,
            self.model,
        )

    def diagnose_chat(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AIResponse:
        """同步诊断对话入口

        首轮对话使用 DIAGNOSIS_PROMPT 模板注入上下文，
        后续轮次使用 FOLLOWUP_PROMPT 保持对话连贯。

        Args:
            message: 用户消息
            context: 诊断上下文（match_report, bar_features 等）

        Returns:
            结构化的 AI 回复
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有事件循环中，创建新线程跑
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._diagnose_chat_async(message, context),
                    )
                    return future.result(timeout=90)
            else:
                return loop.run_until_complete(
                    self._diagnose_chat_async(message, context)
                )
        except RuntimeError:
            return asyncio.run(self._diagnose_chat_async(message, context))

    async def _diagnose_chat_async(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AIResponse:
        """异步诊断对话核心逻辑"""
        # 首轮对话：构建完整上下文 prompt
        if not self._conversation_history and context:
            self._current_context = context
            user_prompt = DIAGNOSIS_PROMPT.format(
                match_report=context.get("match_report", "无"),
                focus_items=context.get("focus_items", message),
                bar_features=context.get("bar_features", "无"),
                detector_params=context.get("detector_params", "无"),
                knowledge_rules=context.get("knowledge_rules", "无"),
            )
        elif self._conversation_history:
            # 后续轮次：使用追问模板
            previous = self._conversation_history[-1].get("content", "")
            user_prompt = FOLLOWUP_PROMPT.format(
                user_message=message,
                current_focus=self._current_context.get("focus_items", "未指定"),
                previous_analysis=previous[:500],
            )
        else:
            # 无上下文的首轮
            user_prompt = message

        # 添加用户消息到历史
        self._conversation_history.append({"role": "user", "content": user_prompt})

        # 构建完整 messages 列表
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self._conversation_history)

        # 调用 LLM
        raw_text = await self._call_llm(messages)

        # 添加 AI 回复到历史
        self._conversation_history.append({"role": "assistant", "content": raw_text})

        # 解析结构化输出
        return self._format_response(raw_text)

    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """调用 LLM API — 根据 provider 选择后端"""
        if self.provider == "openai":
            return await self._call_openai(messages)
        elif self.provider == "ollama":
            return await self._call_ollama(messages)
        else:
            logger.warning("未知的 LLM 提供者: %s", self.provider)
            return f"[未配置 LLM 提供者: {self.provider}]"

    async def _call_openai(self, messages: List[Dict[str, str]]) -> str:
        """调用 OpenAI 兼容 API"""
        if not self.api_key:
            return "[OpenAI API Key 未配置]"

        try:
            import httpx

            url = f"{self.base_url}/chat/completions"
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": 1500,
                        "temperature": 0.5,
                    },
                )
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0]["message"]["content"].strip()
                return "[OpenAI 返回空响应]"

        except ImportError:
            logger.warning("httpx 未安装，无法调用 OpenAI")
            return "[httpx 未安装]"
        except Exception as e:
            logger.error("OpenAI API 调用失败: %s", e)
            return f"[OpenAI API 错误: {e}]"

    async def _call_ollama(self, messages: List[Dict[str, str]]) -> str:
        """调用 Ollama 本地 API"""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                message = data.get("message", {})
                return message.get("content", "[Ollama 返回空响应]")

        except ImportError:
            logger.warning("httpx 未安装，无法调用 Ollama")
            return "[httpx 未安装]"
        except Exception as e:
            logger.error("Ollama API 调用失败: %s", e)
            return f"[Ollama API 错误: {e}]"

    def _format_response(self, raw_text: str) -> AIResponse:
        """解析 AI 回复中的结构化输出

        尝试从回复中提取 JSON 代码块，解析参数建议和高亮K线。
        如果没有 JSON，纯文本作为 text 返回。
        """
        suggested_params: List[Dict[str, Any]] = []
        highlighted_bars: List[int] = []
        follow_up: Optional[str] = None
        confidence: float = 0.0
        display_text = raw_text

        # 尝试提取 JSON 代码块
        json_pattern = r"```json\s*\n(.*?)\n\s*```"
        match = re.search(json_pattern, raw_text, re.DOTALL)

        if match:
            try:
                parsed = json.loads(match.group(1))
                suggested_params = parsed.get("param_changes", [])
                highlighted_bars = parsed.get("highlighted_bars", [])
                confidence = float(parsed.get("confidence", 0.0))
                # 从显示文本中移除 JSON 块
                display_text = raw_text[: match.start()].strip()
            except (json.JSONDecodeError, ValueError):
                logger.debug("JSON 解析失败，作为纯文本返回")

        # 检测追问（以 ? 或 ？ 结尾的最后一句话）
        lines = display_text.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line and (line.endswith("?") or line.endswith("？")):
                follow_up = line
                break

        return AIResponse(
            text=display_text,
            suggested_params=suggested_params,
            highlighted_bars=highlighted_bars,
            follow_up_question=follow_up,
            confidence=confidence,
        )

    def reset_conversation(self) -> None:
        """清空对话历史，开始新的诊断会话"""
        self._conversation_history.clear()
        self._current_context.clear()
        logger.info("诊断对话已重置")

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """返回当前对话历史"""
        return list(self._conversation_history)
