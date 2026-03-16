"""
Agent Teams 集成测试
演示Agent如何诊断和修复现有Bug
"""

import sys
import os
import logging
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import (
    BaseAgent,
    AgentState,
    DiagnosticAgent,
    CodeAgent,
    HumanAgent,
    OrchestratorAgent,
)
from src.communication import InMemoryMessageBus
from src.visualization import ConsoleDashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent_teams_test")


class AgentTeamsSystem:
    """Agent Teams 系统集成"""

    def __init__(self, project_root: str = "."):
        self.project_root = project_root

        self.message_bus = InMemoryMessageBus()

        self.orchestrator = OrchestratorAgent(
            agent_id="orchestrator",
            config={"project_root": project_root},
            message_bus=self.message_bus,
        )

        self.diagnostic_agent = DiagnosticAgent(
            agent_id="diagnostic",
            config={"project_root": project_root},
            message_bus=self.message_bus,
        )

        self.code_agent = CodeAgent(
            agent_id="code",
            config={"project_root": project_root},
            message_bus=self.message_bus,
        )

        self.human_agent = HumanAgent(
            agent_id="human",
            config={"project_root": project_root, "auto_approve_low_risk": False},
            message_bus=self.message_bus,
        )

        self.dashboard = ConsoleDashboard()

        self._setup_message_routing()

    def _setup_message_routing(self) -> None:
        """设置消息路由"""
        def route_to_diagnostic(message):
            return self.diagnostic_agent.process_message(message)

        def route_to_code(message):
            return self.code_agent.process_message(message)

        def route_to_human(message):
            return self.human_agent.process_message(message)

        def route_to_orchestrator(message):
            return self.orchestrator.process_message(message)

        self.message_bus.register_agent("diagnostic", route_to_diagnostic)
        self.message_bus.register_agent("code", route_to_code)
        self.message_bus.register_agent("human", route_to_human)
        self.message_bus.register_agent("orchestrator", route_to_orchestrator)

        self.orchestrator.register_agent("diagnostic", {
            "name": "诊断专家",
            "capabilities": ["diagnose", "analyze_logs", "analyze_code"],
        })
        self.orchestrator.register_agent("code", {
            "name": "代码修复专家",
            "capabilities": ["generate_fix", "apply_fix", "rollback"],
        })
        self.orchestrator.register_agent("human", {
            "name": "人类接口",
            "capabilities": ["request_confirmation", "collect_feedback"],
        })

    def initialize(self) -> None:
        """初始化系统"""
        logger.info("初始化 Agent Teams 系统...")

        self.message_bus.start()

        self.orchestrator.initialize()
        self.diagnostic_agent.initialize()
        self.code_agent.initialize()
        self.human_agent.initialize()

        logger.info("Agent Teams 系统初始化完成")

    def run_diagnosis(self) -> Dict[str, Any]:
        """运行诊断"""
        logger.info("=" * 60)
        logger.info("开始系统诊断...")
        logger.info("=" * 60)

        result = self.diagnostic_agent.execute_task({
            "type": "diagnose",
            "scope": "full",
        })

        if result.success:
            logger.info(f"诊断完成，发现 {result.output.get('issue_count', 0)} 个问题")

            issues = result.output.get("issues", [])
            for issue in issues:
                severity = issue.get("severity", "unknown")
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")
                logger.info(f"  {icon} [{severity}] {issue.get('title')}")

            self.dashboard.update_state({
                "agents": {
                    "orchestrator": self.orchestrator.get_status(),
                    "diagnostic": self.diagnostic_agent.get_status(),
                    "code": self.code_agent.get_status(),
                    "human": self.human_agent.get_status(),
                },
                "issues": issues,
            })
            self.dashboard.render()

        return result.output

    def generate_fix_proposal(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """生成修复提案"""
        logger.info(f"\n生成修复提案: {issue.get('title')}")

        result = self.code_agent.execute_task({
            "type": "generate_fix",
            "issue": issue,
        })

        if result.success:
            logger.info(f"修复提案已生成: {result.output.get('proposal_id')}")
            logger.info(f"风险等级: {result.output.get('risk_level')}")

            if result.output.get("diff"):
                logger.info("\n修复差异预览:")
                print("-" * 40)
                print(result.output.get("diff"))
                print("-" * 40)

        return result.output

    def request_human_confirmation(self, proposal: Dict[str, Any]) -> bool:
        """请求人类确认"""
        logger.info("\n请求人类确认...")

        result = self.human_agent.execute_task({
            "type": "request_confirmation",
            "title": f"确认修复: {proposal.get('title', '未知')}",
            "description": proposal.get("diff", ""),
            "context": {
                "risk_level": proposal.get("risk_level", "medium"),
                "file_path": proposal.get("file_path"),
            },
        })

        if result.success:
            confirmation_id = result.output.get("confirmation_id")
            logger.info(f"等待确认: {confirmation_id}")

            response = self.dashboard.prompt_confirmation(
                "是否应用此修复?",
                ["y", "n", "s"]
            )

            if response == "y":
                logger.info("用户确认应用修复")
                return True
            elif response == "s":
                logger.info("用户选择跳过此修复")
                return False
            else:
                logger.info("用户拒绝修复")
                return False

        return False

    def apply_fix(self, proposal_id: str) -> Dict[str, Any]:
        """应用修复"""
        logger.info(f"\n应用修复: {proposal_id}")

        result = self.code_agent.execute_task({
            "type": "apply_fix",
            "proposal_id": proposal_id,
        })

        if result.success:
            logger.info("✅ 修复已成功应用")
            logger.info(f"备份文件: {result.output.get('backup_path')}")
        else:
            logger.error(f"❌ 修复应用失败: {result.output.get('error')}")

        return result.output

    def run_auto_repair_workflow(self, auto_confirm: bool = False) -> None:
        """运行自动修复工作流"""
        logger.info("\n" + "=" * 60)
        logger.info("🚀 开始自动修复工作流")
        logger.info("=" * 60)

        diagnosis_result = self.run_diagnosis()

        issues = diagnosis_result.get("issues", [])

        if not issues:
            logger.info("✅ 未发现问题，系统状态正常")
            return

        critical_issues = [i for i in issues if i.get("severity") == "critical"]

        if not critical_issues:
            logger.info("未发现严重问题，跳过自动修复")
            return

        for issue in critical_issues:
            logger.info(f"\n处理问题: {issue.get('title')}")

            proposal = self.generate_fix_proposal(issue)

            if "error" in proposal:
                logger.error(f"生成修复提案失败: {proposal.get('error')}")
                continue

            should_apply = auto_confirm or self.request_human_confirmation(proposal)

            if should_apply:
                apply_result = self.apply_fix(proposal.get("proposal_id"))
                if "error" not in apply_result:
                    logger.info("✅ 修复成功")
                else:
                    logger.error("❌ 修复失败")
            else:
                logger.info("⏭️ 跳过此修复")

        logger.info("\n" + "=" * 60)
        logger.info("🏁 自动修复工作流完成")
        logger.info("=" * 60)

    def shutdown(self) -> None:
        """关闭系统"""
        logger.info("关闭 Agent Teams 系统...")

        self.orchestrator.shutdown()
        self.diagnostic_agent.shutdown()
        self.code_agent.shutdown()
        self.human_agent.shutdown()

        self.message_bus.stop()

        logger.info("Agent Teams 系统已关闭")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🤖 Agent Teams 系统测试")
    print("=" * 60)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    system = AgentTeamsSystem(project_root)

    try:
        system.initialize()

        print("\n选择运行模式:")
        print("1. 仅诊断 (查看问题)")
        print("2. 自动修复 (需要确认)")
        print("3. 完全自动修复 (无需确认)")
        print("4. 退出")

        choice = input("\n请选择 [1-4]: ").strip()

        if choice == "1":
            system.run_diagnosis()
        elif choice == "2":
            system.run_auto_repair_workflow(auto_confirm=False)
        elif choice == "3":
            system.run_auto_repair_workflow(auto_confirm=True)
        elif choice == "4":
            print("退出...")
        else:
            print("无效选择，运行诊断模式...")
            system.run_diagnosis()

    except KeyboardInterrupt:
        print("\n\n用户中断...")
    finally:
        system.shutdown()


if __name__ == "__main__":
    main()
