"""
回测验证器Agent模块
连接到威科夫回测引擎 - 负责策略验证和性能评估
修复版：正确调用状态机生成信号
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import os
import json
import logging
import numpy as np
import pandas as pd

from .base_agent import BaseAgent, AgentCapability, AgentState, TaskResult
from .message import AgentMessage, MessageType, Priority


@dataclass
class BacktestResult:
    """回测结果"""
    backtest_id: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    metrics: Dict[str, float] = field(default_factory=dict)


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

AVAILABLE_DATA = {
    "ETHUSDT_1d": "ETHUSDT_1d.csv",
    "ETHUSDT_8h": "ETHUSDT_8h.csv", 
    "ETHUSDT_4h": "ETHUSDT_4h.csv",
    "ETHUSDT_1h": "ETHUSDT_1h.csv",
    "ETHUSDT_15m": "ETHUSDT_15m.csv",
    "ETHUSDT_5m": "ETHUSDT_5m.csv",
}


class BacktestValidatorAgent(BaseAgent):
    """回测验证器Agent - 连接到威科夫回测引擎"""

    def __init__(
        self,
        agent_id: str = "backtest_validator",
        name: str = "回测验证器",
        description: str = "负责策略验证和性能评估",
        config: Optional[Dict[str, Any]] = None,
        message_bus: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        super().__init__(agent_id, name, description, config, message_bus, llm_client)

        self.project_root = config.get("project_root", ".") if config else "."
        self.backtest_history: List[BacktestResult] = []
        
        self.backtest_engine = None
        self.state_machine = None
        self.regime_detector = None

        self._setup_capabilities()
        self._register_handlers()

    def _setup_capabilities(self) -> None:
        """设置Agent能力"""
        self.add_capability(AgentCapability(
            name="run_backtest",
            description="运行回测",
            input_schema={"strategy": "string", "params": "dict", "period": "string"},
            output_schema={"result": "BacktestResult"},
        ))

        self.add_capability(AgentCapability(
            name="validate_strategy",
            description="验证策略",
            input_schema={"config": "dict"},
            output_schema={"valid": "bool", "issues": "list"},
        ))

        self.add_capability(AgentCapability(
            name="compare_strategies",
            description="比较策略",
            input_schema={"strategies": "list"},
            output_schema={"comparison": "dict"},
        ))

    def _register_handlers(self) -> None:
        """注册消息处理器"""
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task_assign)
        self.register_handler(MessageType.REQUEST, self._handle_request)

    def initialize(self) -> None:
        """初始化 - 连接到回测系统"""
        super().initialize()
        
        from src.backtest.engine import BacktestEngine
        from src.core.wyckoff_state_machine import EnhancedWyckoffStateMachine, StateConfig
        from src.plugins.market_regime import RegimeDetector
        
        config = StateConfig()
        config.PATH_SELECTION_THRESHOLD = 0.5
        config.STATE_SWITCH_HYSTERESIS = 0.05
        
        self.backtest_engine = BacktestEngine(initial_capital=10000, commission_rate=0.001)
        self.state_machine = EnhancedWyckoffStateMachine(config)
        self.regime_detector = RegimeDetector()
        
        self.logger.info(f"已连接到威科夫回测系统，数据目录: {DATA_DIR}")
        self.logger.info(f"可用数据: {list(AVAILABLE_DATA.keys())}")

    def execute_task(self, task: Dict[str, Any]) -> TaskResult:
        """执行任务"""
        start_time = datetime.now()
        self.update_state(AgentState.WORKING)

        try:
            task_type = task.get("type", "run_backtest")

            if task_type == "run_backtest":
                result = self._run_backtest(task)
            elif task_type == "validate_strategy":
                result = self._validate_strategy(task)
            elif task_type == "compare_strategies":
                result = self._compare_strategies(task)
            else:
                result = {"error": f"未知任务类型: {task_type}"}

            duration = (datetime.now() - start_time).total_seconds()

            task_result = TaskResult(
                success="error" not in result,
                output=result,
                duration_seconds=duration,
            )
            self.record_task_result(task_result)
            return task_result

        except Exception as e:
            self.logger.error(f"任务执行失败: {e}", exc_info=True)
            return TaskResult(
                success=False,
                output={},
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )
        finally:
            self.update_state(AgentState.IDLE)

    def _handle_task_assign(self, message: AgentMessage) -> AgentMessage:
        """处理任务分配"""
        task = message.content
        result = self.execute_task(task)

        return message.create_response({
            "task_type": task.get("type"),
            "success": result.success,
            "output": result.output,
            "error": result.error_message,
        })

    def _handle_request(self, message: AgentMessage) -> AgentMessage:
        """处理请求"""
        request_type = message.content.get("request_type")

        if request_type == "get_status":
            return message.create_response(self.get_status())
        elif request_type == "get_history":
            return message.create_response({
                "backtests": [self._backtest_to_dict(b) for b in self.backtest_history]
            })
        elif request_type == "get_available_data":
            return message.create_response({"data": list(AVAILABLE_DATA.keys())})
        else:
            return message.create_error_response(f"未知请求类型: {request_type}")

    def _run_backtest(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """运行回测 - 正确调用状态机生成信号"""
        strategy = task.get("strategy", "wyckoff")
        data_source = task.get("data_source", "ETHUSDT_4h")
        
        data = self._load_historical_data(data_source)
        
        if data is None:
            return {"error": f"无法加载数据: {data_source}，可用数据: {list(AVAILABLE_DATA.keys())}"}
        
        self.logger.info(f"加载数据成功: {len(data)} 条K线, 时间范围: {data.index[0]} ~ {data.index[-1]}")
        
        if self.backtest_engine is None:
            from src.backtest.engine import BacktestEngine
            self.backtest_engine = BacktestEngine(initial_capital=10000, commission_rate=0.001)
        
        if self.state_machine is None:
            from src.core.wyckoff_state_machine import EnhancedWyckoffStateMachine
            self.state_machine = EnhancedWyckoffStateMachine()
        
        signals = self._generate_signals_from_state_machine(data)
        
        self.logger.info(f"状态机生成 {len(signals)} 个交易信号")
        
        if len(signals) == 0:
            self.logger.warning("未生成任何交易信号，回测可能无交易")
        
        result = self.backtest_engine.run(
            data=data,
            state_machine=self.state_machine,
            signals=signals,
        )
        
        backtest = BacktestResult(
            backtest_id=f"bt_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            strategy=strategy,
            start_date=str(data.index[0]),
            end_date=str(data.index[-1]),
            initial_capital=result.initial_capital if hasattr(result, 'initial_capital') else 10000,
            final_capital=self.backtest_engine.capital,
            total_return=(self.backtest_engine.capital - 10000) / 10000,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            win_rate=result.win_rate,
            trade_count=result.total_trades,
            metrics={"signal_count": len(signals)},
        )
        
        self.backtest_history.append(backtest)
        
        return {
            "backtest_id": backtest.backtest_id,
            "total_return": backtest.total_return,
            "sharpe_ratio": backtest.sharpe_ratio,
            "max_drawdown": backtest.max_drawdown,
            "win_rate": backtest.win_rate,
            "trade_count": backtest.trade_count,
            "data_source": data_source,
            "bars_count": len(data),
            "signal_count": len(signals),
        }

    def _generate_signals_from_state_machine(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """使用状态机生成交易信号"""
        signals = []
        
        for idx, row in data.iterrows():
            try:
                candle = pd.Series({
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume'],
                })
                
                context = {}
                
                self.state_machine.process_candle(candle, context)
                
                current_signals = self.state_machine.generate_signals()
                
                if current_signals:
                    for sig in current_signals:
                        signal_type = sig.get('type', '')
                        if 'buy' in signal_type.lower():
                            action = 'BUY'
                        elif 'sell' in signal_type.lower():
                            action = 'SELL'
                        else:
                            continue
                        
                        confidence = sig.get('confidence', 0)
                        if confidence < 0.3:
                            continue
                        
                        signals.append({
                            'timestamp': idx,
                            'signal': action,
                            'confidence': confidence,
                            'state': sig.get('state', 'unknown'),
                            'price': row['close'],
                            'strength': sig.get('strength', 'weak'),
                            'action': sig.get('action', 'monitor'),
                            'reason': sig.get('description', '')
                        })
                        
            except Exception as e:
                self.logger.debug(f"处理K线失败 [{idx}]: {e}")
                continue
        
        self.logger.info(f"状态机生成 {len(signals)} 个有效信号")
        return signals

    def _load_historical_data(self, data_key: str) -> Optional[pd.DataFrame]:
        """加载历史数据"""
        if data_key not in AVAILABLE_DATA:
            self.logger.error(f"未知数据源: {data_key}")
            return None
        
        csv_file = os.path.join(DATA_DIR, AVAILABLE_DATA[data_key])
        
        if not os.path.exists(csv_file):
            self.logger.error(f"数据文件不存在: {csv_file}")
            return None
        
        try:
            data = pd.read_csv(csv_file)
            
            time_columns = ['timestamp', 'Timestamp', 'time', 'Time', 'date', 'Date', 'Open_time', 'open_time']
            time_col = None
            for col in time_columns:
                if col in data.columns:
                    time_col = col
                    break
            
            if time_col:
                data[time_col] = pd.to_datetime(data[time_col])
                data.set_index(time_col, inplace=True)
            
            data.columns = [c.lower() for c in data.columns]
            
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            missing = [c for c in required_cols if c not in data.columns]
            if missing:
                self.logger.error(f"数据缺少必需列: {missing}")
                return None
            
            data = data.dropna(subset=required_cols)
            
            self.logger.info(f"成功加载 {len(data)} 条K线数据")
            return data
            
        except Exception as e:
            self.logger.error(f"加载数据失败: {e}")
            return None

    def _validate_strategy(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """验证策略"""
        config = task.get("config", {})

        issues = []
        
        required_keys = ["confidence_threshold", "stability_threshold"]
        for key in required_keys:
            if key not in config:
                issues.append({
                    "type": "missing_config",
                    "key": key,
                    "severity": "warning",
                })
        
        if "confidence_threshold" in config:
            if not 0 <= config["confidence_threshold"] <= 1:
                issues.append({
                    "type": "invalid_range",
                    "key": "confidence_threshold",
                    "severity": "error",
                })
        
        return {
            "valid": len([i for i in issues if i["severity"] == "error"]) == 0,
            "issues": issues,
            "warnings": len([i for i in issues if i["severity"] == "warning"]),
        }

    def _compare_strategies(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """比较策略"""
        strategies = task.get("strategies", [])
        
        if not strategies:
            return {"error": "没有提供策略"}
        
        comparison = []
        for strategy in strategies:
            result = self._run_backtest({"strategy": strategy})
            if "error" not in result:
                comparison.append({
                    "strategy": strategy,
                    "total_return": result.get("total_return", 0),
                    "sharpe_ratio": result.get("sharpe_ratio", 0),
                    "max_drawdown": result.get("max_drawdown", 0),
                    "win_rate": result.get("win_rate", 0),
                })
        
        comparison.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
        
        return {
            "comparison": comparison,
            "best_strategy": comparison[0]["strategy"] if comparison else None,
        }

    def _backtest_to_dict(self, backtest: BacktestResult) -> Dict[str, Any]:
        """将回测结果转换为字典"""
        return {
            "backtest_id": backtest.backtest_id,
            "strategy": backtest.strategy,
            "total_return": backtest.total_return,
            "sharpe_ratio": backtest.sharpe_ratio,
            "max_drawdown": backtest.max_drawdown,
            "win_rate": backtest.win_rate,
            "trade_count": backtest.trade_count,
        }
