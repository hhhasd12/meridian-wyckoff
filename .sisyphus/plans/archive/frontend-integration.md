# 前后端集成修复计划

> **目标**: 前端从纯只读监控升级为完整控制台——可控进化、实时推送、所有Tab有数据
> **前提**: 953 tests, 前端80%完成(2个Shell+1个Bug), 后端5个REST+1个WS
> **预估**: 15个Gap, 4个Wave

---

## Gap 总览

| # | 类别 | Gap描述 | 复杂度 | Wave |
|---|------|---------|--------|------|
| 7 | 数据格式 | get_current_state()返回不匹配前端WyckoffStateResult类型 | Large | 1 |
| 8 | 数据流 | FvgZones图表插件已挂载但useOverlays从未调用setFvgSignals | Medium | 1 |
| 1 | API | 缺POST进化start/stop端点 | Small | 2 |
| 9 | UI | EvolutionTab缺Start/Stop按钮 | Small | 2 |
| 13 | 前端 | api.ts缺6个API调用函数 | Small | 2 |
| 6 | 架构 | EventBus未桥接到WebSocket(2s轮询而非事件推送) | Large | 2 |
| 5 | WS | 缺signals/advisor/logs/trades主题 | Medium | 2 |
| 14 | 前端 | App.tsx WS消息处理缺4个type分发 | Small | 2 |
| 4 | 后端 | 缺日志推送机制(logging→WS) | Medium | 3 |
| 12 | 数据流 | LogsTab有UI但store.logs从未写入 | Medium | 3 |
| 10 | 数据流 | TradesTab硬编码空数组 | Medium | 3 |
| 3 | API | 缺GET /api/trades交易历史端点 | Medium | 3 |
| 11 | 数据流 | AdvisorTab纯静态文本 | Medium | 3 |
| 2 | API | 缺GET /api/advisor/*端点 | Small | 3 |
| 15 | 配置 | POST /api/config只改内存,无验证/广播/GET | Medium | 4 |

---

## Wave 1: 数据格式修复（前端能正确显示数据）

### Task 1: 重写get_current_state()匹配前端类型
**文件**: `src/plugins/wyckoff_engine/plugin.py` L49-71
**问题**: 返回`{timeframes, state_machines, ...}`,前端期望`{current_state, phase, direction, confidence, signal, critical_levels, ...}`
**修改**:
- 从engine的多TF状态机中聚合:取主TF(H4)的当前state/phase/direction
- 构建critical_levels从state_machine的key_price_tracker
- 包含fvg_signals从engine的perception结果
- 返回格式严格匹配`frontend/src/types/api.ts` L50-63 WyckoffStateResult
**验收**: WyckoffPanel显示真实phase/direction/confidence

### Task 2: 连接FvgZones到useOverlays
**文件**: `frontend/src/hooks/useOverlays.ts` L63-69
**修改**:
- L69后添加: `fvgRef.current?.setFvgSignals(wyckoff.fvg_signals ?? [])`
- 在`frontend/src/types/api.ts`的WyckoffStateResult中添加`fvg_signals: FVGSignal[]`
**验收**: 图表上能看到FVG区域渲染

---

## Wave 2: 进化控制+实时推送

### Task 3: 后端添加进化控制API
**文件**: `src/api/app.py`
**新增**:
- `POST /api/evolution/start` → 调用evolution_plugin.start_evolution()
- `POST /api/evolution/stop` → 调用evolution_plugin.stop_evolution()
- `GET /api/evolution/status` → 调用evolution_plugin.get_evolution_status()
**验收**: curl POST能触发进化启停

### Task 4: 前端api.ts添加6个缺失函数
**文件**: `frontend/src/core/api.ts`
**新增**: startEvolution(), stopEvolution(), fetchEvolutionStatus(), fetchTrades(), fetchAdvisorLatest(), fetchAdvisorHistory()
**验收**: TypeScript编译通过，函数可调用

### Task 5: EvolutionTab添加控制按钮
**文件**: `frontend/src/components/EvolutionTab.tsx`
**修改**: StatusBar区域添加Start/Stop按钮，调用api.startEvolution()/stopEvolution()
**验收**: 点击按钮能触发后端进化启停

### Task 6: EventBus桥接到WebSocket(事件驱动推送)
**文件**: `src/api/app.py`
**修改**:
- API lifespan启动时订阅EventBus关键事件:
  - `trading.signal` → 广播给所有WS客户端
  - `evolution.cycle_complete` → 广播进化结果
  - `position.opened/closed` → 广播持仓变化
  - `advisor.analysis_complete` → 广播AI分析
- 新建`_broadcast_to_clients(msg)`工具函数
- 保留2s轮询作为fallback，事件驱动作为主推送
**验收**: 进化完成时前端0延迟收到通知（不等2s/30s）

### Task 7: WS添加新主题+App.tsx消息分发
**文件**: `src/api/app.py` L502-508, `frontend/src/App.tsx` L72-93
**修改**:
- 后端valid主题集合添加: signals, advisor, logs, trades
- 后端_collect_topic_data()添加4个新主题数据收集
- 前端App.tsx WS消息switch添加: trading_signal→addSignal, advisor_analysis→setAdvisorAnalysis, log_entry→addLog, trade_closed→addTrade
**验收**: 所有主题数据能从后端推到前端store

---

## Wave 3: 填充所有Placeholder

### Task 8: 日志推送机制
**文件**: 新建`src/api/log_bridge.py`, 修改`src/api/app.py`
**修改**:
- 创建`WsBroadcastHandler(logging.Handler)`类,缓存最近100条日志
- API启动时添加到root logger
- WS logs主题从handler读取新日志
**验收**: LogsTab实时显示系统日志

### Task 9: TradesTab对接交易历史
**文件**: `src/api/app.py`, `frontend/src/components/TradesTab.tsx`
**修改**:
- 后端: `GET /api/trades` 从position_manager读取已关闭仓位
- 前端: TradesTab从store读取trades数据（替换DEMO_TRADES空数组）
- store.ts添加trades状态+addTrade action
**验收**: TradesTab显示真实交易记录

### Task 10: AdvisorTab对接AI顾问
**文件**: `src/api/app.py`, `frontend/src/components/AdvisorTab.tsx`
**修改**:
- 后端: `GET /api/advisor/latest` + `GET /api/advisor/history`
  调用evolution_advisor插件的get_last_analysis()/get_analysis_history()
- 前端: 重构AdvisorTab展示分析结果、策略建议、错误模式
- types/api.ts添加AdvisorAnalysis接口
**验收**: AdvisorTab显示AI分析结果（无AI配置时显示"未配置"而非空白）

---

## Wave 4: 配置完善

### Task 11: 配置热重载增强
**文件**: `src/api/app.py` L261-281
**修改**:
- 新增`GET /api/config` — 返回当前完整配置
- POST添加配置验证(类型检查,范围检查)
- 配置更新后通过EventBus广播`config.updated`事件
- 可选: 配置更新后持久化到config.yaml
**验收**: 前端能查看+修改配置，修改后全系统生效

---

## 验证标准

```bash
# 后端
pytest tests/ -v  # ≥ 953 passed
python run.py --mode=api  # API启动成功

# 前端
cd frontend && npx tsc --noEmit  # 0 errors
cd frontend && npx vite build    # build成功

# 集成
# 1. 启动API模式 → 启动前端 → 浏览器打开
# 2. WyckoffPanel显示phase/direction（非空）
# 3. 图表显示FVG区域
# 4. EvolutionTab有Start/Stop按钮
# 5. 点击Start → 后端开始进化 → 前端实时看到结果
# 6. LogsTab显示系统日志
```
