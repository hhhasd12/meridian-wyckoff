"""
Agent消息定义模块
定义Agent间通信的消息格式和类型
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import uuid


class MessageType(Enum):
    """消息类型枚举"""
    TASK_ASSIGN = "TASK_ASSIGN"
    TASK_STATUS = "TASK_STATUS"
    TASK_COMPLETE = "TASK_COMPLETE"
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    ERROR = "ERROR"
    COLLABORATE = "COLLABORATE"
    SHARE_INFO = "SHARE_INFO"
    ASK_HELP = "ASK_HELP"
    CONTROL = "CONTROL"
    HEARTBEAT = "HEARTBEAT"
    SHUTDOWN = "SHUTDOWN"
    HUMAN_INPUT = "HUMAN_INPUT"
    HUMAN_CONFIRM = "HUMAN_CONFIRM"
    HUMAN_FEEDBACK = "HUMAN_FEEDBACK"
    DIAGNOSTIC_RESULT = "DIAGNOSTIC_RESULT"
    FIX_PROPOSAL = "FIX_PROPOSAL"
    FIX_APPLIED = "FIX_APPLIED"
    VALIDATION_RESULT = "VALIDATION_RESULT"


class Priority(Enum):
    """消息优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5


@dataclass
class AgentMessage:
    """Agent间通信消息格式"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    sender: str = ""
    receiver: str = ""
    message_type: MessageType = MessageType.REQUEST
    priority: Priority = Priority.NORMAL
    content: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    requires_response: bool = False
    response_deadline: Optional[datetime] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "sender": self.sender,
            "receiver": self.receiver,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "content": self.content,
            "context": self.context,
            "requires_response": self.requires_response,
            "response_deadline": self.response_deadline.isoformat() if self.response_deadline else None,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """从字典创建消息"""
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())[:8]),
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data.get("timestamp"), str) else data.get("timestamp", datetime.now()),
            sender=data.get("sender", ""),
            receiver=data.get("receiver", ""),
            message_type=MessageType(data.get("message_type", "REQUEST")),
            priority=Priority(data.get("priority", 2)),
            content=data.get("content", {}),
            context=data.get("context", {}),
            requires_response=data.get("requires_response", False),
            response_deadline=datetime.fromisoformat(data["response_deadline"]) if data.get("response_deadline") else None,
            correlation_id=data.get("correlation_id"),
        )

    def create_response(self, content: Dict[str, Any], success: bool = True) -> "AgentMessage":
        """创建响应消息"""
        return AgentMessage(
            sender=self.receiver,
            receiver=self.sender,
            message_type=MessageType.RESPONSE,
            priority=self.priority,
            content={"success": success, **content},
            correlation_id=self.message_id,
        )

    def create_error_response(self, error_message: str) -> "AgentMessage":
        """创建错误响应消息"""
        return AgentMessage(
            sender=self.receiver,
            receiver=self.sender,
            message_type=MessageType.ERROR,
            priority=self.priority,
            content={"success": False, "error": error_message},
            correlation_id=self.message_id,
        )
