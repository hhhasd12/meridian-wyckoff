"""兼容层 shim — 向后兼容重导出

.. deprecated::
    ``src.core.anomaly_validator`` 已废弃，
    请改用 ``src.plugins.risk_management.anomaly_validator``。
"""

import warnings as _warnings

_warnings.warn(
    "src.core.anomaly_validator 已废弃，请改用 src.plugins.risk_management.anomaly_validator",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.risk_management.anomaly_validator import (  # noqa: E402, F401
    AnomalyEvent,
    AnomalyType,
    AnomalyValidator,
    CorrelationData,
    ValidationResult,
)

__all__ = [
    "AnomalyType",
    "ValidationResult",
    "AnomalyEvent",
    "CorrelationData",
    "AnomalyValidator",
]
