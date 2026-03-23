# 威科夫引擎 v3.0 — 全面清理与完工计划

> 目标：清除全部死代码（5,698行）、修复代码质量问题、完成前端数据集成、审计进化系统、归零技术债
> 创建：2026-03-21
> 状态：待执行

## 基线

- 测试：1189 passed, 0 failed
- 平台：Windows (Python 3.11, Node 18+)
- 最低测试要求：≥ 1182 passed（删除 numba 测试文件后允许减少对应数量）
- 代码库：18 个插件、22 个前端文件、530 行 API

## 工作目标

### Must Have
- 删除 8 个死代码文件 + 1 个死测试文件（共 ~5,700 行）
- 修复 `make_ohlcv()` 生成无效 OHLC 数据的 bug（消除 571 个 UserWarning）
- 为 4 个 `except Exception: pass` 添加日志（dashboard/engine/position_manager）
- 为 ~13 个 `except Exception:` 静默回退块添加日志
- 前端静态文件通过 FastAPI 服务（`/` 指向 `frontend/dist/`）
- TradesTab/SignalPanel/LogsTab 接入真实数据（WebSocket/REST）
- AdvisorTab 接入真实 advisor 数据
- 进化系统过拟合 7 根因审计（对照新代码判定哪些已修复/哪些仍在）
- EvolutionPlugin.start_evolution() 实际驱动进化循环
- 清理 git 中 33 个 `__pycache__` 文件
- 归档已完成的 `.sisyphus/plans/` 计划文件

### Must NOT Have
- 不修改内核层（`src/kernel/`）的任何逻辑
- 不引入新的第三方依赖
- 不修改任何已通过的测试的断言逻辑（修复测试数据生成器除外）
- 不重构任何工作中的插件内部实现
- 不修改 `config.yaml` 的 schema
- 不做性能优化（除非是删死代码的副产品）

---

## TODOs

### Wave 1: 清理垃圾（无依赖，立即可做）

- [x] 1. **[A] 删除 8 个死代码文件**
  - 删除文件：
    - `src/plugins/evolution/weight_variator_legacy.py` (1,378行)
    - `src/plugins/evolution/wfa_backtester.py` (1,108行)
    - `src/plugins/evolution/numba_accelerator.py` (1,081行)
    - `src/plugins/evolution/evolution_storage.py` (377行)
    - `src/plugins/data_pipeline/data_sanitizer.py` (845行)
    - `src/plugins/wyckoff_state_machine/context_builder.py` (538行)
    - `src/plugins/wyckoff_state_machine/wyckoff_state_machine_legacy.py` (37行)
    - `src/utils/visualizer.py` (334行)
  - 同时删除：`tests/plugins/test_numba_accelerator.py`
  - 验收：`pytest tests/ -v` 全部通过（数量 = 基线 - numba测试数）
  - 禁止：不删除任何被 import 的文件；删除前用 grep 再次确认无引用

- [x] 2. **[A] 清理 git 中的 `__pycache__` 文件**
  - 执行 `git rm -r --cached __pycache__/ */__pycache__/ 2>/dev/null`
  - 确认 `.gitignore` 包含 `__pycache__/` 和 `*.pyc`
  - 验收：`git ls-files --cached "*__pycache__*"` 返回空
  - 禁止：不修改 `.gitignore` 之外的配置文件

- [x] 3. **[B] 修复 `make_ohlcv()` OHLC 数据生成 bug**
  - 文件：`tests/fixtures/ohlcv_generator.py` 第 72-82 行
  - 问题：`open` 和随机噪声可能导致 `open > high` 或 `open < low`
  - 修复：在生成 OHLC 后，强制保证 `high = max(open, high, close)` 且 `low = min(open, low, close)`
  - 验收：运行 `pytest tests/ -v -W error::UserWarning 2>&1 | grep "candle_physical"` 无匹配
  - 禁止：不修改 `candle_physical.py` 的验证逻辑


### Wave 2: 代码质量修复（依赖 Wave 1 完成）

- [x] 4. **[B] 为 4 个 `except Exception: pass` 添加 logger.warning**
  - 位置（bare except + pass，完全静默）：
    - `src/plugins/dashboard/plugin.py:60` — stop_monitoring 失败
    - `src/plugins/wyckoff_engine/engine.py:564` — TR 数据提取失败
    - `src/plugins/wyckoff_engine/engine.py:1201` — 止损计算失败
    - `src/plugins/position_manager/plugin.py:395` — risk_management 查找失败
  - 修复：将 `pass` 替换为 `logger.warning("描述: %s", e)`（需先将 `except Exception:` 改为 `except Exception as e:`）
  - 验收：grep 确认这 4 处不再有 `except Exception: pass`
  - 禁止：不改变 except 块的控制流逻辑（仍然吞掉异常，只加日志）

- [x] 5. **[B] 为 ~13 个静默 `except Exception:` 块添加日志**
  - 位置（bare except + fallback return 但无日志）：
    - `src/plugins/wyckoff_engine/engine.py:530,795,1167` (3处)
    - `src/plugins/pattern_detection/curve_boundary.py:722,983,1010` (3处)
    - `src/plugins/pattern_detection/plugin.py:344` (1处)
    - `src/plugins/perception/fvg_detector.py:168` (1处)
    - `src/plugins/evolution/genetic_algorithm.py:45` (1处)
    - `src/plugins/wyckoff_state_machine/state_machine_v2.py:499` (1处)
    - `src/api/app.py:310,340` (2处)
    - `src/utils/error_handler.py:196` (1处)
  - 修复：添加 `logger.debug` 或 `logger.warning`（根据严重程度选择级别）
  - 验收：`grep -rn "except Exception:" src/ | grep -v "as e" | grep -v logger` 返回空
  - 禁止：不改变异常处理的控制流；不将 debug 级别改为 error

### Wave 3: 前端数据集成（依赖 Wave 2 完成）

- [x] 6. **[C] FastAPI 静态文件服务 + run.py web 模式修复**
  - 文件：`src/api/app.py`、`run.py`
  - 修改 app.py：
    - 在文件末尾（`if __name__` 之前）添加 `StaticFiles` 挂载：`app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")`
    - 仅当 `frontend/dist/` 目录存在时挂载（`if os.path.isdir(...):`）
  - 修改 run.py：
    - `run_web_server()` 函数改为：先检查 `frontend/dist/index.html` 是否存在；存在则启动 API server（前端通过 StaticFiles 服务）；不存在则提示先运行 `cd frontend && npm run build`
  - 验收：`frontend/dist/` 存在时，访问 `http://localhost:8000/` 返回前端页面
  - 禁止：不修改前端构建配置；不修改 CORS 设置

- [x] 7. **[C] 后端 `/api/trades` 端点 + TradesTab 数据接入**
  - 文件：`src/api/app.py`、`frontend/src/components/TradesTab.tsx`、`frontend/src/core/api.ts`、`frontend/src/core/store.ts`
  - 后端：添加 `GET /api/trades` 端点，从 position_manager 获取 `get_closed_trades()` 或已平仓位历史
  - 前端 api.ts：添加 `fetchTrades()` 函数
  - 前端 store.ts：添加 `trades: TradeRecord[]` 和 `setTrades`
  - 前端 TradesTab.tsx：用 `useQuery` 拉取 `/api/trades`，替换硬编码空数组
  - 验收：TradesTab 显示来自后端的交易记录（即使为空列表，也是从 API 获取而非硬编码）
  - 禁止：不修改 TradesTab 的 UI 布局

- [x] 8. **[C] SignalPanel 数据接入（WebSocket wyckoff 主题扩展）**
  - 文件：`src/api/app.py`、`frontend/src/App.tsx`、`frontend/src/core/store.ts`
  - 后端 app.py：在 `_collect_topic_data` 的 `wyckoff` 主题中，除了 `wyckoff_state` 外，额外发送最新信号数据（从 wyckoff_engine 的 `get_latest_signal()` 获取）
  - 前端 App.tsx：在 `wyckoff_state` case 中，检查 `msg.data` 是否包含 signal 字段，有则调用 `addSignal()`
  - 验收：当 wyckoff_engine 产生信号时，SignalPanel 实时显示
  - 禁止：不新增独立的 WebSocket 主题


- [x] 9. **[C] LogsTab 数据接入（WebSocket system_status 扩展）**
  - 文件：`src/api/app.py`、`frontend/src/App.tsx`
  - 后端 app.py：在 `system_status` 主题的 `_collect_topic_data` 中，添加 `recent_logs` 字段（从 audit_logger 获取最近 20 条日志）
  - 前端 App.tsx：在 `system_status` case 中（目前是空 break），解析 `msg.data.recent_logs` 并调用 `addLog()`
  - 验收：LogsTab 显示来自后端的日志条目
  - 禁止：不创建新的 WebSocket 主题；不修改 audit_logger 插件本身

- [x] 10. **[C] AdvisorTab 数据接入**
  - 文件：`src/api/app.py`、`frontend/src/components/AdvisorTab.tsx`、`frontend/src/core/store.ts`、`frontend/src/types/api.ts`
  - 后端：添加 `GET /api/advisor/latest` 端点，从 evolution_advisor 插件获取最新分析结果
  - 前端 store.ts：添加 `advisorAnalysis` 状态和 `setAdvisorAnalysis`
  - 前端 api.ts：添加 `fetchAdvisorLatest()` 函数
  - 前端 AdvisorTab.tsx：用 `useQuery` 拉取数据，替换纯静态占位文本
  - 验收：AdvisorTab 显示来自后端的 advisor 分析（或 "无分析" 的动态状态）
  - 禁止：不修改 evolution_advisor 插件本身

- [x] 11. **[C] system_status WS 处理 + evolution/latest 前端调用 + 缺失集成**
  - 文件：`frontend/src/App.tsx`、`frontend/src/core/api.ts`
  - 在 App.tsx 的 `system_status` case 中提取 `msg.data` 并调用 `setSystemInfo()`
  - 前端已有 `fetchEvolutionResults()` 但缺少对 `/api/evolution/latest` 的调用——在 EvolutionTab 中添加 `useQuery` 调用
  - 前端已有 `updateConfig()` API 函数但无 UI 调用——在 Header 或设置面板添加简单调用入口
  - 验收：system_status 消息被处理；evolution latest 数据在前端可见
  - 禁止：不新建独立页面或路由

- [x] 12. **[C] Dockerfile 前端构建集成**
  - 文件：`Dockerfile`
  - 添加 Node.js 构建阶段（multi-stage build）：
    - Stage 1: `FROM node:18-slim AS frontend-build`，执行 `npm ci && npm run build`
    - Stage 2: 在现有 python 阶段中 `COPY --from=frontend-build /app/frontend/dist ./frontend/dist/`
  - 验收：`docker build .` 成功；容器启动后 `curl localhost:9527/` 返回前端 HTML
  - 禁止：不修改 `docker-compose.yml`；不修改前端构建配置

### Wave 4: 进化系统审计（依赖 Wave 1 死代码清理完成）

- [x] 13. **[D] 审计过拟合 7 根因（对照新代码逐条判定）**
  - 参考：`.sisyphus/plans/evolution-overfit-fix.md` 中的 7 个根因
  - 审计文件：`genetic_algorithm.py`、`wfa_validator.py`、`evaluator.py`、`bar_by_bar_backtester.py`、`anti_overfit.py`、`run_evolution.py`
  - 对每个根因输出判定：✅ 已修复 / ⚠️ 部分修复 / ❌ 仍存在
  - 输出写入 `.sisyphus/notepads/full-system-cleanup/decisions.md`
  - 验收：7 个根因全部有明确判定和代码行号引用
  - 禁止：本任务不修改代码，仅审计和记录

- [x] 14. **[D] 修复审计发现的仍存在的过拟合问题**
  - 依赖：Task 13 审计结果
  - 根据审计判定为 ❌ 或 ⚠️ 的项目，逐一修复
  - 修复范围限定在 `evolution/` 目录和 `run_evolution.py`
  - 验收：所有 7 根因状态变为 ✅ 或有明确的 "设计如此" 理由
  - 禁止：不修改非进化系统的代码

- [x] 15. **[D] EvolutionPlugin.start_evolution() 实际驱动进化循环**
  - 文件：`src/plugins/evolution/plugin.py`
  - 问题：`start_evolution()` 仅设置 `_is_evolving = True`，无实际进化逻辑
  - 修复：添加 `run_evolution_cycle()` 方法，封装 `run_evolution.py` 中的核心循环逻辑（GA评估→WFA验证→AntiOverfit检查→采纳/拒绝）
  - `start_evolution()` 调用后应在后台任务中执行 `run_evolution_cycle()`
  - 修复 `run.py` 的 `run_evolution_system()`：改为通过 EvolutionPlugin 驱动，不再 subprocess 调用 `run_evolution.py`
  - 验收：`python run.py --mode=evolution` 通过插件系统运行进化；`start_evolution()` API 可远程触发进化
  - 禁止：不删除 `run_evolution.py`（保留为独立运行选项）


### Wave 5: 技术债归零（依赖 Wave 1-4 完成）

- [x] 16. **[E] 归档已完成的 `.sisyphus/plans/` 文件**
  - 创建 `.sisyphus/plans/archive/` 目录
  - 移动 5 个已完成的计划到 archive：
    - `production-readiness.md` ✅
    - `architecture-redesign.md` ✅
    - `evolution-redesign.md` ✅
    - `evolution-dashboard.md` ✅
    - `frontend-integration.md`（被本计划取代）
  - 保留在 plans/ 的：
    - `system-architecture-v3.md`（参考文档，永久保留）
    - `evolution-overfit-fix.md`（Task 13-14 依赖）
    - `full-system-cleanup.md`（本计划）
  - 验收：`ls .sisyphus/plans/` 只有 3 个文件
  - 禁止：不删除任何文件，只是移动到 archive

- [x] 17. **[E] 更新 AGENTS.md 反映当前状态**
  - 文件：`AGENTS.md`
  - 更新内容：
    - 测试数量：1189 → 实际数量（删除 numba 测试后）
    - `.sisyphus/` 归档表格：标记已归档的计划，更新 `evolution-overfit-fix.md` 状态
    - 移除 "待执行" (🔧) 标记中已被本计划完成的项目
    - 模块状态总览：移除已删除的死代码文件引用
  - 验收：AGENTS.md 中所有信息与代码库实际状态一致
  - 禁止：不修改代码风格规范或测试指南部分

- [x] 18. **[E] 验证 18 个 plugin-manifest.yaml 元数据**
  - 逐一检查 18 个 `plugin-manifest.yaml`：
    - `name` 与目录名一致
    - `version` 为 `3.0.0`
    - `entry_point` 指向实际存在的文件和类
    - `dependencies` 列表中的插件确实存在
  - 如有错误则修复
  - 验收：所有 18 个 manifest 通过验证
  - 禁止：不修改插件逻辑代码

---

## Final Verification Wave

- [x] F1. **测试全通过**：`pytest tests/ -v` — 所有测试 passed，0 failed，0 error
- [x] F2. **警告消除**：`pytest tests/ -v -W error::UserWarning 2>&1 | grep "candle_physical"` — 无输出
- [x] F3. **静默异常消除**：`grep -rn "except Exception:" src/ | grep -v "as e"` — 返回空（所有 except 都捕获异常变量）
- [x] F4. **死代码确认**：`wc -l` 确认 8 个死文件已不存在
- [x] F5. **前端可服务**：构建前端 `cd frontend && npm run build`，启动 `python run.py --mode=api`，`curl http://localhost:8000/` 返回 HTML
- [x] F6. **Docker 构建**：`docker build -t wyckoff:v3.0 .` 成功
- [x] F7. **git 干净**：`git ls-files --cached "*__pycache__*"` 返回空
