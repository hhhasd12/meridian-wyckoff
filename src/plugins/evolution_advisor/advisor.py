"""进化顾问 — LLM 分析逻辑

支持两种 LLM 后端：
- OpenAI (GPT-4o-mini): 推荐，每轮 ~$0.003
- Ollama (本地): 免费，需要 GPU

每轮进化后分析：
1. 成功/失败原因
2. MistakeBook 错误模式翻译成人话
3. 检测进化是否卡在局部最优
4. 建议下一轮变异方向
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.plugins.evolution_advisor.prompts import (
    SYSTEM_PROMPT,
    build_cycle_analysis_prompt,
    build_mistake_translation_prompt,
    build_mutation_direction_prompt,
    build_plateau_detection_prompt,
)

logger = logging.getLogger(__name__)


class EvolutionAdvisor:
    """进化顾问 — 调用 LLM 分析进化表现

    Attributes:
        provider: LLM 提供者 ("openai" 或 "ollama")
        model: 模型名称
        api_key: OpenAI API Key
        ollama_url: Ollama 服务地址
        analysis_history: 分析历史记录
    """

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: str = "",
        ollama_url: str = "http://localhost:11434",
        max_history: int = 50,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.ollama_url = ollama_url
        self.max_history = max_history
        self.analysis_history: List[Dict[str, Any]] = []
        self._fitness_history: List[float] = []
        self._config_history: List[Dict[str, Any]] = []

    async def analyze_cycle(
        self,
        cycle_data: Dict[str, Any],
        mistake_patterns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """分析一轮进化结果

        收集当前轮次数据、错题本模式、fitness 历史，
        生成综合分析报告。

        Args:
            cycle_data: 进化轮次数据，包含 generation,
                        best_fitness, best_config 等
            mistake_patterns: MistakeBook 错误模式列表

        Returns:
            分析结果字典，包含 analysis, plateau_warning,
            mutation_advice, timestamp 等字段
        """
        generation = cycle_data.get("generation", 0)
        best_fitness = cycle_data.get("best_fitness", 0.0)
        best_config = cycle_data.get("best_config", {})

        # 更新历史
        self._fitness_history.append(best_fitness)
        self._config_history.append(best_config)

        # 限制历史长度
        if len(self._fitness_history) > self.max_history:
            self._fitness_history = self._fitness_history[-self.max_history :]
        if len(self._config_history) > self.max_history:
            self._config_history = self._config_history[-self.max_history :]

        result: Dict[str, Any] = {
            "generation": generation,
            "best_fitness": best_fitness,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "analysis": "",
            "plateau_warning": None,
            "mistake_summary": None,
            "mutation_advice": None,
        }

        # 1. 轮次分析
        cycle_prompt = build_cycle_analysis_prompt(cycle_data, self.analysis_history)
        cycle_analysis = await self._call_llm(cycle_prompt)
        result["analysis"] = cycle_analysis

        # 2. 错题本翻译（如果有模式数据）
        if mistake_patterns:
            mistake_prompt = build_mistake_translation_prompt(mistake_patterns)
            mistake_analysis = await self._call_llm(mistake_prompt)
            result["mistake_summary"] = mistake_analysis

        # 3. 局部最优检测（至少5轮后开始）
        if len(self._fitness_history) >= 5:
            plateau_prompt = build_plateau_detection_prompt(
                self._fitness_history,
                self._config_history,
            )
            plateau_analysis = await self._call_llm(plateau_prompt)
            result["plateau_warning"] = plateau_analysis

        # 4. 变异方向建议
        if best_config and mistake_patterns:
            mutation_prompt = build_mutation_direction_prompt(
                best_config,
                mistake_patterns,
                best_fitness,
            )
            mutation_advice = await self._call_llm(mutation_prompt)
            result["mutation_advice"] = mutation_advice

        # 保存到历史
        self.analysis_history.append(result)
        if len(self.analysis_history) > self.max_history:
            self.analysis_history = self.analysis_history[-self.max_history :]

        logger.info(
            "进化顾问分析完成: 第%d轮, fitness=%.4f",
            generation,
            best_fitness,
        )

        return result

    async def _call_llm(self, user_prompt: str) -> str:
        """调用 LLM API

        根据 provider 配置选择 OpenAI 或 Ollama 后端。

        Args:
            user_prompt: 用户提示词

        Returns:
            LLM 生成的回复文本
        """
        if self.provider == "openai":
            return await self._call_openai(user_prompt)
        elif self.provider == "ollama":
            return await self._call_ollama(user_prompt)
        else:
            logger.warning(
                "未知的 LLM 提供者: %s, 跳过分析",
                self.provider,
            )
            return f"[未配置 LLM 提供者: {self.provider}]"

    async def _call_openai(self, user_prompt: str) -> str:
        """调用 OpenAI API

        Args:
            user_prompt: 用户提示词

        Returns:
            模型回复文本
        """
        if not self.api_key:
            return "[OpenAI API Key 未配置]"

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": SYSTEM_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": user_prompt,
                            },
                        ],
                        "max_tokens": 500,
                        "temperature": 0.7,
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

    async def _call_ollama(self, user_prompt: str) -> str:
        """调用 Ollama 本地 API

        Args:
            user_prompt: 用户提示词

        Returns:
            模型回复文本
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": SYSTEM_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": user_prompt,
                            },
                        ],
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

    def get_analysis_history(
        self,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取分析历史

        Args:
            limit: 返回的最大记录数

        Returns:
            分析历史列表（最新在后）
        """
        return self.analysis_history[-limit:]

    def get_fitness_trend(self) -> Dict[str, Any]:
        """获取 fitness 趋势摘要

        Returns:
            包含 trend, values, is_plateau 等字段的字典
        """
        if len(self._fitness_history) < 2:
            return {
                "trend": "insufficient_data",
                "values": list(self._fitness_history),
                "is_plateau": False,
            }

        recent = self._fitness_history[-5:]
        if len(recent) >= 3:
            max_val = max(recent)
            min_val = min(recent)
            avg_val = sum(recent) / len(recent)
            variation = (max_val - min_val) / (avg_val + 1e-10)
            is_plateau = variation < 0.02
        else:
            is_plateau = False

        if self._fitness_history[-1] > self._fitness_history[-2]:
            trend = "improving"
        elif self._fitness_history[-1] < self._fitness_history[-2]:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "values": list(self._fitness_history[-10:]),
            "is_plateau": is_plateau,
            "latest": self._fitness_history[-1],
        }
