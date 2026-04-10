# Meridian

威科夫全自动交易逻辑引擎 — 开源插件化框架

## 什么是 Meridian

Meridian 是一个基于威科夫方法论的全自动交易系统框架。它将威科夫理论中的区间识别、事件检测、阶段推进全部系统化，并通过「进化」机制持续优化。

核心设计：**一切皆插件**。数据源、标注、引擎、分析——都是独立的插件模块，即插即用。

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
├── config.yaml              — 全局配置
├── backend/
│   ├── main.py              — FastAPI 入口
│   ├── core/                — 内核框架
│   │   ├── types.py         — BackendPlugin 基类
│   │   ├── plugin_manager.py — 插件自动发现 + 拓扑排序
│   │   ├── event_bus.py     — 发布-订阅事件总线
│   │   ├── api_registry.py  — 路由自动挂载
│   │   └── storage.py       — JSON 原子写入
│   └── plugins/
│       ├── datasource/      — 数据源：本地 CSV 加载
│       ├── annotation/      — 标注：Drawing CRUD + 7维特征提取
│       ├── engine/          — 威科夫引擎：区间/事件/规则三引擎
│       ├── evolution/       — 进化系统：案例库 → 统计优化 → 参数热加载
│       └── backtester/      — 回测框架
├── frontend/                — React + TypeScript
│   └── src/
│       ├── core/            — 插件注册 + AppShell
│       ├── plugins/         — 前端插件（进化工作台等）
│       ├── shared/chart/    — KLineChart v10 封装 + 自定义 Overlay
│       ├── stores/          — Zustand 状态管理
│       └── workers/         — Web Worker 数据处理
└── data/                    — K线数据
```

## 核心架构

```
每根K线到达：

  ┌─────────────┐
  │ 区间引擎      │  没有区间？→ 找 SC/BC 候选 → 三点定区间
  │ RangeEngine  │  有区间？→ 算位置、更新形状
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │ 事件引擎      │  调度检测器：AR / Spring / JOC / SOS / SOW
  │ EventEngine  │
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │ 规则引擎      │  判断阶段转换：A → B → C → D → E
  │ RuleEngine   │  管理方向：SC=SHORT, BC=LONG
  └─────────────┘
```

## 技术栈

- **后端**：Python 3.11+ / FastAPI / Polars / NumPy
- **前端**：React / TypeScript / KLineChart v10 / Zustand
- **存储**：JSON（标注） + SQLite（案例库）
- **数据传输**：二进制 Float64Array

## 设计哲学

1. **一切皆插件**：前后端都插件化，第三方可扩展
2. **因果关系反转**：区间先于状态机，先识别区间再检测事件
3. **识别层与决策层分离**：先把"市场在什么状态"识别对，再做交易决策
4. **先建记忆再建智慧**：失败案例同样完整记录，这是进化的燃料

## 状态

🚧 **Alpha 开发中** — 框架和前端已完成，核心检测算法持续迭代中。

## 联系

寻找志同道合的朋友和团队一起完善这个系统。如果你懂威科夫、有实盘经验、或对量化交易系统开发感兴趣，期待你的来信。

📧 **mzygzyg@outlook.com** / **2156446717@qq.com**
