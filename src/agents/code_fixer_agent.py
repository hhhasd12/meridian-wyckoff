"""
代码修复器Agent模块
负责修复代码bug
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import os
import re
import logging
import shutil

from .base_agent import BaseAgent, AgentCapability, AgentState, TaskResult
from .message import AgentMessage, MessageType, Priority


@dataclass
class FixProposal:
    """修复提案"""
    proposal_id: str
    issue_id: str
    title: str
    description: str
    file_path: str
    original_code: str
    fixed_code: str
    backup_path: Optional[str] = None
    applied: bool = False


class CodeFixerAgent(BaseAgent):
    """代码修复器Agent - 修复代码bug"""

    def __init__(
        self,
        agent_id: str = "code_fixer",
        name: str = "代码修复器",
        description: str = "负责修复代码bug",
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, name, description, config, message_bus, llm_client)

        self.project_root = config.get("project_root", ".") if config else "."
        self.fix_proposals: Dict[str, FixProposal] = {}
        self.backup_dir = os.path.join(self.project_root, ".backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self._setup_capabilities()
        self._register_handlers()

    def _setup_capabilities(self) -> None:
        """设置Agent能力"""
        self.add_capability(AgentCapability(
            name="generate_fix",
            description="生成修复方案",
            input_schema={"issue": "dict"},
            output_schema={"proposal": "FixProposal"},
        ))

        self.add_capability(AgentCapability(
            name="apply_fix",
            description="应用修复",
            input_schema={"proposal_id": "string"},
            output_schema={"success": "bool"},
        ))

        self.add_capability(AgentCapability(
            name="rollback_fix",
            description="回滚修复",
            input_schema={"proposal_id": "string"},
            output_schema={"success": "bool"},
        ))

    def _register_handlers(self) -> None:
        """注册消息处理器"""
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task_assign)
        self.register_handler(MessageType.REQUEST, self._handle_request)

    def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        """执行任务"""
        start_time = datetime.now()
        self.update_state(AgentState.WORKING)

        try:
            task_type = task.get("type", "generate_fix")

            if task_type == "generate_fix":
                result = self._generate_fix(task)
            elif task_type == "apply_fix":
                result = self._apply_fix(task)
            elif task_type == "rollback_fix":
                result = self._rollback_fix(task)
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

    def _handle_request(self, message: AgentMessage) -> AgentMessage:
        """处理请求"""
        request_type = message.content.get("request_type")

        if request_type == "get_status":
            return message.create_response(self.get_status())
        elif request_type == "get_proposals":
            return message.create_response({
                "proposals": [self._proposal_to_dict(p) for p in self.fix_proposals.values()]
            })
        else:
            return message.create_error_response(f"未知请求类型: {request_type}")

    def _generate_fix(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """生成修复方案"""
        issue = task.get("issue")
        if not issue:
            return {"error": "缺少issue参数"}

        file_path = issue.get("location")
        if not file_path or not os.path.exists(file_path):
            return {"error": f"文件不存在: {file_path}"}

        # 读取原始代码
        with open(file_path, "r", encoding="utf-8") as f:
            original_code = f.read()

        # 生成修复代码
        fixed_code = self._generate_fixed_code(file_path, original_code, issue)

        proposal = FixProposal(
            proposal_id=f"fix_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            issue_id=issue.get("issue_id", "unknown"),
            title=f"修复: {issue.get('title', '未知问题')}",
            description=issue.get("description", ""),
            file_path=file_path,
            original_code=original_code,
            fixed_code=fixed_code,
        )

        self.fix_proposals[proposal.proposal_id] = proposal

        return {
            "proposal_id": proposal.proposal_id,
            "title": proposal.title,
            "file_path": file_path,
            "preview": self._generate_diff_preview(original_code, fixed_code),
        }

    def _generate_fixed_code(self, file_path: str, original_code: str, issue: Dict[str, Any]) -> str:
        """生成修复后的代码"""
        lines = original_code.split("\n")
        issue_type = issue.get("category", "bug")
        line_number = issue.get("line_number")

        if issue_type == "bug" and line_number:
            # 简单的行修复
            if "语法错误" in issue.get("title", ""):
                # 尝试修复常见语法错误
                line = lines[line_number - 1] if line_number <= len(lines) else ""
                # 修复缺失的冒号
                if "if " in line and not line.rstrip().endswith(":"):
                    lines[line_number - 1] = line.rstrip() + ":"
                # 修复缺失的括号
                elif line.count("(") > line.count(")"):
                    lines[line_number - 1] = line + ")"

        elif issue_type == "style":
            # 删除未使用的导入
            if "未使用的导入" in issue.get("title", ""):
                import_name = issue.get("description", "").split("'")[1] if "'" in issue.get("description", "") else ""
                if import_name:
                    lines = [l for l in lines if import_name not in l or "import" not in l]

        return "\n".join(lines)

    def _generate_diff_preview(self, original: str, fixed: str) -> str:
        """生成差异预览"""
        import difflib
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile="original",
            tofile="fixed",
        )
        return "".join(diff)

    def _apply_fix(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """应用修复"""
        proposal_id = task.get("proposal_id")
        if not proposal_id:
            return {"error": "缺少proposal_id参数"}

        if proposal_id not in self.fix_proposals:
            return {"error": f"提案不存在: {proposal_id}"}

        proposal = self.fix_proposals[proposal_id]

        # 创建备份
        backup_path = os.path.join(
            self.backup_dir,
            f"{os.path.basename(proposal.file_path)}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
        )
        shutil.copy2(proposal.file_path, backup_path)
        proposal.backup_path = backup_path

        # 应用修复
        with open(proposal.file_path, "w", encoding="utf-8") as f:
            f.write(proposal.fixed_code)

        proposal.applied = True

        return {
            "success": True,
            "proposal_id": proposal_id,
            "file_path": proposal.file_path,
            "backup_path": backup_path,
        }

    def _rollback_fix(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """回滚修复"""
        proposal_id = task.get("proposal_id")
        if not proposal_id:
            return {"error": "缺少proposal_id参数"}

        if proposal_id not in self.fix_proposals:
            return {"error": f"提案不存在: {proposal_id}"}

        proposal = self.fix_proposals[proposal_id]

        if not proposal.applied:
            return {"error": "修复未应用"}

        if not proposal.backup_path or not os.path.exists(proposal.backup_path):
            return {"error": "备份文件不存在"}

        # 恢复备份
        shutil.copy2(proposal.backup_path, proposal.file_path)
        proposal.applied = False

        return {
            "success": True,
            "proposal_id": proposal_id,
            "file_path": proposal.file_path,
        }

    def _proposal_to_dict(self, proposal: FixProposal) -> Dict[str, Any]:
        """将提案转换为字典"""
        return {
            "proposal_id": proposal.proposal_id,
            "issue_id": proposal.issue_id,
            "title": proposal.title,
            "file_path": proposal.file_path,
            "applied": proposal.applied,
            "backup_path": proposal.backup_path,
        }
