"""
决策可视化模块 - 为SystemOrchestrator提供几何拟合和状态决策的可视化

核心功能：
1. 在tr_detector识别新Trading Range或state_machine状态改变时触发绘图
2. 绘制最近200根K线
3. 可视化GeometricAnalyzer识别出的几何形状（圆、圆弧、三角形、通道线）
4. 标注当前威科夫状态
5. 自动保存图片到logs/snapshots目录
"""

import logging
import os
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.patches import Arc, Circle, Polygon, Rectangle

# 导入几何分析相关模块（已迁移到 pattern_detection 插件）
from src.plugins.pattern_detection.curve_boundary import GeometricAnalyzer

logger = logging.getLogger(__name__)


class PlotStyle(Enum):
    """绘图样式枚举"""

    CIRCLE = "circle"
    ARC = "arc"
    TRIANGLE = "triangle"
    CHANNEL = "channel"
    RECTANGLE = "rectangle"
    STATE_MARKER = "state_marker"


class DecisionVisualizer:
    """
    决策可视化器

    主要功能：
    - 在关键决策点（TR识别、状态变化）自动生成可视化图表
    - 展示几何拟合结果，验证算法准确性
    - 提供黑盒透明度，消除系统决策的不确定性
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        初始化决策可视化器

        Args:
            config: 配置参数
                - snapshot_dir: 快照保存目录
                - plot_candles: 绘制的K线数量
                - colors: 颜色配置字典
                - dpi: 图片DPI
                - figsize: 图片尺寸
        """
        self.config = config or {}

        # 设置快照目录
        self.snapshot_dir = self.config.get(
            "snapshot_dir",
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "logs",
                "snapshots",
            ),
        )

        # 确保目录存在
        os.makedirs(self.snapshot_dir, exist_ok=True)

        # 绘图配置
        self.plot_candles = self.config.get("plot_candles", 200)
        self.dpi = self.config.get("dpi", 150)
        self.figsize = self.config.get("figsize", (16, 9))

        # 颜色配置
        self.colors = self.config.get(
            "colors",
            {
                "candle_up": "#26A69A",  # 上涨K线颜色
                "candle_down": "#EF5350",  # 下跌K线颜色
                "price_line": "#2196F3",  # 价格线颜色
                "circle_fit": "#FF9800",  # 圆拟合颜色
                "arc_fit": "#9C27B0",  # 圆弧拟合颜色
                "triangle_fit": "#4CAF50",  # 三角形拟合颜色
                "channel_fit": "#FF5722",  # 通道线拟合颜色
                "rectangle_fit": "#795548",  # 矩形区间颜色
                "support_line": "#3F51B5",  # 支撑线颜色
                "resistance_line": "#F44336",  # 阻力线颜色
                "state_marker": "#FFEB3B",  # 状态标记颜色
                "background": "#1E1E1E",  # 背景颜色
                "grid": "#424242",  # 网格颜色
                "text": "#E0E0E0",  # 文本颜色
            },
        )

        # 几何分析器
        self.geometric_analyzer = GeometricAnalyzer()

        logger.info(f"DecisionVisualizer初始化完成，快照目录: {self.snapshot_dir}")

    def create_snapshot_filename(
        self,
        symbol: str,
        signal: str,
        pattern: str,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """
        创建快照文件名

        Args:
            symbol: 交易对符号
            signal: 信号类型（BUY/SELL/HOLD）
            pattern: 识别出的模式
            timestamp: 时间戳

        Returns:
            完整的文件路径
        """
        if timestamp is None:
            timestamp = datetime.now()

        # 格式化时间戳
        # 修复：时间戳可能是int64类型，需要转换为datetime对象
        if isinstance(timestamp, (int, np.integer)):
            # 如果是整数时间戳（Unix毫秒），转换为datetime
            timestamp_dt = datetime.fromtimestamp(float(timestamp) / 1000.0)
            time_str = timestamp_dt.strftime("%Y%m%d_%H%M%S")
        else:
            # 如果是datetime对象，直接格式化
            time_str = timestamp.strftime("%Y%m%d_%H%M%S")

        # 清理交易对符号（移除特殊字符，特别是斜杠）
        safe_symbol = symbol.replace("/", "_").replace("\\", "_").replace(" ", "_")

        # 清理模式名称（移除特殊字符）
        pattern_clean = pattern.replace(" ", "_").replace("/", "_").replace("\\", "_")

        # 构建文件名
        filename = f"{time_str}_{safe_symbol}_{signal}_{pattern_clean}.png"

        return os.path.join(self.snapshot_dir, filename)

    def plot_candlestick(
        self, ax: Axes, data: pd.DataFrame, start_idx: int = 0
    ) -> None:
        """
        绘制K线图

        Args:
            ax: matplotlib坐标轴
            data: K线数据DataFrame
            start_idx: 起始索引
        """
        # 确保有足够的数据
        if len(data) < 2:
            logger.warning(f"数据不足，无法绘制K线图: {len(data)}根K线")
            return

        # 计算要绘制的数据范围
        end_idx = min(start_idx + self.plot_candles, len(data))
        plot_data = data.iloc[start_idx:end_idx].copy()

        if len(plot_data) == 0:
            logger.warning("没有数据可绘制")
            return

        # 重置索引以便绘图
        plot_data = plot_data.reset_index(drop=True)

        # 绘制K线
        for i, (idx, row) in enumerate(plot_data.iterrows()):
            # 确定K线颜色
            if row["close"] >= row["open"]:
                color = self.colors["candle_up"]
                body_bottom = row["open"]
                body_top = row["close"]
            else:
                color = self.colors["candle_down"]
                body_bottom = row["close"]
                body_top = row["open"]

            # 绘制K线实体
            ax.add_patch(
                Rectangle(
                    (i - 0.3, body_bottom),  # (x, y)
                    0.6,  # width
                    body_top - body_bottom,  # height
                    color=color,
                    alpha=0.7,
                )
            )

            # 绘制上下影线
            ax.plot([i, i], [row["low"], body_bottom], color=color, linewidth=1)
            ax.plot([i, i], [body_top, row["high"]], color=color, linewidth=1)

        # 绘制价格线
        ax.plot(
            plot_data["close"].values,
            color=self.colors["price_line"],
            linewidth=1,
            alpha=0.5,
            label="Price",
        )

    def plot_geometric_shapes(
        self,
        ax: Axes,
        geometric_results: dict[str, Any],
        data: pd.DataFrame,
        start_idx: int = 0,
    ) -> None:
        """
        绘制几何形状

        Args:
            ax: matplotlib坐标轴
            geometric_results: 几何分析结果
            data: K线数据
            start_idx: 起始索引
        """
        if not geometric_results:
            return

        # 计算数据范围
        end_idx = min(start_idx + self.plot_candles, len(data))
        plot_data = data.iloc[start_idx:end_idx].copy()

        if len(plot_data) == 0:
            return

        # 获取价格范围用于缩放
        price_min = plot_data["low"].min()
        price_max = plot_data["high"].max()
        price_range = price_max - price_min

        # 绘制圆拟合
        if "circle_fit" in geometric_results:
            circle_data = geometric_results["circle_fit"]
            if circle_data.get("success", False):
                circle_data.get("center_x", 0)
                center_y = circle_data.get("center_y", 0)
                radius = circle_data.get("radius", 0)

                # 转换为绘图坐标
                plot_center_x = len(plot_data) / 2  # 居中显示
                plot_radius = radius / (price_range / 10)  # 缩放半径

                circle = Circle(
                    (plot_center_x, center_y),
                    plot_radius,
                    color=self.colors["circle_fit"],
                    fill=False,
                    linewidth=2,
                    linestyle="--",
                    label="Circle Fit",
                )
                ax.add_patch(circle)

        # 绘制圆弧
        if "arc_fit" in geometric_results:
            arc_data = geometric_results["arc_fit"]
            if arc_data.get("success", False):
                arc_data.get("center_x", 0)
                center_y = arc_data.get("center_y", 0)
                radius = arc_data.get("radius", 0)
                start_angle = arc_data.get("start_angle", 0)
                end_angle = arc_data.get("end_angle", 180)

                # 转换为绘图坐标
                plot_center_x = len(plot_data) / 2
                plot_radius = radius / (price_range / 10)

                arc = Arc(
                    (plot_center_x, center_y),
                    width=plot_radius * 2,
                    height=plot_radius * 2,
                    angle=0,
                    theta1=start_angle,
                    theta2=end_angle,
                    color=self.colors["arc_fit"],
                    linewidth=2,
                    linestyle="-",
                    label="Arc Fit",
                )
                ax.add_patch(arc)

        # 绘制三角形
        if "triangle_fit" in geometric_results:
            triangle_data = geometric_results["triangle_fit"]
            if triangle_data.get("success", False):
                vertices = triangle_data.get("vertices", [])
                if len(vertices) >= 3:
                    # 转换为绘图坐标
                    plot_vertices = []
                    for v in vertices[:3]:  # 取前三个顶点
                        if len(v) >= 2:
                            # 调整x坐标到绘图范围
                            x_ratio = v[0] / len(data) if len(data) > 0 else 0
                            plot_x = x_ratio * len(plot_data)
                            plot_vertices.append([plot_x, v[1]])

                    if len(plot_vertices) == 3:
                        triangle = Polygon(
                            plot_vertices,
                            closed=True,
                            color=self.colors["triangle_fit"],
                            fill=False,
                            linewidth=2,
                            linestyle="-",
                            alpha=0.7,
                            label="Triangle Fit",
                        )
                        ax.add_patch(triangle)

        # 绘制通道线
        if "channel_fit" in geometric_results:
            channel_data = geometric_results["channel_fit"]
            if channel_data.get("success", False):
                upper_slope = channel_data.get("upper_slope", 0)
                upper_intercept = channel_data.get("upper_intercept", 0)
                lower_slope = channel_data.get("lower_slope", 0)
                lower_intercept = channel_data.get("lower_intercept", 0)

                # 绘制上下通道线
                x_points = np.array([0, len(plot_data)])
                upper_line = upper_slope * x_points + upper_intercept
                lower_line = lower_slope * x_points + lower_intercept

                ax.plot(
                    x_points,
                    upper_line,
                    color=self.colors["channel_fit"],
                    linewidth=2,
                    linestyle="--",
                    label="Channel Upper",
                )
                ax.plot(
                    x_points,
                    lower_line,
                    color=self.colors["channel_fit"],
                    linewidth=2,
                    linestyle="--",
                    label="Channel Lower",
                )

        # 绘制支撑阻力线
        if "support_levels" in geometric_results:
            support_levels = geometric_results["support_levels"]
            for level in support_levels:
                ax.axhline(
                    y=level,
                    color=self.colors["support_line"],
                    linewidth=1,
                    linestyle=":",
                    alpha=0.5,
                )

        if "resistance_levels" in geometric_results:
            resistance_levels = geometric_results["resistance_levels"]
            for level in resistance_levels:
                ax.axhline(
                    y=level,
                    color=self.colors["resistance_line"],
                    linewidth=1,
                    linestyle=":",
                    alpha=0.5,
                )

    def plot_state_marker(
        self, ax: Axes, state_info: dict[str, Any], data: pd.DataFrame
    ) -> None:
        """
        绘制状态标记

        Args:
            ax: matplotlib坐标轴
            state_info: 状态机信息
            data: K线数据
        """
        if not state_info:
            return

        # 获取当前状态
        current_state = state_info.get("current_state", "UNKNOWN")
        state_confidence = state_info.get("state_confidence", 0.0)

        # 在图表右上角添加状态标记
        last_price = data.iloc[-1]["close"] if len(data) > 0 else 0
        price_min = data["low"].min() if len(data) > 0 else 0
        price_max = data["high"].max() if len(data) > 0 else 1

        # 计算标记位置（价格范围的上部）
        price_max - (price_max - price_min) * 0.1

        # 添加状态文本
        state_text = f"State: {current_state}\nConfidence: {state_confidence:.1%}"
        ax.text(
            0.98,  # x位置（相对坐标，0-1）
            0.95,  # y位置（相对坐标，0-1）
            state_text,
            transform=ax.transAxes,
            fontsize=12,
            verticalalignment="top",
            horizontalalignment="right",
            bbox={
                "boxstyle": "round,pad=0.5",
                "facecolor": self.colors["state_marker"],
                "alpha": 0.8,
                "edgecolor": "white",
            },
            color="black",
        )

        # 在最新K线位置添加状态标记点
        if len(data) > 0:
            ax.scatter(
                [len(data) - 1],  # x坐标（最新K线）
                [last_price],  # y坐标（最新价格）
                color=self.colors["state_marker"],
                s=100,  # 点的大小
                marker="o",
                edgecolors="black",
                linewidths=2,
                zorder=10,  # 确保在最上层
                label=f"Current State: {current_state}",
            )

    def create_visualization(
        self,
        data: pd.DataFrame,
        symbol: str,
        signal: str,
        geometric_results: Optional[dict[str, Any]] = None,
        state_info: Optional[dict[str, Any]] = None,
        tr_info: Optional[dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
        timeframe: Optional[str] = None,
    ) -> str:
        """
        创建完整的可视化图表

        Args:
            data: K线数据DataFrame
            symbol: 交易对符号
            signal: 信号类型
            geometric_results: 几何分析结果
            state_info: 状态机信息
            tr_info: 交易区间信息
            timestamp: 时间戳
            timeframe: 时间周期（如1H, 4H, 1D等）

        Returns:
            保存的图片文件路径
        """
        try:
            # 创建图形
            fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

            # 设置暗色主题
            fig.patch.set_facecolor(self.colors["background"])
            ax.set_facecolor(self.colors["background"])

            # 绘制K线图
            self.plot_candlestick(ax, data)

            # 绘制几何形状
            if geometric_results:
                self.plot_geometric_shapes(ax, geometric_results, data)

            # 绘制状态标记
            if state_info:
                self.plot_state_marker(ax, state_info, data)

            # 动态设置X轴范围 - 只显示实际绘制的K线范围
            # 计算实际绘制的K线数量
            plot_candles_count = min(self.plot_candles, len(data))

            # 设置X轴范围，留出一些边距
            x_margin = plot_candles_count * 0.05  # 5%的边距
            ax.set_xlim(-x_margin, plot_candles_count - 1 + x_margin)

            # 设置图表属性
            # 构建标题，包含时间周期信息
            title_parts = [f"Wyckoff Decision Visualization - {symbol}"]
            if timeframe:
                title_parts.append(f"[{timeframe}]")
            if signal and signal != "HOLD":
                title_parts.append(f"Signal: {signal}")

            title = " ".join(title_parts)
            ax.set_title(
                title,
                color=self.colors["text"],
                fontsize=16,
                pad=20,
            )

            ax.set_xlabel("Candle Index", color=self.colors["text"], fontsize=12)
            ax.set_ylabel("Price", color=self.colors["text"], fontsize=12)

            # 设置网格
            ax.grid(True, color=self.colors["grid"], alpha=0.3, linestyle="--")

            # 设置坐标轴颜色
            ax.tick_params(colors=self.colors["text"])
            ax.spines["bottom"].set_color(self.colors["text"])
            ax.spines["top"].set_color(self.colors["text"])
            ax.spines["left"].set_color(self.colors["text"])
            ax.spines["right"].set_color(self.colors["text"])

            # 添加图例
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(
                    handles,
                    labels,
                    loc="upper left",
                    facecolor=self.colors["background"],
                    edgecolor=self.colors["text"],
                    labelcolor=self.colors["text"],
                )

            # 自动调整布局
            plt.tight_layout()

            # 确定模式名称
            pattern = "Unknown"
            if geometric_results:
                if "circle_fit" in geometric_results and geometric_results[
                    "circle_fit"
                ].get("success", False):
                    pattern = "Circle"
                elif "arc_fit" in geometric_results and geometric_results[
                    "arc_fit"
                ].get("success", False):
                    pattern = "Arc"
                elif "triangle_fit" in geometric_results and geometric_results[
                    "triangle_fit"
                ].get("success", False):
                    pattern = "Triangle"
                elif "channel_fit" in geometric_results and geometric_results[
                    "channel_fit"
                ].get("success", False):
                    pattern = "Channel"

            # 创建文件名并保存（确保目录存在）
            filename = self.create_snapshot_filename(symbol, signal, pattern, timestamp)
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            plt.savefig(filename, dpi=self.dpi, bbox_inches="tight")
            plt.close(fig)

            logger.info(f"决策可视化图表已保存: {filename}")
            return filename

        except Exception as e:
            logger.error(f"创建可视化图表时出错: {e}", exc_info=True)
            return ""

    def visualize_tr_detection(
        self,
        data: pd.DataFrame,
        symbol: str,
        tr_result: dict[str, Any],
        geometric_analyzer: Optional[GeometricAnalyzer] = None,
        timeframe: Optional[str] = None,
    ) -> str:
        """
        专门为TR检测结果创建可视化

        Args:
            data: K线数据
            symbol: 交易对符号
            tr_result: TR检测结果
            geometric_analyzer: 几何分析器实例

        Returns:
            保存的图片文件路径
        """
        # 从TR结果中提取几何信息
        geometric_results = {}

        if tr_result.get("detected", False):
            # 尝试从TR结果中提取边界点进行几何分析
            boundaries = tr_result.get("boundaries", {})

            if geometric_analyzer and boundaries:
                # 这里可以添加具体的几何分析逻辑
                # 例如：boundary_points = boundaries.get("points", [])
                # geometric_results = geometric_analyzer.analyze_boundary(boundary_points)
                pass

        # 确定信号类型
        signal = "HOLD"
        if tr_result.get("breakout_direction") == "up":
            signal = "BUY"
        elif tr_result.get("breakout_direction") == "down":
            signal = "SELL"

        # 创建可视化
        return self.create_visualization(
            data=data,
            symbol=symbol,
            signal=signal,
            geometric_results=geometric_results,
            tr_info=tr_result,
            timeframe=timeframe,
        )

    def visualize_state_change(
        self,
        data: pd.DataFrame,
        symbol: str,
        state_info: dict[str, Any],
        previous_state: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> str:
        """
        专门为状态变化创建可视化

        Args:
            data: K线数据
            symbol: 交易对符号
            state_info: 新状态信息
            previous_state: 之前的状态

        Returns:
            保存的图片文件路径
        """
        # 确定信号类型
        signal = "HOLD"
        current_state = state_info.get("current_state", "")

        # 根据状态确定信号
        if "ACCUMULATION" in current_state or "MARKUP" in current_state:
            signal = "BUY"
        elif "DISTRIBUTION" in current_state or "MARKDOWN" in current_state:
            signal = "SELL"

        # 创建可视化
        return self.create_visualization(
            data=data,
            symbol=symbol,
            signal=signal,
            state_info=state_info,
            timeframe=timeframe,
        )


# 便捷函数
def create_decision_visualizer(
    config: Optional[dict[str, Any]] = None,
) -> DecisionVisualizer:
    """创建决策可视化器实例"""
    return DecisionVisualizer(config)
