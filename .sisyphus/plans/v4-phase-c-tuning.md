# V4 Phase C — 检测器调优 + 分析页性能优化

> 状态：Wave 1+2+3 全部完成（2026-03-23）
> 前置：Phase A+B 已完成（API暴露V4数据 + 前端PrinciplesPanel）
> 诊断来源：2026-03-23 会话，5个串联瓶颈确认

## 诊断总结

450+ 根 H4 K线只有 2 次状态变化，根因是 5 个串联瓶颈：

1. **CONFIRMATION_THRESHOLD=2.0 硬编码默认值**（不在 StateConfig 中）→ 数学上不可能确认
2. **position_in_tr 在无TR数据时钳位到 1.0** → TR底部检测器全部失效
3. **STATE_MIN_CONFIDENCE=0.35** vs 检测器离散评分 → 边界卡死
4. **证据链串联依赖** → SC不确认则后续全部阻断
5. **StructureContext 硬编码默认值** → 检测器拿不到有意义上下文

## Wave 1: P0 修复（检测器能产出合理状态转换）

### Task 1.1: StateConfig 补全缺失参数
- **文件**: `src/kernel/types.py` StateConfig 类
- **做什么**: 加入 CONFIRMATION_THRESHOLD=0.8, MAX_HYPOTHESIS_BARS=25
- **为什么**: 这两个参数目前是 state_machine_v4.py 里 getattr 的硬编码默认值(2.0/15)，不可配置不可进化
- **验证**: grep 确认 state_machine_v4.py 的 getattr 能正确读到新值

### Task 1.2: 修复 position_in_tr 退化行为
- **文件**: `src/plugins/wyckoff_state_machine/state_machine_v4.py` _build_structure_context()
- **做什么**: 当 tr_support=0 且 tr_resistance=0 时，position_in_tr 返回 0.5（中性），不要用 close/1.0
- **当前问题**: ETH $200-300 / 1.0 = 200+ → clamp(1.0)，让 ST/SPRING/SO/LPS 检测器永远不触发
- **验证**: 打印几根K线的 position_in_tr 值确认在 0~1 合理范围

### Task 1.3: 降低 STATE_MIN_CONFIDENCE
- **文件**: `src/kernel/types.py` StateConfig
- **做什么**: STATE_MIN_CONFIDENCE 0.35 → 0.25
- **理由**: PS检测器在普通阳线上只得0.3，差0.05过不了门槛。0.25让单条件也能触发假设
- **注意**: 这个值是可进化参数，后续进化系统会自动调优

### Task 1.4: _calc_confirmation_quality 增量调整
- **文件**: `src/plugins/wyckoff_state_machine/state_machine_v4.py`
- **做什么**: 审查 _calc_confirmation_quality 的增量设计，确保单根K线最大增量和阈值匹配
- **当前**: 单根最大0.8，阈值0.8（改后），约1-2根完美K线可确认
- **验证**: 确认典型K线增量在0.3-0.5范围，3-5根K线可确认

### Task 1.5: 运行分析验证
- **做什么**: 启动API，跑分析，确认状态变化次数从2次增加到合理范围（50-200次/2000根）
- **工具**: 前端状态分析页 或 直接 curl POST /api/analyze
- **成功标准**: 能看到 PS→SC→AR→ST 等连续事件序列

## Wave 2: P1 性能优化（分析页体验提升）

### Task 2.1: 前端渲染分离（K线先出，分析后叠加）
- **文件**: `frontend/src/components/AnalysisPage.tsx`
- **做什么**: 
  - 进入分析页自动触发分析（移除手动点击）
  - K线数据先从 analyze 响应的 candles 渲染（或拆为两步请求）
  - 分析overlay异步叠加，加loading状态
- **用户感知**: 图表 <200ms 出现，分析数据 2-3秒后叠加

### Task 2.2: 后端 run_in_executor
- **文件**: `src/api/app.py` analyze_state_machine()
- **做什么**: 把同步CPU密集计算放到线程池，不阻塞FastAPI事件循环
- **改动**: asyncio.get_event_loop().run_in_executor(None, _sync_analyze, ...)

### Task 2.3: 数据切片优化
- **文件**: `src/api/app.py` analyze_state_machine()
- **做什么**: 预计算所有TF的时间对齐映射（向量化 searchsorted），从 10000次 → 5次
- **收益**: 全量计算从 ~3秒 → ~1.5秒

### Task 2.4: 分析结果缓存
- **文件**: `src/api/app.py` 新增 AnalysisCache 类
- **做什么**: 用CSV最后一根K线时间戳做缓存key，数据不变就不重算
- **收益**: 第二次打开分析页 <10ms

## Wave 3: P2 StructureContext 充实（提高检测精度）

### Task 3.1: 从引擎上下文填充 StructureContext
- **文件**: `src/plugins/wyckoff_state_machine/state_machine_v4.py` _build_structure_context()
- **做什么**: 
  - test_quality: 从历史支撑/阻力测试次数计算
  - recovery_speed: 从K线收盘到SC_LOW的距离变化率计算
  - swing_context: 从近期高低点序列判断 "higher_lows"/"lower_highs"/"sideways"
  - direction_bias: 从多TF共振方向计算
- **当前**: 全部硬编码 0.5/"unknown"/0.0

### Task 3.2: 扩大 IDLE 入口
- **文件**: `src/plugins/wyckoff_state_machine/transition_guard.py`
- **做什么**: 考虑给 IDLE 加 UPTREND/DOWNTREND 直接入口
- **注意**: 需要谨慎评估，可能引入误报

## 数据参考

CSV 数据量：
- M5: 900613 行
- M15: 300212 行  
- H1: 75067 行
- H4: 18784 行（约 8 年数据）
- D1: 3135 行

关键文件清单：
- `src/kernel/types.py` — StateConfig 定义
- `src/plugins/wyckoff_state_machine/state_machine_v4.py` — V4 状态机核心
- `src/plugins/wyckoff_state_machine/transition_guard.py` — 转换守卫
- `src/plugins/wyckoff_state_machine/detector_registry.py` — 检测器注册表
- `src/plugins/wyckoff_state_machine/detectors/accumulation.py` — 吸筹检测器(13个)
- `src/plugins/wyckoff_state_machine/detectors/distribution.py` — 派发检测器(9个)
- `src/plugins/wyckoff_state_machine/principles/bar_features.py` — 三大原则打分器
- `src/api/app.py` — /api/analyze 端点
- `frontend/src/components/AnalysisPage.tsx` — 分析页面

## 验证工具

```bash
# 冒烟测试
pytest tests/test_smoke.py -q

# V4 状态机测试
pytest tests/plugins/test_state_machine_v4.py tests/plugins/test_principles.py tests/plugins/test_detectors_v4.py -q

# 前端构建
cd frontend && npx vite build
```
