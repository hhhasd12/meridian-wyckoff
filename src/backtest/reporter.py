"""
回测报告生成模块

生成详细的中文回测报告，包含交易次数、胜率、回撤等核心数据。

设计原则：
1. 使用 @error_handler 装饰器进行错误处理
2. 详细的中文日志记录
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _setup_error_handler():
    """设置错误处理装饰器"""
    try:
        from src.utils.error_handler import error_handler

        return error_handler
    except ImportError:

        def error_handler_decorator(**kwargs):
            def decorator(func):
                return func

            return decorator

        return error_handler_decorator


error_handler = _setup_error_handler()


class BacktestReporter:
    """
    回测报告生成器

    功能：
    1. 生成详细的交易统计
    2. 生成中文报告
    3. 导出多种格式
    """

    def __init__(self):
        """初始化报告生成器"""
        logger.info("BacktestReporter initialized")

    @error_handler(logger=logger, reraise=False, default_return="")
    def generate_report(
        self,
        result: Any,
        title: str = "回测报告",
    ) -> str:
        """
        生成中文回测报告

        Args:
            result: BacktestResult 实例
            title: 报告标题

        Returns:
            格式化的报告字符串
        """
        lines = []

        # 标题
        lines.append("=" * 60)
        lines.append(f"{title:^60}")
        lines.append("=" * 60)
        lines.append("")

        # 生成时间
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 核心统计
        lines.append("-" * 60)
        lines.append("📊 核心统计")
        lines.append("-" * 60)
        lines.append(f"  总交易次数:    {result.total_trades} 次")
        lines.append(f"  盈利交易:      {result.winning_trades} 次")
        lines.append(f"  亏损交易:      {result.losing_trades} 次")
        lines.append(f"  胜率:          {result.win_rate:.2%}")
        lines.append(f"  总盈亏:         {result.total_pnl:.2f}")
        lines.append(f"  最大回撤:       {result.max_drawdown:.2%}")
        lines.append(f"  夏普比率:       {result.sharpe_ratio:.2f}")
        lines.append("")

        # 收益统计
        lines.append("-" * 60)
        lines.append("💰 收益统计")
        lines.append("-" * 60)

        if result.trades:
            pnls = [t.pnl for t in result.trades]
            avg_win = (
                sum(p for p in pnls if p > 0) / len([p for p in pnls if p > 0])
                if any(p > 0 for p in pnls)
                else 0
            )
            avg_loss = (
                sum(p for p in pnls if p < 0) / len([p for p in pnls if p < 0])
                if any(p < 0 for p in pnls)
                else 0
            )

            lines.append(f"  平均盈利:      {avg_win:.2f}")
            lines.append(f"  平均亏损:      {avg_loss:.2f}")
            lines.append(
                f"  盈亏比:        {abs(avg_win / avg_loss) if avg_loss != 0 else 0:.2f}"
            )
            lines.append(f"  期望收益:      {sum(pnls) / len(pnls):.2f}")

        lines.append("")

        # 交易明细
        lines.append("-" * 60)
        lines.append("📋 交易记录")
        lines.append("-" * 60)

        if result.trades:
            for i, trade in enumerate(result.trades, 1):
                pnl_str = f"+{trade.pnl:.2f}" if trade.pnl > 0 else f"{trade.pnl:.2f}"
                direction_str = "🟢 买入" if trade.direction == "BUY" else "🔴 卖出"
                lines.append(
                    f"  {i}. {direction_str} | "
                    f"价格: {trade.price:.2f} | "
                    f"数量: {trade.quantity:.4f} | "
                    f"盈亏: {pnl_str}"
                )

        lines.append("")

        # 结尾
        lines.append("=" * 60)
        lines.append("报告生成完毕")
        lines.append("=" * 60)

        report = "\n".join(lines)

        # 保存到文件
        self._save_report(report, title)

        return report

    def _save_report(self, report: str, title: str):
        """保存报告到文件"""
        try:
            filename = (
                f"reports/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            import os

            os.makedirs("reports", exist_ok=True)
            with open(filename, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"报告已保存到: {filename}")
        except Exception as e:
            logger.warning(f"保存报告失败: {e}")

    @error_handler(logger=logger, reraise=False, default_return={})
    def generate_summary(self, result: Any) -> dict[str, Any]:
        """
        生成摘要字典

        Args:
            result: BacktestResult 实例

        Returns:
            摘要字典
        """
        return {
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate": f"{result.win_rate:.2%}",
            "total_pnl": f"{result.total_pnl:.2f}",
            "max_drawdown": f"{result.max_drawdown:.2%}",
            "sharpe_ratio": f"{result.sharpe_ratio:.2f}",
        }


__all__ = ["BacktestReporter"]
