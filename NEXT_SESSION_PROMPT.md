# Meridian — 新对话提示词（2026-04-09 14:03）

## 项目背景
威科夫全自动交易逻辑引擎。插件化架构，Python后端(FastAPI) + React前端(KLineChart)。
项目路径：`F:\VCPToolBox\wyckoff`

## 当前状态：P0-P3代码全部完成
后端43个文件 + 前端26个文件，全部经过审查和修复，零遗留WARNING。

### 后端插件（6个，全部就绪）
| 插件 | 路径 | 文件数 | 状态 |
|------|------|--------|------|
| core | backend/core/ | 7 | ✓ 审查通过 |
| datasource | backend/plugins/datasource/ | 3 | ✓ 审查通过 |
| annotation | backend/plugins/annotation/ | 4 | ✓ 审查通过 |
| engine | backend/plugins/engine/ | 13 | ✓ 审查+修复通过 |
| evolution | backend/plugins/evolution/ | 10 | ✓ 审查通过 |
| backtester | backend/plugins/backtester/ | 6 | ✓ 审查通过 |

### 前端（标注工作台完整可用）
| 目录 | 文件数 | 内容 |
|------|--------|------|
| core/ | 4 | types/PluginRegistry/AppShell/Sidebar |
| stores/ | 2 | appStore/drawingStore(含undo/redo) |
| services/ | 2 | api.ts(全部端点)/cache.ts(IndexedDB) |
| shared/chart/ | 7 | ChartWidget/DrawingToolbar/chartUtils/3个overlay |
| workers/ | 2 | dataWorker/useDataWorker |
| plugins/evolution-workbench/ | 8 | EvolutionPage+组件+面板 |
| themes/ | 1 | variables.css |

### 技术栈
- 后端：Python3.11+ FastAPI + Polars + SQLite
- 前端：React 18 + KLineChart 10 + Zustand 5 + Vite 6+ TypeScript 5
- 端口：后端 6100/ 前端 5173
- 启动：双击`start.bat`

## 本次任务：前端补充必要面板

### 需要新增的前端功能

#### 1. 回测面板（最重要）
在进化工作台中新增一个面板或Tab：
- **触发按钮**：选择币种+时间框架 → 点击"运行回测" → 调用 `POST /api/backtester/run`
- **结果展示**：显示回测结果（事件数量、阶段转换数量、评分四维度）
- **历史列表**：调用 `GET /api/backtester/history` 显示历史回测记录
- **详情查看**：点击某次回测 → 调用 `GET /api/backtester/result/{run_id}` → 显示事件列表和时间线

#### 2. 进化面板
- **优化按钮**：点击"优化参数" → 调用 `POST /api/evolution/optimize`
- **参数展示**：显示当前参数版本和关键参数值
- **案例统计**：调用 `GET /api/evolution/cases/stats` 显示案例库统计

#### 3. 引擎状态面板
- **状态展示**：调用 `GET /api/engine/state/{symbol}/{timeframe}` 显示当前引擎状态（阶段、方向、活跃区间）
- 这个可以集成到标注工作台的侧边栏

### 后端API端点（已就绪，前端直接调用）

#### 回测
```
POST /api/backtester/run
  body: { "symbol": "ETHUSDT", "timeframe": "1d", "params": null }
  返回: { "run_id", "total_bars", "total_events", "total_transitions", "score": {...} }

GET /api/backtester/result/{run_id}
  返回: 完整回测结果（events/transitions/timeline/score）

GET /api/backtester/history
  返回: { "runs": [{ "run_id", "symbol", "timeframe", "total_bars", "score_summary" }] }
```

#### 进化
```
POST /api/evolution/optimize
  body: { "symbol": "ETHUSDT", "timeframe": "1d" }

GET /api/evolution/cases/stats
GET /api/evolution/params/current
GET /api/evolution/params/history
```

#### 引擎
```
GET /api/engine/state/{symbol}/{timeframe}
GET /api/engine/state/{symbol}/all
```

### 前端现有结构（新增文件应放在这里）
```
frontend/src/plugins/evolution-workbench/
├── index.ts# 插件注册
├── EvolutionPage.tsx     # 主页面（已有标注面板）
├── config/
│   └── wyckoffEvents.ts  # 事件定义
├── components/
│   ├── EventTypePopup.tsx
│   ├── PhaseSelectPopup.tsx
│   └── PropertyEditor.tsx
└── panels/
    ├── AnnotationPanel.tsx   # 已有
    ├── FeaturePanel.tsx      # 已有
    ├── BacktestPanel.tsx     # ← 新增
    └── EvolutionPanel.tsx    # ← 新增
```

### 设计要求
-暗色主题，和现有UI风格一致（参考 variables.css）
- 面板切换用Tab或按钮组，不要弹窗
- 回测结果的事件列表可以点击定位到K线图上的对应位置
- 保持简洁，不过度设计

### api.ts 已有的端点封装
`frontend/src/services/api.ts` 已经封装了 engine(4端点) + evolution(9端点) 的调用。
回测端点需要新增封装（3个端点）。

### 关键注意事项
1. 前端代理端口是 6100（vite.config.ts 中配置）
2. K线数据通过 ArrayBuffer + Web Worker 解码
3. 标注数据通过 drawingStore(Zustand) 管理
4. 所有日志用 console，不用 alert

## 验收标准
1. 回测面板：能触发回测 + 显示结果 + 查看历史
2. 进化面板：能触发优化 + 显示参数+ 显示案例统计
3. 引擎状态：能看到当前阶段和方向
4. 不破坏现有标注功能