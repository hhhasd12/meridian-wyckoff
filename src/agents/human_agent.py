"""
人类接口Agent模块
负责人类交互和关键决策确认
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import logging
import queue
import threading

from .base_agent import BaseAgent, AgentCapability, AgentState, TaskResult
from .message import AgentMessage, MessageType, Priority


@dataclass
class PendingConfirmation:
    """待确认项"""
    confirmation_id: str
    title: str
    description: str
    options: List[Dict[str, Any]]
    context: Dict[str, Any]
    created_at: datetime
    deadline: Optional[datetime] = None
    response: Optional[str] = None
    responded_at: Optional[datetime] = None


@dataclass
class HumanFeedback:
    """人类反馈"""
    feedback_id: str
    target_id: str
    feedback_type: str
    content: str
    rating: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)


class HumanAgent(BaseAgent):
    """人类接口Agent - 人机交互专家"""

    def __init__(
        self,
        agent_id: str = "human",
        name: str = "人类接口",
        description: str = "负责人类交互和关键决策确认",
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, name, description, config, message_bus, llm_client)

        self.auto_approve_low_risk = config.get("auto_approve_low_risk", False) if config else False
        self.confirmation_timeout = config.get("confirmation_timeout", 300) if config else 300

        self._pending_confirmations: Dict[str, PendingConfirmation] = {}
        self._feedback_history: List[HumanFeedback] = []
        self._response_queue: queue.Queue = queue.Queue()
        self._callbacks: Dict[str, Callable] = {}

        self._setup_capabilities()
        self._register_handlers()

    def _setup_capabilities(self) -> None:
        """设置Agent能力"""
        self.add_capability(AgentCapability(
            name="request_confirmation",
            description="请求人类确认",
            input_schema={"title": "string", "description": "string", "options": "list"},
            output_schema={"confirmation_id": "string", "response": "string"},
        ))

        self.add_capability(AgentCapability(
            name="collect_feedback",
            description="收集人类反馈",
            input_schema={"target_id": "string", "feedback_type": "string"},
            output_schema={"feedback_id": "string"},
        ))

        self.add_capability(AgentCapability(
            name="notify",
            description="发送通知",
            input_schema={"message": "string", "level": "string"},
            output_schema={"success": "bool"},
        ))

    def _register_handlers(self) -> None:
        """注册消息处理器"""
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task_assign)
        self.register_handler(MessageType.HUMAN_INPUT, self._handle_human_input)
        self.register_handler(MessageType.HUMAN_CONFIRM, self._handle_human_confirm)
        self.register_handler(MessageType.HUMAN_FEEDBACK, self._handle_human_feedback)
        self.register_handler(MessageType.REQUEST, self._handle_request)

    def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        """执行任务"""
        start_time = datetime.now()
        self.update_state(AgentState.WORKING)

        try:
            task_type = task.get("type", "notify")

            if task_type == "request_confirmation":
                result = self._request_confirmation(task)
            elif task_type == "collect_feedback":
                result = self._collect_feedback(task)
            elif task_type == "notify":
                result = self._notify(task)
            elif task_type == "process_response":
                result = self._process_response(task)
            else:
                result = {"error": f"未知任务类型: {task_type}"}

            duration = (datetime.now() - start_time).total_seconds()

            task_result = TaskResult(
                success="error" not in result,
                output=result,
                duration_seconds=duration,
            )
            self.record_task_result(task_result)
            return task_result

        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            return TaskResult(
                success=False,
                output={},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )
        finally:
            self.update_state(AgentState.IDLE)

    def _handle_task_assign(self, message: AgentMessage) -> AgentMessage:
        """处理任务分配"""
        task = message.content
        result = self.execute_task(task)

        return message.create_response({
            "task_type": task.get("type"),
            "success": result.success,
            "output": result.output,
            "error": result.error_message,
        })

    def _handle_human_input(self, message: AgentMessage) -> AgentMessage:
        """处理人类输入"""
        input_type = message.content.get("input_type")
        input_data = message.content.get("data")

        if input_type == "command":
            return self._handle_command(message, input_data)
        elif input_type == "query":
            return self._handle_query(message, input_data)
        else:
            return message.create_error_response(f"未知输入类型: {input_type}")

    def _handle_command(self, message: AgentMessage, command: Dict[str, Any]) -> AgentMessage:
        """处理命令"""
        cmd = command.get("cmd")

        if cmd == "approve":
            confirmation_id = command.get("confirmation_id")
            if confirmation_id in self._pending_confirmations:
                self._confirm(confirmation_id, "approved")
                return message.create_response({"status": "approved"})
            return message.create_error_response("确认ID不存在")

        elif cmd == "reject":
            confirmation_id = command.get("confirmation_id")
            if confirmation_id in self._pending_confirmations:
                self._confirm(confirmation_id, "rejected")
                return message.create_response({"status": "rejected"})
            return message.create_error_response("确认ID不存在")

        elif cmd == "pause":
            self.broadcast(MessageType.CONTROL, {"action": "pause"})
            return message.create_response({"status": "paused"})

        elif cmd == "resume":
            self.broadcast(MessageType.CONTROL, {"action": "resume"})
            return message.create_response({"status": "resumed"})

        else:
            return message.create_error_response(f"未知命令: {cmd}")

    def _handle_query(self, message: AgentMessage, query: Dict[str, Any]) -> AgentMessage:
        """处理查询"""
        query_type = query.get("type")

        if query_type == "status":
            return message.create_response(self.get_status())
        elif query_type == "pending":
            return message.create_response({
                "pending_confirmations": [
                    self._confirmation_to_dict(c)
                    for c in self._pending_confirmations.values()
                ]
            })
        else:
            return message.create_error_response(f"未知查询类型: {query_type}")

    def _handle_human_confirm(self, message: AgentMessage) -> AgentMessage:
        """处理人类确认"""
        confirmation_id = message.content.get("confirmation_id")
        response = message.content.get("response")

        if confirmation_id not in self._pending_confirmations:
            return message.create_error_response("确认ID不存在")

        self._confirm(confirmation_id, response)

        return message.create_response({
            "confirmation_id": confirmation_id,
            "status": "confirmed",
            "response": response,
        })

    def _handle_human_feedback(self, message: AgentMessage) -> AgentMessage:
        """处理人类反馈"""
        target_id = message.content.get("target_id")
        feedback_type = message.content.get("feedback_type")
        content = message.content.get("content")
        rating = message.content.get("rating")

        feedback = HumanFeedback(
            feedback_id=f"fb_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            target_id=target_id,
            feedback_type=feedback_type,
            content=content,
            rating=rating,
        )

        self._feedback_history.append(feedback)

        if target_id in self._callbacks:
            try:
                self._callbacks[target_id](feedback)
            except Exception as e:
                self.logger.error(f"反馈回调失败: {e}")

        return message.create_response({
            "feedback_id": feedback.feedback_id,
            "status": "recorded",
        })

    def _handle_request(self, message: AgentMessage) -> AgentMessage:
        """处理请求"""
        request_type = message.content.get("request_type")

        if request_type == "get_status":
            return message.create_response(self.get_status())
        elif request_type == "get_pending":
            return message.create_response({
                "pending_confirmations": [
                    self._confirmation_to_dict(c)
                    for c in self._pending_confirmations.values()
                ]
            })
        elif request_type == "get_feedback":
            return message.create_response({
                "feedback_history": [
                    self._feedback_to_dict(f) for f in self._feedback_history
                ]
            })
        else:
            return message.create_error_response(f"未知请求类型: {request_type}")

    def _request_confirmation(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """请求确认"""
        title = task.get("title", "需要确认")
        description = task.get("description", "")
        options = task.get("options", [
            {"label": "确认", "value": "approved"},
            {"label": "拒绝", "value": "rejected"},
        ])
        context = task.get("context", {})
        risk_level = context.get("risk_level", "medium")

        if self.auto_approve_low_risk and risk_level == "low":
            return {
                "confirmation_id": "auto_approved",
                "status": "auto_approved",
                "response": "approved",
            }

        confirmation = PendingConfirmation(
            confirmation_id=f"conf_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            title=title,
            description=description,
            options=options,
            context=context,
            created_at=datetime.now(),
        )

        self._pending_confirmations[confirmation.confirmation_id] = confirmation

        self.logger.info(f"等待确认: {title}")

        return {
            "confirmation_id": confirmation.confirmation_id,
            "status": "pending",
            "title": title,
            "description": description,
            "options": options,
        }

    def _collect_feedback(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """收集反馈"""
        target_id = task.get("target_id")
        feedback_type = task.get("feedback_type", "general")

        return {
            "feedback_id": f"fb_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "target_id": target_id,
            "feedback_type": feedback_type,
            "status": "collecting",
        }

    def _notify(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """发送通知"""
        message_text = task.get("message", "")
        level = task.get("level", "info")

        self.logger.log(
            logging.INFO if level == "info" else logging.WARNING if level == "warning" else logging.ERROR,
            f"[通知] {message_text}"
        )

        return {
            "success": True,
            "message": message_text,
            "level": level,
            "notified_at": datetime.now().isoformat(),
        }

    def _process_response(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理响应"""
        confirmation_id = task.get("confirmation_id")
        response = task.get("response")

        if confirmation_id not in self._pending_confirmations:
            return {"error": "确认ID不存在"}

        self._confirm(confirmation_id, response)

        return {
            "success": True,
            "confirmation_id": confirmation_id,
            "response": response,
        }

    def _confirm(self, confirmation_id: str, response: str) -> None:
        """确认"""
        if confirmation_id in self._pending_confirmations:
            confirmation = self._pending_confirmations[confirmation_id]
            confirmation.response = response
            confirmation.responded_at = datetime.now()

            self._response_queue.put({
                "confirmation_id": confirmation_id,
                "response": response,
            })

            self.logger.info(f"确认已处理: {confirmation_id} -> {response}")

    def register_callback(self, target_id: str, callback: Callable) -> None:
        """注册回调"""
        self._callbacks[target_id] = callback

    def get_response(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """获取响应"""
        try:
            return self._response_queue.get(timeout=timeout or self.confirmation_timeout)
        except queue.Empty:
            return None

    def wait_for_confirmation(self, confirmation_id: str, timeout: Optional[float] = None) -> Optional[str]:
        """等待确认"""
        timeout = timeout or self.confirmation_timeout
        start_time = datetime.now()

        while True:
            if confirmation_id not in self._pending_confirmations:
                return None

            confirmation = self._pending_confirmations[confirmation_id]
            if confirmation.response:
                return confirmation.response

            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                return None

            threading.Event().wait(0.1)

    def _confirmation_to_dict(self, confirmation: PendingConfirmation) -> Dict[str, Any]:
        """将确认转换为字典"""
        return {
            "confirmation_id": confirmation.confirmation_id,
            "title": confirmation.title,
            "description": confirmation.description,
            "options": confirmation.options,
            "created_at": confirmation.created_at.isoformat(),
            "response": confirmation.response,
            "responded_at": confirmation.responded_at.isoformat() if confirmation.responded_at else None,
        }

    def _feedback_to_dict(self, feedback: HumanFeedback) -> Dict[str, Any]:
        """将反馈转换为字典"""
        return {
            "feedback_id": feedback.feedback_id,
            "target_id": feedback.target_id,
            "feedback_type": feedback.feedback_type,
            "content": feedback.content,
            "rating": feedback.rating,
            "created_at": feedback.created_at.isoformat(),
        }
