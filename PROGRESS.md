# Meridian 开发进度

> 最后更新: 2026-04-08 21:20（修正版）

## 总览

| 模块 | 文件数 | 状态 |
|------|--------|------|
| Core（内核+main+config） | 10 | ✅审查通过 |
| datasource（数据源） | 5 | ✅ 审查通过 |
| annotation（标注） | 7 | ✅ 修复+审查通过 |
| engine（引擎+4检测器） | 16 | ✅ P2+路A+修复 审查通过 |
| evolution（进化） | 9 | ✅ 审查通过 |
| **后端合计** | **47** | **0CRITICAL · 全部通过** |
| 前端脚手架 | 已初始化 | ⏳ React+Vite+TS 骨架已存在 |

### 引擎检测器状态
- [x] base_detector.py — 检测器基类
- [x] bounce.py — AR/SOS/SOW 反弹检测
- [x] boundary_test.py — Spring/UTAD/ST-B 边界测试
- [x] extreme_event.py — SC/BC极端事件
- [ ] breakout.py — 突破确认（未实现）
- [ ] effort_result.py — 努力回报分析（未实现）
- [ ] narrow_range.py — 窄幅整理（未实现）
- [ ] trendline_break.py — 趋势线突破（未实现）
- [ ] volume_climax.py — 量能高潮（未实现）
- [ ] volume_dry.py — 量能枯竭（未实现）

---

## P0 — 核心框架 + 数据源 + 标注

### 后端核心 (backend/core/ + main.py + config.yaml)
- [x] config.yaml — 全局配置（端口6100）
- [x] types.py — BackendPlugin 基类 + PluginContext
- [x] storage.py — JSON 原子读写
- [x] event_bus.py — 事件总线
- [x] api_registry.py — 路由自动注册
- [x] plugin_manager.py — 插件自动发现 + manifest +拓扑排序
- [x] main.py — FastAPI 入口 + lifespan
- [x] README.md — 内核文档（13.96KB）

### 数据源插件 (backend/plugins/datasource/)
- [x] manifest.json
- [x] plugin.py — load_candles() + get_candles_df()
- [x] local_loader.py — CSV/TSV→Polars
- [x] routes.py

### 标注插件 (backend/plugins/annotation/)
- [x] manifest.json — dependencies: [datasource]
- [x] plugin.py
- [x] drawing_store.py — JSON CRUD + 重复ID检测
- [x] feature_extractor.py — 7维特征
- [x] routes.py — _build_event_payload + _try_auto_features
- [x] README.md

### P0 审查
- [x] 第1轮: 0C/7W/6I → 修复通过
- [x] 第4轮缝隙修复: import路径/symbol注入/特征自动提取 — 通过

---

## P2 — 引擎插件 (backend/plugins/engine/)

### 核心文件
- [x] models.py — 数据结构（5.88KB）
- [x] params.py — 进化参数（3.06KB）
- [x] range_engine.py — 区间引擎（12.89KB）+ _check_st + ST保护
- [x] event_engine.py — 事件引擎调度
- [x] rule_engine.py — 阶段转换路径图（6.48KB）
- [x] plugin.py — 3个事件订阅 + _on_annotation
- [x] routes.py — API路由
- [x] README.md — 引擎设计文档（37.64KB）
- [x] IMPLEMENTATION.md — 施工提示词（44.3KB）

### 检测器（4/10已实现）
- [x] base_detector.py + bounce.py + boundary_test.py + extreme_event.py
- [ ] 6个检测器未实现（breakout/effort_result/narrow_range/trendline_break/volume_climax/volume_dry）

### 路A — 引擎串联
- [x] SC→AR→ST→create_range→boundary_test 全链路通
- [x] CRITICAL修复: ST死代码（缩进修复）

### 审查
- [x] 第2轮: 0C/7W → 修复通过
- [x] 第3轮路A: 0C/1W/4I
- [x] 第4轮CRITICAL修复 — 通过

---

##进化插件 (backend/plugins/evolution/)

- [x] case_store.py — SQLite三表 + CRUD（14.76KB）
- [x] case_builder.py — annotation→EventCase（7.60KB）
- [x] optimizer.py — 百分位数 + 负样本排除（6.77KB）
- [x] params_manager.py — 版本化存储 + 回滚（4.14KB）
- [x] plugin.py — 5个事件订阅 + run_optimization（12.35KB）
- [x] routes.py — 12个API端点（5.14KB）
- [x] manifest.json — publishes/subscribes声明
- [x] README.md — 设计文档（18.34KB）

### 审查
- [x] 第5轮: 0C/0W/3I

---

## 前端 (frontend/)

### 已存在
- [x] package.json — React + Vite + TypeScript
- [x] vite.config.ts — Vite配置
- [x] tsconfig.json — TypeScript配置
- [x] src/ — 源码目录（内容待确认）
- [x] index.html — 入口

### 待实现
- [ ] App Shell + 路由 + 侧边栏
- [ ] KLineChart 集成 + K线展示
- [ ] 画图工具（平行通道/callout/阶段标记）
- [ ] annotation API 对接
- [ ] 引擎状态面板
- [ ] 进化工作台面板

---

## 项目文档体系

| 文档 | 位置 | 大小 |
|------|------|------|
| SYSTEM_DESIGN_V3.md | docs/ | 62.73KB |
| MERIDIAN_ARCHITECTURE.md | docs/ | 42.95KB |
| IMPLEMENTATION_PROMPT.md | docs/ | 39.46KB |
| WORKBENCH_DESIGN.md | docs/ | 22.94KB |
| engine/README.md | plugins/engine/ | 37.64KB |
| engine/IMPLEMENTATION.md | plugins/engine/ | 44.3KB |
| evolution/README.md | plugins/evolution/ | 18.34KB |
| core/README.md | backend/core/ | 13.96KB |
| CONSTRUCTION.md | 根目录 | 6.33KB |
| AGENTS.md | 根目录 | 7.45KB |
| README.md | 根目录 | 4.05KB |
| PROGRESS.md | 根目录 | 本文件 |

## 设计决策索引

| 系列 | 数量 | 来源 |
|------|------|------|
| RD-55~59 | 5 | V3理论讨论 |
| MD-1~10 | 10 | Meridian架构 |
| CD-1~4 | 4 | Core施工 |
| WD-1~13 | 13 | 标注工作台 |
| ED-1~11 | 11 | 引擎设计 |
| EVD-1~9 | 9 | 进化设计 |
| **合计** | **52** | |

---

## 下一步

- [ ] **前端开发** — 基于已有脚手架继续
- [ ] 引擎检测器补全（6个）
- [ ] 实盘监控插件（P2）
- [ ] AI分析师插件（P3）
- [ ] 回测引擎插件（P3）
- [ ] 交易日志插件（P3）