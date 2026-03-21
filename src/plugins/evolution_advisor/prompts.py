"""进化顾问 Prompt 模板

为 LLM 提供结构化的分析提示，覆盖四种场景：
1. 进化轮次分析（成功/失败原因）
2. MistakeBook 错误模式翻译
3. 局部最优检测
4. 变异方向建议
"""

from typing import Any, Dict, List


SYSTEM_PROMPT = """你是一个量化交易系统的进化顾问。你的工作是分析自动进化系统的表现，
用人类可理解的语言解释进化过程中发生了什么，并提出下一步优化建议。

你面对的系统：
- 基于威科夫理论的加密货币交易系统
- 使用遗传算法（GA）进化交易参数
- 通过Walk-Forward Analysis（WFA）验证防止过拟合
- 错题本（MistakeBook）记录交易失败模式

你的角色：
- 镜子不是手 — 帮看清进化在干什么，不碰控制面板
- 用简洁中文回答
- 给出具体可操作的建议
- 检测进化是否卡住或走偏

限制：
- 不要建议直接修改代码
- 不要生成交易信号
- 回答控制在 300 字以内
"""


def build_cycle_analysis_prompt(
    cycle_data: Dict[str, Any],
    history: List[Dict[str, Any]],
) -> str:
    """构建进化轮次分析 Prompt

    Args:
        cycle_data: 当前轮次数据，包含 generation, best_fitness,
                    best_config, population_stats 等
        history: 近几轮的历史数据列表

    Returns:
        完整的 user prompt 字符串
    """
    generation = cycle_data.get("generation", 0)
    best_fitness = cycle_data.get("best_fitness", 0.0)
    best_config = cycle_data.get("best_config", {})
    pop_stats = cycle_data.get("population_stats", {})

    history_lines = []
    for h in history[-5:]:
        g = h.get("generation", "?")
        f = h.get("best_fitness", 0.0)
        history_lines.append(f"  第{g}轮: fitness={f:.4f}")

    history_str = "\n".join(history_lines) if history_lines else "  无历史数据"

    config_lines = []
    for k, v in best_config.items():
        if isinstance(v, float):
            config_lines.append(f"  {k}: {v:.4f}")
        else:
            config_lines.append(f"  {k}: {v}")
    config_str = "\n".join(config_lines) if config_lines else "  无配置数据"

    return f"""分析第 {generation} 轮进化结果：

当前最佳 fitness: {best_fitness:.4f}
种群统计: {pop_stats}

最佳配置:
{config_str}

近期历史:
{history_str}

请分析：
1. 这一轮进化的表现如何？fitness 是否在提升？
2. 配置参数是否合理？有没有明显偏离正常范围的？
3. 下一轮应该关注什么方向？
"""


def build_mistake_translation_prompt(
    patterns: List[Dict[str, Any]],
) -> str:
    """构建 MistakeBook 错误模式翻译 Prompt

    Args:
        patterns: MistakeBook 分析出的错误模式列表

    Returns:
        完整的 user prompt 字符串
    """
    if not patterns:
        return "当前没有检测到错误模式。请简要说明这可能意味着什么。"

    pattern_lines = []
    for i, p in enumerate(patterns[:10], 1):
        pattern_type = p.get("pattern", "UNKNOWN")
        frequency = p.get("frequency", 0.0)
        description = p.get("description", "")
        module = p.get("module", "")

        pattern_lines.append(
            f"{i}. 模式: {pattern_type}\n"
            f"   频率: {frequency:.1%}\n"
            f"   模块: {module}\n"
            f"   描述: {description}"
        )

    patterns_str = "\n".join(pattern_lines)

    return f"""以下是交易系统错题本检测到的错误模式：

{patterns_str}

请用简单易懂的语言：
1. 解释每个错误模式是什么意思
2. 它们对交易表现有什么影响
3. 建议进化系统应该如何调整来减少这些错误
"""


def build_plateau_detection_prompt(
    fitness_history: List[float],
    config_history: List[Dict[str, Any]],
) -> str:
    """构建局部最优检测 Prompt

    Args:
        fitness_history: 近N轮的 fitness 值列表
        config_history: 近N轮的最佳配置列表

    Returns:
        完整的 user prompt 字符串
    """
    if len(fitness_history) < 3:
        return "历史数据不足（少于3轮），无法检测局部最优。"

    fitness_str = ", ".join(f"{f:.4f}" for f in fitness_history[-10:])

    # 检查配置变化幅度
    config_changes = []
    for i in range(1, min(len(config_history), 6)):
        prev = config_history[i - 1]
        curr = config_history[i]
        changes = {}
        for key in curr:
            if key in prev:
                prev_val = prev[key]
                curr_val = curr[key]
                if isinstance(prev_val, (int, float)) and isinstance(
                    curr_val, (int, float)
                ):
                    if prev_val != 0:
                        pct = abs(curr_val - prev_val) / abs(prev_val)
                        if pct > 0.01:
                            changes[key] = f"{pct:.1%}"
        if changes:
            config_changes.append(f"  轮次{i}: {changes}")

    changes_str = "\n".join(config_changes) if config_changes else "  配置变化极小"

    return f"""进化系统可能卡在局部最优，请诊断：

近期 fitness 序列: [{fitness_str}]

配置变化幅度:
{changes_str}

请判断：
1. fitness 是否停滞？（连续5轮波动 < 2% 视为停滞）
2. 配置是否收敛到一个点不再变化？
3. 如果确认卡住，建议采取什么措施？（如增大变异率、重新初始化部分种群等）
"""


def build_mutation_direction_prompt(
    current_config: Dict[str, Any],
    mistake_patterns: List[Dict[str, Any]],
    fitness: float,
) -> str:
    """构建变异方向建议 Prompt

    Args:
        current_config: 当前最佳配置
        mistake_patterns: 错题本模式列表
        fitness: 当前 fitness 值

    Returns:
        完整的 user prompt 字符串
    """
    config_lines = []
    for k, v in current_config.items():
        if isinstance(v, float):
            config_lines.append(f"  {k}: {v:.4f}")
        else:
            config_lines.append(f"  {k}: {v}")
    config_str = "\n".join(config_lines) if config_lines else "  无配置数据"

    pattern_summary = []
    for p in mistake_patterns[:5]:
        pt = p.get("pattern", "UNKNOWN")
        freq = p.get("frequency", 0.0)
        pattern_summary.append(f"  {pt}: {freq:.1%}")
    patterns_str = "\n".join(pattern_summary) if pattern_summary else "  无明显错误模式"

    return f"""当前 fitness: {fitness:.4f}

当前配置:
{config_str}

主要错误模式:
{patterns_str}

请建议：
1. 哪些参数应该增大？哪些应该减小？为什么？
2. 变异幅度建议（保守/适中/激进）？
3. 有没有参数组合可能产生协同效应？
"""
