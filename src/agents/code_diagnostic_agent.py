"""
代码诊断器Agent模块
负责诊断代码问题，"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import os
import ast
import logging
import traceback

from .base_agent import BaseAgent, AgentCapability, AgentState, TaskResult
from .message import AgentMessage, MessageType, Priority


@dataclass
class CodeIssue:
    """代码问题"""
    issue_id: str
    severity: str  # critical, warning, info
    category: str  # bug, style, performance, security
    title: str
    description: str
    location: Optional[str] = None
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)


class CodeDiagnosticAgent(BaseAgent):
    """代码诊断器Agent - 诊断代码问题"""

    def __init__(
        self,
        agent_id: str = "code_diagnostic",
        name: str = "代码诊断器",
        description: str = "负责诊断代码问题",
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, name, description, config, message_bus, llm_client)

        self.project_root = config.get("project_root", ".") if config else "."
        self.issues_found: List[CodeIssue] = []

        self._setup_capabilities()
        self._register_handlers()

    def _setup_capabilities(self) -> None:
        """设置Agent能力"""
        self.add_capability(AgentCapability(
            name="diagnose_code",
            description="诊断代码问题",
            input_schema={"target": "string", "deep": "bool"},
            output_schema={"issues": "list"},
        ))

        self.add_capability(AgentCapability(
            name="analyze_file",
            description="分析单个文件",
            input_schema={"file_path": "string"},
            output_schema={"issues": "list"},
        ))

        self.add_capability(AgentCapability(
            name="check_syntax",
            description="检查语法错误",
            input_schema={"code": "string"},
            output_schema={"errors": "list"},
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
            task_type = task.get("type", "diagnose_code")

            if task_type == "diagnose_code":
                result = self._diagnose_code(task)
            elif task_type == "analyze_file":
                result = self._analyze_file(task)
            elif task_type == "check_syntax":
                result = self._check_syntax(task)
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
        elif request_type == "get_issues":
            return message.create_response({
                "issues": [self._issue_to_dict(i) for i in self.issues_found]
            })
        else:
            return message.create_error_response(f"未知请求类型: {request_type}")

    def _diagnose_code(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """诊断代码"""
        target = task.get("target", "src")
        deep = task.get("deep", False)

        issues: List[CodeIssue] = []

        # 扫描代码目录
        target_path = os.path.join(self.project_root, target)
        if os.path.exists(target_path):
            issues.extend(self._scan_directory(target_path, deep))

        self.issues_found = issues

        return {
            "issue_count": len(issues),
            "issues": [self._issue_to_dict(i) for i in issues],
            "scanned_path": target_path,
        }

    def _scan_directory(self, directory: str, deep: bool = False) -> List[CodeIssue]:
        """扫描目录"""
        issues = []

        for root, dirs, files in os.walk(directory):
            # 跳过隐藏目录和缓存
            dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]

            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    issues.extend(self._analyze_python_file(file_path, deep))

        return issues

    def _analyze_python_file(self, file_path: str, deep: bool = False) -> List[CodeIssue]:
        """分析Python文件"""
        issues = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # 1. 语法检查
            try:
                ast.parse(content)
            except SyntaxError as e:
                issues.append(CodeIssue(
                    issue_id=f"SYNTAX_{os.path.basename(file_path)}_{e.lineno}",
                    severity="critical",
                    category="bug",
                    title="语法错误",
                    description=str(e.msg),
                    location=file_path,
                    line_number=e.lineno,
                    suggestions=["修复语法错误"],
                ))

            # 2. 代码风格检查
            for i, line in enumerate(lines, 1):
                # 检查行长度
                if len(line) > 120:
                    issues.append(CodeIssue(
                        issue_id=f"STYLE_{os.path.basename(file_path)}_{i}",
                        severity="info",
                        category="style",
                        title="行过长",
                        description=f"行长度超过120字符 ({len(line)})",
                        location=file_path,
                        line_number=i,
                        suggestions=["拆分长行"],
                    ))

                # 检查TODO/FIXME
                if "TODO" in line or "FIXME" in line:
                    issues.append(CodeIssue(
                        issue_id=f"TODO_{os.path.basename(file_path)}_{i}",
                        severity="info",
                        category="style",
                        title="待办事项",
                        description=line.strip(),
                        location=file_path,
                        line_number=i,
                        suggestions=["处理TODO/FIXME"],
                    ))

            # 3. 深度分析
            if deep:
                issues.extend(self._deep_analyze(file_path, content, lines))

        except Exception as e:
            issues.append(CodeIssue(
                issue_id=f"ERROR_{os.path.basename(file_path)}",
                severity="warning",
                category="bug",
                title="文件读取错误",
                description=str(e),
                location=file_path,
            ))

        return issues

    def _deep_analyze(self, file_path: str, content: str, lines: List[str]) -> List[CodeIssue]:
        """深度分析"""
        issues = []

        # 检查未使用的导入
        tree = ast.parse(content)
        imports = []
        used_names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.Name):
                used_names.add(node.id)

        for name, line_no in imports:
            if name not in used_names:
                issues.append(CodeIssue(
                    issue_id=f"UNUSED_IMPORT_{os.path.basename(file_path)}_{line_no}",
                    severity="info",
                    category="style",
                    title="未使用的导入",
                    description=f"导入 '{name}' 未被使用",
                    location=file_path,
                    line_number=line_no,
                    suggestions=[f"删除未使用的导入: {name}"],
                ))

        return issues

    def _analyze_file(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """分析单个文件"""
        file_path = task.get("file_path")
        if not file_path:
            return {"error": "缺少file_path参数"}

        full_path = os.path.join(self.project_root, file_path)
        if not os.path.exists(full_path):
            return {"error": f"文件不存在: {file_path}"}

        issues = self._analyze_python_file(full_path, deep=True)

        return {
            "file_path": file_path,
            "issue_count": len(issues),
            "issues": [self._issue_to_dict(i) for i in issues],
        }

    def _check_syntax(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """检查语法"""
        code = task.get("code")
        if not code:
            return {"error": "缺少code参数"}

        errors = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append({
                "line": e.lineno,
                "message": str(e.msg),
                "offset": e.offset,
            })

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def _issue_to_dict(self, issue: CodeIssue) -> Dict[str, Any]:
        """将问题转换为字典"""
        return {
            "issue_id": issue.issue_id,
            "severity": issue.severity,
            "category": issue.category,
            "title": issue.title,
            "description": issue.description,
            "location": issue.location,
            "line_number": issue.line_number,
            "suggestions": issue.suggestions,
        }
