"""
可视化工具模块

提供 K 线图绘制和威科夫状态标注功能。

设计原则：
1. 使用 @error_handler 装饰器进行错误处理
2. 支持威科夫状态机的阶段标注
3. 可直接读取回测引擎输出
"""

import logging
from typing import Any

import pandas as pd

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


# 威科夫阶段颜色映射
WYCKOFF_COLORS = {
    "ACCUMULATION_A": "#4CAF50",  # 绿色 - 吸筹A
    "ACCUMULATION_B": "#8BC34A",  # 浅绿 - 吸筹B
    "ACCUMULATION_C": "#CDDC39",  # 黄绿 - 吸筹C
    "ACCUMULATION_D": "#FFEB3B",  # 黄色 - 吸筹D
    "ACCUMULATION_E": "#FFC107",  # 琥珀 - 吸筹E
    "DISTRIBUTION_A": "#F44336",  # 红色 - 派发A
    "DISTRIBUTION_B": "#E91E63",  # 粉色 - 派发B
    "DISTRIBUTION_C": "#9C27B0",  # 紫色 - 派发C
    "DISTRIBUTION_D": "#673AB7",  # 深紫 - 派发D
    "DISTRIBUTION_E": "#3F51B5",  # 靛蓝 - 派发E
    "TRENDING_UP": "#00BCD4",  # 青色 - 上涨趋势
    "TRENDING_DOWN": "#FF9800",  # 橙色 - 下跌趋势
    "UNKNOWN": "#9E9E9E",  # 灰色 - 未知
}


class WyckoffVisualizer:
    """
    威科夫可视化工具

    功能：
    1. 绘制 K 线图
    2. 标注威科夫状态阶段
    3. 标注关键事件
    """

    def __init__(self):
        """初始化可视化工具"""
        self.figures: list[Any] = []
        logger.info("WyckoffVisualizer initialized")

    @error_handler(logger=logger, reraise=False, default_return=None)
    def plot_candlestick(
        self,
        data: pd.DataFrame,
        title: str = "K线图",
        width: int = 1200,
        height: int = 600,
    ) -> Any:
        """
        绘制 K 线图

        Args:
            data: OHLCV 数据
            title: 图表标题
            width: 宽度
            height: 高度

        Returns:
            Plotly 图表对象
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            logger.warning("plotly 未安装")
            return None

        # 创建图表
        fig = make_subplots(
            rows=2,
            cols=1,
            row_heights=[0.7, 0.3],
            subplot_titles=("K线图", "成交量"),
            vertical_spacing=0.1,
        )

        # K 线
        fig.add_trace(
            go.Candlestick(
                x=data.index,
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                name="OHLC",
            ),
            row=1,
            col=1,
        )

        # 成交量
        colors = [
            "green" if data["close"].iloc[i] >= data["open"].iloc[i] else "red"
            for i in range(len(data))
        ]

        fig.add_trace(
            go.Bar(
                x=data.index,
                y=data["volume"],
                marker_color=colors,
                name="成交量",
            ),
            row=2,
            col=1,
        )

        # 布局
        fig.update_layout(
            title=title,
            width=width,
            height=height,
            showlegend=True,
            xaxis_rangeslider_visible=False,
        )

        self.figures.append(fig)

        return fig

    @error_handler(logger=logger, reraise=False)
    def add_wyckoff_markers(
        self,
        fig: Any,
        states: list[dict[str, Any]],
    ) -> Any:
        """
        在图表上添加威科夫状态标注

        Args:
            fig: Plotly 图表对象
            states: 状态列表

        Returns:
            更新后的图表
        """
        try:
            import plotly.graph_objects as go
        except ImportError:
            return fig

        # 遍历状态，添加标注
        for state in states:
            timestamp = state.get("timestamp")
            state_name = state.get("state", "UNKNOWN")
            confidence = state.get("confidence", 0.0)

            # 获取颜色
            color = WYCKOFF_COLORS.get(state_name, WYCKOFF_COLORS["UNKNOWN"])

            # 添加箭头标注
            fig.add_trace(
                go.Scatter(
                    x=[timestamp],
                    y=[state.get("price", 0)],
                    mode="markers+text",
                    marker=dict(
                        symbol="arrow-up"
                        if "ACCUMULATION" in state_name
                        else "arrow-down",
                        size=20,
                        color=color,
                    ),
                    text=[state_name.replace("_", " ")],
                    textposition="top center",
                    name=state_name,
                    showlegend=False,
                ),
                row=1,
                col=1,
            )

        return fig

    @error_handler(logger=logger, reraise=False)
    def add_trade_markers(
        self,
        fig: Any,
        trades: list[Any],
    ) -> Any:
        """
        在图表上添加交易标注

        Args:
            fig: Plotly 图表对象
            trades: 交易列表

        Returns:
            更新后的图表
        """
        try:
            import plotly.graph_objects as go
        except ImportError:
            return fig

        # 买入点
        buy_times = [t.timestamp for t in trades if t.direction == "BUY"]
        buy_prices = [t.price for t in trades if t.direction == "BUY"]

        fig.add_trace(
            go.Scatter(
                x=buy_times,
                y=buy_prices,
                mode="markers",
                marker=dict(
                    symbol="triangle-up",
                    size=15,
                    color="green",
                ),
                name="买入",
            ),
            row=1,
            col=1,
        )

        # 卖出点
        sell_times = [t.timestamp for t in trades if t.direction == "SELL"]
        sell_prices = [t.price for t in trades if t.direction == "SELL"]

        fig.add_trace(
            go.Scatter(
                x=sell_times,
                y=sell_prices,
                mode="markers",
                marker=dict(
                    symbol="triangle-down",
                    size=15,
                    color="red",
                ),
                name="卖出",
            ),
            row=1,
            col=1,
        )

        return fig

    @error_handler(logger=logger, reraise=False)
    def add_equity_curve(
        self,
        equity_curve: list[float],
        timestamps: list[Any],
        title: str = "权益曲线",
    ) -> Any:
        """
        绘制权益曲线

        Args:
            equity_curve: 权益列表
            timestamps: 时间戳列表
            title: 图表标题

        Returns:
            Plotly 图表对象
        """
        try:
            import plotly.graph_objects as go
        except ImportError:
            return None

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=equity_curve,
                mode="lines",
                fill="tozeroy",
                line=dict(color="blue", width=2),
                name="权益",
            )
        )

        fig.update_layout(
            title=title,
            xaxis_title="时间",
            yaxis_title="权益",
        )

        return fig

    @error_handler(logger=logger, reraise=False)
    def save_html(self, fig: Any, filename: str):
        """
        保存图表为 HTML

        Args:
            fig: Plotly 图表对象
            filename: 文件名
        """
        try:
            import os

            os.makedirs("exports/visualizations", exist_ok=True)
            filepath = f"exports/visualizations/{filename}"
            fig.write_html(filepath)
            logger.info(f"图表已保存: {filepath}")
        except Exception as e:
            logger.warning(f"保存图表失败: {e}")


__all__ = ["WYCKOFF_COLORS", "WyckoffVisualizer"]
