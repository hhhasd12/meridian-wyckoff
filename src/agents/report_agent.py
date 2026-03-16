"""
报告专家Agent模块
负责报告生成和信息整合
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import os
import json
import logging

from .base_agent import BaseAgent, AgentCapability, AgentState, TaskResult
from .message import AgentMessage, MessageType, Priority


@dataclass
class Report:
    """报告"""
    report_id: str
    title: str
    type: str
    content: str
    timestamp: datetime
    sections: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Notification:
    """通知"""
    notification_id: str
    title: str
    message: str
    level: str
    recipients: List[str]
    timestamp: datetime
    read: bool = False


class ReportAgent(BaseAgent):
    """报告专家Agent - 报告生成和信息整合专家"""

    def __init__(
        self,
        agent_id: str = "report",
        name: str = "报告专家",
        description: str = "负责报告生成和信息整合",
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, name, description, config, message_bus, llm_client)

        self.project_root = config.get("project_root", ".") if config else "."
        self.report_dir = os.path.join(self.project_root, "reports")
        os.makedirs(self.report_dir, exist_ok=True)

        self.reports: Dict[str, Report] = {}
        self.notifications: List[Notification] = []
        self.archives: List[Report] = []

        self._setup_capabilities()
        self._register_handlers()

    def _setup_capabilities(self) -> None:
        """设置Agent能力"""
        self.add_capability(AgentCapability(
            name="generate_report",
            description="生成报告",
            input_schema={"title": "string", "type": "string", "data": "dict"},
            output_schema={"report": "Report"},
        ))

        self.add_capability(AgentCapability(
            name="send_notification",
            description="发送通知",
            input_schema={"title": "string", "message": "string", "level": "string", "recipients": "list"},
            output_schema={"notification": "Notification"},
        ))

        self.add_capability(AgentCapability(
            name="archive_report",
            description="归档报告",
            input_schema={"report_id": "string"},
            output_schema={"success": "bool"},
        ))

        self.add_capability(AgentCapability(
            name="generate_summary",
            description="生成摘要",
            input_schema={"data": "dict"},
            output_schema={"summary": "string"},
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
            task_type = task.get("type", "report")

            if task_type == "report":
                result = self._generate_report(task)
            elif task_type == "notify":
                result = self._send_notification(task)
            elif task_type == "archive":
                result = self._archive_report(task)
            elif task_type == "summary":
                result = self._generate_summary(task)
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
        elif request_type == "get_reports":
            return message.create_response({
                "reports": [self._report_to_dict(r) for r in self.reports.values()]
            })
        elif request_type == "get_notifications":
            return message.create_response({
                "notifications": [self._notification_to_dict(n) for n in self.notifications]
            })
        else:
            return message.create_error_response(f"未知请求类型: {request_type}")

    def _generate_report(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """生成报告"""
        title = task.get("title", "报告")
        report_type = task.get("type", "general")
        data = task.get("data", {})

        # 生成报告内容
        sections = []

        if report_type == "diagnostic":
            sections = [
                {
                    "title": "执行摘要",
                    "content": f"本次诊断共发现 {len(data.get('issues', []))} 个问题",
                },
                {
                    "title": "问题详情",
                    "content": self._format_issues(data.get("issues", [])),
                },
                {
                    "title": "修复建议",
                    "content": self._format_suggestions(data.get("recommendations", [])),
                },
            ]
        elif report_type == "backtest":
            sections = [
                {
                    "title": "回测结果",
                    "content": self._format_metrics(data.get("metrics", {})),
                },
                {
                    "title": "性能分析",
                    "content": self._format_performance(data.get("performance", {})),
                },
                {
                    "title": "风险评估",
                    "content": self._format_risk(data.get("risk", {})),
                },
            ]
        else:
            sections = [
                {
                    "title": "概述",
                    "content": "这是一份通用报告",
                },
                {
                    "title": "详细信息",
                    "content": str(data),
                },
            ]

        # 生成Markdown内容
        content = f"# {title}\n\n"
        for section in sections:
            content += f"## {section['title']}\n\n{section['content']}\n\n"

        report = Report(
            report_id=f"report_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            title=title,
            type=report_type,
            content=content,
            timestamp=datetime.now(),
            sections=sections,
            metadata=data,
        )

        # 保存报告
        report_path = os.path.join(self.report_dir, f"{report.report_id}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)

        self.reports[report.report_id] = report

        return {
            "report_id": report.report_id,
            "title": report.title,
            "type": report.type,
            "sections": len(report.sections),
            "saved_path": report_path,
        }

    def _send_notification(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """发送通知"""
        title = task.get("title", "通知")
        message = task.get("message", "")
        level = task.get("level", "info")
        recipients = task.get("recipients", ["human"])

        notification = Notification(
            notification_id=f"notif_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            title=title,
            message=message,
            level=level,
            recipients=recipients,
            timestamp=datetime.now(),
        )

        self.notifications.append(notification)

        # 发送通知消息
        if self.message_bus:
            for recipient in recipients:
                self.send_message(
                    recipient,
                    MessageType.HUMAN_INPUT,
                    {
                        "input_type": "notification",
                        "data": {
                            "notification_id": notification.notification_id,
                            "title": title,
                            "message": message,
                            "level": level,
                        },
                    },
                )

        return {
            "notification_id": notification.notification_id,
            "title": title,
            "level": level,
            "recipients": recipients,
        }

    def _archive_report(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """归档报告"""
        report_id = task.get("report_id")

        if report_id in self.reports:
            report = self.reports.pop(report_id)
            self.archives.append(report)
            return {"success": True, "report_id": report_id}

        return {"error": f"报告不存在: {report_id}"}

    def _generate_summary(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """生成摘要"""
        data = task.get("data", {})

        # 生成摘要
        summary = "# 执行摘要\n\n"

        if "issues" in data:
            summary += f"## 问题发现\n\n发现 {len(data['issues'])} 个问题\n\n"
            for issue in data['issues'][:3]:  # 只显示前3个问题
                summary += f"- {issue.get('title', '问题')}\n"

        if "metrics" in data:
            summary += "## 性能指标\n\n"
            for key, value in data['metrics'].items():
                summary += f"- {key}: {value}\n"

        if "recommendations" in data:
            summary += "## 建议\n\n"
            for rec in data['recommendations']:
                summary += f"- {rec}\n"

        return {"summary": summary}

    def _format_issues(self, issues: List[Dict[str, Any]]) -> str:
        """格式化问题"""
        content = ""
        for i, issue in enumerate(issues, 1):
            content += f"### 问题 {i}: {issue.get('title', '未知问题')}\n\n"
            content += f"**严重程度**: {issue.get('severity', 'medium')}\n\n"
            content += f"**描述**: {issue.get('description', '')}\n\n"
            if issue.get('suggestions'):
                content += "**建议**:\n"
                for suggestion in issue['suggestions']:
                    content += f"- {suggestion}\n"
                content += "\n"
        return content

    def _format_suggestions(self, suggestions: List[str]) -> str:
        """格式化建议"""
        content = ""
        for i, suggestion in enumerate(suggestions, 1):
            content += f"{i}. {suggestion}\n\n"
        return content

    def _format_metrics(self, metrics: Dict[str, Any]) -> str:
        """格式化指标"""
        content = ""
        for key, value in metrics.items():
            content += f"- **{key}**: {value}\n"
        return content

    def _format_performance(self, performance: Dict[str, Any]) -> str:
        """格式化性能"""
        content = ""
        if performance:
            content += "性能分析详情:\n\n"
            for key, value in performance.items():
                content += f"- {key}: {value}\n"
        else:
            content = "暂无性能分析数据"
        return content

    def _format_risk(self, risk: Dict[str, Any]) -> str:
        """格式化风险"""
        content = ""
        if risk:
            content += "风险评估:\n\n"
            content += f"**风险等级**: {risk.get('level', 'medium')}\n\n"
            if risk.get('factors'):
                content += "**风险因素**:\n"
                for factor in risk['factors']:
                    content += f"- {factor}\n"
        else:
            content = "暂无风险评估数据"
        return content

    def _report_to_dict(self, report: Report) -> Dict[str, Any]:
        """将报告转换为字典"""
        return {
            "report_id": report.report_id,
            "title": report.title,
            "type": report.type,
            "sections": len(report.sections),
            "timestamp": report.timestamp.isoformat(),
        }

    def _notification_to_dict(self, notification: Notification) -> Dict[str, Any]:
        """将通知转换为字典"""
        return {
            "notification_id": notification.notification_id,
            "title": notification.title,
            "level": notification.level,
            "recipients": notification.recipients,
            "read": notification.read,
            "timestamp": notification.timestamp.isoformat(),
        }
