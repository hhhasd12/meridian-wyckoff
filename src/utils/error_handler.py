"""
错误处理装饰器模块

提供统一的错误处理、日志记录和异常管理装饰器。

使用方式：
    from src.utils.error_handler import error_handler, log_execution_time

    @error_handler(logger=logger, reraise=False, default_return=None)
    def my_function():
        ...
"""

import contextlib
import functools
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class ErrorSeverity(Enum):
    """错误严重程度枚举"""

    LOW = "low"  # 低 - 不影响核心功能
    MEDIUM = "medium"  # 中 - 影响部分功能
    HIGH = "high"  # 高 - 影响核心功能
    CRITICAL = "critical"  # 严重 - 系统无法正常工作


class ErrorCategory(Enum):
    """错误类别枚举"""

    VALIDATION = "validation"  # 数据验证错误
    NETWORK = "network"  # 网络相关错误
    DATA = "data"  # 数据处理错误
    COMPUTATION = "computation"  # 计算错误
    TIMEOUT = "timeout"  # 超时错误
    AUTH = "auth"  # 认证/授权错误
    CONFIG = "config"  # 配置错误
    UNKNOWN = "unknown"  # 未知错误


@dataclass
class ErrorContext:
    """错误上下文信息"""

    timestamp: datetime
    function_name: str
    error_type: str
    error_message: str
    severity: ErrorSeverity
    category: ErrorCategory
    args: tuple = ()
    kwargs: Optional[dict[str, Any]] = None

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


def error_handler(
    logger: Optional[logging.Logger] = None,
    reraise: bool = True,
    default_return: Any = None,
    log_level: int = logging.ERROR,
    capture_exceptions: tuple = (Exception,),
    context_provider: Optional[Callable] = None,
):
    """
    通用错误处理装饰器

    Args:
        logger: 日志记录器，默认使用模块级logger
        reraise: 是否重新抛出异常，默认True
        default_return: 异常时的默认返回值
        log_level: 日志级别，默认ERROR
        capture_exceptions: 捕获的异常类型元组
        context_provider: 额外的上下文提供者函数

    Returns:
        装饰后的函数

    Example:
        @error_handler(logger=logger, reraise=False, default_return=[])
        def fetch_data():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or logging.getLogger(func.__module__)
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                # 记录成功执行（可选，DEBUG级别）
                if func_logger.isEnabledFor(logging.DEBUG):
                    func_logger.debug(
                        f"函数 {func.__name__} 执行成功，耗时 {execution_time:.3f}s"
                    )

                return result

            except capture_exceptions as e:
                execution_time = time.time() - start_time

                # 构建错误上下文
                error_type = type(e).__name__
                error_message = str(e)
                severity = _determine_severity(e)
                category = _categorize_error(e)

                # 调用上下文提供者（如果有）
                extra_context = {}
                if context_provider:
                    with contextlib.suppress(Exception):
                        extra_context = context_provider(*args, **kwargs) or {}

                # 记录错误日志
                error_context = ErrorContext(
                    timestamp=datetime.now(),
                    function_name=func.__name__,
                    error_type=error_type,
                    error_message=error_message,
                    severity=severity,
                    category=category,
                    args=args,
                    kwargs=kwargs,
                )

                func_logger.log(
                    log_level,
                    f"函数 {func.__name__} 执行失败: [{severity.value}] {error_type}: {error_message}",
                    extra={
                        "error_context": error_context.__dict__,
                        "execution_time": execution_time,
                        "extra_context": extra_context,
                    },
                    exc_info=True,
                )

                if reraise:
                    raise

                return default_return

        return wrapper

    return decorator


def log_execution_time(
    logger: Optional[logging.Logger] = None,
    threshold_seconds: float = 1.0,
    warn_slow: bool = True,
):
    """
    执行时间日志装饰器

    Args:
        logger: 日志记录器
        threshold_seconds: 阈值，超过则记录警告
        warn_slow: 是否对慢执行记录警告

    Returns:
        装饰后的函数
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or logging.getLogger(func.__module__)
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                if execution_time > threshold_seconds and warn_slow:
                    func_logger.warning(
                        f"函数 {func.__name__} 执行较慢: {execution_time:.3f}s (阈值: {threshold_seconds}s)"
                    )
                elif func_logger.isEnabledFor(logging.DEBUG):
                    func_logger.debug(
                        f"函数 {func.__name__} 执行耗时: {execution_time:.3f}s"
                    )

                return result

            except Exception as e:
                execution_time = time.time() - start_time
                func_logger.error(
                    f"函数 {func.__name__} 执行失败，耗时: {execution_time:.3f}s",
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator


def retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    logger: Optional[logging.Logger] = None,
):
    """
    重试装饰器

    Args:
        max_attempts: 最大尝试次数
        delay_seconds: 初始延迟秒数
        backoff_factor: 退避因子
        exceptions: 需要重试的异常类型
        logger: 日志记录器

    Returns:
        装饰后的函数
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or logging.getLogger(func.__module__)
            current_delay = delay_seconds
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        func_logger.warning(
                            f"函数 {func.__name__} 第 {attempt}/{max_attempts} 次尝试失败: {e}, "
                            f"{current_delay:.1f}秒后重试..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        func_logger.exception(
                            f"函数 {func.__name__} 达到最大重试次数 {max_attempts}, 最终失败"
                        )

            if last_exception is not None:
                raise last_exception

        return wrapper

    return decorator


def _determine_severity(error: Exception) -> ErrorSeverity:
    """根据异常类型确定严重程度"""
    error_name = type(error).__name__.lower()

    critical_errors = [
        "memoryerror",
        "systemerror",
        "keyboardinterrupt",
    ]
    high_errors = [
        "valueerror",
        "typeerror",
        "keyerror",
        "attributeerror",
    ]
    medium_errors = [
        "timeouterror",
        "connectionerror",
        "httperror",
    ]

    if error_name in critical_errors:
        return ErrorSeverity.CRITICAL
    if error_name in high_errors:
        return ErrorSeverity.HIGH
    if error_name in medium_errors:
        return ErrorSeverity.MEDIUM
    return ErrorSeverity.LOW


def _categorize_error(error: Exception) -> ErrorCategory:
    """根据异常类型分类错误"""
    error_name = type(error).__name__.lower()

    if any(x in error_name for x in ["value", "type", "validate"]):
        return ErrorCategory.VALIDATION
    if any(x in error_name for x in ["network", "connection", "http", "request"]):
        return ErrorCategory.NETWORK
    if any(x in error_name for x in ["data", "parse", "format"]):
        return ErrorCategory.DATA
    if any(x in error_name for x in ["timeout"]):
        return ErrorCategory.TIMEOUT
    if any(x in error_name for x in ["auth", "permission", "access"]):
        return ErrorCategory.AUTH
    if any(x in error_name for x in ["config", "setting"]):
        return ErrorCategory.CONFIG
    return ErrorCategory.UNKNOWN


# 导出常用装饰器
__all__ = [
    "ErrorCategory",
    "ErrorContext",
    "ErrorSeverity",
    "error_handler",
    "log_execution_time",
    "retry",
]
