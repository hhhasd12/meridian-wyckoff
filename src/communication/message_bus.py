"""
消息总线模块
实现Agent间的消息传递机制
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import logging
import queue
import threading
from dataclasses import dataclass, field

from ..agents.message import AgentMessage, MessageType, Priority


@dataclass
class MessageRecord:
    """消息记录"""
    message: AgentMessage
    status: str = "pending"
    delivered_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


class MessageBus(ABC):
    """消息总线抽象基类"""

    @abstractmethod
    def register_agent(self, agent_id: str, callback: Callable[[AgentMessage], None]) -> None:
        """注册Agent"""
        pass

    @abstractmethod
    def unregister_agent(self, agent_id: str) -> None:
        """注销Agent"""
        pass

    @abstractmethod
    def send(self, message: AgentMessage) -> str:
        """发送消息"""
        pass

    @abstractmethod
    def broadcast(self, message: AgentMessage) -> None:
        """广播消息"""
        pass

    @abstractmethod
    def get_message_history(self, agent_id: Optional[str] = None) -> List[AgentMessage]:
        """获取消息历史"""
        pass


class InMemoryMessageBus(MessageBus):
    """内存消息总线 - 用于单进程场景"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._agents: Dict[str, Callable[[AgentMessage], None]] = {}
        self._message_queues: Dict[str, queue.Queue] = defaultdict(lambda: queue.Queue(maxsize=100))
        self._message_history: List[MessageRecord] = []
        self._lock = threading.Lock()
        self._running = False
        self._dispatcher_thread: Optional[threading.Thread] = None

        self.logger = logging.getLogger("message_bus")

    def start(self) -> None:
        """启动消息总线"""
        self._running = True
        self._dispatcher_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher_thread.start()
        self.logger.info("消息总线已启动")

    def stop(self) -> None:
        """停止消息总线"""
        self._running = False
        if self._dispatcher_thread:
            self._dispatcher_thread.join(timeout=5)
        self.logger.info("消息总线已停止")

    def register_agent(self, agent_id: str, callback: Callable[[AgentMessage], None]) -> None:
        """注册Agent"""
        with self._lock:
            self._agents[agent_id] = callback
            if agent_id not in self._message_queues:
                self._message_queues[agent_id] = queue.Queue(maxsize=100)
        self.logger.info(f"Agent已注册: {agent_id}")

    def unregister_agent(self, agent_id: str) -> None:
        """注销Agent"""
        with self._lock:
            self._agents.pop(agent_id, None)
            self._message_queues.pop(agent_id, None)
        self.logger.info(f"Agent已注销: {agent_id}")

    def send(self, message: AgentMessage) -> str:
        """发送消息"""
        receiver = message.receiver

        if receiver == "BROADCAST":
            self.broadcast(message)
            return message.message_id

        with self._lock:
            if receiver not in self._agents:
                self.logger.warning(f"目标Agent不存在: {receiver}")
                return ""

            msg_queue = self._message_queues.get(receiver)
            if msg_queue is None:
                return ""

            try:
                msg_queue.put_nowait(message)
                record = MessageRecord(
                    message=message,
                    status="queued",
                    delivered_at=datetime.now()
                )
                self._add_to_history(record)
                self.logger.debug(f"消息已入队: {message.message_id} -> {receiver}")
            except queue.Full:
                self.logger.error(f"消息队列已满: {receiver}")
                return ""

        return message.message_id

    def broadcast(self, message: AgentMessage) -> None:
        """广播消息"""
        with self._lock:
            for agent_id in self._agents:
                if agent_id != message.sender:
                    msg_queue = self._message_queues.get(agent_id)
                    if msg_queue:
                        try:
                            msg_queue.put_nowait(message)
                        except queue.Full:
                            self.logger.warning(f"广播消息队列已满: {agent_id}")

        record = MessageRecord(
            message=message,
            status="broadcast",
            delivered_at=datetime.now()
        )
        self._add_to_history(record)
        self.logger.debug(f"消息已广播: {message.message_id}")

    def _dispatch_loop(self) -> None:
        """消息分发循环"""
        while self._running:
            try:
                for agent_id, msg_queue in list(self._message_queues.items()):
                    try:
                        message = msg_queue.get_nowait()
                        callback = self._agents.get(agent_id)
                        if callback:
                            try:
                                callback(message)
                                self._update_message_status(message.message_id, "processed")
                            except Exception as e:
                                self.logger.error(f"消息处理失败: {agent_id} - {e}")
                                self._update_message_status(message.message_id, "error")
                    except queue.Empty:
                        continue
            except Exception as e:
                self.logger.error(f"分发循环异常: {e}")

            threading.Event().wait(0.01)

    def _add_to_history(self, record: MessageRecord) -> None:
        """添加消息到历史记录"""
        with self._lock:
            self._message_history.append(record)
            if len(self._message_history) > self.max_history:
                self._message_history = self._message_history[-self.max_history:]

    def _update_message_status(self, message_id: str, status: str) -> None:
        """更新消息状态"""
        with self._lock:
            for record in reversed(self._message_history):
                if record.message.message_id == message_id:
                    record.status = status
                    record.processed_at = datetime.now()
                    break

    def get_message_history(self, agent_id: Optional[str] = None) -> List[AgentMessage]:
        """获取消息历史"""
        with self._lock:
            if agent_id:
                return [
                    r.message for r in self._message_history
                    if r.message.sender == agent_id or r.message.receiver == agent_id
                ]
            return [r.message for r in self._message_history]

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            total = len(self._message_history)
            by_type: Dict[str, int] = defaultdict(int)
            by_status: Dict[str, int] = defaultdict(int)

            for record in self._message_history:
                by_type[record.message.message_type.value] += 1
                by_status[record.status] += 1

            return {
                "total_messages": total,
                "registered_agents": list(self._agents.keys()),
                "by_type": dict(by_type),
                "by_status": dict(by_status),
                "queue_sizes": {
                    agent_id: q.qsize()
                    for agent_id, q in self._message_queues.items()
                }
            }
