"""
简化版自动化回测框架测试
验证核心功能是否正常工作
"""

import sys
import os
import logging
from datetime import datetime
import numpy as np
import pandas as pd

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入核心模块
try:
    from src.core.wfa_backtester import WFABacktester
    from src.core.mistake_book import (
        MistakeBook,
        MistakeType,
        ErrorSeverity,
        ErrorPattern,
    )
    from src.core.self_correction_workflow import SelfCorrectionWorkflow
except ImportError as e:
    print(f"导入模块失败: {e}")
    sys.exit(1)

# 配置日志
logging.basicConfig(level=logging.WARNING)  # 减少日志输出


def create_simple_data():
    """创建简单测试数据"""
    dates = pd.date_range(end=datetime.now(), periods=100, freq="D")
    data = pd.DataFrame(
        {
            "open": np.random.randn(len(dates)).cumsum() + 100,
            "high": np.random.randn(len(dates)).cumsum() + 101,
            "low": np.random.randn(len(dates)).cumsum() + 99,
            "close": np.random.randn(len(dates)).cumsum() + 100,
            "volume": np.random.randint(1000, 10000, len(dates)),
        },
        index=dates,
    )
    return data


def simple_performance_evaluator(config, data):
    """简单性能评估函数"""
    return {
        "SHARPE_RATIO": np.random.uniform(0.5, 2.0),
        "MAX_DRAWDOWN": np.random.uniform(0.05, 0.2),
        "WIN_RATE": np.random.uniform(0.4, 0.7),
        "PROFIT_FACTOR": np.random.uniform(1.0, 2.0),
        "CALMAR_RATIO": np.random.uniform(0.5, 3.0),
        "STABILITY_SCORE": np.random.uniform(0.6, 0.9),
        "COMPOSITE_SCORE": np.random.uniform(0.5, 0.8),
    }


def test_basic_functionality():
    """测试基本功能"""
    print("测试自动化回测框架基本功能")
    print("=" * 50)

    # 1. 测试错题本
    print("\n1. 测试错题本...")
    mistake_book = MistakeBook({"max_records": 10})

    # 添加错误
    for i in range(5):
        mistake_book.record_mistake(
            mistake_type=MistakeType.STATE_MISJUDGMENT,
            severity=ErrorSeverity.MEDIUM,
            context={"test": i},
            expected="correct",
            actual="wrong",
            confidence_before=0.8,
            confidence_after=0.3,
            impact_score=0.5,
            module_name="test",
            timeframe="H4",
            patterns=[ErrorPattern.FREQUENT_FALSE_POSITIVE],
        )

    stats = mistake_book.get_statistics()
    print(f"   错题本: {stats['total_errors']} 个错误记录")

    # 2. 测试WFA回测引擎
    print("\n2. 测试WFA回测引擎...")
    backtester = WFABacktester(
        {
            "train_days": 30,
            "test_days": 10,
            "step_days": 5,
        }
    )

    baseline_config = {
        "weights": {"W": 0.3, "D": 0.2, "H4": 0.2, "H1": 0.15, "M15": 0.1, "M5": 0.05},
        "threshold": 0.7,
    }

    data = create_simple_data()
    backtester.initialize_with_baseline(
        baseline_config=baseline_config,
        historical_data=data,
        performance_evaluator=simple_performance_evaluator,
    )

    print(f"   WFA引擎初始化完成")

    # 3. 测试自我修正工作流
    print("\n3. 测试自我修正工作流...")
    workflow_config = {
        "initial_config": baseline_config,
        "min_errors_for_correction": 3,
        "max_mutations_per_cycle": 2,
    }

    workflow = SelfCorrectionWorkflow(
        config=workflow_config,
        mistake_book=mistake_book,
        wfa_backtester=backtester,
    )

    workflow.set_performance_evaluator(simple_performance_evaluator)
    workflow.set_historical_data(data)

    # 初始化WFA
    if workflow.initialize_wfa_baseline():
        print("   WFA基准配置初始化成功")
    else:
        print("   WFA基准配置初始化失败")
        return False

    # 运行修正周期
    print("\n4. 运行修正周期...")
    try:
        result = workflow.run_correction_cycle()
        print(f"   修正周期结果: {'成功' if result['success'] else '失败'}")
        print(f"   耗时: {result['duration_seconds']:.2f}秒")

        # 检查工作流状态
        status = workflow.get_workflow_status()
        print(f"   工作流状态: {status['current_stage']}")
        print(f"   修正历史: {status['correction_history_count']} 次")

        return result["success"]

    except Exception as e:
        print(f"   修正周期执行失败: {e}")
        return False


def main():
    """主函数"""
    print("自动化回测框架简化测试")
    print("=" * 50)

    try:
        success = test_basic_functionality()

        print("\n" + "=" * 50)
        if success:
            print("[PASS] 自动化回测框架基本功能测试通过")
            print("核心组件: 错题本、WFA回测引擎、自我修正工作流 正常工作")
        else:
            print("[FAIL] 自动化回测框架测试失败")

        return success

    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    np.random.seed(42)
    result = main()

    # 保存测试结果
    with open("simple_test_result.txt", "w") as f:
        f.write(f"测试时间: {datetime.now()}\n")
        f.write(f"测试结果: {'通过' if result else '失败'}\n")

    print(f"\n测试结果已保存到 simple_test_result.txt")
    sys.exit(0 if result else 1)
