"""
协调器Agent模块
负责团队协调和任务分配
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import threading
import time

from .base_agent import BaseAgent, AgentCapability, AgentState, TaskResult
from .message import AgentMessage, MessageType, Priority


@dataclass
class Task:
    """任务定义"""
    task_id: str
    task_type: str
    description: str
    assigned_to: Optional[str] = None
    status: str = "pending"
    priority: Priority = Priority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    dependencies: List[str] = field(default_factory=list)


@dataclass
class WorkflowState:
    """工作流状态"""
    workflow_id: str
    current_phase: str
    tasks: List[Task]
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"


class OrchestratorAgent(BaseAgent):
    """协调器Agent - 团队总指挥"""

    def __init__(
        self,
        agent_id: str = "orchestrator",
        name: str = "协调器",
        description: str = "负责团队协调和任务分配",
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, name, description, config, message_bus, llm_client)

        self.agents: Dict[str, Dict[str, Any]] = {}
        self.tasks: Dict[str, Task] = {}
        self.workflows: Dict[str, WorkflowState] = {}
        self._running = False
        self._workflow_thread: Optional[threading.Thread] = None

        self._setup_capabilities()
        self._register_handlers()

    def _setup_capabilities(self) -> None:
        """设置Agent能力"""
        self.add_capability(AgentCapability(
            name="coordinate",
            description="协调团队执行任务",
            input_schema={"workflow": "string", "params": "dict"},
            output_schema={"workflow_id": "string", "status": "string"},
        ))

        self.add_capability(AgentCapability(
            name="assign_task",
            description="分配任务给Agent",
            input_schema={"task": "Task", "agent_id": "string"},
            output_schema={"success": "bool"},
        ))

        self.add_capability(AgentCapability(
            name="monitor_progress",
            description="监控任务进度",
            input_schema={"workflow_id": "string"},
            output_schema={"progress": "dict"},
        ))

    def _register_handlers(self) -> None:
        """注册消息处理器"""
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task_assign)
        self.register_handler(MessageType.TASK_STATUS, self._handle_task_status)
        self.register_handler(MessageType.TASK_COMPLETE, self._handle_task_complete)
        self.register_handler(MessageType.REQUEST, self._handle_request)

    def register_agent(self, agent_id: str, agent_info: Dict[str, Any]) -> None:
        """注册Agent"""
        self.agents[agent_id] = agent_info
        self.logger.info(f"Agent已注册: {agent_id}")

    def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        """执行任务"""
        start_time = datetime.now()
        self.update_state(AgentState.WORKING)

        try:
            task_type = task.get("type", "coordinate")

            if task_type == "coordinate":
                result = self._coordinate(task)
            elif task_type == "start_workflow":
                result = self._start_workflow(task)
            elif task_type == "stop_workflow":
                result = self._stop_workflow(task)
            elif task_type == "assign_task":
                result = self._assign_task(task)
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

    def _handle_task_status(self, message: AgentMessage) -> AgentMessage:
        """处理任务状态更新"""
        task_id = message.content.get("task_id")
        status = message.content.get("status")

        if task_id in self.tasks:
            self.tasks[task_id].status = status
            if status == "completed":
                self.tasks[task_id].completed_at = datetime.now()
                self.tasks[task_id].result = message.content.get("result")

        return message.create_response({"acknowledged": True})

    def _handle_task_complete(self, message: AgentMessage) -> AgentMessage:
        """处理任务完成"""
        task_id = message.content.get("task_id")
        result = message.content.get("result")

        if task_id in self.tasks:
            self.tasks[task_id].status = "completed"
            self.tasks[task_id].completed_at = datetime.now()
            self.tasks[task_id].result = result

        return message.create_response({"acknowledged": True})

    def _handle_request(self, message: AgentMessage) -> AgentMessage:
        """处理请求"""
        request_type = message.content.get("request_type")

        if request_type == "get_status":
            return message.create_response(self.get_status())
        elif request_type == "get_agents":
            return message.create_response({"agents": self.agents})
        elif request_type == "get_tasks":
            return message.create_response({
                "tasks": [self._task_to_dict(t) for t in self.tasks.values()]
            })
        elif request_type == "get_workflows":
            return message.create_response({
                "workflows": [self._workflow_to_dict(w) for w in self.workflows.values()]
            })
        else:
            return message.create_error_response(f"未知请求类型: {request_type}")

    def _coordinate(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """协调执行"""
        workflow_type = task.get("workflow", "auto_repair")
        params = task.get("params", {})

        workflow_id = f"wf_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        if workflow_type == "auto_repair":
            workflow_tasks = self._create_auto_repair_workflow(workflow_id, params)
        elif workflow_type == "diagnose":
            workflow_tasks = self._create_diagnose_workflow(workflow_id, params)
        else:
            return {"error": f"未知工作流类型: {workflow_type}"}

        workflow = WorkflowState(
            workflow_id=workflow_id,
            current_phase="initialized",
            tasks=workflow_tasks,
            started_at=datetime.now(),
        )

        self.workflows[workflow_id] = workflow

        for t in workflow_tasks:
            self.tasks[t.task_id] = t

        return {
            "workflow_id": workflow_id,
            "status": "initialized",
            "task_count": len(workflow_tasks),
        }

    def _create_auto_repair_workflow(self, workflow_id: str, params: Dict[str, Any]) -> List[Task]:
        """创建自动修复工作流"""
        return [
            Task(
                task_id=f"{workflow_id}_diagnose",
                task_type="diagnose",
                description="诊断系统问题",
                assigned_to="diagnostic",
                priority=Priority.HIGH,
            ),
            Task(
                task_id=f"{workflow_id}_generate_fix",
                task_type="generate_fix",
                description="生成修复方案",
                assigned_to="code",
                priority=Priority.HIGH,
                dependencies=[f"{workflow_id}_diagnose"],
            ),
            Task(
                task_id=f"{workflow_id}_confirm",
                task_type="request_confirmation",
                description="请求人类确认",
                assigned_to="human",
                priority=Priority.HIGH,
                dependencies=[f"{workflow_id}_generate_fix"],
            ),
            Task(
                task_id=f"{workflow_id}_apply_fix",
                task_type="apply_fix",
                description="应用修复",
                assigned_to="code",
                priority=Priority.HIGH,
                dependencies=[f"{workflow_id}_confirm"],
            ),
        ]

    def _create_diagnose_workflow(self, workflow_id: str, params: Dict[str, Any]) -> List[Task]:
        """创建诊断工作流"""
        return [
            Task(
                task_id=f"{workflow_id}_diagnose",
                task_type="diagnose",
                description="诊断系统问题",
                assigned_to="diagnostic",
                priority=Priority.HIGH,
            ),
        ]

    def _start_workflow(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """启动工作流"""
        workflow_id = task.get("workflow_id")

        if workflow_id not in self.workflows:
            return {"error": f"工作流不存在: {workflow_id}"}

        workflow = self.workflows[workflow_id]
        workflow.status = "running"

        self._execute_workflow(workflow)

        return {
            "workflow_id": workflow_id,
            "status": "started",
        }

    def _stop_workflow(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """停止工作流"""
        workflow_id = task.get("workflow_id")

        if workflow_id not in self.workflows:
            return {"error": f"工作流不存在: {workflow_id}"}

        workflow = self.workflows[workflow_id]
        workflow.status = "stopped"
        workflow.completed_at = datetime.now()

        return {
            "workflow_id": workflow_id,
            "status": "stopped",
        }

    def _assign_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """分配任务"""
        task_data = task.get("task")
        agent_id = task.get("agent_id")

        if agent_id not in self.agents:
            return {"error": f"Agent不存在: {agent_id}"}

        new_task = Task(
            task_id=task_data.get("task_id", f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}"),
            task_type=task_data.get("task_type"),
            description=task_data.get("description", ""),
            assigned_to=agent_id,
            priority=Priority(task_data.get("priority", 2)),
        )

        self.tasks[new_task.task_id] = new_task

        self.send_message(
            receiver=agent_id,
            message_type=MessageType.TASK_ASSIGN,
            content={
                "task_id": new_task.task_id,
                "type": new_task.task_type,
                "description": new_task.description,
            },
            priority=new_task.priority,
        )

        return {
            "task_id": new_task.task_id,
            "assigned_to": agent_id,
            "status": "assigned",
        }

    def _execute_workflow(self, workflow: WorkflowState) -> None:
        """执行工作流"""
        for task in workflow.tasks:
            if task.dependencies:
                all_deps_completed = all(
                    self.tasks.get(dep_id, Task(task_id="", task_type="", description="")).status == "completed"
                    for dep_id in task.dependencies
                )
                if not all_deps_completed:
                    continue

            if task.assigned_to and task.status == "pending":
                task.status = "assigned"
                task.started_at = datetime.now()

                self.send_message(
                    receiver=task.assigned_to,
                    message_type=MessageType.TASK_ASSIGN,
                    content={
                        "task_id": task.task_id,
                        "type": task.task_type,
                        "description": task.description,
                    },
                    priority=task.priority,
                )

    def start(self) -> None:
        """启动协调器"""
        self._running = True
        self.logger.info("协调器已启动")

    def stop(self) -> None:
        """停止协调器"""
        self._running = False
        self.logger.info("协调器已停止")

    def _task_to_dict(self, task: Task) -> Dict[str, Any]:
        """将任务转换为字典"""
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "description": task.description,
            "assigned_to": task.assigned_to,
            "status": task.status,
            "priority": task.priority.value,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "result": task.result,
        }

    def _workflow_to_dict(self, workflow: WorkflowState) -> Dict[str, Any]:
        """将工作流转换为字典"""
        return {
            "workflow_id": workflow.workflow_id,
            "current_phase": workflow.current_phase,
            "status": workflow.status,
            "started_at": workflow.started_at.isoformat(),
            "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
            "task_count": len(workflow.tasks),
        }
