"""
决策可视化器 (DecisionVisualizer) 单元测试
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.plugins.dashboard.decision_visualizer import DecisionVisualizer, PlotStyle


class TestPlotStyle:
    """测试绘图样式枚举"""

    def test_style_values(self):
        """测试枚举值"""
        assert PlotStyle.CIRCLE.value == "circle"
        assert PlotStyle.ARC.value == "arc"
        assert PlotStyle.TRIANGLE.value == "triangle"
        assert PlotStyle.CHANNEL.value == "channel"
        assert PlotStyle.RECTANGLE.value == "rectangle"
        assert PlotStyle.STATE_MARKER.value == "state_marker"

    def test_style_members(self):
        """测试枚举成员数量"""
        assert len(list(PlotStyle)) == 6


class TestDecisionVisualizer:
    """测试决策可视化器"""

    def test_initialization(self):
        """测试初始化"""
        visualizer = DecisionVisualizer()
        assert visualizer is not None
        assert hasattr(visualizer, "config")
        assert hasattr(visualizer, "snapshot_dir")

    def test_initialization_with_custom_config(self):
        """测试自定义配置初始化"""
        custom_config = {
            "snapshot_dir": "/custom/snapshots",
            "plot_candles": 100,
            "dpi": 200,
            "figsize": (20, 10),
        }
        visualizer = DecisionVisualizer(config=custom_config)
        assert visualizer.config["snapshot_dir"] == "/custom/snapshots"
        assert visualizer.config["plot_candles"] == 100
        assert visualizer.config["dpi"] == 200

    def test_default_config_values(self):
        """测试默认配置值"""
        visualizer = DecisionVisualizer()
        # 验证默认配置
        assert visualizer.plot_candles == 200
        assert visualizer.dpi == 150
        assert visualizer.figsize == (16, 9)

    def test_default_colors(self):
        """测试默认颜色配置"""
        visualizer = DecisionVisualizer()
        assert "candle_up" in visualizer.colors
        assert "candle_down" in visualizer.colors
        assert "price_line" in visualizer.colors
        assert "background" in visualizer.colors

    def test_snapshot_directory_creation(self, tmp_path):
        """测试快照目录创建"""
        custom_dir = str(tmp_path / "test_snapshots")
        config = {"snapshot_dir": custom_dir}
        visualizer = DecisionVisualizer(config=config)
        # 验证目录已创建
        assert os.path.exists(custom_dir)


class TestVisualizationOutput:
    """测试可视化输出功能"""

    def test_plot_style_enum_in_output(self):
        """测试绘图样式在输出中的应用"""
        # 验证 PlotStyle 可以用于条件判断
        styles = list(PlotStyle)
        assert PlotStyle.CIRCLE in styles
        assert PlotStyle.ARC in styles

    def test_color_config_access(self):
        """测试颜色配置访问"""
        visualizer = DecisionVisualizer()
        # 验证可以访问各种颜色
        assert visualizer.colors["circle_fit"] is not None
        assert visualizer.colors["arc_fit"] is not None
        assert visualizer.colors["triangle_fit"] is not None
