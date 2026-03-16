"""
异步向量化进化档案员 (Async Evolution Archivist)
实现实时向量化记忆系统，不阻塞交易主线程

设计原则：
1. 双线程设计：主线程只负责把日志推送到队列（Queue）
2. 后台线程：从队列取出日志 -> 调用Embedding接口 -> 存入本地向量库
3. 异步处理：所有向量化操作在后台进行，不阻塞主线程
4. 简单存储：使用JSONL文本追加，无需重型数据库
5. 智能检索：支持自然语言查询历史进化决策

架构：
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────┐
│  主线程         │    │   异步队列          │    │  后台线程       │
│  (交易决策)     │───▶│   (Queue)          │───▶│  (向量化处理)   │
│                 │    │                     │    │                 │
│  record_log()   │    │                     │    │  _process_queue()│
│                 │    │                     │    │                 │
└─────────────────┘    └─────────────────────┘    └─────────────────┘
                                                            │
                                                            ▼
                                                    ┌─────────────────┐
                                                    │  向量存储       │
                                                    │  (JSONL文件)    │
                                                    │                 │
                                                    └─────────────────┘
"""

import json
import logging
import os
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


class EvolutionEventType(Enum):
    """进化事件类型枚举"""

    WEIGHT_ADJUSTMENT = "weight_adjustment"  # 权重调整
    THRESHOLD_CHANGE = "threshold_change"    # 阈值变化
    PARAMETER_TUNING = "parameter_tuning"    # 参数调优
    ERROR_CORRECTION = "error_correction"    # 错误纠正
    PERFORMANCE_IMPROVEMENT = "performance_improvement"  # 性能改进
    SYSTEM_ADAPTATION = "system_adaptation"  # 系统适应


@dataclass
class EvolutionLog:
    """进化日志数据结构"""

    timestamp: datetime
    event_type: EvolutionEventType
    module: str  # 模块名称，如 "period_weight_filter", "threshold_parameters"
    parameter: str  # 参数名称，如 "RSI_threshold", "confidence_weight"
    old_value: Any
    new_value: Any
    change_percent: float  # 变化百分比
    reason: str  # 调整原因，如 "降低假阳性率", "提高敏感性"
    context: dict[str, Any] = field(default_factory=dict)  # 上下文信息
    performance_impact: Optional[float] = None  # 性能影响评分
    embedding: Optional[list[float]] = None  # 向量嵌入

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["event_type"] = self.event_type.value
        data["embedding"] = self.embedding if self.embedding else []
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvolutionLog":
        """从字典创建"""
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        data["event_type"] = EvolutionEventType(data["event_type"])
        return cls(**data)


class EmbeddingProvider:
    """
    向量嵌入提供者
    支持多种嵌入方式：Mock、OpenAI、Ollama等
    """

    def __init__(self, provider_type: str = "mock", config: Optional[dict] = None):
        """
        初始化嵌入提供者

        Args:
            provider_type: 提供者类型，可选 "mock", "openai", "ollama"
            config: 配置字典
        """
        self.provider_type = provider_type
        self.config = config or {}

        if provider_type == "openai":
            self._init_openai()
        elif provider_type == "ollama":
            self._init_ollama()
        else:
            self._init_mock()

    def _init_mock(self):
        """初始化Mock嵌入提供者（用于测试）"""
        logger.info("使用Mock嵌入提供者")
        self.dimension = 384  # 模拟384维向量

    def _init_openai(self):
        """初始化OpenAI嵌入提供者"""
        try:
            import openai
            api_key = self.config.get("api_key")
            if not api_key:
                logger.warning("未提供OpenAI API密钥，回退到Mock模式")
                self._init_mock()
                self.provider_type = "mock"
                return

            self.client = openai.OpenAI(api_key=api_key)
            self.model = self.config.get("model", "text-embedding-3-small")
            self.dimension = 1536  # OpenAI text-embedding-3-small 维度
            logger.info(f"使用OpenAI嵌入提供者，模型: {self.model}")

        except ImportError:
            logger.warning("未安装openai库，回退到Mock模式")
            self._init_mock()
            self.provider_type = "mock"

    def _init_ollama(self):
        """初始化Ollama嵌入提供者"""
        try:
            import requests
            self.ollama_url = self.config.get("url", "http://localhost:11434")
            self.model = self.config.get("model", "nomic-embed-text")
            self.dimension = 768  # nomic-embed-text 维度

            # 测试连接
            try:
                response = requests.get(f"{self.ollama_url}/api/tags")
                if response.status_code == 200:
                    logger.info(f"使用Ollama嵌入提供者，模型: {self.model}")
                else:
                    logger.warning("Ollama连接失败，回退到Mock模式")
                    self._init_mock()
                    self.provider_type = "mock"
            except Exception as e:
                logger.warning(f"Ollama连接异常: {e}，回退到Mock模式")
                self._init_mock()
                self.provider_type = "mock"

        except ImportError:
            logger.warning("未安装requests库，回退到Mock模式")
            self._init_mock()
            self.provider_type = "mock"

    def get_embedding(self, text: str) -> list[float]:
        """
        获取文本的向量嵌入

        Args:
            text: 输入文本

        Returns:
            向量嵌入列表
        """
        if self.provider_type == "mock":
            return self._get_mock_embedding(text)
        if self.provider_type == "openai":
            return self._get_openai_embedding(text)
        if self.provider_type == "ollama":
            return self._get_ollama_embedding(text)
        return self._get_mock_embedding(text)

    def _get_mock_embedding(self, text: str) -> list[float]:
        """生成Mock向量嵌入"""
        # 简单的哈希函数生成伪随机向量
        import hashlib
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        np.random.seed(seed)
        embedding = np.random.randn(self.dimension).tolist()

        # 归一化
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = (embedding / norm).tolist()

        return embedding

    def _get_openai_embedding(self, text: str) -> list[float]:
        """获取OpenAI向量嵌入"""
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                encoding_format="float"
            )
            return response.data[0].embedding
        except Exception:
            logger.exception("OpenAI嵌入失败，回退到Mock模式")
            return self._get_mock_embedding(text)

    def _get_ollama_embedding(self, text: str) -> list[float]:
        """获取Ollama向量嵌入"""
        try:
            import requests
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                }
            )
            if response.status_code == 200:
                return response.json()["embedding"]
            logger.error(f"Ollama嵌入失败: {response.status_code}")
            return self._get_mock_embedding(text)
        except Exception:
            logger.exception("Ollama嵌入异常，回退到Mock模式")
            return self._get_mock_embedding(text)


class EvolutionArchivist:
    """
    异步向量化进化档案员
    主类，管理整个向量化记忆系统
    """

    def __init__(self, config: Optional[dict] = None):
        """
        初始化进化档案员

        Args:
            config: 配置字典，包含以下参数：
                - storage_path: 存储路径（默认: ./evolution_memory.jsonl）
                - embedding_provider: 嵌入提供者配置
                - max_queue_size: 最大队列大小（默认: 1000）
                - process_interval: 处理间隔（秒，默认: 1.0）
                - similarity_threshold: 相似度阈值（默认: 0.7）
        """
        self.config = config or {}

        # 存储配置
        self.storage_path = self.config.get("storage_path", "./evolution_memory.jsonl")
        self.max_queue_size = self.config.get("max_queue_size", 1000)
        self.process_interval = self.config.get("process_interval", 1.0)
        self.similarity_threshold = self.config.get("similarity_threshold", 0.7)

        # 异步队列
        self.log_queue = queue.Queue(maxsize=self.max_queue_size)

        # 嵌入提供者
        embedding_config = self.config.get("embedding_provider", {})
        provider_type = embedding_config.get("type", "mock")
        self.embedding_provider = EmbeddingProvider(provider_type, embedding_config)

        # 后台线程
        self.processing_thread = None
        self.is_running = False

        # 内存缓存（用于快速检索）
        self.memory_cache: list[EvolutionLog] = []
        self.embedding_cache: list[list[float]] = []

        # 加载现有记忆
        self._load_memory()

        logger.info(f"进化档案员初始化完成，存储路径: {self.storage_path}")
        logger.info(f"嵌入提供者: {self.embedding_provider.provider_type}")
        logger.info(f"已加载记忆数量: {len(self.memory_cache)}")

    def start(self):
        """启动后台处理线程"""
        if self.is_running:
            logger.warning("进化档案员已经在运行")
            return

        self.is_running = True
        self.processing_thread = threading.Thread(
            target=self._process_queue_loop,
            daemon=True,
            name="EvolutionArchivist-Processor"
        )
        self.processing_thread.start()

        logger.info("进化档案员后台线程已启动")

    def stop(self):
        """停止后台处理线程"""
        if not self.is_running:
            logger.warning("进化档案员未在运行")
            return

        self.is_running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=5.0)

        logger.info("进化档案员后台线程已停止")

    def record_log(self, log: EvolutionLog):
        """
        记录进化日志（主线程调用）

        Args:
            log: 进化日志对象

        Returns:
            bool: 是否成功加入队列
        """
        try:
            # 非阻塞方式尝试加入队列
            self.log_queue.put_nowait(log)
            logger.debug(f"进化日志已加入队列: {log.event_type.value} - {log.module}.{log.parameter}")
            return True
        except queue.Full:
            logger.warning(f"进化日志队列已满，丢弃日志: {log.event_type.value}")
            return False
        except Exception:
            logger.exception("记录进化日志失败")
            return False

    def record_simple(
        self,
        event_type: EvolutionEventType,
        module: str,
        parameter: str,
        old_value: Any,
        new_value: Any,
        reason: str,
        context: Optional[dict] = None
    ) -> bool:
        """
        简化版记录方法（主线程调用）

        Args:
            event_type: 事件类型
            module: 模块名称
            parameter: 参数名称
            old_value: 旧值
            new_value: 新值
            reason: 调整原因
            context: 上下文信息

        Returns:
            bool: 是否成功加入队列
        """
        # 计算变化百分比
        try:
            if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
                if old_value != 0:
                    change_percent = abs((new_value - old_value) / old_value * 100)
                else:
                    change_percent = 100.0 if new_value != 0 else 0.0
            else:
                change_percent = 0.0
        except Exception:
            change_percent = 0.0

        # 创建日志对象
        log = EvolutionLog(
            timestamp=datetime.now(),
            event_type=event_type,
            module=module,
            parameter=parameter,
            old_value=old_value,
            new_value=new_value,
            change_percent=change_percent,
            reason=reason,
            context=context or {},
            performance_impact=None,
            embedding=None
        )

        return self.record_log(log)

    def _process_queue_loop(self):
        """后台处理循环"""
        logger.info("开始后台处理循环")

        while self.is_running:
            try:
                # 从队列获取日志（带超时）
                try:
                    log = self.log_queue.get(timeout=self.process_interval)
                except queue.Empty:
                    continue

                # 处理日志
                self._process_log(log)

                # 标记任务完成
                self.log_queue.task_done()

            except Exception:
                logger.exception("处理队列时发生错误")
                time.sleep(1.0)  # 错误后暂停1秒

    def _process_log(self, log: EvolutionLog):
        """处理单个日志（后台线程）"""
        try:
            # 生成向量嵌入
            embedding_text = self._create_embedding_text(log)
            embedding = self.embedding_provider.get_embedding(embedding_text)
            log.embedding = embedding

            # 保存到存储
            self._save_log(log)

            # 更新内存缓存
            self.memory_cache.append(log)
            self.embedding_cache.append(embedding)

            logger.info(f"进化日志已处理: {log.event_type.value} - {log.module}.{log.parameter}")

        except Exception:
            logger.exception("处理进化日志失败")

    def _create_embedding_text(self, log: EvolutionLog) -> str:
        """创建用于向量嵌入的文本"""
        parts = [
            f"事件类型: {log.event_type.value}",
            f"模块: {log.module}",
            f"参数: {log.parameter}",
            f"旧值: {log.old_value}",
            f"新值: {log.new_value}",
            f"变化百分比: {log.change_percent:.2f}%",
            f"原因: {log.reason}",
        ]

        # 添加上下文信息
        if log.context:
            context_str = " ".join([f"{k}:{v}" for k, v in log.context.items()])
            parts.append(f"上下文: {context_str}")

        return " ".join(parts)

    def _save_log(self, log: EvolutionLog):
        """保存日志到存储"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(self.storage_path)), exist_ok=True)

            # 追加到JSONL文件
            with open(self.storage_path, "a", encoding="utf-8") as f:
                json_line = json.dumps(log.to_dict(), ensure_ascii=False)
                f.write(json_line + "\n")

        except Exception:
            logger.exception("保存进化日志失败")

    def _load_memory(self):
        """从存储加载记忆"""
        try:
            if not os.path.exists(self.storage_path):
                logger.info(f"存储文件不存在: {self.storage_path}")
                return

            self.memory_cache = []
            self.embedding_cache = []

            with open(self.storage_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        log = EvolutionLog.from_dict(data)

                        # 只加载有嵌入向量的记录
                        if log.embedding and len(log.embedding) > 0:
                            self.memory_cache.append(log)
                            self.embedding_cache.append(log.embedding)

                    except Exception as e:
                        logger.warning(f"解析记忆行失败: {e}")

            logger.info(f"从存储加载了 {len(self.memory_cache)} 条记忆")

        except Exception:
            logger.exception("加载记忆失败")

    def query_history(self, question: str, limit: int = 5) -> list[tuple[EvolutionLog, float]]:
        """
        查询历史记忆（主线程调用）

        Args:
            question: 查询问题，如 "上次为什么要调高RSI阈值？"
            limit: 返回结果数量限制

        Returns:
            列表，包含(进化日志, 相似度分数)元组
        """
        if not self.memory_cache:
            logger.warning("记忆缓存为空，无法查询")
            return []

        try:
            # 获取查询问题的向量嵌入
            query_embedding = self.embedding_provider.get_embedding(question)

            # 计算相似度
            similarities = []
            for i, memory_embedding in enumerate(self.embedding_cache):
                similarity = self._cosine_similarity(query_embedding, memory_embedding)
                similarities.append((i, similarity))

            # 按相似度排序
            similarities.sort(key=lambda x: x[1], reverse=True)

            # 返回结果
            results = []
            for idx, similarity in similarities[:limit]:
                if similarity >= self.similarity_threshold:
                    results.append((self.memory_cache[idx], similarity))

            logger.info(f"查询 '{question}' 返回 {len(results)} 条相关记录")
            return results

        except Exception:
            logger.exception("查询历史记忆失败")
            return []

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """计算余弦相似度"""
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)

            # 确保向量维度一致
            if len(v1) != len(v2):
                min_len = min(len(v1), len(v2))
                v1 = v1[:min_len]
                v2 = v2[:min_len]

            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot_product / (norm1 * norm2)

        except Exception:
            return 0.0

    def get_statistics(self) -> dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total_memories": len(self.memory_cache),
            "queue_size": self.log_queue.qsize(),
            "is_running": self.is_running,
            "storage_path": self.storage_path,
            "embedding_provider": self.embedding_provider.provider_type,
            "embedding_dimension": self.embedding_provider.dimension,
        }

        # 按事件类型统计
        event_counts = {}
        for log in self.memory_cache:
            event_type = log.event_type.value
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        stats["event_counts"] = event_counts

        return stats

    def clear_memory(self):
        """清空记忆（谨慎使用）"""
        self.memory_cache = []
        self.embedding_cache = []

        try:
            if os.path.exists(self.storage_path):
                os.remove(self.storage_path)
                logger.info(f"已清空记忆存储: {self.storage_path}")
        except Exception:
            logger.exception("清空记忆存储失败")


# 使用示例
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 创建进化档案员
    config = {
        "storage_path": "./test_evolution_memory.jsonl",
        "embedding_provider": {
            "type": "mock"
        }
    }

    archivist = EvolutionArchivist(config)
    archivist.start()

    try:
        # 记录一些进化日志
        archivist.record_simple(
            event_type=EvolutionEventType.THRESHOLD_CHANGE,
            module="threshold_parameters",
            parameter="RSI_threshold",
            old_value=70,
            new_value=75,
            reason="降低假阳性率，提高信号质量",
            context={"market_regime": "trending", "volatility": "high"}
        )

        archivist.record_simple(
            event_type=EvolutionEventType.WEIGHT_ADJUSTMENT,
            module="period_weight_filter",
            parameter="H4_weight",
            old_value=0.18,
            new_value=0.22,
            reason="提高4小时周期权重，增强趋势跟踪能力",
            context={"performance_improvement": 0.15}
        )

        # 等待处理完成
        time.sleep(2.0)

        # 查询历史
        results = archivist.query_history("上次为什么要调高RSI阈值？")

        for log, similarity in results:
            pass

        # 获取统计信息
        stats = archivist.get_statistics()
        for key, value in stats.items():
            if key == "event_counts":
                for event, count in value.items():
                    pass
            else:
                pass

    finally:
        archivist.stop()
