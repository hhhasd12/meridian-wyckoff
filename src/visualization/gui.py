"""
Agent Teams 桌面GUI - 优化版
团队竖向排列，状态显示更明显
"""

import customtkinter as ctk
import threading
import queue
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import os

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

logger = logging.getLogger("gui")

_FONTS: Dict[str, Any] = {}

def _font(name: str, size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    if name not in _FONTS:
        _FONTS[name] = ctk.CTkFont(size=size, weight=weight)
    return _FONTS[name]

_STATE_COLORS = {
    "IDLE": "#666666",
    "WORKING": "#00ff88", 
    "WAITING": "#ffaa00",
    "ERROR": "#ff6b6b",
    "SUCCESS": "#00d4ff",
}

_STATE_TEXTS = {
    "IDLE": "空闲",
    "WORKING": "工作中",
    "WAITING": "等待中",
    "ERROR": "错误",
    "SUCCESS": "成功",
}

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

TEAMS = {
    "code": {
        "name": "代码团队",
        "color": "#4CAF50",
        "description": "代码诊断、修复、审查",
        "agents": [
            ("code_diagnostic", "代码诊断器", "诊断代码问题", "🔍"),
            ("code_fixer", "代码修复器", "修复代码bug", "🔧"),
            ("code_reviewer", "代码审查器", "审查代码质量", "📝"),
        ],
    },
    "quant": {
        "name": "量化团队",
        "color": "#2196F3",
        "description": "策略优化、回测验证",
        "agents": [
            ("strategy_optimizer", "策略优化器", "优化交易策略", "📊"),
            ("backtest_validator", "回测验证器", "验证策略效果", "📈"),
        ],
    },
    "coordination": {
        "name": "协调团队",
        "color": "#FF9800",
        "description": "团队协调、报告生成",
        "agents": [
            ("orchestrator", "协调器", "协调团队工作", "🎯"),
            ("reporter", "报告器", "生成报告", "📄"),
            ("human_interface", "人工接口", "人工确认", "👤"),
        ],
    },
}


class AgentCard:
    """Agent卡片 - 增强状态显示"""
    def __init__(self, parent, agent_id: str, name: str, desc: str, icon: str, team_color: str):
        self.agent_id = agent_id
        self.name = name
        self.state = "IDLE"
        self._anim = False
        self._idx = 0

        # 主框架 - 增加高度
        self.frame = ctk.CTkFrame(parent, corner_radius=12, fg_color="#1a1a2e", height=100)
        self.frame.pack(fill="x", pady=4, padx=4)
        self.frame.pack_propagate(False)
        
        # 状态指示条
        self.status_bar = ctk.CTkFrame(self.frame, width=6, fg_color="#333333")
        self.status_bar.place(x=0, y=0, relheight=1)
        
        # 内容区域
        content = ctk.CTkFrame(self.frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=8)
        
        # 上排：图标 + 名称 + 状态
        top = ctk.CTkFrame(content, fg_color="transparent")
        top.pack(fill="x")
        
        ctk.CTkLabel(top, text=icon, font=_font("icon", 24)).pack(side="left")
        
        info = ctk.CTkFrame(top, fg_color="transparent")
        info.pack(side="left", padx=10, fill="x", expand=True)
        
        ctk.CTkLabel(info, text=name, font=_font("name", 13, "bold"), text_color=team_color, anchor="w").pack(fill="x")
        ctk.CTkLabel(info, text=desc, font=_font("desc", 9), text_color="#666", anchor="w").pack(fill="x")
        
        # 状态显示区
        status_frame = ctk.CTkFrame(top, fg_color="transparent")
        status_frame.pack(side="right")
        
        self.spinner = ctk.CTkLabel(status_frame, text="", font=_font("sp", 16))
        self.spinner.pack()
        
        self.status_label = ctk.CTkLabel(status_frame, text="空闲", font=_font("st", 10, "bold"), text_color="#666")
        self.status_label.pack()
        
        # 下排：任务描述
        self.task = ctk.CTkLabel(content, text="等待任务...", font=_font("task", 10), text_color="#888", anchor="w")
        self.task.pack(fill="x", pady=(4, 0))
        
        # 进度条
        self.progress = ctk.CTkProgressBar(content, height=4, corner_radius=2, fg_color="#333", progress_color=team_color)
        self.progress.pack(fill="x", pady=(4, 0))
        self.progress.set(0)

    def set_state(self, state: str, task: str = ""):
        self.state = state
        color = _STATE_COLORS.get(state, "#666")
        
        # 更新状态条颜色
        self.status_bar.configure(fg_color=color)
        
        # 更新状态文字
        self.status_label.configure(text=_STATE_TEXTS.get(state, state), text_color=color)
        
        # 更新任务描述
        self.task.configure(text=task if task else "等待任务...")
        
        # 动画控制
        if state == "WORKING" and not self._anim:
            self._anim = True
            self._animate()
        elif state != "WORKING":
            self._anim = False
            self.spinner.configure(text="")
            if state == "SUCCESS":
                self.progress.set(1)
            elif state == "ERROR":
                self.progress.set(0)
            else:
                self.progress.set(0)

    def _animate(self):
        if not self._anim:
            return
        self._idx = (self._idx + 1) % len(_SPINNER)
        self.spinner.configure(text=_SPINNER[self._idx], text_color="#00ff88")
        self.progress.set(0.3 + 0.4 * ((self._idx % 10) / 10))
        self.frame.after(80, self._animate)


class TeamPanel:
    """团队面板 - 竖向排列"""
    def __init__(self, parent, team_id: str, team_config: Dict[str, Any]):
        self.team_id = team_id
        self.team_config = team_config
        self.cards: Dict[str, AgentCard] = {}

        # 主框架
        self.frame = ctk.CTkFrame(parent, corner_radius=15, fg_color="#0d0d1a")
        
        # 标题区域
        header = ctk.CTkFrame(self.frame, fg_color="transparent", height=40)
        header.pack(fill="x", padx=15, pady=(15, 5))
        header.pack_propagate(False)
        
        # 团队图标和名称
        ctk.CTkLabel(
            header, 
            text=f"▶ {team_config['name']}", 
            font=_font("team", 16, "bold"), 
            text_color=team_config['color']
        ).pack(side="left")
        
        # Agent数量
        ctk.CTkLabel(
            header, 
            text=f"{len(team_config['agents'])} Agent", 
            font=_font("count", 10), 
            text_color="#666"
        ).pack(side="right")
        
        # 分隔线
        ctk.CTkFrame(self.frame, height=2, fg_color=team_config['color']).pack(fill="x", padx=15, pady=5)
        
        # Agent列表区域
        agents_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        agents_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        for aid, nm, dc, ic in team_config['agents']:
            card = AgentCard(agents_frame, aid, nm, dc, ic, team_config['color'])
            self.cards[aid] = card


class ResultPanel:
    """结果面板 - 显示重要内容"""
    def __init__(self, parent):
        self.frame = ctk.CTkFrame(parent, corner_radius=15, fg_color="#0d0d1a")
        
        # 标题
        header = ctk.CTkFrame(self.frame, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(
            header, 
            text="📋 执行结果", 
            font=_font("result", 14, "bold"), 
            text_color="#00d4ff"
        ).pack(side="left")
        
        ctk.CTkButton(
            header,
            text="清空",
            font=_font("clear", 9),
            width=50,
            height=24,
            corner_radius=6,
            fg_color="#333",
            command=self._clear
        ).pack(side="right")
        
        # 结果显示区
        self.result_box = ctk.CTkTextbox(
            self.frame, 
            font=_font("result", 10), 
            corner_radius=8,
            fg_color="#1a1a2e",
            height=150
        )
        self.result_box.pack(fill="both", expand=True, padx=10, pady=10)

    def add_result(self, title: str, content: str, level: str = "info"):
        colors = {
            "info": "#00d4ff",
            "success": "#00ff88",
            "warning": "#ffaa00",
            "error": "#ff6b6b",
        }
        
        t = datetime.now().strftime("%H:%M:%S")
        color = colors.get(level, "#fff")
        
        self.result_box.insert("end", f"\n[{t}] ", "time")
        self.result_box.insert("end", f"{title}\n", "title")
        self.result_box.insert("end", f"{content}\n", "content")
        self.result_box.insert("end", "─" * 40 + "\n", "sep")
        self.result_box.see("end")

    def _clear(self):
        self.result_box.delete("1.0", "end")


class Dashboard:
    """主控制面板 - 优化布局"""
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Agent Teams 控制面板 - 威科夫进化系统")
        self.root.geometry("1200x900")
        
        self.agents: Dict[str, Any] = {}
        self.issues: List[Dict] = []
        self.queue = queue.Queue()
        self.bus = None
        self.ready = False
        self.team_panels: Dict[str, TeamPanel] = {}
        self.result_panel: Optional[ResultPanel] = None
        self.agent_logs: Dict[str, List[str]] = {}
        
        for team_id, team_config in TEAMS.items():
            for aid, _, _, _ in team_config['agents']:
                self.agent_logs[aid] = []
        
        self._build()
        self._poll()

    def _build(self):
        # 主布局
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 左侧：控制面板
        left = ctk.CTkFrame(main, width=220, corner_radius=15)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        
        self._sidebar(left)
        
        # 中间：团队视图（竖向排列）
        center = ctk.CTkFrame(main, width=350, corner_radius=15)
        center.pack(side="left", fill="y", padx=(0, 10))
        center.pack_propagate(False)
        
        self._teams_view(center)
        
        # 右侧：结果和日志
        right = ctk.CTkFrame(main, corner_radius=15)
        right.pack(side="left", fill="both", expand=True)
        
        self._right_panel(right)

    def _sidebar(self, p):
        # 标题
        ctk.CTkLabel(p, text="🤖 Agent Teams", font=_font("ttl", 18, "bold"), text_color="#00d4ff").pack(pady=(20, 5))
        ctk.CTkLabel(p, text="威科夫进化系统", font=_font("sub", 10), text_color="#666").pack(pady=(0, 15))
        
        # 状态
        sf = ctk.CTkFrame(p, fg_color="#1a1a2e", corner_radius=8)
        sf.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(sf, text="系统状态", font=_font("lbl", 9), text_color="#666").pack(anchor="w", padx=10, pady=(8, 2))
        self.status = ctk.CTkLabel(sf, text="● 未就绪", font=_font("st", 12, "bold"), text_color="#ff6b6b")
        self.status.pack(anchor="w", padx=10, pady=(0, 8))
        
        # 按钮
        ctk.CTkLabel(p, text="── 控制 ──", font=_font("sep", 9), text_color="#333").pack(pady=(15, 5))
        
        self.init_btn = ctk.CTkButton(p, text="初始化系统", font=_font("btn", 11), height=38, corner_radius=10, command=self._init)
        self.init_btn.pack(fill="x", padx=10, pady=3)
        
        # 代码团队
        ctk.CTkLabel(p, text="── 代码团队 ──", font=_font("sep", 9), text_color="#4CAF50").pack(pady=(15, 5))
        
        self.code_diag_btn = ctk.CTkButton(p, text="🔍 诊断代码", font=_font("btn", 10), height=32, corner_radius=8, fg_color="#2d2d3d", state="disabled", command=self._diagnose_code)
        self.code_diag_btn.pack(fill="x", padx=10, pady=2)
        
        self.code_review_btn = ctk.CTkButton(p, text="📝 审查代码", font=_font("btn", 10), height=32, corner_radius=8, fg_color="#2d2d3d", state="disabled", command=self._review_code)
        self.code_review_btn.pack(fill="x", padx=10, pady=2)
        
        # 量化团队
        ctk.CTkLabel(p, text="── 量化团队 ──", font=_font("sep", 9), text_color="#2196F3").pack(pady=(15, 5))
        
        self.quant_opt_btn = ctk.CTkButton(p, text="📊 运行进化", font=_font("btn", 10), height=32, corner_radius=8, fg_color="#2d2d3d", state="disabled", command=self._run_evolution)
        self.quant_opt_btn.pack(fill="x", padx=10, pady=2)
        
        self.quant_backtest_btn = ctk.CTkButton(p, text="📈 运行回测", font=_font("btn", 10), height=32, corner_radius=8, fg_color="#2d2d3d", state="disabled", command=self._run_backtest)
        self.quant_backtest_btn.pack(fill="x", padx=10, pady=2)
        
        self.quant_wfa_btn = ctk.CTkButton(p, text="✓ WFA验证", font=_font("btn", 10), height=32, corner_radius=8, fg_color="#2d2d3d", state="disabled", command=self._run_wfa)
        self.quant_wfa_btn.pack(fill="x", padx=10, pady=2)

    def _teams_view(self, p):
        # 标题
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(header, text="👥 Agent 团队", font=_font("ttl", 14, "bold"), text_color="#00d4ff").pack(side="left")
        
        # 团队列表（竖向）
        teams_scroll = ctk.CTkScrollableFrame(p, fg_color="transparent")
        teams_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        
        for team_id, team_config in TEAMS.items():
            panel = TeamPanel(teams_scroll, team_id, team_config)
            panel.frame.pack(fill="x", pady=5)
            self.team_panels[team_id] = panel

    def _right_panel(self, p):
        # 结果面板
        self.result_panel = ResultPanel(p)
        self.result_panel.frame.pack(fill="x", padx=10, pady=10)
        
        # 日志面板
        log_frame = ctk.CTkFrame(p, corner_radius=15, fg_color="#0d0d1a")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(log_header, text="📝 运行日志", font=_font("log", 12, "bold"), text_color="#00d4ff").pack(side="left")
        
        self.log_filter = ctk.CTkComboBox(
            log_header, 
            values=["全部", "代码诊断器", "代码修复器", "代码审查器", "策略优化器", "回测验证器", "协调器"], 
            width=100, 
            corner_radius=6,
            font=_font("filter", 9)
        )
        self.log_filter.pack(side="right")
        self.log_filter.set("全部")
        
        self.log = ctk.CTkTextbox(log_frame, font=_font("lg", 9), corner_radius=8, fg_color="#1a1a2e")
        self.log.pack(fill="both", expand=True, padx=10, pady=10)

    def _log(self, msg: str, lvl: str = "INFO", agent: str = "系统"):
        t = datetime.now().strftime("%H:%M:%S")
        lvl_text = {"INFO": "信息", "ERROR": "错误", "SUCCESS": "成功", "WARNING": "警告"}.get(lvl, lvl)
        log_line = f"[{t}] [{agent}] [{lvl_text}] {msg}"
        
        if agent in self.agent_logs:
            self.agent_logs[agent].append(log_line)
        
        filter_val = self.log_filter.get()
        if filter_val == "全部" or filter_val == agent or agent == "系统":
            self.log.insert("end", log_line + "\n")
            self.log.see("end")
        
        # 同时更新结果面板
        if self.result_panel and lvl in ["SUCCESS", "ERROR", "WARNING"]:
            self.result_panel.add_result(f"[{agent}] {lvl_text}", msg, lvl.lower())

    def _poll(self):
        try:
            while True:
                mt, d = self.queue.get_nowait()
                if mt == "ok":
                    self._on_ok()
                elif mt == "err":
                    self._log(f"错误: {d}", "ERROR")
                elif mt == "done":
                    self._on_done()
                elif mt == "log":
                    msg, lvl, agent = d
                    self._log(msg, lvl, agent)
                elif mt == "upd":
                    aid, st, tk = d
                    self._upd(aid, st, tk)
                elif mt == "api_ok":
                    self._log("API 连接成功", "SUCCESS")
                elif mt == "api_err":
                    self._log(f"API 连接失败: {d}", "ERROR")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _upd(self, aid: str, st: str, tk: str = ""):
        for panel in self.team_panels.values():
            if aid in panel.cards:
                panel.cards[aid].set_state(st, tk)
                return

    def _init(self):
        self._log("正在初始化Agent团队...", "INFO")
        self.init_btn.configure(state="disabled", text="初始化中...")
        
        def th():
            try:
                from src.agents import (
                    CodeDiagnosticAgent, CodeFixerAgent, CodeReviewerAgent,
                    StrategyOptimizerAgent, BacktestValidatorAgent,
                    OrchestratorAgent, ReportAgent, HumanAgent
                )
                from src.communication import InMemoryMessageBus
                
                self.bus = InMemoryMessageBus()
                
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
                
                for team_id, team_config in TEAMS.items():
                    for aid, nm, dc, ic in team_config['agents']:
                        if aid in agent_classes:
                            self.queue.put(("upd", (aid, "WORKING", "初始化中...")))
                            self.queue.put(("log", (f"初始化 {nm}...", "INFO", nm)))
                            cls = agent_classes[aid]
                            a = cls(agent_id=aid, name=nm, description=dc, message_bus=self.bus)
                            self.bus.register_agent(aid, a)
                            a.initialize()
                            self.agents[aid] = a
                            self.queue.put(("upd", (aid, "IDLE", "")))
                            self.queue.put(("log", (f"{nm} 就绪", "SUCCESS", nm)))
                
                self.queue.put(("ok", None))
            except Exception as e:
                self.queue.put(("log", (f"初始化失败: {e}", "ERROR", "系统")))
                self.queue.put(("err", str(e)))
        
        threading.Thread(target=th, daemon=True).start()

    def _on_ok(self):
        self.ready = True
        self._log("系统初始化完成!", "SUCCESS")
        self.status.configure(text="● 运行中", text_color="#00ff88")
        self.init_btn.configure(text="✓ 已就绪", fg_color="#2d8a4e")
        
        self.code_diag_btn.configure(state="normal", fg_color="#4CAF50")
        self.code_review_btn.configure(state="normal", fg_color="#4CAF50")
        self.quant_opt_btn.configure(state="normal", fg_color="#2196F3")
        self.quant_backtest_btn.configure(state="normal", fg_color="#2196F3")
        self.quant_wfa_btn.configure(state="normal", fg_color="#2196F3")

    def _diagnose_code(self):
        self._log("开始诊断代码...", "INFO", "代码诊断器")
        self.code_diag_btn.configure(state="disabled", text="诊断中...")
        self._upd("code_diagnostic", "WORKING", "扫描代码文件...")
        
        def th():
            try:
                d = self.agents.get("code_diagnostic")
                if d:
                    r = d.execute_task({"type": "diagnose_code", "target": "src"})
                    count = r.output.get("issue_count", 0)
                    self.queue.put(("log", (f"诊断完成: 发现 {count} 个问题", "SUCCESS", "代码诊断器")))
                else:
                    self.queue.put(("log", ("代码诊断器未初始化!", "ERROR", "代码诊断器")))
                self.queue.put(("done", None))
            except Exception as e:
                self.queue.put(("log", (f"诊断异常: {e}", "ERROR", "代码诊断器")))
                self.queue.put(("done", None))
        
        threading.Thread(target=th, daemon=True).start()

    def _review_code(self):
        self._log("开始审查代码...", "INFO", "代码审查器")
        self.code_review_btn.configure(state="disabled", text="审查中...")
        self._upd("code_reviewer", "WORKING", "审查代码质量...")
        
        def th():
            try:
                d = self.agents.get("code_reviewer")
                if d:
                    r = d.execute_task({"type": "check_quality", "directory": "src"})
                    score = r.output.get("score", 0)
                    self.queue.put(("log", (f"审查完成: 代码质量分数 {score:.1f}", "SUCCESS", "代码审查器")))
                else:
                    self.queue.put(("log", ("代码审查器未初始化!", "ERROR", "代码审查器")))
                self.queue.put(("done", None))
            except Exception as e:
                self.queue.put(("log", (f"审查异常: {e}", "ERROR", "代码审查器")))
                self.queue.put(("done", None))
        
        threading.Thread(target=th, daemon=True).start()

    def _run_evolution(self):
        self._log("开始运行进化...", "INFO", "策略优化器")
        self.quant_opt_btn.configure(state="disabled", text="进化中...")
        self._upd("strategy_optimizer", "WORKING", "运行进化周期...")
        
        def th():
            try:
                d = self.agents.get("strategy_optimizer")
                if d:
                    r = d.execute_task({"type": "run_evolution", "cycles": 3})
                    cycles = r.output.get("cycles_completed", 0)
                    results = r.output.get("results", [])
                    success = sum(1 for res in results if res.get("success", False))
                    self.queue.put(("log", (f"进化完成: {cycles}周期, {success}次成功", "SUCCESS", "策略优化器")))
                else:
                    self.queue.put(("log", ("策略优化器未初始化!", "ERROR", "策略优化器")))
                self.queue.put(("done", None))
            except Exception as e:
                self.queue.put(("log", (f"进化异常: {e}", "ERROR", "策略优化器")))
                self.queue.put(("done", None))
        
        threading.Thread(target=th, daemon=True).start()

    def _run_backtest(self):
        self._log("开始运行回测...", "INFO", "回测验证器")
        self.quant_backtest_btn.configure(state="disabled", text="回测中...")
        self._upd("backtest_validator", "WORKING", "运行回测引擎...")
        
        def th():
            try:
                d = self.agents.get("backtest_validator")
                if d:
                    r = d.execute_task({"type": "run_backtest", "strategy": "wyckoff"})
                    ret = r.output.get("total_return", 0)
                    sharpe = r.output.get("sharpe_ratio", 0)
                    self.queue.put(("log", (f"回测完成: 收益率{ret:.1%}, 夏普{sharpe:.2f}", "SUCCESS", "回测验证器")))
                else:
                    self.queue.put(("log", ("回测验证器未初始化!", "ERROR", "回测验证器")))
                self.queue.put(("done", None))
            except Exception as e:
                self.queue.put(("log", (f"回测异常: {e}", "ERROR", "回测验证器")))
                self.queue.put(("done", None))
        
        threading.Thread(target=th, daemon=True).start()

    def _run_wfa(self):
        self._log("开始WFA验证...", "INFO", "策略优化器")
        self.quant_wfa_btn.configure(state="disabled", text="验证中...")
        self._upd("strategy_optimizer", "WORKING", "WFA滚动窗口验证...")
        
        def th():
            try:
                d = self.agents.get("strategy_optimizer")
                if d:
                    r = d.execute_task({"type": "run_wfa_validation", "config": {}})
                    passed = r.output.get("passed", False)
                    score = r.output.get("stability_score", 0)
                    status = "通过" if passed else "未通过"
                    lvl = "SUCCESS" if passed else "WARNING"
                    self.queue.put(("log", (f"WFA验证{status}: 稳定性{score:.2f}", lvl, "策略优化器")))
                else:
                    self.queue.put(("log", ("策略优化器未初始化!", "ERROR", "策略优化器")))
                self.queue.put(("done", None))
            except Exception as e:
                self.queue.put(("log", (f"WFA验证异常: {e}", "ERROR", "策略优化器")))
                self.queue.put(("done", None))
        
        threading.Thread(target=th, daemon=True).start()

    def _on_done(self):
        self.code_diag_btn.configure(state="normal", text="🔍 诊断代码", fg_color="#4CAF50")
        self.code_review_btn.configure(state="normal", text="📝 审查代码", fg_color="#4CAF50")
        self.quant_opt_btn.configure(state="normal", text="📊 运行进化", fg_color="#2196F3")
        self.quant_backtest_btn.configure(state="normal", text="📈 运行回测", fg_color="#2196F3")
        self.quant_wfa_btn.configure(state="normal", text="✓ WFA验证", fg_color="#2196F3")
        
        for panel in self.team_panels.values():
            for aid in panel.cards:
                self._upd(aid, "IDLE")

    def run(self):
        self._log("控制面板已启动", "SUCCESS")
        self._log("请点击「初始化系统」启动Agent团队", "INFO")
        self.root.mainloop()


def run_gui():
    Dashboard().run()


if __name__ == "__main__":
    run_gui()
