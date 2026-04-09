# Meridian 开发路线图

> 最后更新: 2026-04-09
> 决策者: WyckoffInspector (首席架构师)

## 当前状态

### 后端 (47文件, 0CRITICAL, 全部审查通过)
| 模块 | 文件数 | 状态 |
|------|--------|------|
| Core内核 | 7 | ✅ 审查通过 |
| datasource数据源 | 5 | ✅ 审查通过 |
| annotation标注 | 7 | ✅ 审查通过 |
| engine引擎 | 16 | ✅ 审查通过 (5/10检测器) |
| evolution进化 | 9 | ✅ 审查通过 |

### 前端 (~27文件, 0 CRITICAL)
-✅ 进化工作台基本可用 (K线+画图+保存+加载)
- ⚠️ callout刷新后显示为竖虚线 (样式问题)
- ⚠️ 事件类型不够用 (14个)
- ⚠️ phaseMarker是单点不是范围

### V3理论实现覆盖度
| V3章节 | 实现状态 | 说明 |
|--------|----------|------|
| §1-2 理论框架 | ✅ 100% | 数据结构+枚举+阶段转换全部实现 |
| §3三引擎架构 | ✅ 100% | 三引擎+插件化|
| §5.2 区间引擎 | ✅ 核心 | seek_candidate+check_st+create_range |
| §5.3 事件引擎 | ⚠️ 50% | 5/10检测器 |
| §5.4 规则引擎 | ✅ 100% | 阶段转换路径图|
| §6 事件全表| ⚠️ 50% | 模板1/2/3/4已实现 |
| §7 回测流水线 | ❌ 0% | 未开始 |
| §8 记忆层 | ✅ 变体 | SQLite+JSON |
| §9 进化方案 | ✅ 100% | 统计优化+百分位数+参数版本化 |
| §5.5 决策层 | ❌ 0% | V3: "识别层完成后再开发" |

###缺失的5个检测器
| 检测器 | V3模板 | 优先级 | 原因 |
|--------|--------|--------|------|
| narrow_range.py | 模板6 (供需确认) | 中 | SOS/SOW确认 |
| effort_result.py | 辅助 | 低 | 努力回报分析 |
| volume_climax.py | 辅助 | 低 | 量能高潮 |
| volume_dry.py | 辅助 | 低 | 量能枯竭 |
| trendline_break.py | 辅助 | 低 | 趋势线突破 |

---

## 路线图

### Phase 1: 前端迭代 — 让标注工具好用 [当前]

**目标**:莱恩能流畅地标注威科夫事件
**优先级**: 最高 — 没有标注就没有进化数据
**预计**: 2-3天

#### P0(必须修)
1. **callout事件气泡修复** —刷新后显示为竖虚线, extendData的text/color未正确传递
   - 文件: `frontend/src/shared/chart/overlays/callout.ts`
2. **事件类型补全** — 从14个扩充到30+
   - 文件: `frontend/src/plugins/evolution-workbench/config/wyckoffEvents.ts`
   - 新增: Creek, Ice, UT, TR, Volume Climax, Volume Dry-up, Markup, Markdown, 自定义文字等
3. **phaseMarker改双点** — 两条垂直虚线+顶部标签+半透明底色, 标记阶段起止范围
   - 文件: `frontend/src/shared/chart/overlays/phaseMarker.ts`

#### P1 (体验改进)
4. **sync drawings增量更新** — 消除全量重建导致的闪烁
   - 文件: `frontend/src/shared/chart/ChartWidget.tsx`
5. **Symbol选择器** — 从后端 `/api/datasource/symbols` 获取可用标的
   - 文件: `frontend/src/plugins/evolution-workbench/EvolutionPage.tsx`
6. **IndexedDB缓存接入** — cache.ts已实现但未调用
   - 文件: `frontend/src/services/cache.ts` + `ChartWidget.tsx`
7. **api.ts补充端点** — engine/evolution共12个端点
   - 文件: `frontend/src/services/api.ts`

**施工方式**:莱恩将施工指南交给代码agent, WyckoffInspector审查

---

### Phase 2: 后端补全 — 关键检测器 + 回测

**目标**: 识别层能完整运行A→B→C→D→E全路径
**预计**: 3-5天

1. ~~**breakout.py**~~ — ✅ 已完成 (703行, 状态机完整+三级边界退回)
2. **narrow_range.py** — SOS/SOW供需确认 (V3模板6)
   - 方向移动→弱反向运动→窄幅横盘
3. **回测流水线** — V3 §7的实现
   - 逐根K线处理, 输出BacktestResult
   - 跑ETH日线数据, 输出事件序列+区间+阶段转换

**施工方式**: WyckoffInspector写设计文档 → 代码agent施工 → 审查

---

### Phase 3: 莱恩标注 + 进化闭环验证

**目标**: 验证 标注→EventCase→案例库→优化 闭环
**这是整个系统的关键验证点。**

1. 莱恩开始标注 (ETH日线, 从最明确的结构开始)
2. 验证annotation→evolution管线(annotation.created→case_builder→case_store)
3. 验证optimizer百分位数优化
4. 验证参数热加载 (evolution.params_updated→engine重载)
5. 第一轮进化: 对比优化前后的引擎候选质量

---

### Phase 4: 剩余检测器 + 决策层

**目标**: V3识别层完整+ 决策层初版

1. effort_result.py — 努力回报分析
2. volume_climax.py + volume_dry.py — 量能分析
3. trendline_break.py — 趋势线突破
4. 渐进供需检测器 (mSOS/mSOW, V3模板5)
5. 回踩确认检测器 (MSOS/MSOW, V3模板7)
6. StrategyEngine初版 (V3 §5.5)
7. MTF协调器 (V3 §3.3)

---

### Phase 5: 实盘 + 5个前端插件

**目标**: 全自动交易系统

####前端插件 (全部遵循MD-2/MD-4插件化)
| 插件 | 后端依赖 | 功能 |
|------|----------|------|
| 📡 实盘监控 | engine + trading | Binance WS + 实时K线 + 引擎状态 |
| 🤖 AI分析师 | ai | OpenAI兼容API + 结构化分析 |
| 🖥️ 后端监控 | 系统端点 | 系统健康 + 插件状态 |
| 📊 回测引擎 | evolution.backtester | 回测参数配置 + 结果可视化 |
| 📋 交易日志 | trading.history | 交易记录 +绩效分析 |

#### 后端插件
| 插件 | 功能 |
|------|------|
| trading | Binance交易执行 +仓位管理 |
| ai | OpenAI兼容API接口 |
| backtester | 回测引擎 |

---

## 设计决策体系索引

| 系列 | 数量 | 来源 | 文档位置 |
|------|------|------|----------|
| RD-1~59 | 59 | V3理论讨论 | docs/SYSTEM_DESIGN_V3.md |
| MD-1~10 | 10 | Meridian架构 | docs/MERIDIAN_ARCHITECTURE.md |
| CD-1~4 | 4 | Core施工 | backend/core/README.md |
| WD-1~13 | 13 | 标注工作台 | docs/WORKBENCH_DESIGN.md |
| ED-1~11 | 11 | 引擎设计 | backend/plugins/engine/README.md |
| EVD-1~9 | 9 | 进化设计 | backend/plugins/evolution/README.md |
| TD-1~10 | 10 | 技术栈 | 设计库日记 |
| **合计** | **116** | | |

---

## 核心原则

1. **标注优先**: 没有标注 → 没有进化数据 → 一切后续都是空转
2. **引擎是学习框架**: 智慧来自莱恩标注, 不来自预设规则 (ED-1)
3. **识别层先于决策层**: 先把市场状态识别做对(RD-17)
4. **插件化一切**: 前后端都插件化, 第三方可扩展 (MD-2)
5. **一次性做对架构**: 后续只迭代细节不迭代架构 (莱恩指示)