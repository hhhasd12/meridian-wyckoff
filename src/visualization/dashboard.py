"""
Agent Teams Dashboard
提供实时监控和交互界面
支持 Streamlit Web界面 和 控制台界面
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import logging
import threading
import time

logger = logging.getLogger("dashboard")

try:
    import streamlit as st
    import pandas as pd
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


class AgentTeamsDashboard:
    """Agent Teams Web仪表盘 (Streamlit)"""

    def __init__(
        self,
        orchestrator: Optional[Any] = None,
        message_bus: Optional[Any] = None,
    ):
        self.orchestrator = orchestrator
        self.message_bus = message_bus
        self._state: Dict[str, Any] = {
            "agents": {},
            "tasks": [],
            "messages": [],
            "workflows": [],
            "issues": [],
        }
        self._running = False
        self._update_thread: Optional[threading.Thread] = None

    def update_state(self, state: Dict[str, Any]) -> None:
        """更新状态"""
        self._state.update(state)

    def set_agents(self, agents: Dict[str, Any]) -> None:
        """设置Agent状态"""
        self._state["agents"] = agents

    def set_issues(self, issues: List[Dict[str, Any]]) -> None:
        """设置问题列表"""
        self._state["issues"] = issues

    def add_message(self, message: Dict[str, Any]) -> None:
        """添加消息"""
        self._state["messages"].append(message)
        if len(self._state["messages"]) > 100:
            self._state["messages"] = self._state["messages"][-100:]

    def render(self) -> None:
        """渲染仪表盘"""
        if not STREAMLIT_AVAILABLE:
            logger.warning("Streamlit不可用，使用控制台模式")
            console = ConsoleDashboard()
            console._state = self._state
            console.render()
            return

        st.set_page_config(
            page_title="Agent Teams Dashboard",
            page_icon="🤖",
            layout="wide",
        )

        st.title("🤖 Agent Teams Dashboard")

        self._render_system_overview()
        self._render_agent_status()
        self._render_issues_panel()
        self._render_message_log()
        self._render_human_interaction()

    def _render_system_overview(self) -> None:
        """渲染系统概览"""
        st.subheader("📊 系统状态概览")

        col1, col2, col3, col4 = st.columns(4)

        agents = self._state.get("agents", {})
        tasks = self._state.get("tasks", [])
        messages = self._state.get("messages", [])
        issues = self._state.get("issues", [])

        with col1:
            st.metric("Agent数量", len(agents))

        with col2:
            st.metric("任务数", len(tasks))

        with col3:
            critical_count = sum(1 for i in issues if i.get("severity") == "critical")
            st.metric("问题数", len(issues), delta=f"-{critical_count} 严重")

        with col4:
            st.metric("消息数", len(messages))

    def _render_agent_status(self) -> None:
        """渲染Agent状态"""
        st.subheader("🤖 Agent 状态")

        agents = self._state.get("agents", {})

        if not agents:
            st.info("暂无Agent")
            return

        cols = st.columns(min(len(agents), 4))

        for i, (agent_id, info) in enumerate(agents.items()):
            col = cols[i % len(cols)]
            with col:
                state = info.get("state", "UNKNOWN")
                state_icon = {"IDLE": "🟢", "WORKING": "🔵", "ERROR": "🔴", "WAITING": "🟡"}.get(state, "⚪")
                st.markdown(f"**{state_icon} {info.get('name', agent_id)}**")
                st.caption(f"状态: {state}")
                if info.get("task_count"):
                    st.caption(f"任务数: {info.get('task_count')}")

    def _render_issues_panel(self) -> None:
        """渲染问题面板"""
        st.subheader("🔍 诊断问题")

        issues = self._state.get("issues", [])

        if not issues:
            st.success("✅ 未发现问题")
            return

        for issue in issues:
            severity = issue.get("severity", "warning")
            severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")

            with st.expander(f"{severity_icon} {issue.get('title', '未知问题')}"):
                st.write(f"**严重程度**: {severity}")
                st.write(f"**类别**: {issue.get('category', '')}")
                st.write(f"**描述**: {issue.get('description', '')}")

                if issue.get("location"):
                    st.code(issue.get("location"), language="text")

                if issue.get("evidence"):
                    st.write("**证据**:")
                    for evidence in issue.get("evidence", []):
                        st.write(f"- {evidence}")

                if issue.get("suggestions"):
                    st.write("**建议**:")
                    for suggestion in issue.get("suggestions", []):
                        st.write(f"- {suggestion}")

    def _render_message_log(self) -> None:
        """渲染消息日志"""
        st.subheader("💬 消息通信日志")

        messages = self._state.get("messages", [])

        if not messages:
            st.info("暂无消息")
            return

        for msg in messages[-20:]:
            timestamp = msg.get("timestamp", "")
            if isinstance(timestamp, str) and len(timestamp) > 19:
                timestamp = timestamp[:19]

            sender = msg.get("sender", "?")
            receiver = msg.get("receiver", "?")
            msg_type = msg.get("message_type", "")

            st.text(f"[{timestamp}] {sender} → {receiver}: {msg_type}")

    def _render_human_interaction(self) -> None:
        """渲染人类交互区域"""
        st.subheader("👤 人类交互")

        issues = self._state.get("issues", [])
        critical_issues = [i for i in issues if i.get("severity") == "critical"]

        if critical_issues:
            st.warning("⚠️ 发现严重问题，需要确认修复方案")

            for issue in critical_issues:
                st.write(f"- {issue.get('title')}")

            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("✅ 确认修复", key="confirm_fix"):
                    st.success("已确认，开始修复...")

            with col2:
                if st.button("❌ 拒绝修复", key="reject_fix"):
                    st.error("已拒绝修复")

            with col3:
                if st.button("📋 查看详情", key="view_details"):
                    st.info("查看详细修复方案...")
        else:
            st.success("✅ 系统运行正常，无需人工干预")

    def get_state_json(self) -> str:
        """获取状态JSON"""
        return json.dumps(self._state, default=str, ensure_ascii=False, indent=2)


class ConsoleDashboard:
    """控制台仪表盘 - 无需Streamlit依赖"""

    def __init__(self):
        self._state: Dict[str, Any] = {
            "agents": {},
            "tasks": [],
            "messages": [],
            "workflows": [],
            "issues": [],
        }

    def update_state(self, state: Dict[str, Any]) -> None:
        """更新状态"""
        self._state.update(state)

    def render(self) -> None:
        """渲染控制台输出"""
        print("\n" + "=" * 60)
        print("🤖 Agent Teams Dashboard (Console)")
        print("=" * 60)

        agents = self._state.get("agents", {})
        issues = self._state.get("issues", [])

        print("\n📊 Agent 状态:")
        print("-" * 40)
        if agents:
            for agent_id, info in agents.items():
                state = info.get("state", "UNKNOWN")
                icon = {"IDLE": "🟢", "WORKING": "🔵", "ERROR": "🔴", "WAITING": "🟡"}.get(state, "⚪")
                print(f"  {icon} {info.get('name', agent_id)}: {state}")
        else:
            print("  暂无Agent")

        print("\n🔍 问题列表:")
        print("-" * 40)
        if issues:
            for issue in issues:
                severity = issue.get("severity", "warning")
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")
                print(f"  {icon} [{severity}] {issue.get('title', '未知问题')}")
                print(f"     位置: {issue.get('location', 'N/A')}")
                print(f"     描述: {issue.get('description', '')[:50]}...")
        else:
            print("  ✅ 未发现问题")

        print("\n" + "=" * 60)

    def render_issue_detail(self, issue: Dict[str, Any]) -> None:
        """渲染问题详情"""
        print("\n" + "=" * 60)
        print(f"🔍 问题详情: {issue.get('title', '未知问题')}")
        print("=" * 60)

        print(f"\n问题ID: {issue.get('issue_id', '')}")
        print(f"严重程度: {issue.get('severity', '')}")
        print(f"类别: {issue.get('category', '')}")
        print(f"描述: {issue.get('description', '')}")

        if issue.get("location"):
            print(f"\n位置: {issue.get('location')}")

        if issue.get("evidence"):
            print("\n证据:")
            for e in issue.get("evidence", []):
                print(f"  - {e}")

        if issue.get("suggestions"):
            print("\n建议:")
            for s in issue.get("suggestions", []):
                print(f"  - {s}")

        print("=" * 60)

    def prompt_confirmation(self, title: str, options: List[str] = None) -> str:
        """提示确认"""
        options = options or ["y", "n"]
        while True:
            response = input(f"\n{title} [{'/'.join(options)}]: ").lower().strip()
            if response in options:
                return response
            print(f"无效输入，请选择: {'/'.join(options)}")


def run_dashboard(
    orchestrator: Optional[Any] = None,
    message_bus: Optional[Any] = None,
    port: int = 8501,
    use_console: bool = False,
) -> None:
    """运行仪表盘"""
    if use_console or not STREAMLIT_AVAILABLE:
        print("=" * 60)
        print("启动控制台模式 Dashboard")
        print("=" * 60)
        dashboard = ConsoleDashboard()
        return dashboard

    print("=" * 60)
    print("启动 Streamlit Dashboard")
    print(f"请在浏览器访问: http://localhost:{port}")
    print("=" * 60)

    dashboard = AgentTeamsDashboard(orchestrator, message_bus)
    return dashboard
