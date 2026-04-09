# Meridian — 开源插件化威科夫分析框架

> 架构设计文档 v1.0 | 2026-04-08
> 唯一真相源：本文档定义系统的整体架构、插件接口、API契约、数据流和施工优先级。
> 威科夫理论核心仍以SYSTEM_DESIGN_V3.md 为准。

---

## 目录

1. 项目愿景
2. 整体架构
3. 前端架构
4. 后端架构
5. API契约
6. 数据流全景
7. 项目结构
8. 施工优先级
9. 与V3设计文档的关系
10. 技术决策记录

---

## 1. 项目愿景

Meridian 是一个开源的、插件化的威科夫市场分析框架。

**核心理念：一切皆插件。**

框架本身只做三件事：管理插件、传递数据、提供通信。所有业务功能都以插件形式存在，可以独立开发、独立部署、独立测试。第三方开发者可以编写自己的插件来扩展框架。

**六个内置插件：**

| 插件 | 功能 |
|------|------|
|📐 进化工作台 | 手动标注威科夫结构 → 自动提取特征 → 积累案例 → 参数进化 → 回测验证 |
| 📡 实盘监控 | 连接交易所 → 引擎自动检测 → 信号生成 → 全自动交易 |
| 🤖 AI 分析师 | AI 读取图表和引擎状态 → 分析建议 → 标注辅助 |
| 🖥️ 后端监控 | 系统健康 → 引擎状态 → 日志 → 性能指标 |
| 📊 回测引擎 | 历史验证 → 策略对比 → 绩效报告 |
| 📋 交易日志 | 交易记录 → PnL统计 → 复盘 |

**闭环进化：**
标注喂进化 → 进化喂引擎 → 引擎出信号 → 交易结果反馈进化 → 用得越多越准。

---

## 2. 整体架构

### 2.1 架构总览

```
┌──────────────────────────────────────────────────────────┐
│                  前端（React + TypeScript）                │
│                                │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐            │
│  │进化工作台│ │实盘监控│ │AI分析师│ │后端监控│ ...│
│  │(前端插件)│ │(前端插件)│ │(前端插件)│ │(前端插件)│            │
│  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘            │
│      └──────────┼──────────┼──────────┘│
│                 │                │
│  ┌──────────────┴────────────────────────────────────┐   │
│  │              前端核心（App Shell）                   │   │
│  │  侧边栏导航 · 路由 · 全局状态 · 插件注册 · 通信总线 │   │
│  │  共享组件库: K线图表 · 画图工具 · 面板 · 命令面板    │   │
│  └──────────────┬────────────────────────────────────┘   │
└─────────────────┼────────────────────────────────────────┘
                │  HTTP REST + WebSocket
┌─────────────────┼────────────────────────────────────────┐
│                  后端（Python + FastAPI）                  │
│  ┌──────────────┴────────────────────────────────────┐   │
│  │              后端核心（Core Framework）              │   │
│  │  插件管理器 · 事件总线 · 数据管道 · API路由注册     │   │
│  └──┬──────┬──────┬──────┬──────┬──────┬─────────────┘   │
│  ┌──┴──┐┌──┴──┐┌──┴──┐┌──┴──┐┌──┴──┐┌──┴──┐             │
│  │数据源││标注 ││引擎 ││进化 ││交易 ││ AI│ ...          │
│  │插件 ││插件 ││插件 ││插件 ││插件 ││插件 ││
│  └─────┘└─────┘└─────┘└─────┘└─────┘└─────┘              │
│  ┌───────────────────────────────────────────────────┐   │
│  │                    存储层                │   │
│  │  标注库 · 案例库 · 区间库 · 规则日志 · 交易记录    │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### 2.2 前后端分离原则

-前端是纯展示+交互层，不包含任何业务逻辑
- 后端是所有计算和决策的唯一来源
- 通信：HTTP REST（请求-响应）+ WebSocket（实时推送）
- 前端独立构建部署（`npm run build` →静态文件）
- 后端独立运行（`python main.py`）

### 2.3 插件化设计原则

1. 框架核心只做三件事：管理插件、传递数据、提供通信
2. 所有业务功能都在插件里
3. 插件之间通过事件总线解耦通信，不直接调用
4. 插件可以声明依赖（如"交易插件依赖引擎插件"）
5. 插件有标准生命周期：注册 → 初始化 → 启动 → 停止 → 卸载
6. 安装插件 = 把文件夹放到 plugins/ 目录 → 重启 → 自动加载

---

## 3. 前端架构

### 3.1 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 框架 | React 18 + TypeScript 5 | 组件化，类型安全 |
| 构建 | Vite |秒级热更新 |
| 图表 | KLineChart v10 | 唯一内置画图工具的开源K线库 |
| 状态管理 | Zustand + zundo | 极轻量 +撤销重做 |
| 面板布局 | allotment | 可拖拽/可调整大小的分割面板 |
| 样式 | Tailwind CSS v4 + CSS Variables | 原子化CSS + 主题系统 |
| K线传输 | ArrayBuffer | 二进制传输，零解析 |
| 本地缓存 | IndexedDB (Dexie.js) | K线下载一次，永久缓存 |
| 后台计算 | Web Worker | 主线程只做渲染 |

### 3.2 应用壳（App Shell）

应用壳是框架的骨架，不属于任何插件：

```
┌──────────────────────────────────────────────────┐
│ [侧边栏]│ [插件渲染区]                │
│            │                                      │
│   📐│   当前活跃插件的完整页面              │
│   📡       │   每个插件拥有整个区域的控制权        │
│   🤖       │   自己的布局、面板、工具栏            │
│   🖥️       │                                      │
│   📊       │                                      │
│   📋       │                                      │
│            │                                      │
│   ───│                                      │
│   ＋│  ← 安装新插件                        │
│   ⚙│  ← 全局设置                          │
└──────────────────────────────────────────────────┘
```

App Shell 提供的能力：

| 能力 | 说明 |
|------|------|
| 侧边栏导航 | 显示所有已安装插件图标，点击切换 |
| 路由系统 | 每个插件注册自己的路由，App Shell负责切换 |
| 全局状态 | 当前标的(symbol)、当前周期(timeframe)、主题 |
| 共享组件库 | K线图表、画图工具、面板容器等 |
| 插件注册表 | 管理前端插件的注册/激活/停用 |
| 前端事件总线 | 插件间通信 |
| 命令面板 | Ctrl+K全局搜索 |
| 通知系统 | 全局通知队列 |

### 3.3 前端插件接口

```typescript
interface MeridianFrontendPlugin {
  // 元数据
  id: string;                    // 唯一标识
  name: string;                  // 显示名称
  icon: string;                  // 侧边栏图标
  version: string;               // 版本号

  // 路由
  routes: PluginRoute[];

  // 生命周期（均可选）
  onActivate?: () => void;       // 切换到此插件时
  onDeactivate?: () => void;     // 离开此插件时
  onInstall?: () => void;
  onUninstall?: () => void;

  // 扩展点（可选）
  extensions?: PluginExtension[];
  dependencies?: string[];
}

interface PluginRoute {
  path: string;
  component: React.ComponentType;
  label?: string;
}

interface PluginExtension {
  target: string;                // 目标扩展点
  component: React.ComponentType;
  priority?: number;
}
```

### 3.4 内置前端插件

#### 3.4.1 📐 进化工作台（EvolutionWorkbench）

页面布局：
```
┌─[标的▾]─[5m|15m|1H|4H|D|W]──────[📂加载]─[▶回测]──┐
│┌──┐┌─────────────────────────────┐┌────────────────┐│
││工││││📋 标注管理     ││
││具││                             ││ 事件列表       ││
││栏││        K线图表              ││ 点击跳转       ││
││  ││   + 标注叠加层              ││ 右键编辑       ││
││↗ ││   + 大周期标注可见││                ││
││╱ ││                             ││🔬 特征透视     ││
││▱ ││                             ││ 7维特征矩阵    ││
││─ ││                             ││ 后续结果       ││
│││ ││                             ││                ││
││💬││                             ││📐 区间状态     ││
││🗑││                             ││🧬 进化仪表盘   ││
│└──┘└─────────────────────────────┘│📊 回测结果     ││
│└────────────────┘│
└──────────────────────────────────────────────────────┘
```

右侧面板：

**📋 标注管理面板：**
- 已标注事件列表，按时间排序
- 每条：事件类型图标 + 名称 + 日期 + 周期
- 点击跳转、右键编辑/删除
- 筛选器：按类型/周期/阶段

**🔬 特征透视面板：**
- 选中事件后显示 7 维特征（量比/下影线/实体位置/距支撑/恐慌度/趋势长度/斜率）
- 后续结果：5/10/20bar价格变化
- 与案例库同类事件对比

**📐 区间状态面板：**
- 区间形状/斜率/宽度/三锚点/阶段/强度/Creek/Ice

**🧬 进化仪表盘面板：**
- 各类事件案例数量和变体数
- 参数进化历史（当前值 vs 初始值）
- [▶ 运行进化] [📥 导出] [📤 导入]

**📊 回测结果面板：**
- 胜率/盈亏比/最大回撤/夏普/总PnL
- PnL曲线、逐笔交易列表

画图工具栏：

| 工具 | 快捷键 | 用途 |
|------|--------|------|
| ↗光标 | 1| 选择/移动 |
| ╱ 趋势线 | 2 | 画趋势线 |
| ▱ 平行通道 | 3 | 画区间 |
| ─ 水平线 | 4 | 支撑/阻力 |
| │垂直线 | 5 | 阶段分割 |
| ▭矩形 | 6 | 区域标记 |
| 💬 事件气泡 | 7 | 标注事件 |
| 🏷 阶段标记 | 8 | 标注阶段 |
|🗑 删除 | Del | 删除 |

交互规范（复刻TradingView）：
-Esc 退出当前工具
- Ctrl+Z/Y 撤销/重做
- 锚点拖拽、右键菜单、K线磁吸
- 自动保存（debounce 1秒）
- 多周期同步（标注锚定数据坐标）
- 大周期标注在小周期上保持可见

#### 3.4.2 📡 实盘监控（LiveMonitor）

页面布局：
```
┌─[●LIVE]─[ETHUSDT]─[$3,847+2.34%]─[4H|D]─[⚙设置]──┐
│┌────────────────────────────────┐┌──────────────────┐│
││                                ││🔍 引擎状态       ││
││       实时K线图表               ││ 阶段/方向/置信度 ││
││  + 引擎自动标注（半透明）       ││ 区间/强度/等待中 ││
││  + 手动修正标注                 ││                ││
││                                ││🌐 多周期共振││
││                                ││ W/D/4H/1H状态   ││
││                                ││ 综合确定性       ││
││                                ││                  ││
││                                ││⚡ 信号            ││
││                                ││ 待触发/已触发    ││
││                                ││仓位/止损/目标   ││
││                                ││                  ││
│└────────────────────────────────┘│🛡仓位/风险      ││
│                                  │ 持仓/PnL/回撤    ││
│                                  └──────────────────┘│
│● Binance 23ms ·引擎运行中 · 参数 v3.2│
└───────────────────────────────────────────────────────┘
```

右侧面板：

**🔍 引擎状态：** 当前阶段 + 结构类型 + 方向 + 置信度（颜色编码）+ 区间形状 + 强度 + 最近事件 + 等待检测的事件

**🌐 多周期共振：** 每个TF的阶段+方向、阶段共振度、方向共振度、综合确定性、仓位系数建议

**⚡ 信号：** 待触发条件 + 触发价格 + 方向 + 建议仓位/止损/目标

**🛡 仓位/风险：** 当前持仓 + 未实现PnL + 最大回撤 + 风险敞口

全自动交易：引擎信号 → 计算仓位 → 自动下单 → 自动止损止盈 → 结果反馈进化

手动修正：在实盘图上修正引擎标注 → 差异记录为高价值进化燃料

#### 3.4.3 🤖 AI 分析师（AIAnalyst）

页面布局：左边K线图 + 右边对话窗口。AI可以在图上画标注。

AI能力：
- 读取图表状态（结构化JSON，不是截图）
- 分析标注质量
- 建议标注
- 解释引擎决策
- 案例库检索对比
- 生成分析报告
- 多标的扫描

AI接入：支持 OpenAI 兼容 API（NewAPI/OpenRouter/直连）

侧边栏模式：在进化/实盘页面可呼出AI侧边栏

#### 3.4.4 🖥️ 后端监控（SystemMonitor）

面板：系统资源(CPU/内存/磁盘) + 引擎状态(各引擎运行/空闲/错误) + 连接状态(交易所/前端WS/AI/数据库) + 实时日志(可筛选) + 性能指标(API请求数/响应时间/延迟/错误) + 插件状态

#### 3.4.5 📊 回测引擎（Backtester）

选择标的+时间范围+参数版本 → 运行回测 → 绩效指标 + PnL曲线 + 逐笔交易 + 策略对比 + 检测准确率

#### 3.4.6 📋 交易日志（TradeJournal）

交易记录表格+ 日/周/月统计 + 复盘（点击交易跳转到当时K线+引擎快照）+ 标签系统 + 导出CSV/PDF

### 3.5 前端增强特性（8项）

**F1: 可拖拽面板布局**
面板可拖动位置、调整大小、折叠/展开。技术：allotment。状态持久化到localStorage。

**F2: 工作空间（Workspace）**
保存当前状态（插件+布局+标的+周期+面板开关）为工作空间。多个工作空间一键切换。

**F3: 多图表同屏**
同页面 1/2/4/6 个图表。联动模式（标注同步+十字光标同步+时间范围同步）或独立模式。

**F4: 命令面板**
Ctrl+K 唤出。搜标的/功能/标注/命令/设置。键盘导航。

**F5: 告警/通知系统**
全局通知队列。类型：紧急(交易/止损/错误)、重要(信号/阶段转换)、信息(状态更新)。可选Telegram/Discord推送（插件）。

**F6: 数据可视化增强**
可叠加：Volume Profile、深度图、资金费率、持仓量、热力图。每种可作为插件开发。

**F7: 主题系统**
CSS Variables驱动。内置暗色+亮色。自定义配色。所有插件自动跟随。主题可导出/导入。

**F8: 插件市场（远期）**
初期：手动安装。中期：CLI安装。远期：在线市场+一键安装。

### 3.6 共享组件库

| 组件 | 说明 |
|------|------|
| ChartWidget | KLineChart 包装，支持历史+实时+标注叠加 |
| DrawingToolbar | 画图工具栏 |
| PanelContainer | 可折叠面板 |
| SplitLayout | 可拖拽分割布局 |
| TimeframeSelector | 周期切换 |
| SymbolSelector | 标的选择（支持搜索） |
| CommandPalette | 命令面板 |
| NotificationToast | 通知弹出|
| DataTable | 数据表格（排序/筛选/分页） |
| MiniChart | 迷你图表 |
| StatusBadge | 状态徽章 |---

## 4. 后端架构

### 4.1 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 框架 | FastAPI + Uvicorn | 异步高性能 |
| 数据处理 | Polars | 替代Pandas，性能10x+ |
| 实时通信 | WebSocket (fastapi) | 实时推送 |
| 存储 | SQLite (aiosqlite) | 轻量级，单文件，异步 |
| 数值计算 | NumPy | 特征提取、指标计算 |
| 交易所 | ccxt | 多交易所统一接口 |
| AI | httpx | 调用OpenAI兼容API |
| 二进制传输 | numpy.tobytes() | K线零解析传输 |
| 配置 | pydantic-settings | 类型安全配置 |

### 4.2 核心框架

后端核心框架由四个组件构成：

**① 插件管理器（PluginManager）**
```python
class PluginManager:
    async def register(self, plugin: BackendPlugin) -> None
    async def start_all(self) -> None          # 按依赖顺序启动
    async def stop_all(self) -> None           # 逆序停止
    def get_plugin(self, plugin_id: str) -> BackendPlugin
    async def health_check(self) -> dict
```

**② 事件总线（EventBus）**
```python
class EventBus:
    async def publish(self, event_type: str, data: Any) -> None  # 异步不阻塞
    def subscribe(self, event_type: str, handler: Callable) -> None
    def unsubscribe(self, event_type: str, handler: Callable) -> None
```

**③ 数据管道（DataPipeline）**
```python
class DataPipeline:
    async def get_candles(self, symbol, timeframe, start, end) -> pl.DataFrame
    async def subscribe_realtime(self, symbol, timeframe, callback) -> None
    async def unsubscribe_realtime(self, symbol, timeframe) -> None
```

**④ API路由注册（APIRegistry）**
```python
class APIRegistry:
    def register_routes(self, plugin_id: str, router: APIRouter) -> None
    def register_websocket(self, plugin_id: str, path: str, handler: Callable) -> None
```

### 4.3 后端插件接口

```python
from abc import ABC, abstractmethod
from fastapi import APIRouter

class BackendPlugin(ABC):
    # 元数据
    id: str
    name: str
    version: str
    dependencies: list[str] = []

    # 生命周期
    @abstractmethod
    async def on_init(self, ctx: PluginContext) -> None: ...
    @abstractmethod
    async def on_start(self) -> None: ...
    @abstractmethod
    async def on_stop(self) -> None: ...
    async def on_health_check(self) -> dict:
        return {"status": "ok"}

    # API路由（可选）
    def get_router(self) -> APIRouter | None:
        return None

    # 事件订阅（可选）
    def get_subscriptions(self) -> dict[str, Callable]:
        return {}

class PluginContext:
    event_bus: EventBus
    data_pipeline: DataPipeline
    storage: StorageManager
    config: dictget_plugin: Callable
```

### 4.4 内置后端插件

#### 4.4.1 数据源插件（DataSource）
- 本地TSV/CSV文件读取+ Binance WebSocket实时数据
- 统一数据格式（Polars DataFrame）
- 二进制传输（numpy.tobytes → ArrayBuffer）
- API: `GET /api/datasource/candles/{symbol}/{tf}` → ArrayBuffer
- API: `GET /api/datasource/symbols` → JSON
- WS: `ws://host/ws/candles/{symbol}/{tf}`
- 发布: `candle.new`

#### 4.4.2 标注插件（Annotation）
- Drawing CRUD + 7维特征提取 + EventCase自动生成
- API: `GET/POST/PUT/DELETE /api/annotation/drawings/{symbol}`
- API: `GET /api/annotation/features/{symbol}/{drawing_id}`
- 发布: `annotation.created`, `annotation.updated`, `annotation.deleted`

#### 4.4.3 引擎插件（WyckoffEngine）
- 内含三个子引擎：区间引擎 + 事件引擎 + 规则引擎
- 依赖: `datasource`, `annotation`(可选)
- API: `GET /api/engine/state/{symbol}/{tf}`
- API: `GET /api/engine/state/{symbol}/all`
- API: `POST /api/engine/start`, `POST /api/engine/stop`
- API: `GET /api/engine/ranges/{symbol}`, `GET /api/engine/events/{symbol}`
- WS: `ws://host/ws/engine/{symbol}`
- 发布: `engine.phase_changed`, `engine.event_detected`, `engine.signal_generated`, `engine.range_created`
- 订阅: `candle.new`, `evolution.params_updated`

#### 4.4.4 进化插件（Evolution）
- 案例库管理 + 参数优化 + 变体聚类 + 参数版本管理 + 回测验证
- 依赖: `annotation`, `engine`
- API: `GET /api/evolution/stats`
- API: `GET /api/evolution/cases`, `GET /api/evolution/params/{version}`
- API: `POST /api/evolution/run`, `POST /api/evolution/backtest`
- 发布: `evolution.params_updated`, `evolution.generation_complete`
- 订阅: `annotation.created`, `trading.position_closed`

#### 4.4.5 交易插件（Trading）
- 交易所连接(ccxt) + 订单管理 + 仓位管理 + 风险控制 + 全自动执行
- 风险控制：单笔最大仓位、最大同时持仓数、日最大亏损、止损强制执行
- 依赖: `engine`
- API: `GET /api/trading/positions`, `GET /api/trading/orders`
- API: `POST /api/trading/order`, `DELETE /api/trading/order/{id}`
- API: `GET /api/trading/history`, `GET /api/trading/balance`
- WS: `ws://host/ws/trading`
- 发布: `trading.order_placed`, `trading.order_filled`, `trading.position_closed`
- 订阅: `engine.signal_generated`

#### 4.4.6 AI插件（AIAnalyst）
- OpenAI兼容API调用 + 图表状态序列化 + 对话管理 + 标注建议
- 依赖: `datasource`, `annotation`, `engine`, `evolution`
- API: `POST /api/ai/chat`, `GET /api/ai/analyze/{symbol}/{tf}`
- API: `PUT /api/ai/config`
- 配置：provider + api_base + api_key + model

### 4.5 存储层

```
storage/
├── meridian.db                # SQLite主数据库
│   ├── event_cases表# 案例库
│   ├── ranges 表               # 区间库
│   ├── rule_logs 表            # 规则日志
│   ├── trades 表               # 交易记录
│   └── candle_cache 表         # K线缓存
├── drawings/                # 标注数据（JSON per symbol）
│   ├── ETHUSDT.json
│   └── BTCUSDT.json
├── evolution/                  # 进化参数版本（JSON）
│   ├── params_v1.json
│   ├── params_v2.json
│   └── params_latest.json
└── workspaces/                 # 工作空间配置（JSON）
```

标注用JSON：数据量小、便于人工检查、git diff友好。
案例库用SQLite：数量持续增长、需要条件查询和聚合统计。

### 4.6 事件总线事件清单

| 事件名 | 发布者 | 订阅者 | 数据 |
|--------|--------|--------|------|
| candle.new | DataSource | Engine | symbol, tf, candle |
| annotation.created | Annotation | Evolution | drawing |
| annotation.updated | Annotation | Evolution | drawing |
| annotation.deleted | Annotation | Evolution | drawing_id |
| engine.phase_changed | Engine | Trading, AI | symbol, tf, phase, direction |
| engine.event_detected | Engine | Annotation, AI | event |
| engine.signal_generated | Engine | Trading | signal |
| engine.range_created | Engine | — | range |
| evolution.params_updated | Evolution | Engine | params_version, params |
| evolution.generation_complete | Evolution | — | generation, stats |
| trading.order_placed | Trading | — | order |
| trading.order_filled | Trading | Evolution | order |
| trading.position_closed | Trading | Evolution | position, pnl |---

## 5. API 契约

### 5.1 REST API 总览

所有路由以 `/api/{plugin_id}/` 为前缀，由框架 APIRegistry 自动注册。

```
#===== 数据源 =====
GET  /api/datasource/candles/{symbol}/{tf}?start=&end=  → ArrayBuffer
GET  /api/datasource/symbols→ JSON

# ===== 标注 =====
GET    /api/annotation/drawings/{symbol}→ JSON [Drawing]
POST   /api/annotation/drawings/{symbol}                 → JSON Drawing
PUT    /api/annotation/drawings/{symbol}/{id}             → JSON Drawing
DELETE /api/annotation/drawings/{symbol}/{id}             → JSON {ok}
GET    /api/annotation/features/{symbol}/{drawing_id}    → JSON Features

# ===== 引擎 =====
GET  /api/engine/state/{symbol}/{tf}                     → JSON EngineState
GET  /api/engine/state/{symbol}/all→ JSON {tf: State}
POST /api/engine/start                                   → JSON {ok}
POST /api/engine/stop                                    → JSON {ok}
GET  /api/engine/ranges/{symbol}→ JSON [Range]
GET  /api/engine/events/{symbol}                         → JSON [Event]

# ===== 进化 =====
GET  /api/evolution/stats                → JSON Stats
GET  /api/evolution/cases?type=&tf=&limit=               → JSON [Case]
GET  /api/evolution/params/{version}                     → JSON Params
GET  /api/evolution/params/latest                        → JSON Params
POST /api/evolution/run                                  → JSON {generation}
POST /api/evolution/backtest                             → JSON Result

# ===== 交易 =====
GET    /api/trading/positions                            → JSON [Position]
GET    /api/trading/orders                               → JSON [Order]
POST   /api/trading/order                                → JSON Order
DELETE /api/trading/order/{id}                            → JSON {ok}
GET    /api/trading/history?start=&end=                  → JSON [Trade]
GET    /api/trading/balance                              → JSON Balance

# ===== AI =====
POST /api/ai/chat                                → JSON {reply}
GET  /api/ai/analyze/{symbol}/{tf}                       → JSON Report
PUT  /api/ai/config                                      → JSON {ok}

# ===== 系统 =====
GET  /api/system/health                                  → JSON {status}
GET  /api/system/plugins                                 → JSON [Plugin]
GET  /api/system/logs?level=&source=&limit=              → JSON [Log]
GET  /api/system/metrics→ JSON Metrics
GET  /api/system/config                                  → JSON Config
PUT  /api/system/config                                  → JSON Config
```

### 5.2 WebSocket API

```
# K线实时数据
ws://host/ws/candles/{symbol}/{tf}
  → { type: "candle", data: { time, open, high, low, close, volume } }

# 引擎状态
ws://host/ws/engine/{symbol}
  → { type: "state_update", data: EngineState }→ { type: "event_detected", data: Event }
  → { type: "signal", data: Signal }

# 交易
ws://host/ws/trading
  → { type: "order_update", data: Order }
  → { type: "position_update", data: Position }

# 系统日志
ws://host/ws/system/logs
  → { type: "log", data: { level, message, timestamp, source } }
```

### 5.3 核心数据类型

```typescript
// K线：ArrayBuffer传输，每根= 6个float64 = 48字节
// 前端用 Float64Array 按偏移量读取

interface Drawing {
  id: string;
  symbol: string;
  type: "trend_line" | "parallel_channel" | "horizontal_line" |
        "vertical_line" | "rectangle" | "callout" | "phase_marker";
  points: { time: number; price: number }[];
  properties: {
    color?: string;
    lineWidth?: number;
    lineStyle?: "solid" | "dashed" | "dotted";
    text?: string;
    eventType?: string;       // 威科夫事件类型
    phase?: string;           // 阶段标记
    timeframe?: string;
  };
  created_at: string;
  updated_at: string;
}

interfaceEngineState {
  symbol: string;
  timeframe: string;
  current_phase: "A" | "B" | "C" | "D" | "E" | "TREND" | "UNKNOWN";
  structure_type: "accumulation" | "distribution" |
                  "re_accumulation" | "re_distribution" | "unknown";
  direction: "long" | "short" | "neutral";
  confidence: number;          // 0-1
  active_range: Range | null;
  recent_events: Event[];
  pending_detections: string[];
  params_version: string;
}

interface Range {
  id: string;
  symbol: string;
  timeframe: string;
  status: "CANDIDATE" | "CONFIRMED" | "ACTIVE" |"BROKEN" | "ARCHIVED" | "REJECTED";
  shape: "horizontal" | "ascending" | "descending";
  channel_slope: number;
  channel_width: number;
  anchors: {
    primary1: { time: number; price: number };  // SC/BC
    primary2: { time: number; price: number };  // ST
    opposite: { time: number; price: number };  // AR
  };
  strength: number;
  current_phase: string;
  entry_trend: "down" | "up";
  creek: TrendLine | null;
  ice: TrendLine | null;
}

interface Event {
  id: string;
  event_type: string;
  event_result: "SUCCESS" | "FAILED" | "SKIPPED" | "PENDING";
  range_id: string;
  phase: string;
  timeframe: string;
  start_bar: number;
  end_bar: number;
  extreme_price: number;
  volume_ratio: number;
  effort_vs_result: number;
  penetration_depth: number;
  confidence: number;
  timestamp: string;
}

interface Signal {
  id: string;
  symbol: string;
  timeframe: string;
  action: "buy" | "sell" | "close_long" | "close_short";
  trigger_price: number;
  confidence: number;
  position_size: number;
  stop_loss: number;
  take_profit: number;
  reason: string;
  timestamp: string;
}
```

---

## 6. 数据流全景

### 6.1 标注 → 进化（进化工作台）

```
莱恩在图上画标注
    ↓
前端 POST /api/annotation/drawings/{symbol}
    ↓
标注插件保存 Drawing → drawings/{symbol}.json
    ↓
发布 annotation.created
    ↓
标注插件自动提取 7维特征
    ↓
生成 EventCase（标注 + 特征 + K线快照 + 后续结果）
    ↓
存入 meridian.db → event_cases 表
    ↓
进化插件订阅 →更新统计
    ↓
莱恩点击 [▶ 运行进化]
    ↓
进化插件读取案例 → 统计分析 → 优化参数 → 变体聚类
    ↓
新参数存入 evolution/params_v{N}.json
    ↓
发布 evolution.params_updated
    ↓
引擎插件订阅 → 加载新参数
```

### 6.2 实盘数据流

```
Binance WebSocket 推送实时K线
    ↓
数据源插件接收 → 标准化 → 发布 candle.new
    ↓
引擎插件订阅
    ↓
区间引擎: SC/BC → AR/ST → 三点定区间
事件引擎: 8种检测模板
规则引擎: 阶段转换 → 方向 → 信号
    ↓
发布 engine.signal_generated
    ↓
交易插件订阅 → 计算仓位 → 自动下单
    ↓
交易所返回成交 → 发布 trading.order_filled
    ↓
前端 WebSocket 实时接收 → 图表/面板/通知更新
```

### 6.3 闭环：交易 → 进化

```
交易完成（止盈/止损/阶段变化平仓）
    ↓
发布 trading.position_closed（含PnL）
    ↓
进化插件订阅 → 关联到对应引擎事件 → 更新EventCase后续结果
    ↓
积累数据 → 触发进化 → 新参数 → 引擎 → 更好的信号
```

### 6.4 手动修正→ 进化

```
莱恩在实盘图上修正引擎标注
    ↓
POST修正标注 → 标注插件对比人工 vs 引擎
    ↓
差异记录为"修正案例"（高价值进化燃料）
    ↓
进化系统重点学习 → 减少未来偏差
```

---

## 7. 项目结构

```
meridian/
├── README.md
├── LICENSE
├── config.yaml
├── requirements.txt
│
├── backend/
│   ├── main.py                # FastAPI 入口
│   ├── core/                         # 核心框架（不可插拔）
│   │   ├── plugin_manager.py
│   │   ├── event_bus.py
│   │   ├── data_pipeline.py
│   │   ├── api_registry.py
│   │├── storage.py
│   │   ├── websocket_manager.py
│   │   └── types.py
│   │
│   ├── plugins/      # 后端插件
│   │   ├── datasource/
│   │   │   ├── plugin.py
│   │   │   ├── local_loader.py
│   │   │├── binance_ws.py
│   │   │   └── routes.py
│   │   ├── annotation/
│   │   │   ├── plugin.py
│   │   │   ├── drawing_store.py
│   │   │   ├── feature_extractor.py
│   │   │   ├── case_builder.py
│   │   │   └── routes.py
│   │   ├── engine/
│   │   │   ├── plugin.py
│   │   │   ├── range_engine.py
│   │   │   ├── event_engine.py
│   │   │   ├── rule_engine.py
│   │   │   ├── detectors/
│   │   │   │   ├── base_detector.py
│   │   │   │   ├── sc_detector.py
│   │   │   │   ├── ar_detector.py
│   │   │   │   ├── st_detector.py
│   │   │   │   ├── spring_detector.py
│   │   │   │   ├── utad_detector.py
│   │   │   │   ├── sos_detector.py
│   │   │   │   ├── sow_detector.py
│   │   │   │   └── joc_detector.py
│   │   │   ├── models.py
│   │   │   └── routes.py
│   │   ├── evolution/
│   │   │   ├── plugin.py
│   │   │   ├── case_store.py
│   │   │   ├── optimizer.py
│   │   │   ├── clusterer.py
│   │   │   ├── backtester.py
│   │   │   └── routes.py
│   │   ├── trading/
│   │   │   ├── plugin.py
│   │   │   ├── exchange.py
│   │   │   ├── position_manager.py
│   │   │   ├── risk_manager.py
│   │   │   ├── order_executor.py
│   │   │   └── routes.py
│   │   └── ai/
│   │       ├── plugin.py
│   │       ├── llm_client.py
│   │       ├── chart_serializer.py
│   │       ├── conversation.py
│   │       └── routes.py
│   │
│   └── storage/
│       ├── meridian.db
│       ├── drawings/
│       ├── evolution/
│       └── workspaces/
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── core/
│       │   ├── PluginRegistry.ts
│       │   ├── EventBus.ts
│       │   ├── AppShell.tsx
│       │   ├── Sidebar.tsx
│       │   ├── router.ts
│       │   └── types.ts
│       ├── stores/
│       │   ├── appStore.ts
│       │   ├── drawingStore.ts
│       │   ├── notificationStore.ts
│       │   └── workspaceStore.ts
│       ├── shared/
│       │   ├── chart/
│       │   │   ├── ChartWidget.tsx
│       │   │   ├── DrawingToolbar.tsx
│       │   │   └── ChartOverlay.tsx
│       │   ├── layout/
│       │   │   ├── PanelContainer.tsx
│       │   │   └── SplitLayout.tsx
│       │   ├── controls/
│       │   │   ├── TimeframeSelector.tsx
│       │   │   ├── SymbolSelector.tsx
│       │   │   └── StatusBadge.tsx
│       │   ├── feedback/
│       │   │   ├── CommandPalette.tsx
│       │   │   ├── NotificationToast.tsx
│       │   │   └── LoadingSpinner.tsx
│       │   └── data/
│       │       ├── DataTable.tsx
│       │       └── MiniChart.tsx
│       ├── plugins/
│       │   ├── evolution-workbench/
│       │   │   ├── index.ts
│       │   │   ├── EvolutionPage.tsx
│       │   │   ├── panels/
│       │   │   │   ├── AnnotationPanel.tsx
│       │   │   │   ├── FeaturePanel.tsx
│       │   │   │   ├── RangePanel.tsx
│       │   │   │   ├── EvolutionDashboard.tsx
│       │   │   │   └── BacktestPanel.tsx
│       │   │   └── hooks/
│       │   ├── live-monitor/
│       │   │   ├── index.ts
│       │   │   ├── LivePage.tsx
│       │   │   ├── panels/
│       │   │   │   ├── EngineStatePanel.tsx
│       │   │   │   ├── MultiTFPanel.tsx
│       │   │   │   ├── SignalPanel.tsx
│       │   │   │   └── PositionPanel.tsx
│       │   │   └── hooks/
│       │   ├── ai-analyst/
│       │   │   ├── index.ts
│       │   │   ├── AIPage.tsx
│       │   │   ├── ChatWindow.tsx
│       │   │   ├── AISidebar.tsx
│       │   │   └── hooks/
│       │   ├── system-monitor/
│       │   │   ├── index.ts
│       │   │   ├── MonitorPage.tsx
│       │   │   └── panels/
│       │   ├── backtester/
│       │   │   ├── index.ts
│       │   │   ├── BacktestPage.tsx
│       │   │   └── panels/
│       │   └── trade-journal/
│       │       ├── index.ts
│       │       ├── JournalPage.tsx
│       │       └── panels/
│       ├── services/
│       │   ├── api.ts
│       │   ├── websocket.ts
│       │   └── cache.ts
│       ├── workers/
│       │   ├── dataWorker.ts
│       │   └── computeWorker.ts
│       ├── themes/
│       │   ├── variables.css
│       │   ├── dark.css
│       │   └── light.css
│       └── utils/
│           ├── binary.ts
│           ├── format.ts
│           └── keyboard.ts
│
├── data/
│   └── ETHUSDT/
│       ├── 5m.tsv
│       ├── 1h.tsv
│       └── 1d.tsv
│
├── docs/
│   ├── SYSTEM_DESIGN_V3.md
│   ├── WORKBENCH_DESIGN.md
│   ├── PLUGIN_DEV_GUIDE.md
│   └── API_REFERENCE.md
│
└── archive/
```

---

## 8. 施工优先级

### P0: 核心框架 + 进化工作台（MVP）

**目标**：能打开应用 → 加载K线 → 画标注 → 保存 → 看特征

后端：
- [ ] 核心框架（PluginManager + EventBus + DataPipeline + APIRegistry + Storage）
- [ ] 数据源插件（本地TSV加载 + 二进制传输）
- [ ] 标注插件（Drawing CRUD + 7维特征提取）

前端：
- [ ] App Shell（侧边栏 + 路由 + 插件注册）
- [ ] 共享组件（ChartWidget + DrawingToolbar + PanelContainer）
- [ ] 进化工作台插件（K线图表 + 画图工具 + 标注面板 + 特征面板）
- [ ] 基础主题（暗色）
- [ ] 基础快捷键

验收标准：
1. 启动后端→ 启动前端 → 浏览器打开看到侧边栏 + 进化工作台
2. 选择标的和周期 → 加载K线数据 → 图表正常显示
3. 使用画图工具画平行通道/趋势线/事件气泡 → 保存成功
4. 选中标注 → 右侧显示7维特征
5. 切换周期 → 标注跟随映射
6. Ctrl+Z 撤销 → 生效

### P1: 进化系统 + 引擎

**目标**：标注能生成案例 → 能跑进化 → 引擎能用进化参数检测

后端：
- [ ] 标注插件增强（EventCase生成）
- [ ] 进化插件（案例库 + 参数优化 + 变体聚类 + 参数版本管理）
- [ ] 引擎插件-区间引擎（SC/BC检测 → AR/ST → 三点定区间）
- [ ] 引擎插件-事件引擎（8种检测模板）
- [ ] 引擎插件-规则引擎（阶段转换 → 方向管理）

前端：
- [ ] 进化工作台增强（区间状态面板 + 进化仪表盘 + 回测面板）
- [ ] 可拖拽面板布局（F1）

验收标准：
1. 标注事件 → 自动生成EventCase → 案例库可查看
2. 点击运行进化 → 参数更新 → 版本保存
3. 引擎在历史数据上运行 → 能检测到区间和事件
4. 回测面板显示检测结果 vs 人工标注对比

### P2: 实盘 + 交易

**目标**：连接交易所 → 引擎实时运行 → 全自动交易

后端：
- [ ] 数据源插件增强（Binance WebSocket）
- [ ] 交易插件（交易所连接 + 订单管理 + 风险控制 + 全自动执行）
- [ ] 引擎插件增强（实时模式 + 多周期独立运行）

前端：
- [ ] 实盘监控插件（全部面板）
- [ ] 告警/通知系统（F5）
- [ ] 多图表同屏（F3）

验收标准：
1. 连接Binance → 实时K线流入 → 图表实时更新
2. 引擎自动检测 → 图上显示半透明区间和事件标记
3. 信号生成 → 自动下单 → 仓位面板更新
4. 止损触发 → 自动平仓 → 通知弹出
5. 手动修正标注 → 差异记录到案例库

### P3: AI + 监控 + 增强

**目标**：AI分析 + 系统监控 + 所有增强特性

后端：
- [ ] AI插件（LLM客户端 + 图表序列化 + 对话管理）

前端：
- [ ] AI分析师插件（对话 + 图上标注 + 侧边栏模式）
- [ ] 后端监控插件
- [ ] 回测引擎插件
- [ ] 交易日志插件
- [ ] 命令面板（F4）
- [ ] 工作空间（F2）
- [ ] 数据可视化增强（F6）
- [ ] 主题系统完善（F7）
- [ ] 插件市场框架（F8）

---

## 9. 与V3设计文档的关系

SYSTEM_DESIGN_V3.md 中的55条设计决策（RD）仍然是引擎插件的理论基础：

| V3内容 | 在Meridian中的位置 |
|--------|-------------------|
| 三引擎架构 (RD-1~15) | 引擎插件内部结构 |
| 事件检测模板 (RD-16~30) | engine/detectors/ 目录 |
| 进化四层分离 (RD-50~55) | 进化插件的参数管理 |
| 区间生命周期 | engine/range_engine.py |
| 阶段转换规则 | engine/rule_engine.py |
| 数据结构 (Range/Event/EventCase) | engine/models.py + annotation/case_builder.py |

V3描述"引擎怎么思考"，本文档描述"整个系统怎么组织"。

---

## 10. 技术决策记录

| ID | 决策 | 理由 |
|----|------|------|
| MD-1 | 项目命名 Meridian | 莱恩选定|
| MD-2 | 前后端都插件化 | 开源框架可扩展性 |
| MD-3 | SQLite 为主存储 | 轻量单文件，异步支持 |
| MD-4 | 前端插件 = React模块 + 注册接口 | 简单直接，不需要微前端复杂度 |
| MD-5 | 后端插件 = Python模块 + BackendPlugin接口 | 清晰的生命周期和依赖管理 |
| MD-6 | 事件总线解耦 | 插件之间不直接调用 |
| MD-7 | 实盘全自动交易 | 莱恩确认 |
| MD-8 | AI接入OpenAI兼容API | 支持NewAPI/OpenRouter/直连|
| MD-9 | 8个前端增强特性全部实现 | 莱恩确认 |
| MD-10 | 旧设计文档移入docs/保留| V3理论核心仍有效 |
| TD-1 | Polars替代Pandas | 性能10x+ |
| TD-2 | ArrayBuffer二进制传输 | 比JSON快100倍 |
| TD-3 | Python壳+Rust核（渐进） | 先跑通再跑快 |
| TD-5 | React18+ TS5 + Vite | 组件化+类型安全+快速构建 |
| TD-6 | ArrayBuffer裸二进制 | 零解析直接读|
| TD-7 | IndexedDB本地缓存 | K线下载一次永久缓存 |
| TD-8 | Web Worker | 主线程只做渲染 |
| TD-9 | Zustand + zundo | 极轻量+撤销重做 |
| TD-10 | KLineChart v10 | 唯一内置画图工具的开源K线库 |

---

> 文档结束。施工从P0开始，逐级推进。