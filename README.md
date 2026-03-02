# 威科夫全自动逻辑引擎

**项目状态：** 生产就绪（模拟交易模式）
**最后更新：** 2026-03-02
**当前版本：** v1.2

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
run_live.py（生产守护进程入口）
    ↓
ProductionSystemRunner
    ↓
SystemOrchestrator（system_orchestrator_legacy.py 为核心实现）
    ↓
┌─────────────────────────────────────────────────────────────┐
│  物理感知层                                                  │
│  market_regime.py      市场体制检测（ATR/ADX，独立模块）    │
│  tr_detector.py        Trading Range 识别与锁定             │
│  curve_boundary.py     几何边界拟合（弧形/三角/通道）       │
│  breakout_validator.py 突破验证（突破+回踩不破逻辑）        │
│  fvg_detector.py       FVG检测（LuxAlgo算法）               │
│  candle_physical.py    K线实体物理属性                      │
│  pin_body_analyzer.py  针体/实体比分析（努力与结果）        │
│  data_sanitizer.py     异常数据封装（AnomalyEvent，不抹除） │
│  anomaly_validator.py  异常验证层                           │
│  circuit_breaker.py    熔断机制保护                         │
├─────────────────────────────────────────────────────────────┤
│  多周期融合层                                                │
│  data_pipeline.py          多周期数据同步与缓存             │
│  period_weight_filter.py   周期权重过滤器                   │
│  conflict_resolver.py      多周期冲突解决（辩证逻辑）       │
│  micro_entry_validator.py  微观入场验证                     │
├─────────────────────────────────────────────────────────────┤
│  状态机决策层                                                │
│  wyckoff_state_machine_legacy.py  22节点状态机核心实现     │
│  wyckoff_state_machine/           包结构（从legacy导出）    │
│    evidence_chain.py              证据链管理器              │
├─────────────────────────────────────────────────────────────┤
│  自动化进化层                                                │
│  mistake_book.py              错题本（失败交易模式识别）    │
│  weight_variator_legacy.py    权重定向变异算法              │
│  wfa_backtester.py            Walk-Forward Analysis验证    │
│  performance_monitor.py       性能自监控与健康检查          │
│  evolution_archivist.py       进化档案员（JSONL记忆存储）   │
│  self_correction_workflow.py  闭环自修正工作流              │
├─────────────────────────────────────────────────────────────┤
│  可视化与回测                                                │
│  decision_visualizer.py   决策快照（状态/TR变化时触发）     │
│  backtest/engine.py       回测引擎（胜率/回撤/夏普比率）    │
│  backtest/reporter.py     中文回测报告                      │
│  utils/visualizer.py      K线图+威科夫状态标注              │
└─────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
wyckoff/
├── src/
│   ├── core/
│   │   ├── system_orchestrator.py        向后兼容 shim（重定向到 legacy）
│   │   ├── system_orchestrator_legacy.py ★ 实际 SystemOrchestrator 代码
│   │   ├── orchestrator/                 新包结构（HealthStatus/AlertLevel等）
│   │   ├── market_regime.py              市场体制检测
│   │   ├── tr_detector.py                TR识别
│   │   ├── curve_boundary.py             几何边界拟合
│   │   ├── breakout_validator.py         突破验证
│   │   ├── anomaly_validator.py          异常验证
│   │   ├── circuit_breaker.py            熔断机制
│   │   ├── data_pipeline.py              多周期数据管道
│   │   ├── data_sanitizer.py             异常数据清洗
│   │   ├── decision_visualizer.py        决策可视化
│   │   ├── period_weight_filter.py       周期权重过滤
│   │   ├── conflict_resolver.py          冲突解决
│   │   ├── micro_entry_validator.py      微观入场验证
│   │   ├── wyckoff_state_machine/        状态机包（从legacy导出）
│   │   ├── wyckoff_state_machine_legacy.py ★ 实际22节点状态机代码
│   │   ├── mistake_book.py               错题本
│   │   ├── weight_variator.py            shim（重定向到legacy）
│   │   ├── weight_variator_legacy.py     ★ 实际权重变异代码
│   │   ├── evolution/                    进化包（从legacy导出）
│   │   ├── wfa_backtester.py             WFA回测
│   │   ├── performance_monitor.py        性能监控
│   │   ├── evolution_archivist.py        进化档案员
│   │   └── self_correction_workflow.py   自修正闭环
│   ├── perception/
│   │   ├── fvg_detector.py               FVG检测
│   │   ├── candle_physical.py            K线物理属性
│   │   └── pin_body_analyzer.py          针体/实体分析
│   ├── data/
│   │   ├── binance_fetcher.py            Binance实时数据获取
│   │   ├── cleaner.py                    数据清洗（NumPy安全）
│   │   ├── loader.py                     本地CSV/Parquet加载
│   │   └── feature_factory.py            VWAP/RSI/EMA等特征计算
│   ├── backtest/
│   │   ├── engine.py                     回测引擎
│   │   └── reporter.py                   中文回测报告
│   ├── utils/
│   │   └── visualizer.py                 K线可视化
│   └── visualization/
│       └── heritage_panel.py             遗产分数面板
├── tests/                                测试套件（305通过/51跳过）
├── docs/
│   ├── SYSTEM_DIAGNOSIS.md               系统错误诊断报告
│   ├── REFACTORING_STATUS.md             重构状态记录
│   ├── TECH_SPECS.md                     技术规范（数据格式标准）
│   └── deployment_guide.md              详细部署指南
├── examples/                             功能演示脚本
├── scripts/                              数据获取脚本
├── run_live.py                           ★ 生产守护进程启动入口
├── run_evolution.py                      进化模式独立运行
├── config.yaml                           生产配置文件
├── config.example.yaml                   配置模板（带注释）
└── ISSUES.md                             已知问题清单
```

> **架构说明**：系统存在三个核心模块的 shim/legacy/新包 并存结构
> （`system_orchestrator`, `weight_variator`, `wyckoff_state_machine`）。
> 实际逻辑代码均在 `*_legacy.py` 文件中，新包和 shim 仅为导入兼容层，
> 这是历史重构遗留的结构，不影响运行，但新功能开发应直接在 legacy 文件中进行。

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
# 生产守护进程模式（推荐）
python run_live.py

# 指定配置文件
python run_live.py custom_config.yaml

# 独立进化模式
python run_evolution.py
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
# 预期结果：356 passed
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
- **异步框架**：asyncio, aiohttp（Windows 需 SelectorEventLoop）
- **可视化**：Plotly, Matplotlib
- **测试框架**：pytest, pytest-asyncio
- **数据源**：Binance REST API（直连或系统代理）

---

## 测试验证

```bash
# 运行全部测试
pytest tests/ -v

# 预期结果
# 305 passed, 51 skipped
# 51 skipped 为历史重构遗留，核心逻辑全部通过
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
- [x] ~~合并 `run_live.py` 与 `run_system.py` 为单一生产入口~~ — `run_system.py` 不存在，`run_live.py` 已是唯一生产入口，无需合并
- [x] ~~解决 `DataPipeline` 同名类冲突（`core/data_pipeline.py` vs `orchestrator/flow.py`）~~ — `orchestrator/flow.py` 中重命名为 `DataFlowPipeline`，保留 `DataPipeline` 向后兼容别名
- [x] ~~清理 `scripts/` 目录重复数据获取脚本~~ — 删除6个冗余脚本，保留 `fetch_eth_history.py`/`fetch_multi.py`/`download_eth_data.py`/`generate_eth_data.py`

### 第三阶段（长期）
- [ ] Web 监控仪表板（实时可视化系统状态）
- [ ] REST API 服务（外部系统集成接口）
- [ ] 进化档案员接入真实向量库（替换 Mock 嵌入）
- [ ] 多交易对并行分析（ETH/SOL 扩展）

---

## 文档索引

| 文档 | 说明 |
|------|------|
| `ISSUES.md` | 已知问题清单与修复建议 |
| `docs/PLAN_IMPLEMENTATION_STATUS.md` | 计划书实现状态对照（含修复记录） |
| `docs/TECH_SPECS.md` | 数据格式规范（OHLCV标准、DatetimeIndex要求） |
| `docs/ERROR_HANDLING_STANDARD.md` | 错误处理与日志记录规范 |
| `STARTUP_GUIDE.md` | 生产环境启动与故障排除指南 |
| `config.example.yaml` | 配置文件模板（含400+参数注释） |
| `项目开发计划书.md` | 完整开发计划（v1.3） |

---

## 风险声明

本系统为**技术研究用途**，不构成投资建议。实盘交易风险自负，作者不对任何交易损失承担责任。

- 实盘交易前必须充分测试和验证
- 建议模拟模式运行至少 1 个月
- 定期监控系统健康状态和日志

---

**项目标语**：从盘感到算法，从逻辑到生命
**设计哲学**：辩证思考，全局观照，自我进化
**最后更新**：2026-03-02（v1.2，全部已知缺口已修复）
