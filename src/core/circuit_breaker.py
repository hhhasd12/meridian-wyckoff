"""兼容层 shim — 向后兼容重导出

.. deprecated::
    ``src.core.circuit_breaker`` 已废弃，
    请改用 ``src.plugins.risk_management.circuit_breaker``。
"""

import warnings as _warnings

_warnings.warn(
    "src.core.circuit_breaker 已废弃，请改用 src.plugins.risk_management.circuit_breaker",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.risk_management.circuit_breaker import (  # noqa: E402, F401
    CircuitBreaker,
    CircuitBreakerEvent,
    CircuitBreakerStatus,
    DataQualityMetrics,
    MarketType,
    TripReason,
)

__all__ = [
    "CircuitBreakerStatus",
    "MarketType",
    "TripReason",
    "CircuitBreakerEvent",
    "DataQualityMetrics",
    "CircuitBreaker",
]
