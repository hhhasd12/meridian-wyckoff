"""WyckoffEngine 插件壳 — 插件系统集成"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.kernel.base_plugin import BasePlugin
from src.plugins.wyckoff_engine.engine import EngineEvents, WyckoffEngine
from src.kernel.types import TradingDecision

logger = logging.getLogger(__name__)


class WyckoffEnginePlugin(BasePlugin):
    """统一信号引擎插件

    将 WyckoffEngine 包装为插件系统可管理的组件。
    提供 get_current_state() 和 process_market_data() 代理方法。
    """

    def __init__(self, name: str = "wyckoff_engine", **kwargs: Any) -> None:
        super().__init__(name=name, **kwargs)
        self.engine: Optional[WyckoffEngine] = None

    async def activate(self, context: dict[str, Any]) -> None:
        """激活插件 — 向后兼容（实际初始化已在 on_load 中完成）"""
        if self.engine is not None:
            return
        config = context.get("config", {}).get("wyckoff_engine", {})
        self.engine = WyckoffEngine(config)
        logger.info("WyckoffEngine plugin activated")

    async def deactivate(self) -> None:
        """停用插件"""
        self.engine = None
        logger.info("WyckoffEngine plugin deactivated")

    def on_load(self) -> None:
        """加载插件 — 初始化 WyckoffEngine"""
        config = self._config or {}
        self.engine = WyckoffEngine(config)
        logger.info("WyckoffEngine 引擎初始化完成")

    def on_unload(self) -> None:
        """卸载插件"""
        self.engine = None

    # ================================================================
    # 公开 API — 供 src/api/app.py 和编排器调用
    # ================================================================

    def get_current_state(self) -> Optional[Dict[str, Any]]:
        """获取引擎当前状态快照（含 V4 三层语义 + 三大原则分数）

        Returns:
            包含引擎状态的字典，引擎未激活时返回 None
        """
        if self.engine is None:
            return None
        sm_states: Dict[str, Any] = {}
        for tf, sm in self.engine._state_machines.items():
            sm_entry: Dict[str, Any] = {
                "current_state": sm.current_state,
                "direction": sm.direction.value if sm.direction else None,
                "confidence": sm._state_confidences.get(sm.current_state, 0.0),
            }
            # V4 三层语义
            sm_entry["phase"] = getattr(sm, "current_phase", "IDLE")
            sm_entry["last_confirmed_event"] = getattr(
                sm, "last_confirmed_event", "IDLE"
            )

            # V4 活跃假设
            hyp = getattr(sm, "active_hypothesis", None)
            if hyp is not None:
                sm_entry["hypothesis"] = {
                    "event_name": hyp.event_name,
                    "status": hyp.status.value if hyp.status else None,
                    "confidence": round(hyp.confidence, 4),
                    "bars_held": hyp.bars_held,
                    "confirmation_quality": round(hyp.confirmation_quality, 4),
                    "rejection_reason": hyp.rejection_reason,
                }
            else:
                sm_entry["hypothesis"] = None

            # V4 关键价位（边界）
            sm_entry["boundaries"] = dict(getattr(sm, "critical_levels", {}))

            # V4 三大原则分数（从打分器最后结果获取）
            scorer = getattr(sm, "_scorer", None)
            if scorer is not None:
                last_features = getattr(scorer, "_last_features", None)
                if last_features is not None:
                    sm_entry["principles"] = {
                        "supply_demand": round(last_features.supply_demand, 4),
                        "cause_effect": round(last_features.cause_effect, 4),
                        "effort_result": round(last_features.effort_result, 4),
                    }
                    sm_entry["bar_features"] = {
                        "volume_ratio": round(last_features.volume_ratio, 4),
                        "body_ratio": round(last_features.body_ratio, 4),
                        "is_stopping_action": last_features.is_stopping_action,
                        "spread_vs_volume_divergence": round(
                            last_features.spread_vs_volume_divergence, 4
                        ),
                    }
                else:
                    sm_entry["principles"] = None
                    sm_entry["bar_features"] = None
            else:
                sm_entry["principles"] = None
                sm_entry["bar_features"] = None

            # V4 证据链（最近5条）
            evidence_chain = getattr(sm, "evidence_chain", [])
            sm_entry["recent_evidence"] = [
                {
                    "type": e.evidence_type,
                    "value": round(e.value, 4),
                    "confidence": round(e.confidence, 4),
                    "description": e.description,
                }
                for e in evidence_chain[-5:]
            ]

            sm_states[tf] = sm_entry

        return {
            "timeframes": self.engine._timeframes,
            "state_machines": sm_states,
            "last_candle_time": str(self.engine.last_processed_candle_time)
            if self.engine.last_processed_candle_time
            else None,
            "bar_index": self.engine._bar_index,
        }

    def process_market_data(
        self,
        symbol: str,
        timeframes: List[str],
        data_dict: Dict[str, pd.DataFrame],
    ) -> Tuple[TradingDecision, EngineEvents]:
        """代理到内部引擎的市场数据处理

        Args:
            symbol: 交易对符号
            timeframes: 时间框架列表
            data_dict: {时间框架: DataFrame} 数据字典

        Returns:
            (TradingDecision, EngineEvents) 元组

        Raises:
            RuntimeError: 引擎未激活
        """
        if self.engine is None:
            raise RuntimeError("WyckoffEngine未激活，请先调用activate()")
        return self.engine.process_market_data(symbol, timeframes, data_dict)
