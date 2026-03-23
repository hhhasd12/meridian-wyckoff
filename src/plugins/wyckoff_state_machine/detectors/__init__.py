"""插件化检测器目录

从 AccumulationDetectorMixin / DistributionDetectorMixin 迁移而来。
每个检测器实现 NodeDetector 接口，返回 NodeScore 证据。
"""

from ..detector_registry import DetectorRegistry, NodeDetector, NodeScore

__all__ = ["DetectorRegistry", "NodeDetector", "NodeScore"]
