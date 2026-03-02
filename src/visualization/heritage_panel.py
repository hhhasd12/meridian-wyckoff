"""
遗产分数可视化调试面板
解决遗产数学黑盒陷阱：实时显示Heritage Score来源和传递路径
"""

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class HeritageVisualizer:
    """
    遗产分数可视化器

    功能：
    1. 实时显示Heritage Score数值
    2. 可视化遗产系数传递路径
    3. 显示遗产分数来源（哪个父状态传递了多少强度）
    4. 历史遗产分数变化趋势
    5. 动态阈值监控
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.heritage_history: list[dict] = []
        self.threshold_history: list[dict] = []
        self.coefficient_history: list[dict] = []

        # 遗产系数配置（参数化，非黑盒）
        self.coefficients = {
            "sc_to_ar": self.config.get("sc_to_ar_coef", 0.8),  # SC → AR 传递系数
            "sc_to_st": self.config.get("sc_to_st_coef", 1.2),  # SC → ST 传递系数
            "ar_to_st": self.config.get("ar_to_st_coef", 0.7),  # AR → ST 传递系数
            "ar_to_test": self.config.get("ar_to_test_coef", 0.9),  # AR → Test 传递系数
            "decay_rate": self.config.get("decay_rate", 0.7),  # 默认衰减系数
        }

    def record_heritage_event(self, event: dict):
        """
        记录遗产事件

        Args:
            event: 包含以下字段的字典：
                - timestamp: 时间戳
                - state: 当前状态（如'SC', 'AR', 'ST'）
                - heritage_score: 遗产分数 [0, 1]
                - intensity: 本状态强度 [0, 1]
                - parent_states: 父状态列表 [{'state': 'PS', 'intensity': 0.8, 'contribution': 0.64}]
                - coefficient_used: 使用的系数 {'sc_to_ar': 0.8, ...}
                - confidence: 置信度 [0, 1]
        """
        self.heritage_history.append(event)

        # 限制历史记录长度
        if len(self.heritage_history) > 1000:
            self.heritage_history = self.heritage_history[-1000:]

    def record_threshold_event(self, event: dict):
        """
        记录动态阈值事件

        Args:
            event: 包含以下字段的字典：
                - timestamp: 时间戳
                - threshold_type: 阈值类型（如'pin_threshold', 'volume_threshold'）
                - base_value: 基础值
                - volatility_factor: 波动率因子
                - regime_factor: 市场体制因子
                - final_value: 最终值
                - regime: 当前市场体制
        """
        self.threshold_history.append(event)

    def record_coefficient_event(self, event: dict):
        """
        记录系数调整事件（用于进化跟踪）

        Args:
            event: 包含以下字段的字典：
                - timestamp: 时间戳
                - coefficient_name: 系数名称
                - old_value: 旧值
                - new_value: 新值
                - change_reason: 调整原因
                - performance_impact: 性能影响评估
        """
        self.coefficient_history.append(event)

    def create_heritage_dashboard(self, last_n: int = 50) -> go.Figure:
        """
        创建遗产分数仪表板

        Args:
            last_n: 显示最近N个事件

        Returns:
            Plotly Figure对象
        """
        if not self.heritage_history:
            return self._create_empty_figure("暂无遗产数据")

        # 准备数据
        recent_events = self.heritage_history[-last_n:]
        timestamps = [e["timestamp"] for e in recent_events]
        states = [e["state"] for e in recent_events]
        heritage_scores = [e["heritage_score"] for e in recent_events]
        intensities = [e["intensity"] for e in recent_events]
        confidences = [e.get("confidence", 0.0) for e in recent_events]

        # 创建子图
        fig = make_subplots(
            rows=3,
            cols=2,
            subplot_titles=(
                "遗产分数变化趋势",
                "状态强度与遗产分数对比",
                "遗产系数传递路径（最近事件）",
                "动态阈值监控",
                "置信度与遗产分数关系",
                "系数调整历史",
            ),
            vertical_spacing=0.12,
            horizontal_spacing=0.15,
        )

        # 1. 遗产分数变化趋势
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=heritage_scores,
                mode="lines+markers",
                name="遗产分数",
                line={"color": "blue", "width": 2},
                marker={"size": 8},
            ),
            row=1,
            col=1,
        )

        # 添加状态标记
        for i, state in enumerate(states):
            fig.add_annotation(
                x=timestamps[i],
                y=heritage_scores[i],
                text=state,
                showarrow=False,
                yshift=10,
                font={"size": 9},
                row=1,
                col=1,
            )

        # 2. 状态强度与遗产分数对比
        fig.add_trace(
            go.Scatter(
                x=intensities,
                y=heritage_scores,
                mode="markers",
                name="强度vs遗产",
                marker={
                    "size": 10,
                    "color": confidences,
                    "colorscale": "Viridis",
                    "showscale": True,
                    "colorbar": {"title": "置信度"},
                },
                text=states,
                hovertemplate="状态: %{text}<br>强度: %{x:.3f}<br>遗产分数: %{y:.3f}<br>置信度: %{marker.color:.3f}",
            ),
            row=1,
            col=2,
        )

        # 添加参考线
        fig.add_shape(
            type="line",
            x0=0,
            y0=0,
            x1=1,
            y1=1,
            line={"color": "gray", "width": 1, "dash": "dash"},
            row=1,
            col=2,
        )

        # 3. 遗产系数传递路径（最近事件）
        if recent_events:
            latest_event = recent_events[-1]
            self._add_heritage_path_trace(fig, latest_event, row=2, col=1)

        # 4. 动态阈值监控
        if self.threshold_history:
            self._add_threshold_monitor_trace(fig, row=2, col=2)

        # 5. 置信度与遗产分数关系
        fig.add_trace(
            go.Scatter(
                x=confidences,
                y=heritage_scores,
                mode="markers",
                name="置信度vs遗产",
                marker={
                    "size": 8,
                    "color": intensities,
                    "colorscale": "Plasma",
                    "showscale": True,
                    "colorbar": {"title": "强度"},
                },
                text=states,
                hovertemplate="状态: %{text}<br>置信度: %{x:.3f}<br>遗产分数: %{y:.3f}<br>强度: %{marker.color:.3f}",
            ),
            row=3,
            col=1,
        )

        # 6. 系数调整历史
        if self.coefficient_history:
            self._add_coefficient_history_trace(fig, row=3, col=2)

        # 更新布局
        fig.update_layout(
            height=1200,
            showlegend=False,
            title_text="遗产分数可视化调试面板",
            title_font_size=20,
        )

        # 更新坐标轴标签
        fig.update_xaxes(title_text="时间", row=1, col=1)
        fig.update_yaxes(title_text="遗产分数", row=1, col=1)
        fig.update_xaxes(title_text="状态强度", row=1, col=2)
        fig.update_yaxes(title_text="遗产分数", row=1, col=2)
        fig.update_xaxes(title_text="置信度", row=3, col=1)
        fig.update_yaxes(title_text="遗产分数", row=3, col=1)

        return fig

    def _add_heritage_path_trace(self, fig: go.Figure, event: dict, row: int, col: int):
        """添加遗产传递路径跟踪"""
        if "parent_states" not in event or not event["parent_states"]:
            return

        # 创建节点
        nodes = []
        node_labels = []

        # 添加父节点
        for parent in event["parent_states"]:
            nodes.append(
                {
                    "name": parent["state"],
                    "value": parent["intensity"],
                    "type": "parent",
                }
            )
            node_labels.append(f"{parent['state']} (强度: {parent['intensity']:.2f})")

        # 添加当前节点
        nodes.append(
            {
                "name": event["state"],
                "value": event["heritage_score"],
                "type": "current",
            }
        )
        node_labels.append(f"{event['state']} (遗产: {event['heritage_score']:.2f})")

        # 创建桑基图数据
        source = []
        target = []
        value = []

        for i, parent in enumerate(event["parent_states"]):
            source.append(i)  # 父节点索引
            target.append(len(event["parent_states"]))  # 当前节点索引
            value.append(parent["contribution"])

        # 添加桑基图跟踪
        fig.add_trace(
            go.Sankey(
                node={
                    "pad": 15,
                    "thickness": 20,
                    "line": {"color": "black", "width": 0.5},
                    "label": node_labels,
                    "color": ["blue"] * len(event["parent_states"]) + ["green"],
                },
                link={
                    "source": source,
                    "target": target,
                    "value": value,
                    "hovertemplate": "%{source.label} → %{target.label}<br>贡献度: %{value:.3f}<extra></extra>",
                },
            ),
            row=row,
            col=col,
        )

        # 更新子图标题
        fig.update_layout({f"xaxis{2 * (row - 1) + col}": {"title": "遗产传递路径"}})

    def _add_threshold_monitor_trace(self, fig: go.Figure, row: int, col: int):
        """添加动态阈值监控跟踪"""
        # 按阈值类型分组
        threshold_types = {e["threshold_type"] for e in self.threshold_history}

        for i, th_type in enumerate(list(threshold_types)[:5]):  # 最多显示5种阈值
            type_events = [
                e for e in self.threshold_history if e["threshold_type"] == th_type
            ]

            if len(type_events) < 2:
                continue

            timestamps = [e["timestamp"] for e in type_events[-50:]]
            final_values = [e["final_value"] for e in type_events[-50:]]
            base_values = [e["base_value"] for e in type_events[-50:]]

            # 添加最终值跟踪
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=final_values,
                    mode="lines",
                    name=f"{th_type} (最终)",
                    line={"width": 2},
                    legendgroup=f"group_{i}",
                ),
                row=row,
                col=col,
            )

            # 添加基础值跟踪
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=base_values,
                    mode="lines",
                    name=f"{th_type} (基础)",
                    line={"width": 1, "dash": "dash"},
                    legendgroup=f"group_{i}",
                    showlegend=(i == 0),  # 只在第一个阈值显示图例
                ),
                row=row,
                col=col,
            )

        fig.update_layout(
            {
                f"xaxis{2 * (row - 1) + col}": {"title": "时间"},
                f"yaxis{2 * (row - 1) + col}": {"title": "阈值数值"},
            }
        )

    def _add_coefficient_history_trace(self, fig: go.Figure, row: int, col: int):
        """添加系数调整历史跟踪"""
        # 按系数名称分组
        coeff_names = {e["coefficient_name"] for e in self.coefficient_history}

        for i, coeff_name in enumerate(list(coeff_names)[:6]):  # 最多显示6个系数
            coeff_events = [
                e
                for e in self.coefficient_history
                if e["coefficient_name"] == coeff_name
            ]

            if len(coeff_events) < 2:
                continue

            timestamps = [e["timestamp"] for e in coeff_events]
            values = [e["new_value"] for e in coeff_events]

            # 添加值跟踪
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=values,
                    mode="lines+markers",
                    name=coeff_name,
                    line={"width": 2},
                    marker={"size": 6},
                ),
                row=row,
                col=col,
            )

        fig.update_layout(
            {
                f"xaxis{2 * (row - 1) + col}": {"title": "时间"},
                f"yaxis{2 * (row - 1) + col}": {"title": "系数数值"},
            }
        )

    def _create_empty_figure(self, message: str) -> go.Figure:
        """创建空数据提示图"""
        fig = go.Figure()

        fig.add_annotation(
            text=message,
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 20},
        )

        fig.update_layout(
            title_text="遗产分数可视化调试面板",
            xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
        )

        return fig

    def get_coefficients_report(self) -> dict:
        """获取遗产系数报告"""
        return {
            "coefficients": self.coefficients,
            "last_updated": datetime.now(),
            "total_heritage_events": len(self.heritage_history),
            "total_threshold_events": len(self.threshold_history),
            "total_coefficient_events": len(self.coefficient_history),
        }

    def export_heritage_data(self, filepath: str):
        """导出遗产数据到CSV"""
        if not self.heritage_history:
            return

        df = pd.DataFrame(self.heritage_history)
        df.to_csv(filepath, index=False)


# 简单使用示例
if __name__ == "__main__":
    # 创建可视化器实例
    visualizer = HeritageVisualizer()

    # 模拟一些遗产事件
    import random
    from datetime import datetime, timedelta

    base_time = datetime.now()
    states = ["PS", "SC", "AR", "ST", "TEST", "LPS"]

    for i in range(20):
        timestamp = base_time + timedelta(hours=i)
        state = random.choice(states)
        intensity = random.random()
        heritage_score = intensity * random.uniform(0.7, 1.0)

        # 创建父状态（模拟）
        parent_states = []
        if i > 0:
            parent_state = random.choice(states)
            parent_intensity = random.random()
            parent_contribution = parent_intensity * random.uniform(0.5, 0.9)

            parent_states.append(
                {
                    "state": parent_state,
                    "intensity": parent_intensity,
                    "contribution": parent_contribution,
                }
            )

        event = {
            "timestamp": timestamp,
            "state": state,
            "heritage_score": heritage_score,
            "intensity": intensity,
            "parent_states": parent_states,
            "coefficient_used": {"decay_rate": 0.7},
            "confidence": random.random(),
        }

        visualizer.record_heritage_event(event)

    # 模拟阈值事件
    for i in range(15):
        timestamp = base_time + timedelta(minutes=i * 30)
        visualizer.record_threshold_event(
            {
                "timestamp": timestamp,
                "threshold_type": random.choice(
                    ["pin_threshold", "volume_threshold", "body_threshold"]
                ),
                "base_value": random.uniform(1.0, 2.0),
                "volatility_factor": random.uniform(0.8, 1.5),
                "regime_factor": random.uniform(0.9, 1.1),
                "final_value": random.uniform(1.2, 3.0),
                "regime": random.choice(["TRENDING", "RANGING", "VOLATILE"]),
            }
        )

    # 生成仪表板
    fig = visualizer.create_heritage_dashboard(last_n=15)

    # 保存为HTML文件（在Jupyter中可以直接显示）
    fig.write_html("heritage_dashboard.html")

    # 打印系数报告
    report = visualizer.get_coefficients_report()
    for name, value in report["coefficients"].items():
        pass
