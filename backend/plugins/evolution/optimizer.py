"""统计优化器 — 从案例库中优化引擎参数"""

from __future__ import annotations

import copy
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# 参数 ↔ 特征映射表（EVD-9: 安全系数 ×1.2/×0.8）
PARAM_MAPPINGS: dict[str, list[tuple[str, str, str, int]]] = {
    "st": [
        # (参数路径, 特征名, 方向, 百分位)
        ("range_engine.st_max_distance_pct", "penetration_depth", "upper_bound", 95),
        ("event_engine.volume_dryup_ratio", "volume_ratio", "upper_bound", 90),
    ],
    "ar": [
        ("range_engine.ar_min_bounce_pct", "price_body", "lower_bound", 95),
        ("range_engine.ar_min_bars", "sequence_length", "lower_bound", 90),
    ],
    "spring": [
        ("event_engine.approach_distance", "support_distance", "upper_bound", 90),
        ("event_engine.penetrate_min_depth", "penetration_depth", "lower_bound", 90),
        ("event_engine.recovery_min_pct", "recovery_speed", "lower_bound", 90),
    ],
    "sc": [
        ("event_engine.volume_climax_ratio", "volume_ratio", "lower_bound", 85),
    ],
    "bc": [
        ("event_engine.volume_climax_ratio", "volume_ratio", "lower_bound", 85),
    ],
}


def weighted_values(cases: list[dict], feature_name: str) -> list[float]:
    """提取特征值，按权重重复（EVD-5: weight=3的案例重复3次）"""
    result: list[float] = []
    for case in cases:
        val = case.get(feature_name)
        if val is not None:
            try:
                weight = max(1, int(case.get("weight", 1)))
                result.extend([float(val)] * weight)
            except (ValueError, TypeError):
                pass
    return result


def count_within(values: list[float], threshold: float, direction: str) -> int:
    """计算在阈值内的值数量"""
    if not values:
        return 0
    if direction == "upper_bound":
        return sum(1 for v in values if v <= threshold)
    else:
        return sum(1 for v in values if v >= threshold)


def find_separation_point(
    success_values: list[float],
    rejected_values: list[float],
    direction: str,
) -> float:
    """在 success 和 rejected 之间找分界点（EVD-6）"""
    all_vals = sorted(set(success_values + rejected_values))
    if not all_vals:
        return 0.0

    best_point = all_vals[-1] if direction == "upper_bound" else all_vals[0]
    best_score = -1.0

    for i in range(len(all_vals) - 1):
        midpoint = (all_vals[i] + all_vals[i + 1]) / 2.0
        if direction == "upper_bound":
            s_pass = sum(1 for v in success_values if v <= midpoint)
            r_fail = sum(1 for v in rejected_values if v > midpoint)
        else:
            s_pass = sum(1 for v in success_values if v >= midpoint)
            r_fail = sum(1 for v in rejected_values if v < midpoint)

        s_rate = s_pass / len(success_values) if success_values else 0
        r_rate = r_fail / len(rejected_values) if rejected_values else 0
        score = s_rate + r_rate  # 越高越好

        if score > best_score:
            best_score = score
            best_point = midpoint

    return best_point


def optimize(
    cases: list[dict],
    current_params: dict,
) -> tuple[dict, dict]:
    """
    统计优化：从案例中优化引擎参数。

    返回 (new_params_dict, params_diff_report)

    current_params 是 EngineParams 的 asdict() 形式：
    {
        "version": "...",
        "range_engine": {...},
        "event_engine": {...},
        "rule_engine": {...},
    }
    """
    new_params = copy.deepcopy(current_params)
    params_diff: dict[str, Any] = {}

    # 按事件类型分组
    grouped: dict[str, list[dict]] = {}
    for case in cases:
        et = case.get("event_type", "")
        if et:
            grouped.setdefault(et, []).append(case)

    for event_type, type_cases in grouped.items():
        success = [c for c in type_cases if c.get("event_result") == "success"]
        rejected = [c for c in type_cases if c.get("event_result") == "rejected"]

        # EVD-8: 最少3个成功案例才优化
        if len(success) < 3:
            logger.info("跳过 %s: 成功案例不足 (%d < 3)", event_type, len(success))
            continue

        mapping = PARAM_MAPPINGS.get(event_type, [])
        for param_path, feature_name, direction, percentile in mapping:
            values = weighted_values(success, feature_name)
            if not values:
                continue

            old_val = _get_param(new_params, param_path)

            if direction == "upper_bound":
                # 取高百分位 × 1.2（EVD-9: 宁可宽松）
                threshold = float(np.percentile(values, percentile)) * 1.2
            else:
                # 取低百分位 × 0.8
                threshold = float(np.percentile(values, 100 - percentile)) * 0.8

            # EVD-6: 负样本排除检查
            if rejected:
                rej_values = [
                    float(c[feature_name])
                    for c in rejected
                    if c.get(feature_name) is not None
                ]
                if rej_values:
                    false_positive_rate = count_within(
                        rej_values, threshold, direction
                    ) / len(rej_values)
                    if false_positive_rate > 0.3:
                        threshold = find_separation_point(values, rej_values, direction)
                        logger.info(
                            "负样本调整: %s/%s → %.4f (FPR=%.1f%%)",
                            event_type,
                            param_path,
                            threshold,
                            false_positive_rate * 100,
                        )

            _set_param(new_params, param_path, threshold)

            params_diff[param_path] = {
                "before": old_val,
                "after": round(threshold, 6),
                "cases_count": len(success),
                "event_type": event_type,
            }

            logger.info(
                "优化: %s/%s: %.4f → %.4f (%d cases)",
                event_type,
                param_path,
                old_val or 0,
                threshold,
                len(success),
            )

    return new_params, params_diff


def _get_param(params: dict, path: str) -> Any:
    """获取嵌套参数值，如 'range_engine.st_max_distance_pct'"""
    parts = path.split(".")
    obj = params
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def _set_param(params: dict, path: str, value: Any) -> None:
    """设置嵌套参数值"""
    parts = path.split(".")
    obj = params
    for part in parts[:-1]:
        if isinstance(obj, dict):
            obj = obj.setdefault(part, {})
    if isinstance(obj, dict):
        obj[parts[-1]] = value
