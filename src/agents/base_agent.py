"""
Agent基类模块
定义所有Agent的基础接口和通用功能
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import logging
import asyncio

from .message import AgentMessage, MessageType, Priority


class AgentState(Enum):
    """Agent状态枚举"""
    IDLE = "IDLE"
    WORKING = "WORKING"
    WAITING = "WAITING"
    ERROR = "ERROR"
    SHUTDOWN = "SHUTDOWN"


@dataclass
class AgentCapability:
    """Agent能力描述"""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    output: Dict[str, Any]
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Agent基类 - 所有Agent的基础接口"""

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.config = config or {}
        self.message_bus = message_bus
        self.llm_client = llm_client

        self.state = AgentState.IDLE
        self.capabilities: List[AgentCapability] = []
        self.local_state: Dict[str, Any] = {}
        self.message_history: List[AgentMessage] = []
        self.task_history: List[TaskResult] = []
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._running = False

        self.logger = logging.getLogger(f"agent.{agent_id}")

        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """注册默认消息处理器"""
        self._message_handlers[MessageType.HEARTBEAT] = self._handle_heartbeat
        self._message_handlers[MessageType.SHUTDOWN] = self._handle_shutdown
        self._message_handlers[MessageType.CONTROL] = self._handle_control
        self._message_handlers[MessageType.TASK_STATUS] = self._handle_task_status_default

    def _handle_task_status_default(self, message: AgentMessage) -> AgentMessage:
        """默认的任务状态处理器"""
        return message.create_response({
            "status": "received",
            "agent_id": self.agent_id,
            "state": self.state.value,
        })

    def register_handler(self, message_type: MessageType, handler: Callable) -> None:
        """注册消息处理器"""
        self._message_handlers[message_type] = handler

    def initialize(self) -> bool:
        """初始化Agent"""
        self.logger.info(f"初始化Agent: {self.name} ({self.agent_id})")
        self._setup_capabilities()
        self._running = True
        return True

    def _setup_capabilities(self) -> None:
        """设置Agent能力（子类重写）"""
        pass

    @abstractmethod
    def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        """执行任务（子类必须实现）"""
        pass

    def process_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """处理接收到的消息"""
        self.message_history.append(message)
        self.logger.debug(f"收到消息: {message.message_type.value} from {message.sender}")

        handler = self._message_handlers.get(message.message_type)
        if handler:
            try:
                return handler(message)
            except Exception as e:
                self.logger.error(f"处理消息失败: {e}")
                return message.create_error_response(str(e))
        else:
            self.logger.warning(f"未找到消息处理器: {message.message_type.value}")
            return None

    def _handle_heartbeat(self, message: AgentMessage) -> AgentMessage:
        """处理心跳消息"""
        return message.create_response({
            "state": self.state.value,
            "message_count": len(self.message_history),
            "task_count": len(self.task_history),
        })

    def _handle_shutdown(self, message: AgentMessage) -> AgentMessage:
        """处理关闭消息"""
        self._running = False
        self.state = AgentState.SHUTDOWN
        return message.create_response({"shutdown": True})

    def _handle_control(self, message: AgentMessage) -> AgentMessage:
        """处理控制消息"""
        action = message.content.get("action")
        if action == "pause":
            self.state = AgentState.WAITING
        elif action == "resume":
            self.state = AgentState.IDLE
        elif action == "reset":
            self._reset_state()
        return message.create_response({"action": action, "state": self.state.value})

    def _reset_state(self) -> None:
        """重置Agent状态"""
        self.local_state.clear()
        self.message_history.clear()
        self.task_history.clear()
        self.state = AgentState.IDLE

    def send_message(
        self,
        receiver: str,
        message_type: MessageType,
        content: Dict[str, Any],
        priority: Priority = Priority.NORMAL,
        requires_response: bool = False,
    ) -> Optional[str]:
        """发送消息"""
        if not self.message_bus:
            self.logger.warning("消息总线未配置，无法发送消息")
            return None

        message = AgentMessage(
            sender=self.agent_id,
            receiver=receiver,
            message_type=message_type,
            priority=priority,
            content=content,
            requires_response=requires_response,
        )

        return self.message_bus.send(message)

    def broadcast(self, message_type: MessageType, content: Dict[str, Any]) -> None:
        """广播消息"""
        self.send_message("BROADCAST", message_type, content)

    def update_state(self, new_state: AgentState) -> None:
        """更新Agent状态"""
        old_state = self.state
        self.state = new_state
        self.logger.info(f"状态变更: {old_state.value} -> {new_state.value}")
        self.broadcast(MessageType.TASK_STATUS, {
            "old_state": old_state.value,
            "new_state": new_state.value,
        })

    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "capabilities": [
                {"name": c.name, "description": c.description}
                for c in self.capabilities
            ],
            "message_count": len(self.message_history),
            "task_count": len(self.task_history),
            "success_rate": self._calculate_success_rate(),
        }

    def _calculate_success_rate(self) -> float:
        """计算任务成功率"""
        if not self.task_history:
            return 0.0
        successful = sum(1 for t in self.task_history if t.success)
        return successful / len(self.task_history)

    def add_capability(self, capability: AgentCapability) -> None:
        """添加能力"""
        self.capabilities.append(capability)

    def record_task_result(self, result: TaskResult) -> None:
        """记录任务结果"""
        self.task_history.append(result)
        if len(self.task_history) > 100:
            self.task_history = self.task_history[-100:]

    def shutdown(self) -> None:
        """关闭Agent"""
        self._running = False
        self.state = AgentState.SHUTDOWN
        self.logger.info(f"Agent已关闭: {self.name}")
