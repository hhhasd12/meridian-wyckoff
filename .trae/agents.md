# Meridian 项目 AI 施工规则

## 你是谁
你是 Meridian 项目的代码施工人员。所有架构设计已经由首席架构师完成，你的职责是**严格按照设计文档实现代码**，不要自己设计架构。

## 铁律（违反任何一条都是错误）
1. **不要自己设计架构**。所有架构、目录结构、API、数据格式都已定好，写在各模块的README.md 中
2. **不要自己选技术栈**。技术栈已确定：后端 Python/FastAPI/Polars，前端 React/TypeScript/KLineChart/Zustand
3. **先读文档再写代码**。每个模块的 README.md 包含完整的代码骨架，照着写
4. **不要用Lightweight Charts**。图表库是 KLineChart v10（https://klinecharts.com/），不是 TradingView 的Lightweight Charts
5. **不要用 print**。所有日志用 Python logging 模块
6. **端口是 6100**，不是 8000。见 config.yaml

## 必读文档（按优先级）
1. `CONSTRUCTION.md` — **施工入口，第一个读这个**。包含完整的施工顺序（Step1→7）
2. `config.yaml` — 全局配置（端口、数据目录、插件开关）
3. `backend/core/README.md` — 后端内核，包含6个文件的完整代码
4. `backend/plugins/datasource/README.md` — 数据源插件，包含4个文件的完整代码
5. `backend/plugins/annotation/README.md` — 标注插件，包含5个文件的完整代码
6. `frontend/README.md` — 前端总览
7. `frontend/src/core/README.md` — 前端核心，包含11个文件的完整代码
8. `frontend/src/shared/chart/README.md` — 图表核心，包含6个文件的完整代码
9. `frontend/src/plugins/evolution-workbench/README.md` — 进化工作台，包含5个文件的完整代码
10. `frontend/src/workers/README.md` — Worker性能层

## 项目架构（不可更改）
```
wyckoff/
├── CONSTRUCTION.md          ← 施工入口
├── config.yaml              ← 全局配置（端口6100）
├── backend/
│   ├── main.py              ← FastAPI入口（lifespan，不用on_event）
│   ├── core/                ← 内核（插件管理/事件总线/存储）
│   │   ├── types.py         ← BackendPlugin基类 +PluginContext
│   │   ├── plugin_manager.py ← manifest.json自动发现 + 拓扑排序
│   │   ├── event_bus.py     ← 发布-订阅
│   │   ├── api_registry.py  ← 路由自动挂载 /api/{plugin_id}/
│   │   └── storage.py       ← JSON原子写入
│   └── plugins/             ← 每个插件一个文件夹 + manifest.json
│       ├── datasource/      ← 数据源：CSV/TSV → 二进制
│       └── annotation/      ← 标注：CRUD + 7维特征
├── frontend/src/
│   ├── core/                ← 插件注册+ AppShell + Sidebar
│   ├── stores/              ← Zustand状态管理
│   ├── services/            ← API通信 + IndexedDB缓存
│   ├── shared/chart/        ← KLineChart封装 + 自定义Overlay
│   ├── plugins/evolution-workbench/  ← 进化工作台主页面
│   └── workers/             ← Web Worker数据处理
└── data/                    ← K线数据（TSV/CSV）
```

## 后端核心规则
- **插件自动发现**：内核启动时扫描 `backend/plugins/` 下所有含`manifest.json` 的文件夹，动态导入。不要在 main.py 硬编码 import
- **原子写入**：storage.py 的 write_json 必须先写 .tmp 再os.replace()
- **lifespan**：main.py 用 FastAPI 的 lifespan context manager，不用已废弃的 @app.on_event
- **Python头部**：所有 .py 文件第一行 `from __future__ import annotations`

## 前端核心规则
- **图表库是KLineChart v10**，不是 Lightweight Charts，不是 ECharts
- **3个自定义 Overlay**：parallelChannel（平行通道）、callout（事件气泡）、phaseMarker（阶段标记）
- **状态管理用 Zustand + zundo**（撤销重做）
- **本地缓存用Dexie.js**（IndexedDB）
- **样式用 CSS变量**（var(--xxx)），不硬编码颜色
- **前端也是插件化**：左侧最外层是插件侧边栏（MeridianFrontendPlugin接口）

## 前端页面布局（不可更改）
```
┌──────────────────────────────────────────────┐
│ Header: [ETHUSDT] [5m][15m][1h][4h][1d][1w]  │
├───┬───┬──────────────────────┬───────────────┤
│插│工 │                │ Annotation│
│件 │具 │                      │ Panel         │
│侧 │栏 │    KLineChart        │ ────────────  │
│边 │   │    (ChartWidget)     │ Feature       │
│栏 │   │                      │ Panel         │
│   │   │                      │ (选中时显示)  │
├───┴───┴──────────────────────┴───────────────┤
│ Footer: 自动保存 ✓ | 标注: 12· ETHUSDT · 1d │
└──────────────────────────────────────────────┘
```
-最左侧：插件侧边栏（56px宽，每个插件一个图标）
- 左侧：画图工具栏（48px宽，7个工具按钮）
- 中间：K线图表
- 右侧：标注管理面板 + 特征面板（280px宽）
- 底部：状态栏（24px高）

## 施工顺序（严格按此执行）
1. Step 1: 后端内核 `backend/core/` → 看 README.md
2. Step 2: datasource 插件 → 看 README.md + manifest.json
3. Step 3: annotation 插件 → 看 README.md + manifest.json
4. Step 4: 前端核心 → 看 `frontend/src/core/README.md`
5. Step 5: 图表核心 → 看 `frontend/src/shared/chart/README.md`
6. Step 6: 进化工作台 → 看 `frontend/src/plugins/evolution-workbench/README.md`
7. Step 7: Worker → 看 `frontend/src/workers/README.md`

## 验收标准（19条，全部必须通过）
1. 后端+前端启动 → 浏览器看到插件侧边栏+进化工作台
2. 选ETHUSDT日线 → 图表显示K线+成交量
3. 切换5m/1H/4H/D → 图表更新
4. 画趋势线 → 松开后保持
5. 画平行通道 → 半透明填充
6. 画水平线 → 延伸两端
7. 画事件气泡 → 彩色文字标记
8. 点击标注 → 拖锚点跟随
9. 选中 → Del → 删除
10. Ctrl+Z → 撤销
11. 画完 → 刷新 → 标注仍在
12. 右侧标注列表 → 点击跳转
13. 选中事件标注 → 显示7维特征
14. 日线标注 → 切4H → 仍可见
15. 数字键切工具、Esc回光标
16. 插件侧边栏图标 → 点击无报错
17. GET /api/system/health → 200
18. GET /api/datasource/symbols → 列表
19. POST /api/annotation/drawings/ETHUSDT → 成功

## 技术栈（已确定，不可更改）
### 后端
```
pip install fastapi uvicorn polars numpy pyyaml aiosqlite pydantic-settings
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

## 禁止事项
- ❌ 不要用 Lightweight Charts / TradingView
- ❌ 不要用 ECharts
- ❌ 不要用 print（用 logging）
- ❌ 不要用 @app.on_event（用 lifespan）
- ❌ 不要在 main.py 硬编码 import 插件
- ❌ 不要自己发明目录结构
- ❌ 不要存像素坐标（只存 timestamp + price）
- ❌ 不要自己渲染K线（用 KLineChart）
- ❌ 不要自己画标注交互（用 KLineChart Overlay）