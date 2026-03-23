"""
曲线边界拟合模块（Pivot Spline Fitting）
解决几何拟合代码缺失问题：识别圆弧底、收敛三角形等非线性TR边界
"""

import logging
import math
import warnings
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd
from numpy import typing as npt
from scipy.interpolate import UnivariateSpline
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)


class BoundaryType(Enum):
    """边界类型枚举"""

    ARC_BOTTOM = "ARC_BOTTOM"  # 圆弧底
    ARC_TOP = "ARC_TOP"  # 圆弧顶
    TRIANGLE_SYMMETRICAL = "TRIANGLE_SYMMETRICAL"  # 对称三角形
    TRIANGLE_ASCENDING = "TRIANGLE_ASCENDING"  # 上升三角形
    TRIANGLE_DESCENDING = "TRIANGLE_DESCENDING"  # 下降三角形
    CHANNEL_UP = "CHANNEL_UP"  # 上升通道
    CHANNEL_DOWN = "CHANNEL_DOWN"  # 下降通道
    RECTANGLE = "RECTANGLE"  # 矩形区间
    UNKNOWN = "UNKNOWN"  # 未知类型


class GeometricAnalyzer:
    """
    几何分析器 - 实现真正的几何形状识别算法
    解决审计报告中指出的几何拟合代码缺失问题
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self.circle_fit_threshold = self.config.get("circle_fit_threshold", 0.8)
        self.arc_angle_threshold = self.config.get(
            "arc_angle_threshold", 90
        )  # 最小圆弧角度（度）
        self.triangle_convergence_angle = self.config.get(
            "triangle_convergence_angle", 15
        )  # 三角形收敛角度阈值

    def fit_circle(self, points: npt.NDArray[np.float64]) -> dict[str, Any]:
        """
        拟合圆到一组点

        Args:
            points: Nx2数组，每行是(x, y)坐标

        Returns:
            包含圆心、半径、拟合误差的字典
        """
        if len(points) < 3:
            return {"success": False, "error": "至少需要3个点拟合圆"}

        try:
            # 转换为齐次坐标
            x = points[:, 0]
            y = points[:, 1]

            # 最小二乘法拟合圆
            # 圆方程: (x - a)² + (y - b)² = r²
            # 展开: x² + y² - 2ax - 2by + (a² + b² - r²) = 0
            # 令 c = a² + b² - r²
            # 则方程: x² + y² - 2ax - 2by + c = 0

            # 构建线性方程组
            A = np.column_stack([-2 * x, -2 * y, np.ones_like(x)])
            B = -(x**2 + y**2)

            # 求解最小二乘解
            solution, _residuals, _rank, _s = np.linalg.lstsq(A, B, rcond=None)

            a, b, c = solution
            r = np.sqrt(a**2 + b**2 - c)

            # 计算拟合误差
            distances = np.sqrt((x - a) ** 2 + (y - b) ** 2)
            errors = np.abs(distances - r)
            avg_error = np.mean(errors)
            max_error = np.max(errors)

            # 计算拟合质量（R²）
            # 对于圆拟合，使用距离的方差作为总平方和
            ss_res = np.sum(errors**2)

            # 如果所有点都在完美的圆上，误差为0，SS_tot可能为0
            if ss_res < 1e-10:  # 几乎完美拟合
                r_squared = 1.0
            else:
                ss_tot = np.sum((distances - np.mean(distances)) ** 2)
                if ss_tot > 1e-10:
                    r_squared = 1 - (ss_res / ss_tot)
                    # 限制R²在[0, 1]范围内
                    r_squared = max(0, min(1, r_squared))
                else:
                    r_squared = 1.0  # 所有点距离相同，完美拟合

            return {
                "success": True,
                "center_x": a,
                "center_y": b,
                "radius": r,
                "r_squared": r_squared,
                "avg_error": avg_error,
                "max_error": max_error,
                "points_count": len(points),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def detect_arc(self, points: npt.NDArray[np.float64]) -> dict[str, Any]:
        """
        检测圆弧

        Args:
            points: Nx2数组，每行是(x, y)坐标

        Returns:
            圆弧检测结果
        """
        if len(points) < 5:
            return {"is_arc": False, "reason": "点数不足"}

        # 拟合圆
        circle_result = self.fit_circle(points)

        if not circle_result["success"]:
            return {"is_arc": False, "reason": "圆拟合失败"}

        # 检查拟合质量
        if circle_result["r_squared"] < self.circle_fit_threshold:
            return {
                "is_arc": False,
                "reason": f"拟合质量不足: {circle_result['r_squared']:.3f}",
            }

        # 计算圆弧角度
        center_x = circle_result["center_x"]
        center_y = circle_result["center_y"]

        # 计算每个点相对于圆心的角度
        angles = []
        for x, y in points:
            dx = x - center_x
            dy = y - center_y
            angle = math.degrees(math.atan2(dy, dx))
            if angle < 0:
                angle += 360
            angles.append(angle)

        # 排序角度
        angles_sorted = sorted(angles)

        # 计算角度跨度
        angle_span = angles_sorted[-1] - angles_sorted[0]

        # 处理角度环绕
        if angle_span < 0:
            angle_span += 360

        # 检查是否构成有效圆弧
        if angle_span < self.arc_angle_threshold:
            return {"is_arc": False, "reason": f"角度跨度不足: {angle_span:.1f}度"}

        # 检查点是否按顺序排列（圆弧应该是连续的）
        angle_diffs = []
        for i in range(1, len(angles_sorted)):
            diff = angles_sorted[i] - angles_sorted[i - 1]
            if diff < 0:
                diff += 360
            angle_diffs.append(diff)

        # 最大角度间隔不应太大
        max_gap = max(angle_diffs) if angle_diffs else 0
        if max_gap > 60:  # 最大间隔不超过60度
            return {"is_arc": False, "reason": f"点不连续，最大间隔: {max_gap:.1f}度"}

        # 确定圆弧方向（凸或凹）
        # 计算点的凸包或使用简单方法判断
        is_convex = self._check_arc_convexity(points, center_x, center_y)

        return {
            "is_arc": True,
            "circle_result": circle_result,
            "angle_span": angle_span,
            "start_angle": angles_sorted[0],
            "end_angle": angles_sorted[-1],
            "is_convex": is_convex,
            "avg_angle_gap": np.mean(angle_diffs) if angle_diffs else 0,
            "max_angle_gap": max_gap,
        }

    def _check_arc_convexity(
        self, points: npt.NDArray[np.float64], center_x: float, center_y: float
    ) -> bool:
        """检查圆弧是凸的还是凹的"""
        if len(points) < 3:
            return True

        # 简单方法：计算点相对于圆心的平均距离变化
        distances = []
        for x, y in points:
            dist = math.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
            distances.append(dist)

        # 计算距离的变化趋势
        if len(distances) >= 3:
            # 检查距离是否单调变化
            increasing = all(
                distances[i] <= distances[i + 1] for i in range(len(distances) - 1)
            )
            decreasing = all(
                distances[i] >= distances[i + 1] for i in range(len(distances) - 1)
            )

            # 如果距离单调变化，可能是凸的；否则可能是凹的或复杂形状
            return increasing or decreasing
        return True

    def detect_triangle(
        self,
        upper_points: npt.NDArray[np.float64],
        lower_points: npt.NDArray[np.float64],
    ) -> dict[str, Any]:
        """
        检测三角形形态

        Args:
            upper_points: 上边界点
            lower_points: 下边界点

        Returns:
            三角形检测结果
        """
        if len(upper_points) < 3 or len(lower_points) < 3:
            return {"is_triangle": False, "reason": "边界点数不足"}

        # 拟合直线到上下边界
        upper_line = self.fit_line(upper_points)
        lower_line = self.fit_line(lower_points)

        if not upper_line["success"] or not lower_line["success"]:
            return {"is_triangle": False, "reason": "直线拟合失败"}

        # 计算两条直线的交点
        intersection = self._find_line_intersection(
            upper_line["slope"],
            upper_line["intercept"],
            lower_line["slope"],
            lower_line["intercept"],
        )

        if intersection is None:
            return {"is_triangle": False, "reason": "直线平行，无交点"}

        # 检查收敛性（交点应在合理范围内）
        # 计算交点相对于数据范围的x坐标
        all_x = np.concatenate([upper_points[:, 0], lower_points[:, 0]])
        x_min, x_max = np.min(all_x), np.max(all_x)
        x_range = x_max - x_min

        # 交点应在数据范围之外（收敛）
        intersection_x = intersection[0]

        # 计算收敛角度
        angle1 = math.degrees(math.atan(upper_line["slope"]))
        angle2 = math.degrees(math.atan(lower_line["slope"]))
        convergence_angle = abs(angle1 - angle2)

        # 确定三角形类型
        triangle_type = "UNKNOWN"
        if convergence_angle < self.triangle_convergence_angle:
            triangle_type = "SYMMETRICAL" if abs(angle1 + angle2) < 10 else "WEDGE"
        elif upper_line["slope"] < 0 and lower_line["slope"] > 0:
            triangle_type = "SYMMETRICAL"
        elif upper_line["slope"] < 0 and abs(lower_line["slope"]) < 0.1:
            triangle_type = "DESCENDING"
        elif lower_line["slope"] > 0 and abs(upper_line["slope"]) < 0.1:
            triangle_type = "ASCENDING"

        # 检查是否有效三角形
        is_valid = (
            convergence_angle > 5  # 最小收敛角度
            and convergence_angle < 60  # 最大收敛角度
            and (
                intersection_x > x_max + x_range * 0.1  # 向右收敛
                or intersection_x < x_min - x_range * 0.1
            )
        )  # 向左收敛

        return {
            "is_triangle": is_valid,
            "triangle_type": triangle_type,
            "convergence_angle": convergence_angle,
            "intersection": intersection,
            "upper_line": upper_line,
            "lower_line": lower_line,
            "x_range": (x_min, x_max),
            "intersection_offset": (intersection_x - x_max)
            if intersection_x > x_max
            else (intersection_x - x_min),
        }

    def fit_line(self, points: npt.NDArray[np.float64]) -> dict[str, Any]:
        """拟合直线到一组点"""
        if len(points) < 2:
            return {"success": False, "error": "至少需要2个点拟合直线"}

        try:
            x = points[:, 0]
            y = points[:, 1]

            # 最小二乘法拟合直线 y = mx + b
            A = np.vstack([x, np.ones_like(x)]).T
            m, b = np.linalg.lstsq(A, y, rcond=None)[0]

            # 计算拟合误差
            y_pred = m * x + b
            residuals = y - y_pred
            rss = np.sum(residuals**2)
            tss = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (rss / tss) if tss > 0 else 0

            return {
                "success": True,
                "slope": m,
                "intercept": b,
                "r_squared": r_squared,
                "avg_error": np.mean(np.abs(residuals)),
                "points_count": len(points),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _find_line_intersection(
        self, m1: float, b1: float, m2: float, b2: float
    ) -> Optional[tuple[float, float]]:
        """求两条直线的交点"""
        if abs(m1 - m2) < 1e-10:  # 平行线
            return None

        x = (b2 - b1) / (m1 - m2)
        y = m1 * x + b1
        return (x, y)

    def analyze_geometry(
        self,
        upper_points: npt.NDArray[np.float64],
        lower_points: npt.NDArray[np.float64],
    ) -> dict[str, Any]:
        """
        综合分析几何形状

        Args:
            upper_points: 上边界点
            lower_points: 下边界点

        Returns:
            几何分析结果
        """
        results = {
            "upper_arc": self.detect_arc(upper_points),
            "lower_arc": self.detect_arc(lower_points),
            "triangle": self.detect_triangle(upper_points, lower_points),
            "channel": self.analyze_channel(upper_points, lower_points),
        }

        # 确定主要几何形态
        primary_shape = "UNKNOWN"
        confidence = 0.0

        # 检查圆弧形态
        if results["upper_arc"]["is_arc"] and results["lower_arc"]["is_arc"]:
            # 双圆弧形态
            if (
                results["upper_arc"]["is_convex"]
                and not results["lower_arc"]["is_convex"]
            ):
                primary_shape = "ROUNDING_BOTTOM"
                confidence = min(
                    results["upper_arc"]["circle_result"]["r_squared"],
                    results["lower_arc"]["circle_result"]["r_squared"],
                )
            elif (
                not results["upper_arc"]["is_convex"]
                and results["lower_arc"]["is_convex"]
            ):
                primary_shape = "ROUNDING_TOP"
                confidence = min(
                    results["upper_arc"]["circle_result"]["r_squared"],
                    results["lower_arc"]["circle_result"]["r_squared"],
                )

        # 检查三角形形态
        elif results["triangle"]["is_triangle"]:
            primary_shape = f"TRIANGLE_{results['triangle']['triangle_type']}"
            confidence = min(
                results["triangle"]["upper_line"]["r_squared"],
                results["triangle"]["lower_line"]["r_squared"],
            )

        # 检查通道形态
        elif results["channel"]["is_channel"]:
            primary_shape = f"CHANNEL_{results['channel']['channel_type']}"
            confidence = results["channel"]["parallel_confidence"]

        return {
            "primary_shape": primary_shape,
            "confidence": confidence,
            "detailed_results": results,
        }

    def analyze_channel(
        self,
        upper_points: npt.NDArray[np.float64],
        lower_points: npt.NDArray[np.float64],
    ) -> dict[str, Any]:
        """
        分析通道形态

        Args:
            upper_points: 上边界点
            lower_points: 下边界点

        Returns:
            通道分析结果
        """
        if len(upper_points) < 3 or len(lower_points) < 3:
            return {"is_channel": False, "reason": "点数不足"}

        # 拟合直线到上下边界
        upper_line = self.fit_line(upper_points)
        lower_line = self.fit_line(lower_points)

        if not upper_line["success"] or not lower_line["success"]:
            return {"is_channel": False, "reason": "直线拟合失败"}

        # 检查平行度
        slope_diff = abs(upper_line["slope"] - lower_line["slope"])
        avg_slope = (upper_line["slope"] + lower_line["slope"]) / 2

        # 平行度阈值
        parallel_threshold = 0.1
        is_parallel = slope_diff < parallel_threshold

        if not is_parallel:
            return {
                "is_channel": False,
                "reason": f"边界不平行，斜率差: {slope_diff:.3f}",
            }

        # 检查间距一致性
        # 计算上下边界之间的平均距离
        distances = []
        for i in range(min(len(upper_points), len(lower_points))):
            dist = abs(upper_points[i, 1] - lower_points[i, 1])
            distances.append(dist)

        avg_distance = np.mean(distances)
        distance_std = np.std(distances)
        distance_cv = distance_std / avg_distance if avg_distance > 0 else 0

        # 通道类型
        channel_type = "HORIZONTAL"
        if avg_slope > 0.05:
            channel_type = "ASCENDING"
        elif avg_slope < -0.05:
            channel_type = "DESCENDING"

        # 通道质量评分
        parallel_confidence = 1.0 - (slope_diff / parallel_threshold)
        spacing_confidence = max(0, 1.0 - distance_cv * 2)  # 距离变异系数越小越好
        overall_confidence = (parallel_confidence + spacing_confidence) / 2

        return {
            "is_channel": True,
            "channel_type": channel_type,
            "parallel_confidence": parallel_confidence,
            "spacing_confidence": spacing_confidence,
            "overall_confidence": overall_confidence,
            "avg_slope": avg_slope,
            "avg_distance": avg_distance,
            "distance_cv": distance_cv,
            "upper_line": upper_line,
            "lower_line": lower_line,
        }


class CurveBoundaryFitter:
    """
    曲线边界拟合器

    功能：
    1. 检测枢轴点（局部高点和低点）
    2. 使用样条曲线拟合枢轴点
    3. 识别边界类型（圆弧形、三角形、通道等）
    4. 计算边界置信度和有效性
    5. 提供边界突破检测

    设计原则：
    1. 非线性拟合：识别圆弧底等非直线边界
    2. 多周期适应：适应不同时间框架的波动
    3. 噪声容忍：使用平滑处理减少假信号
    4. 实时计算：支持增量更新
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        初始化曲线边界拟合器

        Args:
            config: 配置字典，包含以下参数：
                - pivot_window: 枢轴点检测窗口（默认5）
                - min_pivot_distance: 枢轴点最小距离（默认10）
                - spline_smoothness: 样条曲线平滑度（默认0.5，0-1之间）
                - min_boundary_points: 边界识别最少点数（默认8）
                - arc_detection_threshold: 圆弧检测阈值（默认0.3）
                - triangle_convergence_threshold: 三角形收敛阈值（默认0.15）
                - channel_parallel_threshold: 通道平行度阈值（默认0.1）
        """
        self.config = config or {}
        self.pivot_window = self.config.get("pivot_window", 5)
        self.min_pivot_distance = self.config.get("min_pivot_distance", 10)
        self.spline_smoothness = self.config.get("spline_smoothness", 0.5)
        self.min_boundary_points = self.config.get("min_boundary_points", 8)
        self.arc_detection_threshold = self.config.get("arc_detection_threshold", 0.3)
        self.triangle_convergence_threshold = self.config.get(
            "triangle_convergence_threshold", 0.15
        )
        self.channel_parallel_threshold = self.config.get(
            "channel_parallel_threshold", 0.1
        )

        # 几何分析器
        self.geometric_analyzer = GeometricAnalyzer(
            {
                "circle_fit_threshold": 0.7,
                "arc_angle_threshold": 60,
                "triangle_convergence_angle": 20,
            }
        )

        # 状态跟踪
        self.boundary_history: list[dict[str, Any]] = []
        self.current_boundary: Optional[dict[str, Any]] = None

    def detect_pivot_points(
        self, prices: pd.Series, include_time: bool = True
    ) -> dict[str, list[Any]]:
        """
        检测枢轴点（局部高点和低点）

        Args:
            prices: 价格序列（可以是close、high、low等）
            include_time: 是否包含时间索引

        Returns:
            Dict包含：
                - highs: 高点列表 [(index, value), ...] 或 [value, ...]
                - lows: 低点列表 [(index, value), ...] 或 [value, ...]
        """
        if len(prices) < self.pivot_window * 2:
            return {"highs": [], "lows": []}

        # 使用scipy的argrelextrema检测局部极值
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            # 检测局部高点
            high_indices = argrelextrema(
                prices.values, np.greater, order=self.pivot_window
            )[0]

            # 检测局部低点
            low_indices = argrelextrema(
                prices.values, np.less, order=self.pivot_window
            )[0]

        # 过滤过于接近的枢轴点
        prices_array = np.array(prices.values)
        high_indices = self._filter_close_pivots(high_indices, prices_array)
        low_indices = self._filter_close_pivots(low_indices, prices_array)

        # 格式化输出
        if include_time:
            highs = [(prices.index[i], prices.iloc[i]) for i in high_indices]
            lows = [(prices.index[i], prices.iloc[i]) for i in low_indices]
        else:
            highs = [prices.iloc[i] for i in high_indices]
            lows = [prices.iloc[i] for i in low_indices]

        return {"highs": highs, "lows": lows}

    def _filter_close_pivots(
        self, indices: npt.NDArray[np.int64], values: npt.NDArray[np.float64]
    ) -> npt.NDArray[np.int64]:
        """过滤过于接近的枢轴点"""
        if len(indices) <= 1:
            return indices

        filtered = []
        sorted_indices = np.sort(indices)

        # 始终保留第一个点
        filtered.append(sorted_indices[0])

        for i in range(1, len(sorted_indices)):
            # 检查与上一个点的距离
            if sorted_indices[i] - filtered[-1] >= self.min_pivot_distance:
                # 距离足够，保留
                filtered.append(sorted_indices[i])
            else:
                # 距离太近，保留值更极端的点
                prev_idx = filtered[-1]
                curr_idx = sorted_indices[i]

                if values[curr_idx] > values[prev_idx]:
                    # 当前点是更高高点，替换前一个点
                    filtered[-1] = curr_idx
                # 否则丢弃当前点（前一个点已经是更低低点或更高高点）

        return np.array(filtered)

    def fit_spline_boundary(
        self, pivot_points: list[tuple[Any, float]], is_upper: bool = True
    ) -> Optional[dict[str, Any]]:
        """
        使用样条曲线拟合边界

        Args:
            pivot_points: 枢轴点列表 [(index, value), ...]
            is_upper: 是否为上边界（True: 高点拟合，False: 低点拟合）

        Returns:
            Dict包含：
                - boundary_type: 边界类型
                - spline_function: 拟合的样条函数
                - confidence: 拟合置信度 [0, 1]
                - pivot_points: 使用的枢轴点
                - fitted_points: 拟合点 [(x, y), ...]
                - curvature: 平均曲率
                - slope: 平均斜率
        """
        if len(pivot_points) < self.min_boundary_points:
            return None

        # 提取x坐标（时间索引转换为数值）和y坐标（价格）
        x_indices = np.arange(len(pivot_points))
        y_values = np.array([p[1] for p in pivot_points])

        # 样条曲线拟合
        try:
            # 使用UnivariateSpline进行平滑拟合
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                spline = UnivariateSpline(
                    x_indices,
                    y_values,
                    s=len(pivot_points) * (1 - self.spline_smoothness),
                )

            # 生成拟合点
            x_fine = np.linspace(0, len(pivot_points) - 1, 100)
            y_fine = spline(x_fine)

            # 计算曲率（二阶导数）
            spline_derivative2 = spline.derivative(n=2)
            curvature = float(np.mean(np.abs(spline_derivative2(x_fine))))

            # 计算斜率（一阶导数）
            spline_derivative1 = spline.derivative(n=1)
            slopes = spline_derivative1(x_fine)
            avg_slope = np.mean(slopes)

            # 计算拟合误差（R²）
            y_pred = spline(x_indices)
            ss_res = np.sum((y_values - y_pred) ** 2)
            ss_tot = np.sum((y_values - np.mean(y_values)) ** 2)

            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0

            # 计算置信度（基于R²和枢轴点数量）
            points_confidence = min(
                len(pivot_points) / 20, 1.0
            )  # 最多20个点达到最大置信度
            fit_confidence = max(0, min(1, r_squared))  # R²作为拟合置信度

            confidence = 0.6 * fit_confidence + 0.4 * points_confidence

            # 识别边界类型
            boundary_type, type_confidence = self._classify_boundary(
                x_fine, y_fine, slopes, curvature, is_upper
            )

            # 结合类型置信度
            final_confidence = confidence * type_confidence

            return {
                "boundary_type": boundary_type,
                "spline_function": spline,
                "confidence": final_confidence,
                "pivot_points": pivot_points,
                "fitted_points": list(zip(x_fine, y_fine)),
                "curvature": curvature,
                "slope": avg_slope,
                "r_squared": r_squared,
                "type_confidence": type_confidence,
                "is_upper": is_upper,
                "num_points": len(pivot_points),
            }

        except Exception as e:
            logger.debug("边界拟合失败: %s", e)
            return None

    def _classify_boundary(
        self,
        x: npt.ArrayLike,
        y: npt.ArrayLike,
        slopes: npt.ArrayLike,
        curvature: float,
        is_upper: bool,
    ) -> tuple[BoundaryType, float]:
        """
        分类边界类型

        Args:
            x: x坐标
            y: y坐标
            slopes: 斜率数组
            curvature: 平均曲率
            is_upper: 是否为上边界

        Returns:
            (边界类型, 类型置信度)
        """
        # 转换为numpy数组
        x_arr = np.asarray(x, dtype=np.float64)
        y_arr = np.asarray(y, dtype=np.float64)
        slopes_arr = np.asarray(slopes, dtype=np.float64)

        # 计算关键特征
        np.max(y_arr) - np.min(y_arr)
        x_range = np.max(x_arr) - np.min(x_arr)

        if x_range == 0:
            return BoundaryType.UNKNOWN, 0.0

        # 斜率变化特征
        slope_change = np.std(slopes_arr) / (np.mean(np.abs(slopes_arr)) + 1e-10)

        # 使用几何分析器进行精确分类
        points = np.column_stack([x_arr, y_arr])

        # 分析几何形状
        if len(points) >= 5:  # 需要足够点数进行几何分析
            arc_result = self.geometric_analyzer.detect_arc(points)

            if arc_result["is_arc"]:
                # 检测到圆弧
                if is_upper:
                    if arc_result["is_convex"]:
                        return BoundaryType.ARC_TOP, arc_result["circle_result"][
                            "r_squared"
                        ]
                    return BoundaryType.UNKNOWN, 0.5
                if not arc_result["is_convex"]:
                    return BoundaryType.ARC_BOTTOM, arc_result["circle_result"][
                        "r_squared"
                    ]
                return BoundaryType.UNKNOWN, 0.5

        # 判断是否为圆弧形（基于曲率）
        if curvature > self.arc_detection_threshold:
            # 根据曲率方向判断是圆弧顶还是圆弧底
            if is_upper and np.mean(slopes_arr) < 0:
                # 上边界且向下弯曲 → 圆弧顶
                return BoundaryType.ARC_TOP, min(curvature * 2, 1.0)
            if not is_upper and np.mean(slopes_arr) > 0:
                # 下边界且向上弯曲 → 圆弧底
                return BoundaryType.ARC_BOTTOM, min(curvature * 2, 1.0)

        # 判断是否为三角形（收敛）
        # 计算起点和终点的斜率差
        start_slope = slopes_arr[0]
        end_slope = slopes_arr[-1]
        slope_diff = abs(start_slope - end_slope)

        if slope_diff > self.triangle_convergence_threshold:
            # 斜率变化明显，可能是三角形
            if is_upper and np.mean(slopes_arr) < 0:
                # 上边界向下倾斜 → 下降三角形或对称三角形
                if start_slope > 0 and end_slope < 0:
                    return BoundaryType.TRIANGLE_SYMMETRICAL, min(slope_diff * 3, 0.8)
                return BoundaryType.TRIANGLE_DESCENDING, min(slope_diff * 3, 0.8)
            if not is_upper and np.mean(slopes_arr) > 0:
                # 下边界向上倾斜 → 上升三角形或对称三角形
                if start_slope < 0 and end_slope > 0:
                    return BoundaryType.TRIANGLE_SYMMETRICAL, min(slope_diff * 3, 0.8)
                return BoundaryType.TRIANGLE_ASCENDING, min(slope_diff * 3, 0.8)

        # 判断是否为通道（平行）
        if slope_change < self.channel_parallel_threshold:
            # 斜率变化小，可能是通道
            avg_slope = np.mean(slopes_arr)
            if avg_slope > 0.05:
                return BoundaryType.CHANNEL_UP, 0.7
            if avg_slope < -0.05:
                return BoundaryType.CHANNEL_DOWN, 0.7
            return BoundaryType.RECTANGLE, 0.7

        # 默认未知类型
        return BoundaryType.UNKNOWN, 0.5

    def detect_trading_range(
        self, high_prices: pd.Series, low_prices: pd.Series, close_prices: pd.Series
    ) -> Optional[dict[str, Any]]:
        """
        检测交易区间（TR）的曲线边界

        Args:
            high_prices: 高价序列
            low_prices: 低价序列
            close_prices: 收盘价序列

        Returns:
            Dict包含：
                - upper_boundary: 上边界拟合结果
                - lower_boundary: 下边界拟合结果
                - tr_confidence: TR置信度 [0, 1]
                - boundary_distance: 边界距离（百分比）
                - price_position: 当前价格在TR中的位置 [0, 1]
                - breakout_direction: 突破方向（1: 向上突破, -1: 向下跌破, 0: 无突破）
                - breakout_strength: 突破强度 [0, 1]
        """
        # 检测高点枢轴点
        high_pivots = self.detect_pivot_points(high_prices, include_time=True)
        low_pivots = self.detect_pivot_points(low_prices, include_time=True)

        if not high_pivots["highs"] or not low_pivots["lows"]:
            return None

        # 拟合上边界（使用高点）
        upper_boundary = self.fit_spline_boundary(high_pivots["highs"], is_upper=True)

        # 拟合下边界（使用低点）
        lower_boundary = self.fit_spline_boundary(low_pivots["lows"], is_upper=False)

        if not upper_boundary or not lower_boundary:
            return None

        # 计算边界距离（以百分比表示）
        upper_price = upper_boundary["spline_function"](
            len(upper_boundary["pivot_points"]) - 1
        )
        lower_price = lower_boundary["spline_function"](
            len(lower_boundary["pivot_points"]) - 1
        )

        if lower_price > 0:
            boundary_distance_pct = (upper_price - lower_price) / lower_price * 100
        else:
            boundary_distance_pct = 0

        # 计算当前价格位置
        current_price = close_prices.iloc[-1]
        if upper_price != lower_price:
            price_position = (current_price - lower_price) / (upper_price - lower_price)
        else:
            price_position = 0.5

        # 计算TR置信度（结合上下边界的置信度）
        tr_confidence = (
            upper_boundary["confidence"] + lower_boundary["confidence"]
        ) / 2

        # 检测突破
        breakout_direction = 0
        breakout_strength = 0.0

        # 计算最近价格与边界的距离（以ATR为单位）
        recent_highs = high_prices.iloc[-10:]
        recent_lows = low_prices.iloc[-10:]
        close_prices.iloc[-10:]

        atr = self._calculate_atr(high_prices, low_prices, close_prices)

        if atr > 0:
            # 检查向上突破
            upper_distance = (np.max(recent_highs) - upper_price) / atr
            if upper_distance > 1.5:  # 超过1.5倍ATR
                breakout_direction = 1
                breakout_strength = min(upper_distance / 3, 1.0)

            # 检查向下跌破
            lower_distance = (lower_price - np.min(recent_lows)) / atr
            if lower_distance > 1.5:
                breakout_direction = -1
                breakout_strength = min(lower_distance / 3, 1.0)

        # 使用几何分析器进行综合分析
        geometry_result = None
        if upper_boundary and lower_boundary:
            # 提取枢轴点坐标
            upper_pivot_points = np.array(
                [
                    [i, point[1]]
                    for i, point in enumerate(upper_boundary["pivot_points"])
                ]
            )
            lower_pivot_points = np.array(
                [
                    [i, point[1]]
                    for i, point in enumerate(lower_boundary["pivot_points"])
                ]
            )

            # 分析几何形状
            geometry_result = self.geometric_analyzer.analyze_geometry(
                upper_pivot_points, lower_pivot_points
            )

        return {
            "upper_boundary": upper_boundary,
            "lower_boundary": lower_boundary,
            "tr_confidence": tr_confidence,
            "boundary_distance": boundary_distance_pct,
            "price_position": max(0, min(1, price_position)),
            "breakout_direction": breakout_direction,
            "breakout_strength": breakout_strength,
            "current_price": current_price,
            "upper_price": upper_price,
            "lower_price": lower_price,
            "atr": atr,
            "timestamp": close_prices.index[-1],
            "geometry_analysis": geometry_result,
        }

    def _calculate_atr(
        self,
        high_series: pd.Series,
        low_series: pd.Series,
        close_series: pd.Series,
        period: int = 14,
    ) -> float:
        """计算平均真实波幅（简化版）"""
        if len(close_series) < period + 1:
            return 0.0

        try:
            # 转换为 numpy 数组进行计算
            high_arr = np.array(high_series)
            low_arr = np.array(low_series)
            close_arr = np.array(close_series)

            n = len(close_arr)
            tr_values = np.zeros(n)

            for i in range(n):
                if i == 0:
                    tr_values[i] = high_arr[i] - low_arr[i]
                else:
                    tr1 = high_arr[i] - low_arr[i]
                    tr2 = abs(high_arr[i] - close_arr[i - 1])
                    tr3 = abs(low_arr[i] - close_arr[i - 1])
                    tr_values[i] = max(tr1, tr2, tr3)

            # 计算 ATR
            if n >= period:
                atr_value = np.mean(tr_values[-period:])
                return float(atr_value)
            return 0.0

        except Exception as e:
            logger.debug("ATR 计算失败: %s", e)
            return 0.0

        try:
            # 转换为 numpy 数组进行计算
            high_arr = np.array(high)
            low_arr = np.array(low)
            close_arr = np.array(close)

            n = len(close_arr)
            tr = np.zeros(n)

            for i in range(n):
                if i == 0:
                    tr[i] = high_arr[i] - low_arr[i]
                else:
                    tr1 = high_arr[i] - low_arr[i]
                    tr2 = abs(high_arr[i] - close_arr[i - 1])
                    tr3 = abs(low_arr[i] - close_arr[i - 1])
                    tr[i] = max(tr1, tr2, tr3)

            # 计算 ATR
            if n >= period:
                atr = np.mean(tr[-period:])
                return float(atr)
            return 0.0

        except Exception as e:
            logger.debug("ATR 计算失败: %s", e)
            return 0.0

    def record_boundary_event(self, tr_result: dict[str, Any]) -> None:
        """记录边界事件到历史"""
        self.boundary_history.append(tr_result)

        # 限制历史记录长度
        if len(self.boundary_history) > 1000:
            self.boundary_history = self.boundary_history[-1000:]

        # 更新当前边界
        self.current_boundary = tr_result

    def get_boundary_history(self, n: int = 50) -> list[dict[str, Any]]:
        """获取最近N次边界检测历史"""
        return self.boundary_history[-n:] if n > 0 else self.boundary_history

    def get_current_boundary(self) -> Optional[dict[str, Any]]:
        """获取当前边界"""
        return self.current_boundary


# 简单使用示例
if __name__ == "__main__":
    # 创建模拟数据（圆弧底形态）
    np.random.seed(42)
    num_points = 200

    # 生成圆弧底价格
    x_values = np.linspace(0, 2 * np.pi, num_points)
    arc_bottom = 100 + 10 * np.sin(x_values)  # 正弦波模拟圆弧底
    noise = np.random.randn(num_points) * 2

    high_prices = arc_bottom + 3 + np.abs(noise) * 1.5
    low_prices = arc_bottom - 3 - np.abs(noise) * 1.5
    close_prices = arc_bottom + noise

    dates = pd.date_range("2024-01-01", periods=num_points, freq="h")

    high_series = pd.Series(high_prices, index=dates)
    low_series = pd.Series(low_prices, index=dates)
    close_series = pd.Series(close_prices, index=dates)

    # 创建曲线边界拟合器
    fitter = CurveBoundaryFitter(
        {
            "pivot_window": 7,
            "min_pivot_distance": 15,
            "spline_smoothness": 0.7,
        }
    )

    # 检测TR边界
    trading_range_result = fitter.detect_trading_range(
        high_series, low_series, close_series
    )

    if trading_range_result:
        # 记录事件
        fitter.record_boundary_event(trading_range_result)
    else:
        pass
