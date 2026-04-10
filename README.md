# Meridian

威科夫全自动交易逻辑引擎 — 开源插件化框架

## 什么是 Meridian

Meridian 是一个基于威科夫方法论的全自动交易系统框架。它将威科夫理论中的区间识别、事件检测、阶段推进、交易决策全部系统化，并通过「进化」机制持续优化。

核心设计：**一切皆插件**。数据源、标注、引擎、交易、AI 分析——都是独立的插件模块，即插即用。

## 快速启动

### 后端
```bash
pip install fastapi uvicorn polars numpy aiosqlite pydantic-settings
python -m uvicorn backend.main:app --reload --port 6100
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`

## 项目结构

```
meridian/
├── README.md                ← 你在这里
├── config.yaml              — 全局配置
├── docs/                    — 系统级设计文档
│   ├── SYSTEM_DESIGN_V3.md       — 威科夫理论核心（55条RD）
│   ├── MERIDIAN_ARCHITECTURE.md   — 系统架构设计
│   ├── WORKBENCH_DESIGN.md        — 标注工作台设计
│   └── IMPLEMENTATION_PROMPT.md   — P0施工总览
├── backend/
│   ├── main.py              — 后端入口
│   ├── core/                — 内核框架
│   │   ├── README.md        — 插件开发指南
│   │   ├── types.py         — BackendPlugin 基类 + PluginContext
│   │   ├── plugin_manager.py
│   │   ├── event_bus.py
│   │   ├── api_registry.py
│   │   └── storage.py
│├── plugins/             — 后端插件（每个插件一个文件夹）
│   │   ├── datasource/      — 数据源：本地 TSV/CSV 加载
│   │   └── annotation/      — 标注：Drawing CRUD + 特征提取
│   └── storage/             — 持久化数据
├── frontend/                — React + TypeScript
│   └── src/
│       ├── core/            — 前端内核
│├── plugins/         — 前端插件
│       ├── shared/          — 共享组件（图表、Overlay）
│       └── stores/          — 状态管理
└── data/                    — K线数据（TSV格式）
```

## 内置插件

| 插件 | 后端 | 前端 | 优先级 | 状态 |
|------|------|------|--------|------|
| 进化工作台 | datasource + annotation | evolution-workbench | P0 | 🚧 施工中 |
| 实盘监控 | engine + trading | live-monitor | P2 | 📋 设计中 |
| AI分析师 | ai | ai-analyst | P3 | 📋 设计中 |
| 回测引擎 | evolution.backtester | backtester | P3 | 📋 设计中 |
| 交易日志 | trading.history | trade-journal | P3 | 📋 设计中 |
| 后端监控 | （系统端点） | system-monitor | P3 | 📋 设计中 |

## 文档索引

| 文档 | 内容 | 读者 |
|------|------|------|
| [SYSTEM_DESIGN_V3.md](docs/SYSTEM_DESIGN_V3.md) | 威科夫理论 → 算法的完整设计，55条设计决策 | 理解"为什么这样做" |
| [MERIDIAN_ARCHITECTURE.md](docs/MERIDIAN_ARCHITECTURE.md) | 系统架构、插件接口、事件总线、数据流 | 理解"系统怎么搭" |
| [WORKBENCH_DESIGN.md](docs/WORKBENCH_DESIGN.md) | 标注工作台交互设计、特征提取、学习管道 | 理解"标注怎么用" |
| [backend/core/README.md](backend/core/README.md) | 插件开发指南：怎么写一个新插件 | 开发新插件 |

## 技术栈

- **后端**：Python 3.11+ FastAPI + Polars + NumPy
- **前端**：React + TypeScript + KLineChart + Zustand
- **存储**：JSON（标注/配置） + SQLite（案例库/交易记录）
- **数据传输**：二进制（Float64Array）

## 设计哲学

1. **一切皆插件**：前后端都插件化，第三方可扩展
2. **因果关系反转**：区间先于状态机，先识别区间再检测事件
3. **系统永远有立场**：不存在空仓等待，每个时刻都有方向
4. **先建记忆再建智慧**：失败案例同样完整记录，这是进化的燃料
5. **识别层与决策层分离**：先把"市场在什么状态"识别对，再做交易决策