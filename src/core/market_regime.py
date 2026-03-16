"""兼容层 shim — 向后兼容重导出

.. deprecated::
    ``src.core.market_regime`` 已废弃，
    请改用 ``src.plugins.market_regime.detector``。
"""

import warnings as _warnings

_warnings.warn(
    "src.core.market_regime 已废弃，请改用 src.plugins.market_regime.detector",
    DeprecationWarning,
    stacklevel=2,
)

from src.plugins.market_regime.detector import (  # noqa: E402, F401
    RegimeDetector,
)

__all__ = [
    "RegimeDetector",
]
