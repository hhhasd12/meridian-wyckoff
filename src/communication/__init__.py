"""
通信模块
实现Agent间的消息传递和协调
"""

from .message_bus import MessageBus, InMemoryMessageBus

__all__ = [
    "MessageBus",
    "InMemoryMessageBus",
]
