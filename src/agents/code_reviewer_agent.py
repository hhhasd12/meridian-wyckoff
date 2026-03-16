"""
代码审查器Agent模块
负责审查代码质量
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import os
import ast
import logging

from .base_agent import BaseAgent, AgentCapability, AgentState, TaskResult
from .message import AgentMessage, MessageType, Priority


@dataclass
class ReviewComment:
    """审查评论"""
    comment_id: str
    severity: str  # critical, major, minor, suggestion
    category: str  # logic, style, performance, security, maintainability
    title: str
    description: str
    location: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class ReviewReport:
    """审查报告"""
    report_id: str
    file_path: str
    timestamp: datetime
    comments: List[ReviewComment]
    score: float  # 0-100
    summary: str
    passed: bool


class CodeReviewerAgent(BaseAgent):
    """代码审查器Agent - 审查代码质量"""

    def __init__(
        self,
        agent_id: str = "code_reviewer",
        name: str = "代码审查器",
        description: str = "负责审查代码质量",
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, name, description, config, message_bus, llm_client)

        self.project_root = config.get("project_root", ".") if config else "."
        self.review_history: List[ReviewReport] = []

        self._setup_capabilities()
        self._register_handlers()

    def _setup_capabilities(self) -> None:
        """设置Agent能力"""
        self.add_capability(AgentCapability(
            name="review_code",
            description="审查代码",
            input_schema={"file_path": "string", "criteria": "list"},
            output_schema={"report": "ReviewReport"},
        ))

        self.add_capability(AgentCapability(
            name="check_quality",
            description="检查代码质量",
            input_schema={"directory": "string"},
            output_schema={"score": "float", "issues": "list"},
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
            task_type = task.get("type", "review_code")

            if task_type == "review_code":
                result = self._review_code(task)
            elif task_type == "check_quality":
                result = self._check_quality(task)
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
        elif request_type == "get_history":
            return message.create_response({
                "history": [self._report_to_dict(r) for r in self.review_history]
            })
        else:
            return message.create_error_response(f"未知请求类型: {request_type}")

    def _review_code(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """审查代码"""
        file_path = task.get("file_path")
        if not file_path:
            return {"error": "缺少file_path参数"}

        full_path = os.path.join(self.project_root, file_path)
        if not os.path.exists(full_path):
            return {"error": f"文件不存在: {file_path}"}

        criteria = task.get("criteria", ["style", "logic", "performance", "security"])

        # 读取代码
        with open(full_path, "r", encoding="utf-8") as f:
            code = f.read()
            lines = code.split("\n")

        comments: List[ReviewComment] = []

        # 执行各项检查
        if "style" in criteria:
            comments.extend(self._check_style(full_path, code, lines))
        if "logic" in criteria:
            comments.extend(self._check_logic(full_path, code, lines))
        if "performance" in criteria:
            comments.extend(self._check_performance(full_path, code, lines))
        if "security" in criteria:
            comments.extend(self._check_security(full_path, code, lines))

        # 计算分数
        score = self._calculate_score(comments)
        passed = score >= 70

        report = ReviewReport(
            report_id=f"review_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            file_path=file_path,
            timestamp=datetime.now(),
            comments=comments,
            score=score,
            summary=self._generate_summary(comments, score),
            passed=passed,
        )

        self.review_history.append(report)

        return {
            "report_id": report.report_id,
            "file_path": file_path,
            "score": score,
            "passed": passed,
            "comment_count": len(comments),
            "comments": [self._comment_to_dict(c) for c in comments],
            "summary": report.summary,
        }

    def _check_style(self, file_path: str, code: str, lines: List[str]) -> List[ReviewComment]:
        """检查代码风格"""
        comments = []

        for i, line in enumerate(lines, 1):
            # 行长度
            if len(line) > 100:
                comments.append(ReviewComment(
                    comment_id=f"STYLE_{i}_length",
                    severity="minor",
                    category="style",
                    title="行过长",
                    description=f"行长度 {len(line)} 超过100",
                    location=file_path,
                    line_number=i,
                    suggestion="拆分长行",
                ))

            # 缺少空格
            if "if(" in line or "for(" in line or "while(" in line:
                comments.append(ReviewComment(
                    comment_id=f"STYLE_{i}_space",
                    severity="minor",
                    category="style",
                    title="缺少空格",
                    description="关键字后缺少空格",
                    location=file_path,
                    line_number=i,
                    suggestion="在关键字后添加空格",
                ))

        return comments

    def _check_logic(self, file_path: str, code: str, lines: List[str]) -> List[ReviewComment]:
        """检查逻辑问题"""
        comments = []

        for i, line in enumerate(lines, 1):
            # 空的if/except块
            if "if " in line or "except" in line:
                if i < len(lines) and lines[i].strip() == "pass":
                    comments.append(ReviewComment(
                        comment_id=f"LOGIC_{i}_empty",
                        severity="major",
                        category="logic",
                        title="空代码块",
                        description="空的if/except块",
                        location=file_path,
                        line_number=i,
                        suggestion="添加适当的处理逻辑",
                    ))

            # 裸except
            if line.strip().startswith("except:"):
                comments.append(ReviewComment(
                    comment_id=f"LOGIC_{i}_bare_except",
                    severity="major",
                    category="logic",
                    title="裸except",
                    description="捕获所有异常可能隐藏bug",
                    location=file_path,
                    line_number=i,
                    suggestion="指定具体的异常类型",
                ))

        return comments

    def _check_performance(self, file_path: str, code: str, lines: List[str]) -> List[ReviewComment]:
        """检查性能问题"""
        comments = []

        for i, line in enumerate(lines, 1):
            # 循环中的字符串拼接
            if "+=" in line and ("\"" in line or "'" in line):
                if i > 0 and "for " in lines[i - 2]:
                    comments.append(ReviewComment(
                        comment_id=f"PERF_{i}_concat",
                        severity="minor",
                        category="performance",
                        title="循环中字符串拼接",
                        description="循环中使用+=拼接字符串效率低",
                        location=file_path,
                        line_number=i,
                        suggestion="使用列表join或StringIO",
                    ))

        return comments

    def _check_security(self, file_path: str, code: str, lines: List[str]) -> List[ReviewComment]:
        """检查安全问题"""
        comments = []

        for i, line in enumerate(lines, 1):
            # 硬编码密码
            if "password" in line.lower() and "=" in line and "\"" in line:
                comments.append(ReviewComment(
                    comment_id=f"SEC_{i}_password",
                    severity="critical",
                    category="security",
                    title="硬编码密码",
                    description="代码中包含硬编码的密码",
                    location=file_path,
                    line_number=i,
                    suggestion="使用环境变量或配置文件",
                ))

            # SQL注入风险
            if "execute" in line and "+" in line and "sql" in line.lower():
                comments.append(ReviewComment(
                    comment_id=f"SEC_{i}_sql",
                    severity="critical",
                    category="security",
                    title="SQL注入风险",
                    description="字符串拼接SQL可能导致注入",
                    location=file_path,
                    line_number=i,
                    suggestion="使用参数化查询",
                ))

            # eval使用
            if "eval(" in line:
                comments.append(ReviewComment(
                    comment_id=f"SEC_{i}_eval",
                    severity="critical",
                    category="security",
                    title="eval使用",
                    description="eval可能执行恶意代码",
                    location=file_path,
                    line_number=i,
                    suggestion="避免使用eval，使用ast.literal_eval",
                ))

        return comments

    def _calculate_score(self, comments: List[ReviewComment]) -> float:
        """计算分数 - 基于问题密度而非绝对数量"""
        if not comments:
            return 100.0

        severity_weights = {
            "critical": 25,
            "major": 15,
            "minor": 5,
            "suggestion": 1,
        }
        
        by_severity = {}
        for c in comments:
            by_severity[c.severity] = by_severity.get(c.severity, 0) + 1
        
        total_penalty = 0
        for severity, count in by_severity.items():
            weight = severity_weights.get(severity, 1)
            if count <= 5:
                total_penalty += count * weight
            elif count <= 20:
                total_penalty += 5 * weight + (count - 5) * weight * 0.5
            else:
                total_penalty += 5 * weight + 15 * weight * 0.5 + (count - 20) * weight * 0.1
        
        score = max(0, 100 - total_penalty)
        
        return min(100, max(0, score))

    def _generate_summary(self, comments: List[ReviewComment], score: float) -> str:
        """生成摘要"""
        if not comments:
            return "代码质量优秀，未发现问题"

        critical = sum(1 for c in comments if c.severity == "critical")
        major = sum(1 for c in comments if c.severity == "major")
        minor = sum(1 for c in comments if c.severity == "minor")

        return f"代码质量分数: {score:.1f}分。发现 {critical} 个严重问题, {major} 个主要问题, {minor} 个次要问题。"

    def _check_quality(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """检查代码质量"""
        directory = task.get("directory", "src")
        full_path = os.path.join(self.project_root, directory)

        if not os.path.exists(full_path):
            return {"error": f"目录不存在: {directory}"}

        all_comments = []
        file_count = 0

        for root, dirs, files in os.walk(full_path):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]

            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()
                        lines = code.split("\n")

                    all_comments.extend(self._check_style(file_path, code, lines))
                    all_comments.extend(self._check_logic(file_path, code, lines))
                    all_comments.extend(self._check_security(file_path, code, lines))
                    file_count += 1

        score = self._calculate_score(all_comments)

        return {
            "directory": directory,
            "file_count": file_count,
            "score": score,
            "issue_count": len(all_comments),
            "issues": [self._comment_to_dict(c) for c in all_comments[:20]],  # 只返回前20个
        }

    def _comment_to_dict(self, comment: ReviewComment) -> Dict[str, Any]:
        """将评论转换为字典"""
        return {
            "comment_id": comment.comment_id,
            "severity": comment.severity,
            "category": comment.category,
            "title": comment.title,
            "description": comment.description,
            "location": comment.location,
            "line_number": comment.line_number,
            "suggestion": comment.suggestion,
        }

    def _report_to_dict(self, report: ReviewReport) -> Dict[str, Any]:
        """将报告转换为字典"""
        return {
            "report_id": report.report_id,
            "file_path": report.file_path,
            "score": report.score,
            "passed": report.passed,
            "comment_count": len(report.comments),
            "timestamp": report.timestamp.isoformat(),
        }
