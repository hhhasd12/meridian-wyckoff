# Meridian 前端 — 施工指南

## 技术栈
- React 18 + TypeScript 5 + Vite
- KLineChart v10（K线图表+ 内置画图工具）
- Zustand + zundo（状态管理 + 撤销重做）
- Dexie.js（IndexedDB 本地缓存）
- Web Worker + SharedArrayBuffer（重计算卸载到后台线程）

## 目录结构
```
frontend/src/
├── main.tsx                — 入口
├── App.tsx                           — 注册插件 +挂载 AppShell
├── core/                             — 前端内核
│   ├── types.ts                      — MeridianFrontendPlugin 接口
│   ├── PluginRegistry.ts             — 插件注册表
│   ├── AppShell.tsx                  — 主布局（侧边栏 + 内容区）
│   └── Sidebar.tsx                   — 侧边栏导航
├── stores/                           — 全局状态
│   ├── appStore.ts                   — symbol / timeframe / theme
│   └── drawingStore.ts               — drawings +undo/redo
├── services/                         — 后端通信 + 缓存
│   ├── api.ts                        — REST API 封装
│   └── cache.ts                      — IndexedDB 缓存（Dexie）
├── workers/                          — Web Worker
│   ├── dataWorker.ts                 — 二进制解码+ 数据处理
│   └── computeWorker.ts              — 特征计算 + 坐标转换
├── shared/chart/                     — 共享图表组件
│   ├── ChartWidget.tsx               — KLineChart 封装
│   ├── DrawingToolbar.tsx            — 画图工具栏
│   ├── chartUtils.ts                 — Drawing↔ Overlay 映射
│   └── overlays/                     — 自定义 Overlay
│       ├── parallelChannel.ts        — 平行通道
│       ├── callout.ts                — 事件气泡
│       └── phaseMarker.ts            — 阶段标记
├── plugins/evolution-workbench/      — 进化工作台插件
│   ├── index.ts                      — 插件注册
│   ├── EvolutionPage.tsx             — 主页面
│   └── panels/
│       ├── AnnotationPanel.tsx       — 标注管理面板
│       └── FeaturePanel.tsx          — 特征展示面板
├── themes/
│   └── variables.css                 — CSS变量（暗色主题）
└── utils/
    └── keyboard.ts                   — 快捷键系统
```

## 施工顺序

### Step 1: 前端核心
→ 看 `src/core/README.md`
- types.ts / PluginRegistry.ts / AppShell.tsx / Sidebar.tsx
- stores/ (appStore + drawingStore)
- services/ (api.ts + cache.ts)
- themes/variables.css + main.tsx + App.tsx
- ✅ 验证：浏览器看到侧边栏 + 空白内容区

### Step 2:图表核心
→ 看 `src/shared/chart/README.md`
- ChartWidget.tsx（KLineChart 封装）
- 3个自定义 Overlay（parallelChannel / callout / phaseMarker）
- chartUtils.ts（Drawing ↔ Overlay 双向映射）
- DrawingToolbar.tsx
- ✅ 验证：K线图表显示 + 能画线

### Step 3: 进化工作台
→ 看 `src/plugins/evolution-workbench/README.md`
- EvolutionPage.tsx（主页面布局）
- AnnotationPanel.tsx（标注列表 + 点击跳转）
- FeaturePanel.tsx（7维特征展示）
- 快捷键系统
- ✅ 验证：完整的标注工作流

### Step 4: 性能层
→ 看 `src/workers/README.md`
- Web Worker（二进制解码 + 数据处理移出主线程）
- SharedArrayBuffer（K线数据零拷贝共享）
- ✅ 验证：大数据量不卡顿

## 全局规范
- 所有组件用函数组件+ Hooks
- 状态管理统一用 Zustand，不用 useState管跨组件状态
- 样式用 CSS 变量（var(--xxx)），不硬编码颜色
- 后端 API 代理：vite.config.ts 中 `/api` → `http://localhost:6100`
- KLineChart 文档：https://klinecharts.com/