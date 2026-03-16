"""
Agent Teams Web Dashboard
现代化Web界面 - FastAPI后端 + WebSocket实时通信
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("web_dashboard")

active_connections: Set[WebSocket] = set()
agents: Dict[str, Any] = {}
message_bus = None
system_ready = False


class AgentStatus(BaseModel):
    agent_id: str
    name: str
    team: str
    state: str = "IDLE"
    task: str = ""
    last_update: str = ""


class LogMessage(BaseModel):
    timestamp: str
    level: str
    agent: str
    message: str


class ResultMessage(BaseModel):
    timestamp: str
    title: str
    content: str
    level: str


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active.add(websocket)
        logger.info(f"WebSocket连接: {len(self.active)} 个客户端")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active.discard(websocket)
        logger.info(f"WebSocket断开: {len(self.active)} 个客户端")

    async def broadcast(self, message: dict):
        async with self._lock:
            disconnected = set()
            for ws in self.active:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.add(ws)
            for ws in disconnected:
                self.active.discard(ws)


manager = ConnectionManager()

AGENT_CONFIG = {
    "code": {
        "name": "代码团队",
        "color": "#10b981",
        "icon": "💻",
        "agents": [
            {"id": "code_diagnostic", "name": "代码诊断器", "desc": "诊断代码问题", "icon": "🔍"},
            {"id": "code_fixer", "name": "代码修复器", "desc": "修复代码bug", "icon": "🔧"},
            {"id": "code_reviewer", "name": "代码审查器", "desc": "审查代码质量", "icon": "📝"},
        ]
    },
    "quant": {
        "name": "量化团队", 
        "color": "#3b82f6",
        "icon": "📊",
        "agents": [
            {"id": "strategy_optimizer", "name": "策略优化器", "desc": "优化交易策略", "icon": "📈"},
            {"id": "backtest_validator", "name": "回测验证器", "desc": "验证策略效果", "icon": "🎯"},
        ]
    },
    "coordination": {
        "name": "协调团队",
        "color": "#f59e0b",
        "icon": "🎯",
        "agents": [
            {"id": "orchestrator", "name": "协调器", "desc": "协调团队工作", "icon": "🎪"},
            {"id": "reporter", "name": "报告器", "desc": "生成报告", "icon": "📄"},
            {"id": "human_interface", "name": "人工接口", "desc": "人工确认", "icon": "👤"},
        ]
    }
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global message_bus
    try:
        from src.communication import InMemoryMessageBus
        message_bus = InMemoryMessageBus()
        message_bus.start()
        logger.info("消息总线已启动")
    except Exception as e:
        logger.warning(f"消息总线启动失败: {e}")
    
    yield
    
    if message_bus:
        message_bus.stop()
        logger.info("消息总线已停止")


app = FastAPI(title="Agent Teams Dashboard", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return HTMLResponse(content=get_html_page())


@app.get("/api/teams")
async def get_teams():
    return AGENT_CONFIG


@app.get("/api/status")
async def get_status():
    global system_ready
    return {"ready": system_ready, "agents": len(agents)}


@app.post("/api/init")
async def init_system():
    global system_ready, agents, message_bus
    
    if system_ready:
        return {"success": True, "message": "系统已初始化"}
    
    try:
        await manager.broadcast({
            "type": "log",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "INFO",
            "agent": "系统",
            "message": "开始初始化系统..."
        })
        
        from src.agents import (
            CodeDiagnosticAgent, CodeFixerAgent, CodeReviewerAgent,
            StrategyOptimizerAgent, BacktestValidatorAgent,
            OrchestratorAgent, ReportAgent, HumanAgent
        )
        
        agent_classes = {
            "code_diagnostic": CodeDiagnosticAgent,
            "code_fixer": CodeFixerAgent,
            "code_reviewer": CodeReviewerAgent,
            "strategy_optimizer": StrategyOptimizerAgent,
            "backtest_validator": BacktestValidatorAgent,
            "orchestrator": OrchestratorAgent,
            "reporter": ReportAgent,
            "human_interface": HumanAgent,
        }
        
        simple_agents = ["code_diagnostic", "code_fixer", "code_reviewer", "orchestrator", "reporter", "human_interface", "backtest_validator"]
        
        for aid in simple_agents:
            if aid in agent_classes:
                agent_info = None
                for team_config in AGENT_CONFIG.values():
                    for a in team_config["agents"]:
                        if a["id"] == aid:
                            agent_info = a
                            break
                
                if agent_info:
                    await manager.broadcast({
                        "type": "log",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "level": "INFO",
                        "agent": "系统",
                        "message": f"正在初始化 {agent_info['name']}..."
                    })
                    
                    cls = agent_classes[aid]
                    a = cls(agent_id=aid, name=agent_info["name"], message_bus=message_bus)
                    if message_bus:
                        message_bus.register_agent(aid, a.process_message)
                    a.initialize()
                    agents[aid] = a
                    
                    await manager.broadcast({
                        "type": "log",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "level": "SUCCESS",
                        "agent": "系统",
                        "message": f"{agent_info['name']} 初始化完成"
                    })
        
        await manager.broadcast({
            "type": "log",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "INFO",
            "agent": "系统",
            "message": "正在初始化策略优化器（加载多周期数据，可能需要1-2分钟）..."
        })
        
        cls = agent_classes["strategy_optimizer"]
        a = cls(agent_id="strategy_optimizer", name="策略优化器", message_bus=message_bus)
        if message_bus:
            message_bus.register_agent("strategy_optimizer", a.process_message)
        a.initialize()
        agents["strategy_optimizer"] = a
        
        await manager.broadcast({
            "type": "log",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "SUCCESS",
            "agent": "系统",
            "message": "策略优化器初始化完成"
        })
        
        system_ready = True
        await manager.broadcast({
            "type": "system",
            "event": "initialized",
            "message": "系统初始化完成"
        })
        
        return {"success": True, "message": "初始化成功", "agent_count": len(agents)}
        
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        await manager.broadcast({
            "type": "log",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "ERROR",
            "agent": "系统",
            "message": f"初始化失败: {str(e)}"
        })
        return {"success": False, "message": str(e)}


@app.get("/api/data/available")
async def get_available_data():
    return {
        "data_sources": [
            {"id": "ETHUSDT_1d", "name": "ETH/USDT 日线", "timeframe": "1d"},
            {"id": "ETHUSDT_8h", "name": "ETH/USDT 8小时", "timeframe": "8h"},
            {"id": "ETHUSDT_4h", "name": "ETH/USDT 4小时", "timeframe": "4h"},
            {"id": "ETHUSDT_1h", "name": "ETH/USDT 1小时", "timeframe": "1h"},
            {"id": "ETHUSDT_15m", "name": "ETH/USDT 15分钟", "timeframe": "15m"},
            {"id": "ETHUSDT_5m", "name": "ETH/USDT 5分钟", "timeframe": "5m"},
        ]
    }


@app.get("/api/wyckoff/status")
async def get_wyckoff_status():
    """获取威科夫系统状态"""
    global agents
    
    if not system_ready:
        return {"success": False, "message": "系统未初始化"}
    
    strategy_optimizer = agents.get("strategy_optimizer")
    if not strategy_optimizer:
        return {"success": False, "message": "策略优化器未初始化"}
    
    try:
        multi_tf_status = strategy_optimizer._get_multi_timeframe_status({})
        
        wfa_stats = {
            "is_initialized": strategy_optimizer.wfa_backtester.is_initialized if strategy_optimizer.wfa_backtester else False,
            "total_validations": strategy_optimizer.wfa_backtester.total_validations if strategy_optimizer.wfa_backtester else 0,
            "accepted_validations": strategy_optimizer.wfa_backtester.accepted_validations if strategy_optimizer.wfa_backtester else 0,
            "rejected_validations": strategy_optimizer.wfa_backtester.rejected_validations if strategy_optimizer.wfa_backtester else 0,
        }
        
        return {
            "success": True,
            "multi_timeframe": multi_tf_status,
            "wfa_stats": wfa_stats,
            "current_config": strategy_optimizer.current_config if hasattr(strategy_optimizer, 'current_config') else {},
        }
    except Exception as e:
        logger.error(f"获取威科夫状态失败: {e}")
        return {"success": False, "message": str(e)}


@app.get("/api/evolution/progress")
async def get_evolution_progress():
    """获取进化进度"""
    global agents
    
    if not system_ready:
        return {"success": False, "message": "系统未初始化"}
    
    strategy_optimizer = agents.get("strategy_optimizer")
    if not strategy_optimizer:
        return {"success": False, "message": "策略优化器未初始化"}
    
    try:
        optimization_history = [
            {
                "optimization_id": r.optimization_id,
                "method": r.method,
                "improvement": r.improvement,
                "wfa_passed": r.wfa_passed,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in strategy_optimizer.optimization_history[-10:]
        ] if strategy_optimizer.optimization_history else []
        
        return {
            "success": True,
            "optimization_history": optimization_history,
            "total_optimizations": len(strategy_optimizer.optimization_history),
        }
    except Exception as e:
        logger.error(f"获取进化进度失败: {e}")
        return {"success": False, "message": str(e)}


@app.post("/api/evolution/config")
async def set_evolution_config(
    cycles: int = 3,
    eval_mode: str = "fast",
    eval_bars: int = 1000,
    wfa_windows: int = 10,
):
    """设置进化参数"""
    global agents
    
    if not system_ready:
        return {"success": False, "message": "系统未初始化"}
    
    strategy_optimizer = agents.get("strategy_optimizer")
    if not strategy_optimizer:
        return {"success": False, "message": "策略优化器未初始化"}
    
    try:
        strategy_optimizer.evolution_config = {
            "cycles": cycles,
            "eval_mode": eval_mode,
            "eval_bars": eval_bars,
            "wfa_windows": wfa_windows,
        }
        
        return {
            "success": True,
            "message": "进化参数已更新",
            "config": strategy_optimizer.evolution_config,
        }
    except Exception as e:
        logger.error(f"设置进化参数失败: {e}")
        return {"success": False, "message": str(e)}


@app.post("/api/task/{task_type}")
async def run_task(task_type: str, data_source: str = "ETHUSDT_4h"):
    global agents
    
    if not system_ready:
        return {"success": False, "message": "系统未初始化"}
    
    task_map = {
        "diagnose": ("code_diagnostic", {"type": "diagnose_code", "target": "src"}),
        "review": ("code_reviewer", {"type": "check_quality", "directory": "src"}),
        "evolution": ("strategy_optimizer", {"type": "run_evolution", "cycles": 3}),
        "backtest": ("backtest_validator", {"type": "run_backtest", "strategy": "wyckoff", "data_source": data_source}),
        "wfa": ("strategy_optimizer", {"type": "run_wfa_validation", "config": {}}),
    }
    
    if task_type not in task_map:
        return {"success": False, "message": f"未知任务: {task_type}"}
    
    agent_id, task = task_map[task_type]
    
    if agent_id not in agents:
        return {"success": False, "message": f"Agent未初始化: {agent_id}"}
    
    asyncio.create_task(execute_task_async(agent_id, task, task_type))
    
    return {"success": True, "message": f"任务已启动: {task_type}"}


async def execute_task_async(agent_id: str, task: dict, task_type: str):
    global agents
    
    agent = agents.get(agent_id)
    if not agent:
        return
    
    agent_name = ""
    for team_config in AGENT_CONFIG.values():
        for a in team_config["agents"]:
            if a["id"] == agent_id:
                agent_name = a["name"]
                break
    
    main_loop = asyncio.get_event_loop()
    
    if hasattr(agent, 'set_main_loop'):
        agent.set_main_loop(main_loop)
    
    await manager.broadcast({
        "type": "agent_status",
        "agent_id": agent_id,
        "state": "WORKING",
        "task": f"执行{task_type}任务..."
    })
    
    await manager.broadcast({
        "type": "log",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "level": "INFO",
        "agent": agent_name,
        "message": f"开始执行{task_type}任务..."
    })
    
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, agent.execute_task, task
        )
        
        if result.success:
            output = result.output
            
            if task_type == "diagnose":
                msg = f"诊断完成: 发现 {output.get('issue_count', 0)} 个问题"
            elif task_type == "review":
                msg = f"审查完成: 代码质量分数 {output.get('score', 0):.1f}"
            elif task_type == "evolution":
                cycles = output.get("cycles_completed", 0)
                results = output.get("results", [])
                success = sum(1 for r in results if r.get("success", False))
                msg = f"进化完成: {cycles}周期, {success}次成功"
            elif task_type == "backtest":
                ret = output.get("total_return", 0)
                sharpe = output.get("sharpe_ratio", 0)
                msg = f"回测完成: 收益率{ret:.1%}, 夏普{sharpe:.2f}"
            elif task_type == "wfa":
                passed = output.get("passed", False)
                score = output.get("stability_score", 0)
                status = "通过" if passed else "未通过"
                msg = f"WFA验证{status}: 稳定性{score:.2f}"
            else:
                msg = f"任务完成"
            
            await manager.broadcast({
                "type": "log",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "SUCCESS",
                "agent": agent_name,
                "message": msg
            })
            
            await manager.broadcast({
                "type": "result",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "title": f"[{agent_name}] 成功",
                "content": msg,
                "level": "success"
            })
        else:
            await manager.broadcast({
                "type": "log",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "ERROR",
                "agent": agent_name,
                "message": result.error_message or "任务执行失败"
            })
    
    except Exception as e:
        await manager.broadcast({
            "type": "log",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": "ERROR",
            "agent": agent_name,
            "message": str(e)
        })
    
    finally:
        await manager.broadcast({
            "type": "agent_status",
            "agent_id": agent_id,
            "state": "IDLE",
            "task": ""
        })


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


def get_html_page() -> str:
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Teams Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #0f0f1a;
            --bg-secondary: #1a1a2e;
            --bg-tertiary: #252540;
            --accent-green: #10b981;
            --accent-blue: #3b82f6;
            --accent-orange: #f59e0b;
            --accent-red: #ef4444;
            --accent-cyan: #06b6d4;
            --text-primary: #ffffff;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
        }
        
        body {
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }
        
        .container {
            display: grid;
            grid-template-columns: 280px 1fr 380px;
            min-height: 100vh;
            gap: 1px;
            background: var(--bg-tertiary);
        }
        
        .sidebar {
            background: var(--bg-secondary);
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }
        
        .logo {
            text-align: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--bg-tertiary);
        }
        
        .logo h1 {
            font-size: 24px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        
        .logo p {
            color: var(--text-muted);
            font-size: 13px;
        }
        
        .status-card {
            background: var(--bg-tertiary);
            border-radius: 12px;
            padding: 16px;
        }
        
        .status-card .label {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }
        
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--accent-red);
            animation: pulse 2s infinite;
        }
        
        .status-dot.ready {
            background: var(--accent-green);
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .status-text {
            font-weight: 600;
            font-size: 14px;
        }
        
        .section-title {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 12px;
            padding: 0 4px;
        }
        
        .btn-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        
        .btn {
            padding: 14px 16px;
            border: none;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 10px;
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }
        
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .btn.primary {
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
        }
        
        .btn.code {
            background: linear-gradient(135deg, #059669, var(--accent-green));
        }
        
        .btn.quant {
            background: linear-gradient(135deg, #2563eb, var(--accent-blue));
        }
        
        .btn-icon {
            font-size: 18px;
        }
        
        .main-content {
            background: var(--bg-primary);
            padding: 24px;
            overflow-y: auto;
        }
        
        .page-title {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .teams-grid {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        
        .team-card {
            background: var(--bg-secondary);
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid var(--bg-tertiary);
        }
        
        .team-header {
            padding: 16px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--bg-tertiary);
        }
        
        .team-info {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .team-icon {
            font-size: 24px;
        }
        
        .team-name {
            font-size: 16px;
            font-weight: 600;
        }
        
        .team-badge {
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 20px;
            background: var(--bg-tertiary);
            color: var(--text-secondary);
        }
        
        .team-agents {
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        
        .agent-card {
            background: var(--bg-tertiary);
            border-radius: 12px;
            padding: 16px;
            display: grid;
            grid-template-columns: 4px 48px 1fr auto;
            gap: 16px;
            align-items: center;
            transition: all 0.2s;
        }
        
        .agent-card:hover {
            background: #2a2a45;
        }
        
        .agent-status-bar {
            width: 4px;
            height: 100%;
            min-height: 48px;
            border-radius: 2px;
            background: var(--text-muted);
            transition: background 0.3s;
        }
        
        .agent-status-bar.working {
            background: var(--accent-green);
            animation: statusPulse 1s infinite;
        }
        
        .agent-status-bar.success {
            background: var(--accent-cyan);
        }
        
        .agent-status-bar.error {
            background: var(--accent-red);
        }
        
        @keyframes statusPulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        
        .agent-icon {
            font-size: 28px;
            text-align: center;
        }
        
        .agent-info h4 {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .agent-info p {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        .agent-state {
            text-align: right;
        }
        
        .agent-state .state-badge {
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 6px;
            background: var(--bg-secondary);
            color: var(--text-muted);
        }
        
        .agent-state .state-badge.working {
            background: rgba(16, 185, 129, 0.2);
            color: var(--accent-green);
        }
        
        .agent-state .task-text {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }
        
        .right-panel {
            background: var(--bg-secondary);
            display: flex;
            flex-direction: column;
        }
        
        .panel-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }
        
        .panel-header {
            padding: 20px;
            border-bottom: 1px solid var(--bg-tertiary);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .panel-title {
            font-size: 14px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .panel-content {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }
        
        .results-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .result-item {
            background: var(--bg-tertiary);
            border-radius: 10px;
            padding: 14px;
            border-left: 3px solid var(--accent-cyan);
        }
        
        .result-item.success {
            border-left-color: var(--accent-green);
        }
        
        .result-item.error {
            border-left-color: var(--accent-red);
        }
        
        .result-item.warning {
            border-left-color: var(--accent-orange);
        }
        
        .result-time {
            font-size: 11px;
            color: var(--text-muted);
            margin-bottom: 4px;
        }
        
        .result-title {
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .result-content {
            font-size: 12px;
            color: var(--text-secondary);
        }
        
        .logs-list {
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 12px;
            line-height: 1.6;
        }
        
        .log-entry {
            padding: 6px 0;
            border-bottom: 1px solid var(--bg-tertiary);
            display: flex;
            gap: 8px;
        }
        
        .log-time {
            color: var(--text-muted);
            flex-shrink: 0;
        }
        
        .log-agent {
            color: var(--accent-cyan);
            flex-shrink: 0;
            min-width: 80px;
        }
        
        .log-level {
            flex-shrink: 0;
            min-width: 40px;
        }
        
        .log-level.INFO { color: var(--accent-blue); }
        .log-level.SUCCESS { color: var(--accent-green); }
        .log-level.WARNING { color: var(--accent-orange); }
        .log-level.ERROR { color: var(--accent-red); }
        
        .log-message {
            color: var(--text-secondary);
        }
        
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-muted);
        }
        
        .empty-state .icon {
            font-size: 48px;
            margin-bottom: 16px;
            opacity: 0.5;
        }
        
        .wyckoff-status-panel, .evolution-progress-panel {
            background: var(--bg-secondary);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid var(--bg-tertiary);
        }
        
        .status-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        
        .status-header h3 {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .timeframe-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }
        
        .timeframe-card {
            background: var(--bg-tertiary);
            border-radius: 12px;
            padding: 12px;
            text-align: center;
        }
        
        .timeframe-name {
            font-size: 14px;
            font-weight: 600;
            color: var(--accent-cyan);
            margin-bottom: 4px;
        }
        
        .timeframe-bars {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        .timeframe-state {
            font-size: 11px;
            padding: 4px 8px;
            border-radius: 4px;
            background: var(--bg-secondary);
            color: var(--text-secondary);
            margin-top: 8px;
        }
        
        .wfa-stats {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
        }
        
        .stat-item {
            text-align: center;
        }
        
        .stat-label {
            display: block;
            font-size: 11px;
            color: var(--text-muted);
            margin-bottom: 4px;
        }
        
        .stat-value {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .progress-content {
            max-height: 200px;
            overflow-y: auto;
        }
        
        .evolution-item {
            background: var(--bg-tertiary);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .evolution-info {
            flex: 1;
        }
        
        .evolution-id {
            font-size: 12px;
            font-weight: 600;
            color: var(--accent-cyan);
        }
        
        .evolution-details {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }
        
        .evolution-badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }
        
        .evolution-badge.passed {
            background: rgba(16, 185, 129, 0.2);
            color: var(--accent-green);
        }
        
        .evolution-badge.failed {
            background: rgba(239, 68, 68, 0.2);
            color: var(--accent-red);
        }
        
        .progress-bar-container {
            margin-bottom: 16px;
        }
        
        .progress-bar {
            height: 8px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-cyan), var(--accent-green));
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        
        .progress-text {
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 4px;
        }
        
        .progress-status {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
        
        @media (max-width: 1200px) {
            .container {
                grid-template-columns: 1fr;
            }
            .sidebar, .right-panel {
            display: none;
        }
        
        .nav-menu {
            margin-top: 20px;
        }
        
        .nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 4px;
            color: var(--text-secondary);
        }
        
        .nav-item:hover {
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }
        
        .nav-item.active {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(16, 185, 129, 0.2));
            color: var(--accent-cyan);
            border-left: 3px solid var(--accent-cyan);
        }
        
        .nav-icon {
            font-size: 18px;
        }
        
        .nav-text {
            font-size: 14px;
            font-weight: 500;
        }
        
        .page-container {
            display: none;
        }
        
        .page-container.active {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <aside class="sidebar">
            <div class="logo">
                <h1>🤖 Agent Teams</h1>
                <p>威科夫进化系统 v2.0</p>
            </div>
            
            <div class="status-card">
                <div class="label">系统状态</div>
                <div class="status-indicator">
                    <div class="status-dot" id="statusDot"></div>
                    <span class="status-text" id="statusText">未就绪</span>
                </div>
            </div>
            
            <div class="nav-menu">
                <div class="nav-item active" onclick="showPage('agent')" id="nav-agent">
                    <span class="nav-icon">👥</span>
                    <span class="nav-text">Agent</span>
                </div>
                <div class="nav-item" onclick="showPage('evolution')" id="nav-evolution">
                    <span class="nav-icon">📈</span>
                    <span class="nav-text">进化</span>
                </div>
                <div class="nav-item" onclick="showPage('backtest')" id="nav-backtest">
                    <span class="nav-icon">🎯</span>
                    <span class="nav-text">回测</span>
                </div>
                <div class="nav-item" onclick="showPage('monitor')" id="nav-monitor">
                    <span class="nav-icon">📊</span>
                    <span class="nav-text">监控</span>
                </div>
            </div>
            
            <div style="margin-top: 20px;">
                <div class="section-title">系统控制</div>
                <div class="btn-group">
                    <button class="btn primary" id="initBtn" onclick="initSystem()">
                        <span class="btn-icon">⚡</span>
                        初始化系统
                    </button>
                </div>
            </div>
            
            <div>
                <div class="section-title" style="color: var(--accent-green);">代码团队</div>
                <div class="btn-group">
                    <button class="btn code" id="diagnoseBtn" onclick="runTask('diagnose')" disabled>
                        <span class="btn-icon">🔍</span>
                        诊断代码
                    </button>
                    <button class="btn code" id="reviewBtn" onclick="runTask('review')" disabled>
                        <span class="btn-icon">📝</span>
                        审查代码
                    </button>
                </div>
            </div>
            
            <div>
                <div class="section-title" style="color: var(--accent-blue);">量化团队</div>
                <div class="btn-group">
                    <button class="btn quant" id="evolutionBtn" onclick="runTask('evolution')" disabled>
                        <span class="btn-icon">📈</span>
                        运行进化
                    </button>
                    <button class="btn quant" id="backtestBtn" onclick="runTask('backtest')" disabled>
                        <span class="btn-icon">🎯</span>
                        运行回测
                    </button>
                    <button class="btn quant" id="wfaBtn" onclick="runTask('wfa')" disabled>
                        <span class="btn-icon">✓</span>
                        WFA验证
                    </button>
                </div>
            </div>
        </aside>
        
        <main class="main-content">
            <!-- Agent页面 -->
            <div class="page-container active" id="page-agent">
                <div class="page-title">
                    <span>👥</span>
                    Agent 团队视图
                </div>
                <div class="teams-grid" id="teamsGrid">
                </div>
            </div>
            
            <!-- 进化页面 -->
            <div class="page-container" id="page-evolution">
                <div class="page-title">
                    <span>📈</span>
                    进化系统
                </div>
                <div class="wyckoff-status-panel" id="wyckoffStatusPanel" style="display: block;">
                    <div class="status-header">
                        <h3>📊 多周期状态监控</h3>
                        <button class="btn" style="padding: 6px 12px; font-size: 11px;" onclick="refreshWyckoffStatus()">刷新</button>
                    </div>
                    <div class="timeframe-grid" id="timeframeGrid">
                    </div>
                    <div class="wfa-stats" id="wfaStats">
                        <div class="stat-item">
                            <span class="stat-label">WFA状态</span>
                            <span class="stat-value" id="wfaStatus">未初始化</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">总验证</span>
                            <span class="stat-value" id="totalValidations">0</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">已接受</span>
                            <span class="stat-value" id="acceptedValidations" style="color: var(--accent-green);">0</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">已拒绝</span>
                            <span class="stat-value" id="rejectedValidations" style="color: var(--accent-red);">0</span>
                        </div>
                    </div>
                </div>
                
                <div class="evolution-progress-panel" id="evolutionProgressPanel" style="display: block;">
                    <div class="status-header">
                        <h3>📈 进化进度</h3>
                    </div>
                    <div class="progress-content" id="progressContent">
                        <div class="empty-state">
                            <div class="icon">📈</div>
                            <p>暂无进化记录</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 回测页面 -->
            <div class="page-container" id="page-backtest">
                <div class="page-title">
                    <span>🎯</span>
                    回测系统
                </div>
                <div class="wyckoff-status-panel">
                    <div class="status-header">
                        <h3>📊 性能指标</h3>
                    </div>
                    <div class="wfa-stats">
                        <div class="stat-item">
                            <span class="stat-label">夏普比率</span>
                            <span class="stat-value" id="sharpeRatio">--</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">最大回撤</span>
                            <span class="stat-value" id="maxDrawdown">--</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">胜率</span>
                            <span class="stat-value" id="winRate">--</span>
                        </div>
                        <div class="stat-item">
                            <span class="stat-label">总收益</span>
                            <span class="stat-value" id="totalReturn">--</span>
                        </div>
                    </div>
                </div>
                
                <div class="evolution-progress-panel">
                    <div class="status-header">
                        <h3>📋 交易信号</h3>
                    </div>
                    <div class="progress-content" id="signalsContent">
                        <div class="empty-state">
                            <div class="icon">📋</div>
                            <p>暂无交易信号</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 监控页面 -->
            <div class="page-container" id="page-monitor">
                <div class="page-title">
                    <span>📊</span>
                    多周期监控
                </div>
                <div class="wyckoff-status-panel">
                    <div class="status-header">
                        <h3>📊 实时状态</h3>
                        <button class="btn" style="padding: 6px 12px; font-size: 11px;" onclick="refreshWyckoffStatus()">刷新</button>
                    </div>
                    <div class="timeframe-grid" id="monitorTimeframeGrid">
                    </div>
                </div>
                
                <div class="evolution-progress-panel">
                    <div class="status-header">
                        <h3>📈 TR边界</h3>
                    </div>
                    <div class="progress-content" id="trBoundaries">
                        <div class="empty-state">
                            <div class="icon">📈</div>
                            <p>暂无TR边界数据</p>
                        </div>
                    </div>
                </div>
            </div>
        </main>
        
        <aside class="right-panel">
            <div class="panel-section" style="flex: 0 0 auto; max-height: 35%;">
                <div class="panel-header">
                    <div class="panel-title">📋 执行结果</div>
                    <button class="btn" style="padding: 6px 12px; font-size: 11px;" onclick="clearResults()">清空</button>
                </div>
                <div class="panel-content" id="resultsPanel">
                    <div class="empty-state">
                        <div class="icon">📭</div>
                        <p>暂无执行结果</p>
                    </div>
                </div>
            </div>
            
            <div class="panel-section">
                <div class="panel-header">
                    <div class="panel-title">📝 运行日志</div>
                </div>
                <div class="panel-content" id="logsPanel">
                    <div class="empty-state">
                        <div class="icon">📋</div>
                        <p>暂无日志</p>
                    </div>
                </div>
            </div>
        </aside>
    </div>
    
    <script>
        const teamsConfig = {
            code: {
                name: "代码团队",
                color: "#10b981",
                icon: "💻",
                agents: [
                    {id: "code_diagnostic", name: "代码诊断器", desc: "诊断代码问题", icon: "🔍"},
                    {id: "code_fixer", name: "代码修复器", desc: "修复代码bug", icon: "🔧"},
                    {id: "code_reviewer", name: "代码审查器", desc: "审查代码质量", icon: "📝"},
                ]
            },
            quant: {
                name: "量化团队",
                color: "#3b82f6",
                icon: "📊",
                agents: [
                    {id: "strategy_optimizer", name: "策略优化器", desc: "优化交易策略", icon: "📈"},
                    {id: "backtest_validator", name: "回测验证器", desc: "验证策略效果", icon: "🎯"},
                ]
            },
            coordination: {
                name: "协调团队",
                color: "#f59e0b",
                icon: "🎯",
                agents: [
                    {id: "orchestrator", name: "协调器", desc: "协调团队工作", icon: "🎪"},
                    {id: "reporter", name: "报告器", desc: "生成报告", icon: "📄"},
                    {id: "human_interface", name: "人工接口", desc: "人工确认", icon: "👤"},
                ]
            }
        };
        
        const agentStates = {};
        const logs = [];
        const results = [];
        let ws = null;
        let systemReady = false;
        
        function initUI() {
            const grid = document.getElementById('teamsGrid');
            grid.innerHTML = '';
            
            for (const [teamId, team] of Object.entries(teamsConfig)) {
                const teamCard = document.createElement('div');
                teamCard.className = 'team-card';
                teamCard.innerHTML = `
                    <div class="team-header">
                        <div class="team-info">
                            <span class="team-icon">${team.icon}</span>
                            <span class="team-name" style="color: ${team.color}">${team.name}</span>
                        </div>
                        <span class="team-badge">${team.agents.length} Agents</span>
                    </div>
                    <div class="team-agents" id="team-${teamId}">
                        ${team.agents.map(a => {
                            agentStates[a.id] = {state: 'IDLE', task: ''};
                            return `
                                <div class="agent-card" id="agent-${a.id}">
                                    <div class="agent-status-bar" id="bar-${a.id}"></div>
                                    <div class="agent-icon">${a.icon}</div>
                                    <div class="agent-info">
                                        <h4 style="color: ${team.color}">${a.name}</h4>
                                        <p>${a.desc}</p>
                                    </div>
                                    <div class="agent-state">
                                        <span class="state-badge" id="badge-${a.id}">空闲</span>
                                        <div class="task-text" id="task-${a.id}"></div>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
                grid.appendChild(teamCard);
            }
        }
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleMessage(data);
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected, reconnecting...');
                setTimeout(connectWebSocket, 3000);
            };
        }
        
        function handleMessage(data) {
            switch(data.type) {
                case 'system':
                    if (data.event === 'initialized') {
                        setSystemReady(true);
                    }
                    break;
                case 'agent_status':
                    updateAgentStatus(data.agent_id, data.state, data.task);
                    break;
                case 'log':
                    addLog(data.timestamp, data.level, data.agent, data.message);
                    break;
                case 'result':
                    addResult(data.timestamp, data.title, data.content, data.level);
                    break;
                case 'evolution_progress':
                    updateEvolutionProgress(data);
                    break;
                case 'evolution_cycle_complete':
                    addEvolutionCycleResult(data);
                    break;
            }
        }
        
        function updateEvolutionProgress(data) {
            const currentCycle = data.current_cycle || 0;
            const totalCycles = data.total_cycles || 0;
            const status = data.status || 'unknown';
            const message = data.message || '';
            
            const progressPanel = document.getElementById('evolutionProgressPanel');
            if (!progressPanel) return;
            
            const progressContent = document.getElementById('progressContent');
            if (!progressContent) return;
            
            const progressPercent = totalCycles > 0 ? ((currentCycle / totalCycles) * 100).toFixed(1) : 0;
            
            progressContent.innerHTML = `
                <div class="progress-bar-container">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progressPercent}%"></div>
                    </div>
                    <div class="progress-text">${currentCycle}/${totalCycles} (${progressPercent}%)</div>
                </div>
                <div class="progress-status">
                    <div class="status-item">
                        <span class="stat-label">状态</span>
                        <span class="stat-value">${status}</span>
                    </div>
                    <div class="status-item">
                        <span class="stat-label">当前消息</span>
                        <span class="stat-value">${message}</span>
                    </div>
                </div>
            `;
        }
        
        function addEvolutionCycleResult(data) {
            const cycle = data.cycle || 0;
            const success = data.success || false;
            const improvement = data.improvement || 0;
            const wfa_passed = data.wfa_passed || false;
            const duration = data.duration || 0;
            
            const progressContent = document.getElementById('progressContent');
            if (!progressContent) return;
            
            const passedClass = wfa_passed ? 'passed' : 'failed';
            const passedText = wfa_passed ? 'WFA通过' : 'WFA未通过';
            const improvementText = (improvement * 100).toFixed(2);
            
            const existingContent = progressContent.innerHTML;
            const newResult = `
                <div class="evolution-item">
                    <div class="evolution-info">
                        <div class="evolution-id">周期 ${cycle}</div>
                        <div class="evolution-details">
                            成功: ${success ? '是' : '否'} | 改进: ${improvementText}% | 耗时: ${duration.toFixed(1)}秒
                        </div>
                    </div>
                    <span class="evolution-badge ${passedClass}">${passedText}</span>
                </div>
            `;
            
            if (existingContent.includes('暂无进化记录')) {
                progressContent.innerHTML = newResult;
            } else {
                progressContent.innerHTML = newResult + existingContent;
            }
        }
        
        function updateAgentStatus(agentId, state, task) {
            agentStates[agentId] = {state, task};
            
            const bar = document.getElementById(`bar-${agentId}`);
            const badge = document.getElementById(`badge-${agentId}`);
            const taskEl = document.getElementById(`task-${agentId}`);
            
            if (bar) {
                bar.className = 'agent-status-bar';
                if (state === 'WORKING') bar.classList.add('working');
                else if (state === 'SUCCESS') bar.classList.add('success');
                else if (state === 'ERROR') bar.classList.add('error');
            }
            
            if (badge) {
                badge.className = 'state-badge';
                if (state === 'WORKING') {
                    badge.classList.add('working');
                    badge.textContent = '工作中';
                } else if (state === 'SUCCESS') {
                    badge.textContent = '成功';
                } else if (state === 'ERROR') {
                    badge.textContent = '错误';
                } else {
                    badge.textContent = '空闲';
                }
            }
            
            if (taskEl) {
                taskEl.textContent = task || '';
            }
        }
        
        function addLog(timestamp, level, agent, message) {
            logs.unshift({timestamp, level, agent, message});
            if (logs.length > 100) logs.pop();
            renderLogs();
        }
        
        function addResult(timestamp, title, content, level) {
            results.unshift({timestamp, title, content, level});
            if (results.length > 20) results.pop();
            renderResults();
        }
        
        function renderLogs() {
            const panel = document.getElementById('logsPanel');
            if (logs.length === 0) {
                panel.innerHTML = '<div class="empty-state"><div class="icon">📋</div><p>暂无日志</p></div>';
                return;
            }
            
            panel.innerHTML = `<div class="logs-list">${logs.map(l => `
                <div class="log-entry">
                    <span class="log-time">[${l.timestamp}]</span>
                    <span class="log-agent">[${l.agent}]</span>
                    <span class="log-level ${l.level}">[${l.level}]</span>
                    <span class="log-message">${l.message}</span>
                </div>
            `).join('')}</div>`;
        }
        
        function renderResults() {
            const panel = document.getElementById('resultsPanel');
            if (results.length === 0) {
                panel.innerHTML = '<div class="empty-state"><div class="icon">📭</div><p>暂无执行结果</p></div>';
                return;
            }
            
            panel.innerHTML = `<div class="results-list">${results.map(r => `
                <div class="result-item ${r.level}">
                    <div class="result-time">${r.timestamp}</div>
                    <div class="result-title">${r.title}</div>
                    <div class="result-content">${r.content}</div>
                </div>
            `).join('')}</div>`;
        }
        
        function clearResults() {
            results.length = 0;
            renderResults();
        }
        
        function setSystemReady(ready) {
            systemReady = ready;
            const dot = document.getElementById('statusDot');
            const text = document.getElementById('statusText');
            const initBtn = document.getElementById('initBtn');
            
            if (ready) {
                dot.classList.add('ready');
                text.textContent = '运行中';
                initBtn.textContent = '✓ 已就绪';
                initBtn.disabled = true;
                
                ['diagnoseBtn', 'reviewBtn', 'evolutionBtn', 'backtestBtn', 'wfaBtn'].forEach(id => {
                    document.getElementById(id).disabled = false;
                });
                
                // 初始化后立即获取状态
                refreshWyckoffStatus();
                refreshEvolutionProgress();
            }
        }
        
        function showPage(pageName) {
            // 隐藏所有页面
            document.querySelectorAll('.page-container').forEach(page => {
                page.classList.remove('active');
            });
            
            // 移除所有导航项的active状态
            document.querySelectorAll('.nav-item').forEach(nav => {
                nav.classList.remove('active');
            });
            
            // 显示选中的页面
            const targetPage = document.getElementById('page-' + pageName);
            if (targetPage) {
                targetPage.classList.add('active');
            }
            
            // 激活对应的导航项
            const targetNav = document.getElementById('nav-' + pageName);
            if (targetNav) {
                targetNav.classList.add('active');
            }
            
            // 如果切换到进化或监控页面，刷新状态
            if (pageName === 'evolution' || pageName === 'monitor') {
                refreshWyckoffStatus();
            }
            if (pageName === 'evolution') {
                refreshEvolutionProgress();
            }
        }
        
        async function refreshWyckoffStatus() {
            try {
                const res = await fetch('/api/wyckoff/status');
                const data = await res.json();
                
                if (data.success) {
                    renderWyckoffStatus(data);
                }
            } catch (e) {
                console.error('获取威科夫状态失败:', e);
            }
        }
        
        function renderWyckoffStatus(data) {
            const timeframeGrid = document.getElementById('timeframeGrid');
            const multi_tf = data.multi_timeframe || {};
            const data_summary = multi_tf.data_summary || {};
            
            let html = '';
            for (const [tf, summary] of Object.entries(data_summary)) {
                const bars = summary.bars || 0;
                const start = summary.start ? summary.start.split('T')[0] : 'N/A';
                const end = summary.end ? summary.end.split('T')[0] : 'N/A';
                
                html += `
                    <div class="timeframe-card">
                        <div class="timeframe-name">${tf.toUpperCase()}</div>
                        <div class="timeframe-bars">${bars.toLocaleString()} 条K线</div>
                        <div class="timeframe-state">${start} ~ ${end}</div>
                    </div>
                `;
            }
            timeframeGrid.innerHTML = html;
            
            const wfaStats = data.wfa_stats || {};
            document.getElementById('wfaStatus').textContent = wfaStats.is_initialized ? '已初始化' : '未初始化';
            document.getElementById('totalValidations').textContent = wfaStats.total_validations || 0;
            document.getElementById('acceptedValidations').textContent = wfaStats.accepted_validations || 0;
            document.getElementById('rejectedValidations').textContent = wfaStats.rejected_validations || 0;
        }
        
        async function refreshEvolutionProgress() {
            try {
                const res = await fetch('/api/evolution/progress');
                const data = await res.json();
                
                if (data.success) {
                    renderEvolutionProgress(data);
                }
            } catch (e) {
                console.error('获取进化进度失败:', e);
            }
        }
        
        function renderEvolutionProgress(data) {
            const progressContent = document.getElementById('progressContent');
            const history = data.optimization_history || [];
            
            if (history.length === 0) {
                progressContent.innerHTML = '<div class="empty-state"><div class="icon">📈</div><p>暂无进化记录</p></div>';
                return;
            }
            
            let html = '<div class="evolution-list">';
            for (const item of history) {
                const passedClass = item.wfa_passed ? 'passed' : 'failed';
                const passedText = item.wfa_passed ? 'WFA通过' : 'WFA未通过';
                const improvement = (item.improvement * 100).toFixed(2);
                
                html += `
                    <div class="evolution-item">
                        <div class="evolution-info">
                            <div class="evolution-id">${item.optimization_id}</div>
                            <div class="evolution-details">
                                方法: ${item.method} | 改进: ${improvement}% | ${item.timestamp}
                            </div>
                        </div>
                        <span class="evolution-badge ${passedClass}">${passedText}</span>
                    </div>
                `;
            }
            html += '</div>';
            
            progressContent.innerHTML = html;
        }
        
        async function initSystem() {
            const btn = document.getElementById('initBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="btn-icon">⏳</span> 初始化中...';
            
            try {
                const res = await fetch('/api/init', {method: 'POST'});
                const data = await res.json();
                
                if (data.success) {
                    setSystemReady(true);
                } else {
                    btn.disabled = false;
                    btn.innerHTML = '<span class="btn-icon">⚡</span> 初始化系统';
                    alert('初始化失败: ' + data.message);
                }
            } catch (e) {
                btn.disabled = false;
                btn.innerHTML = '<span class="btn-icon">⚡</span> 初始化系统';
                alert('初始化失败: ' + e.message);
            }
        }
        
        async function runTask(taskType) {
            if (!systemReady) {
                alert('请先初始化系统');
                return;
            }
            
            try {
                await fetch(`/api/task/${taskType}`, {method: 'POST'});
            } catch (e) {
                console.error('Task failed:', e);
            }
        }
        
        initUI();
        connectWebSocket();
    </script>
</body>
</html>'''
