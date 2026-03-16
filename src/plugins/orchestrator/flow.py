"""
系统协调器 - 流程控制模块

负责数据处理流水线的协调和控制。

设计原则：
1. 使用 @error_handler 装饰器进行错误处理
2. 详细的中文错误上下文记录
3. 支持异步处理
"""

import logging
from typing import Any, Callable, Optional

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


class DataFlowPipeline:
    """
    数据处理流水线 - 协调数据处理流程

    注意：此类原名 DataPipeline，为避免与 core/data_pipeline.py 中的
    同名多周期数据同步管道冲突，重命名为 DataFlowPipeline。
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        初始化数据处理流水线

        Args:
            config: 配置字典
        """
        self._config = config or {}
        self._processors: dict[str, Callable] = {}
        self._pipeline_order: list[str] = []

        logger.info("DataFlowPipeline initialized")

    @error_handler(logger=logger, reraise=False)
    def register_processor(
        self, name: str, processor: Callable, position: Optional[int] = None
    ) -> None:
        """
        注册数据处理器

        Args:
            name: 处理器名称
            processor: 处理函数
            position: 在流水线中的位置（可选）
        """
        self._processors[name] = processor

        if position is not None and 0 <= position <= len(self._pipeline_order):
            self._pipeline_order.insert(position, name)
        else:
            self._pipeline_order.append(name)

        logger.debug(f"Processor registered: {name}")

    @error_handler(logger=logger, reraise=False, default_return={})
    async def process(
        self, data: Any, context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        执行数据处理流水线

        Args:
            data: 输入数据
            context: 上下文信息

        Returns:
            处理结果字典
        """
        results = {"input": data, "processors": {}}
        current_data = data

        for processor_name in self._pipeline_order:
            try:
                processor = self._processors.get(processor_name)
                if processor is None:
                    logger.warning(f"Processor not found: {processor_name}")
                    continue

                # 调用处理器
                if callable(processor):
                    result = processor(current_data, context or {})
                    results["processors"][processor_name] = result
                    current_data = result

            except Exception as e:
                logger.exception(f"Error in processor {processor_name}")
                results["processors"][processor_name] = {"error": str(e)}

        results["output"] = current_data
        return results

    @error_handler(logger=logger, reraise=False)
    def remove_processor(self, name: str) -> None:
        """
        移除数据处理器

        Args:
            name: 处理器名称
        """
        if name in self._processors:
            del self._processors[name]

        if name in self._pipeline_order:
            self._pipeline_order.remove(name)

        logger.debug(f"Processor removed: {name}")

    @error_handler(logger=logger, reraise=False)
    def clear(self) -> None:
        """清除所有处理器"""
        self._processors.clear()
        self._pipeline_order.clear()
        logger.info("DataFlowPipeline cleared")

    @error_handler(logger=logger, reraise=False, default_return=[])
    def get_processor_names(self) -> list[str]:
        """
        获取所有处理器名称

        Returns:
            处理器名称列表
        """
        return self._pipeline_order.copy()


class DecisionPipeline:
    """
    决策流水线 - 协调从感知到决策的完整流程
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        初始化决策流水线

        Args:
            config: 配置字典
        """
        self._config = config or {}
        self._stages: dict[str, Callable] = {}
        self._stage_order: list[str] = []

        logger.info("DecisionPipeline initialized")

    @error_handler(logger=logger, reraise=False)
    def register_stage(
        self, name: str, stage: Callable, position: Optional[int] = None
    ) -> None:
        """
        注册决策阶段

        Args:
            name: 阶段名称
            stage: 阶段处理函数
            position: 在流水线中的位置
        """
        self._stages[name] = stage

        if position is not None and 0 <= position <= len(self._stage_order):
            self._stage_order.insert(position, name)
        else:
            self._stage_order.append(name)

        logger.debug(f"Stage registered: {name}")

    @error_handler(logger=logger, reraise=False, default_return={})
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        执行决策流水线

        Args:
            input_data: 输入数据字典

        Returns:
            决策结果字典
        """
        results = {"stages": {}, "final_decision": None}
        context = input_data.copy()

        for stage_name in self._stage_order:
            try:
                stage = self._stages.get(stage_name)
                if stage is None:
                    logger.warning(f"Stage not found: {stage_name}")
                    continue

                # 调用阶段处理函数
                stage_result = await stage(context) if callable(stage) else None
                results["stages"][stage_name] = stage_result
                context[stage_name] = stage_result

            except Exception as e:
                logger.exception(f"Error in stage {stage_name}")
                results["stages"][stage_name] = {"error": str(e)}

        # 最终决策取自最后一个成功的阶段
        if self._stage_order:
            last_stage = self._stage_order[-1]
            if last_stage in results["stages"]:
                results["final_decision"] = results["stages"][last_stage]

        return results

    @error_handler(logger=logger, reraise=False)
    def clear(self) -> None:
        """清除所有阶段"""
        self._stages.clear()
        self._stage_order.clear()
        logger.info("DecisionPipeline cleared")


# 向后兼容别名
DataPipeline = DataFlowPipeline

# 导出
__all__ = ["DataFlowPipeline", "DataPipeline", "DecisionPipeline"]
