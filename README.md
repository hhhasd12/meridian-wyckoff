# 威科夫全自动逻辑引擎

**项目状态：** 生产就绪（插件化架构 v3.0）
**最后更新：** 2026-03-21
**当前版本：** v3.0

---

## 项目简介

本项目构建了一个基于**威科夫（Wyckoff）逻辑**和**FVG（公允价值缺口）**的全自动交易决策系统，设计为具备四大维度的"数字生命体"：

1. **动态感知** — 市场体制识别、FVG检测、曲线边界拟合、突破验证、异常数据语义识别
2. **独立思考** — 22节点威科夫状态机、证据链加权决策、多周期冲突辩证解决
3. **自动进化** — 错题本闭环学习、权重定向变异、WFA防过拟合验证、性能自监控
4. **落地沟通** — 实时交易信号、决策可视化快照、系统健康报告、风险管理

---

## 系统架构

```
run.py（统一入口 — 支持 api/trading/evolution/web/all 5种模式）
    ↓
WyckoffApp（src/app.py — 插件化系统入口）
    ↓
┌─ PluginManager ──────────────────────────────────────────────┐
│                                                               │
│  内核层 src/kernel/（不可插拔）                               │
│  ├── types.py            所有共享类型定义（枚举、数据类）    │
│  ├── base_plugin.py      插件抽象基类                        │
│  ├── plugin_manifest.py  Manifest 解析器                     │
│  ├── plugin_manager.py   插件生命周期管理                    │
│  ├── event_bus.py        事件总线（发布/订阅）               │
│  └── config_system.py    配置系统（YAML + 环境变量）         │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│  插件层 src/plugins/（可插拔，18个业务插件）                  │
│  ├── market_regime/      市场体制检测（ATR/ADX独立计算）     │
│  ├── data_pipeline/      多周期数据同步与缓存               │
│  ├── orchestrator/       系统编排器（决策协调中心）          │
│  ├── wyckoff_state_machine/  22节点威科夫状态机             │
│  ├── wyckoff_engine/     威科夫引擎（统一分析入口）         │
│  ├── pattern_detection/  K线形态识别（TR/FVG/突破验证）     │
│  ├── perception/         感知层（FVG/K线物理属性/针体分析） │
│  ├── signal_validation/  信号验证（微观入场/冲突解决）      │
│  ├── risk_management/    风险管理（仓位/止损/熔断）          │
│  ├── position_manager/   仓位管理（开平仓/止损执行）        │
│  ├── weight_system/      权重系统（变异/WFA/错题本）         │
│  ├── evolution/          自动化进化（闭环学习）              │
│  ├── exchange_connector/ 交易所连接器（Binance API）         │
│  ├── dashboard/          Web 仪表盘（实时监控）              │
│  ├── self_correction/    自我纠错（性能监控/自动恢复）      │
│  ├── evolution_advisor/  进化顾问（AI策略优化）             │
│  ├── telegram_notifier/  Telegram 通知（交易信号推送）      │
│  └── audit_logger/       审计日志（操作记录与合规）         │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│  API层 src/api/（FastAPI 后端，REST + WebSocket）            │
│  工具层 src/utils/（数据处理、可视化工具）                   │
└───────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
wyckoff/
├── src/
│   ├── app.py                              ★ WyckoffApp 插件化系统入口
│   ├── kernel/                             内核层（不可插拔）
│   │   ├── types.py                        所有共享类型定义
│   │   ├── base_plugin.py                  插件抽象基类
│   │   ├── plugin_manifest.py              Manifest 解析器
│   │   ├── plugin_manager.py               插件生命周期管理
│   │   ├── event_bus.py                    事件总线（发布/订阅）
│   │   └── config_system.py                配置系统（YAML + 环境变量）
│   ├── plugins/                            插件层（可插拔，18个业务插件）
│   │   ├── market_regime/                  市场体制检测
│   │   ├── data_pipeline/                  多周期数据同步
│   │   ├── orchestrator/                   系统编排器
│   │   ├── wyckoff_state_machine/          22节点威科夫状态机
│   │   ├── wyckoff_engine/                 威科夫引擎（统一分析入口）
│   │   ├── pattern_detection/              K线形态识别
│   │   ├── perception/                     感知层（FVG/K线物理属性/针体分析）
│   │   ├── signal_validation/              信号验证
│   │   ├── risk_management/                风险管理
│   │   ├── position_manager/               仓位管理
│   │   ├── weight_system/                  权重系统
│   │   ├── evolution/                      自动化进化
│   │   ├── exchange_connector/             交易所连接器
│   │   ├── dashboard/                      Web 仪表盘
│   │   ├── self_correction/                自我纠错
│   │   ├── evolution_advisor/              进化顾问（AI策略优化）
│   │   ├── telegram_notifier/              Telegram 通知
│   │   └── audit_logger/                   审计日志
│   ├── api/                                FastAPI 后端（REST API + WebSocket）
│   └── utils/                              工具层
├── frontend/                               Web 前端（React + TypeScript + Vite）
├── tests/                                  测试套件
│   ├── kernel/                             内核测试
│   └── plugins/                            插件测试
├── docs/                                   文档
├── examples/                               示例代码
├── run.py                                  ★ 统一启动入口（5种模式）
├── run_evolution.py                        进化模式独立运行
├── fetch_data.py                           数据下载工具
├── health_check.py                         系统健康检查
├── config.yaml                             生产配置文件
├── config.example.yaml                     配置模板（带注释）
├── docker-compose.yml                      Docker 容器编排
└── AGENTS.md                               AI代理开发指南
```

> **架构说明**：v3.0 采用三层插件化架构。`src/kernel/` 为不可插拔的内核层，
> `src/plugins/` 为可插拔的业务插件层（18个插件，每个包含 `plugin-manifest.yaml` 和 `plugin.py`），
> `src/api/` 为 FastAPI 后端服务，`src/utils/` 为工具层。
> 新功能开发应以插件形式进行，参见 `docs/PLUGIN_DEVELOPMENT.md`。

---

## 快速开始

### 1. 安装依赖

```bash
cd wyckoff
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.example.yaml config.yaml
```

核心配置项（`config.yaml`）：

```yaml
paper_trading: true          # true=模拟，false=实盘（危险！）

data_sources:
  crypto:
    proxy: ""                # VPN直连留空，走系统代理
    symbols: ["BTC/USDT"]

symbols: ["BTC/USDT"]
timeframes: ["H4", "H1", "M15"]
historical_days: 30
processing_interval: 60      # 数据处理间隔（秒）
```

### 3. 启动

```bash
# Docker 一键启动（推荐）
docker-compose up -d

# 启动 API 服务器（支持前端 + REST API）
python run.py --mode=api

# 启动交易系统（命令行直连模式）
python run.py --mode=trading

# 启动全部服务（API + 前端 + 交易）
python run.py --mode=all

# 独立进化模式
python run.py --mode=evolution

# Windows 用户可使用启动器
start.bat
```

### 4. 运行演示

```bash
python examples/final_digital_life_demo.py    # 四大维度完整演示
python examples/real_time_pipeline_demo.py    # 实时决策流水线
python examples/performance_analysis.py       # 性能分析工具
```

### 5. 运行测试

```bash
pytest tests/ -v
# 预期结果：1186 passed
```

---

## 模块状态总览

| 模块 | 功能 | 实现状态 |
|------|------|---------|
| `market_regime.py` | 市场体制检测（ATR/ADX独立计算） | 完整 |
| `tr_detector.py` | Trading Range识别与锁定 | 完整（WARN-01见下文） |
| `curve_boundary.py` | 几何边界拟合（弧/三角/通道） | 完整 |
| `breakout_validator.py` | 突破验证（防SFP欺骗） | 完整 |
| `fvg_detector.py` | FVG公允价值缺口（LuxAlgo） | 完整 |
| `candle_physical.py` | K线实体物理属性 | 完整 |
| `pin_body_analyzer.py` | 针体/实体努力与结果分析 | 完整 |
| `data_sanitizer.py` | 异常封装（AnomalyEvent，不抹除数据） | 完整 |
| `data_pipeline.py` | 多周期数据同步 | 完整 |
| `period_weight_filter.py` | 周期权重过滤 | 完整 |
| `conflict_resolver.py` | 多周期冲突辩证解决 | 完整 |
| `micro_entry_validator.py` | 微观入场验证 | 完整 |
| `wyckoff_state_machine_legacy.py` | 22节点状态机（吸筹13+派发9） | 完整 |
| `mistake_book.py` | 错题本（失败模式识别） | 完整 |
| `weight_variator_legacy.py` | 权重定向变异 | 完整 |
| `wfa_backtester.py` | Walk-Forward Analysis验证 | 完整 |
| `performance_monitor.py` | 性能自监控 | 完整 |
| `evolution_archivist.py` | 进化记忆存储（JSONL） | 完整 |
| `self_correction_workflow.py` | 错题本→变异→WFA→更新闭环 | 完整 |
| `decision_visualizer.py` | 决策快照（状态/TR变化时触发） | 完整 |
| `binance_fetcher.py` | Binance实时数据 | 完整（VPN直连） |
| `backtest/engine.py` | 回测引擎 | 完整 |
| `utils/visualizer.py` | K线可视化 | 完整 |

---

## 已知问题

所有已知 bug 已于 2026-03-02 修复完毕，当前无待处理问题。

### 正常行为（不是错误）

以下启动日志输出**属于正常行为**，无需修复：

```
INFO  - 存储文件不存在: ./evolution_memory.jsonl   → 首次运行正常，自动创建
WARNING - 在H4时间框架检测到N个异常事件            → VSA分析的正常输出，异常即信号
INFO  - 【当前格局】：未识别出明确TR区间            → 等待盘整形成，属于正常判断
INFO  - Decision: neutral (confidence: 0.00)       → 低置信度不出手，符合设计
INFO  - 最佳配置分数=0.000                         → 首次进化无历史数据，正常初始化
```

---

## 核心特性

### 动态感知能力
- **市场体制智能识别**：趋势市、盘整市、高波动市，仅依赖 ATR/ADX 独立计算，无循环依赖
- **非线性曲线边界拟合**：圆弧底、三角形、通道等非线性 TR 边界识别
- **FVG上下文敏感检测**：基于 LuxAlgo 算法，TR 内部 vs 突破后差异处理
- **突破验证与 SFP 防护**：突破+回踩不破逻辑，防摆动失败模式欺骗
- **异常数据语义识别**：不抹除异常，封装为 AnomalyEvent 供状态机做主力意图分析

### 独立思考能力
- **22节点威科夫状态机**：吸筹 13 节点 + 派发 9 节点完整实现
- **证据链加权决策**：拒绝单一判定，多维证据辩证思考
- **多周期冲突解决**：日线派发 vs 4小时吸筹的辩证逻辑
- **结构确认替代时间确认**：价格突破关键结构位 + 站稳 3 根 K 线
- **遗产分数机制**：状态记忆与强度传递

### 自动进化能力
- **错题本机制**：失败交易自动分析与模式识别
- **权重定向变异**：基于错误模式的参数自适应优化
- **WFA 防过拟合验证**：Walk-Forward Analysis 滚动窗口验证
- **性能自监控**：健康检查、自动恢复、报警机制
- **逻辑基因保护**：VSA 核心公式禁止进化修改

### 落地沟通能力
- **实时交易信号**：BUY/SELL/NEUTRAL + 置信度评分 + 理由链
- **系统健康报告**：每小时生成，保存在 `reports/` 目录
- **决策快照可视化**：TR 识别和状态变化时自动触发截图
- **配置灵活调整**：YAML 配置文件 + 400+ 可调参数

---

## 技术栈

- **运行环境**：Python 3.9+，Windows/Linux
- **数据处理**：NumPy, Pandas, SciPy
- **后端框架**：FastAPI（REST API + WebSocket）
- **前端框架**：React 18 + TypeScript + Vite + Tailwind CSS
- **异步框架**：asyncio, aiohttp（Windows 需 SelectorEventLoop）
- **可视化**：Plotly, Matplotlib
- **测试框架**：pytest, pytest-asyncio
- **容器化**：Docker + docker-compose
- **数据源**：Binance REST API（直连或系统代理）

---

## 测试验证

```bash
# 运行全部测试
pytest tests/ -v
```

---

## 后续优化路线图

### 第一阶段（已完成 ✅）
- [x] ~~修复 BUG-02：`decision_visualizer.py` 中 `symbol.replace('/', '_')`~~ — 已确认正确
- [x] ~~清理 51 个 skipped 测试~~ — 已全部修复（356 passed）
- [x] ~~接入真实 BacktestEngine 替换随机模拟评估器~~ — 已完成
- [x] ~~多周期扩展到五层（D1/H4/H1/M15/M5）~~ — 已完成
- [x] ~~anomaly_validator.py 增加 BTC/ETH 跨品种互证~~ — 已完成
- [x] ~~统一 wyckoff_state_machine 导入路径（相对导入）~~ — 已完成

### 第二阶段（已完成 ✅）
- [x] ~~合并 `run_live.py` 与 `run_system.py` 为单一生产入口~~ — `run.py` 为唯一统一入口
- [x] ~~解决 `DataPipeline` 同名类冲突~~ — 重命名为 `DataFlowPipeline`
- [x] ~~清理 `scripts/` 目录重复数据获取脚本~~ — 已删除

### 第三阶段（已完成 ✅ — v2.0 插件化重构）
- [x] ~~三层插件化架构重构~~ — 内核层 + 插件层 + 工具层
- [x] ~~15个业务插件迁移~~ — 全部插件包含 manifest + plugin.py
- [x] ~~上帝对象拆解~~ — 共享类型提取到 `src/kernel/types.py`
- [x] ~~插件化系统入口~~ — `WyckoffApp` 类（`src/app.py`）
- [x] ~~完整文档更新~~ — AGENTS.md + PLUGIN_DEVELOPMENT.md + README.md

### 第四阶段（已完成 ✅ — v2.1 架构清理）
- [x] ~~删除死代码~~ — src/state/, src/logs/, src/storage/, src/data/ 已清除
- [x] ~~入口点统一~~ — run_live.py 合并进 run.py，统一5种启动模式
- [x] ~~Perception 迁移~~ — src/perception/ 迁入 src/plugins/perception/
- [x] ~~Agent 框架整合~~ — src/agents/ 等4个目录已重构为 src/plugins/evolution_advisor/
- [x] ~~测试目录重组~~ — 清理散乱测试文件，统一到 tests/plugins/

### 第五阶段（已完成 ✅ — v3.0 生产就绪）
- [x] ~~Web 监控仪表板（实时可视化系统状态）~~ — React 18 + TypeScript + Vite + Tailwind CSS
- [x] ~~REST API 服务（外部系统集成接口）~~ — FastAPI 后端（REST + WebSocket）
- [x] ~~Telegram 通知插件~~ — 交易信号实时推送
- [x] ~~审计日志插件~~ — 操作记录与合规追踪

### 第六阶段（长期）
- [ ] 进化档案员接入真实向量库（替换 Mock 嵌入）
- [ ] 多交易对并行分析（ETH/SOL 扩展）

---

## 文档索引

| 文档 | 说明 |
|------|------|
| `docs/PLUGIN_DEVELOPMENT.md` | 插件开发完整指南（架构、Manifest、事件通信、测试） |
| `AGENTS.md` | AI代理开发指南（构建/测试/代码风格） |
| `docs/TECH_SPECS.md` | 数据格式规范（OHLCV标准、DatetimeIndex要求） |
| `docs/ERROR_HANDLING_STANDARD.md` | 错误处理与日志记录规范 |
| `STARTUP_GUIDE.md` | 生产环境启动与故障排除指南 |
| `config.example.yaml` | 配置文件模板（含400+参数注释） |

---

## 风险声明

本系统为**技术研究用途**，不构成投资建议。实盘交易风险自负，作者不对任何交易损失承担责任。

- 实盘交易前必须充分测试和验证
- 建议模拟模式运行至少 1 个月
- 定期监控系统健康状态和日志

---

**项目标语**：从盘感到算法，从逻辑到生命
**设计哲学**：辩证思考，全局观照，自我进化
**最后更新**：2026-03-21（v3.0，生产就绪）
