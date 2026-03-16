"""
Agent Teams 快速测试
非交互式诊断测试
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import DiagnosticAgent, CodeAgent
from src.visualization import ConsoleDashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test")


def main():
    print("\n" + "=" * 60)
    print("🤖 Agent Teams 快速诊断测试")
    print("=" * 60)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    diagnostic = DiagnosticAgent(
        agent_id="diagnostic",
        config={"project_root": project_root},
    )
    diagnostic.initialize()

    code_agent = CodeAgent(
        agent_id="code",
        config={"project_root": project_root},
    )
    code_agent.initialize()

    print("\n📊 运行系统诊断...")
    result = diagnostic.execute_task({"type": "diagnose"})

    if result.success:
        issues = result.output.get("issues", [])
        print(f"\n✅ 诊断完成，发现 {len(issues)} 个问题:\n")

        for i, issue in enumerate(issues, 1):
            severity = issue.get("severity", "unknown")
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")
            print(f"{i}. {icon} [{severity.upper()}] {issue.get('title')}")
            print(f"   位置: {issue.get('location', 'N/A')}")
            print(f"   描述: {issue.get('description', '')[:60]}...")
            print()

        dashboard = ConsoleDashboard()
        dashboard.update_state({
            "agents": {
                "diagnostic": diagnostic.get_status(),
                "code": code_agent.get_status(),
            },
            "issues": issues,
        })
        dashboard.render()

        print("\n" + "=" * 60)
        print("📋 问题详情预览 (第一个严重问题)")
        print("=" * 60)

        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        if critical_issues:
            issue = critical_issues[0]
            print(f"\n问题ID: {issue.get('issue_id')}")
            print(f"标题: {issue.get('title')}")
            print(f"严重程度: {issue.get('severity')}")
            print(f"类别: {issue.get('category')}")
            print(f"\n描述:\n{issue.get('description')}")
            print(f"\n位置: {issue.get('location')}")
            print(f"\n证据:")
            for e in issue.get("evidence", []):
                print(f"  - {e}")
            print(f"\n建议:")
            for s in issue.get("suggestions", []):
                print(f"  - {s}")

            print("\n" + "=" * 60)
            print("🔧 生成修复提案...")
            print("=" * 60)

            fix_result = code_agent.execute_task({
                "type": "generate_fix",
                "issue": issue,
            })

            if fix_result.success:
                print(f"\n提案ID: {fix_result.output.get('proposal_id')}")
                print(f"风险等级: {fix_result.output.get('risk_level')}")
                print(f"\n修复差异预览:")
                print("-" * 40)
                diff = fix_result.output.get("diff", "")
                if diff:
                    print(diff[:1000])
                    if len(diff) > 1000:
                        print("... (截断)")
                else:
                    print("(无差异)")
                print("-" * 40)
            else:
                print(f"生成修复提案失败: {fix_result.output.get('error')}")

    else:
        print(f"❌ 诊断失败: {result.error_message}")

    print("\n" + "=" * 60)
    print("🏁 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
