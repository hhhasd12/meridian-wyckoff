# Meridian P0 施工指南

> 施工人员从这里开始。按顺序做，每一步有详细的 README 告诉你怎么做。

## 必读文档

| 文档 | 位置 | 用途 |
|------|------|------|
| 本文件 | CONSTRUCTION.md | 施工入口，告诉你做什么、按什么顺序 |
| 内核文档 | backend/core/README.md | 插件框架设计 + 每个文件的施工规范 |
| datasource 文档 | backend/plugins/datasource/README.md | 数据源插件的API 和施工要点 |
| annotation 文档 | backend/plugins/annotation/README.md | 标注插件的 API 和施工要点 |
| 代码骨架参考 | docs/IMPLEMENTATION_PROMPT.md | 完整代码骨架（可参考，但以各README 为准） |
| 架构设计 | docs/MERIDIAN_ARCHITECTURE.md | 系统全貌（理解为什么这样设计） |
| 前端总览 | frontend/README.md | 前端技术栈 + 目录结构 + 施工顺序 |
| 前端核心 | frontend/src/core/README.md | 插件框架 + 状态管理 + API通信 |
| 图表核心 | frontend/src/shared/chart/README.md | KLineChart 集成 + 自定义 Overlay |
| 进化工作台 | frontend/src/plugins/evolution-workbench/README.md | 主页面 + 面板 + 快捷键 |
| Worker层 | frontend/src/workers/README.md | Web Worker + 数据解码 |

## P0 目标

做完后用户能：
- 启动后端+ 前端 → 浏览器看到侧边栏 + 进化工作台
- 选标的和周期 → 加载K 线图
- 画平行通道 / 趋势线 / 事件气泡 → 自动保存
- 右侧面板看标注列表 → 点击跳转
- 选中事件标注 → 显示 7 维特征
- 切换周期 → 标注跟随
- Ctrl+Z 撤销

P0 不做：实盘数据、引擎检测、进化优化、交易、AI、监控

## 施工顺序

### Step 1: 后端内核 → `backend/core/`
📖 详细说明：`backend/core/README.md`（底部"施工规范"章节）

按以下顺序创建 7 个文件：
1. `core/__init__.py`（空文件）
2. `core/types.py` — BackendPlugin 基类 + PluginContext
3. `core/storage.py` — JSON 持久化（原子写入）
4. `core/event_bus.py` — 事件总线
5. `core/api_registry.py` — 路由注册
6. `core/plugin_manager.py` — 插件自动发现 + 拓扑排序
7. `backend/main.py` — FastAPI 入口（lifespan）

✅ 验证：`python -m uvicorn backend.main:app --port 6100`
→ 启动无报错，零插件运行
→ GET http://localhost:6100/api/system/health → 200
→ GET http://localhost:6100/api/system/plugins → 空列表

### Step 2: datasource 插件 → `backend/plugins/datasource/`
📖 详细说明：`backend/plugins/datasource/README.md`
📋 插件配置：`backend/plugins/datasource/manifest.json`

创建 4 个文件：
1. `__init__.py`（空文件）
2. `plugin.py` — 实现 BackendPlugin
3. `local_loader.py` — Polars 读CSV/TSV →二进制
4. `routes.py` — 2 个 API 端点

✅ 验证：重启后端
→ GET /api/system/plugins → 包含 datasource
→ GET /api/datasource/symbols → 返回标的列表
→ GET /api/datasource/candles/ETHUSDT/1d → 返回二进制数据

### Step 3: annotation 插件 → `backend/plugins/annotation/`
📖 详细说明：`backend/plugins/annotation/README.md`
📋 插件配置：`backend/plugins/annotation/manifest.json`

创建 5 个文件：
1. `__init__.py`（空文件）
2. `plugin.py` — 实现 BackendPlugin
3. `drawing_store.py` — Drawing CRUD
4. `feature_extractor.py` — 7 维特征提取
5. `routes.py` — 5 个 API 端点

✅ 验证：重启后端
→ GET /api/system/plugins → 包含 datasource + annotation
→ POST /api/annotation/drawings/ETHUSDT → 创建成功
→ GET /api/annotation/drawings/ETHUSDT → 返回标注列表

### Step 4: 前端核心 → `frontend/src/core/`
📖 详细说明：`frontend/src/core/README.md`

11个文件：types.ts /PluginRegistry.ts / Sidebar.tsx / AppShell.tsx / appStore.ts / drawingStore.ts / api.ts / cache.ts / variables.css / main.tsx / App.tsx

✅ 验证：浏览器打开 → 看到侧边栏 + 空白内容区

### Step 5: 图表核心 → `frontend/src/shared/chart/`
📖 详细说明：`frontend/src/shared/chart/README.md`

6 个文件：parallelChannel.ts / callout.ts / phaseMarker.ts / chartUtils.ts / ChartWidget.tsx / DrawingToolbar.tsx

✅ 验证：K线图表显示 + 能画线/通道/气泡

### Step 6: 进化工作台 → `frontend/src/plugins/evolution-workbench/`
📖 详细说明：`frontend/src/plugins/evolution-workbench/README.md`

5 个文件：index.ts / EvolutionPage.tsx / AnnotationPanel.tsx / FeaturePanel.tsx / keyboard.ts

✅ 验证：完整标注工作流 + 19 条验收全部通过

### Step 7: Worker 性能层 → `frontend/src/workers/`
📖 详细说明：`frontend/src/workers/README.md`

2 个文件：dataWorker.ts / useDataWorker.ts（+ 修改 ChartWidget 接入Worker）

✅ 验证：大数据量 K线加载不卡顿

## 全局规范

- **端口**：6100（见 config.yaml）
- **Python日志**：用 `logging` 模块，不用 `print`
- **Python 头部**：统一 `from __future__ import annotations`
- **前端代理**：vite.config.ts 中 `/api` 代理到 `http://localhost:6100`

## 验收标准（19条）

| # | 功能 | 条件 |
|---|------|------|
| 1 | 启动 | 后端+前端启动 → 浏览器看到侧边栏+进化工作台 |
| 2 | K线 | 选ETHUSDT日线 → 图表显示K线+成交量 |
| 3 | 周期 | 切换5m/1H/4H/D → 图表更新 |
| 4 | 趋势线 | 画线 → 松开后保持|
| 5 | 通道 | 画平行通道 → 半透明填充 |
| 6 | 水平线 | 画水平线 → 延伸两端 |
| 7 | 气泡 | 画事件气泡 → 文字标记 |
| 8 |拖拽 | 点击标注 → 拖锚点 →跟随 |
| 9 | 删除 | 选中 → Del → 删除 |
| 10 | 撤销 | Ctrl+Z → 撤销 |
| 11 | 保存 | 画完 → 刷新 → 标注仍在 |
| 12 | 面板 | 右侧标注列表 → 点击跳转 |
| 13 | 特征 | 选中事件标注 → 显示7维特征 |
| 14 | 多周期 | 日线标注 → 切4H →仍可见 |
| 15 | 快捷键 | 数字键切工具、Esc回光标 |
| 16 | 插件栏 | 侧边栏图标 → 点击无报错 |
| 17 | 健康 | GET /api/system/health → 200 |
| 18 | 标的 | GET /api/datasource/symbols → 列表 |
| 19 | 保存API | POST /api/annotation/drawings/ETHUSDT → 成功 |

## 技术栈

### 后端
```
pip install fastapi uvicorn polars numpy aiosqlite pydantic-settings
```

### 前端
```
npm i klinecharts zustand zundo dexie
```

## 启动命令

```bash
# 后端（项目根目录）
python -m uvicorn backend.main:app --reload --port 6100

# 前端
cd frontend
npm run dev
```