# 标注驱动的状态机进化系统

> **状态**：待用户审核
> **日期**：2026-03-23
> **前置**：认知架构重构已完成（95 V4测试通过）
> **核心理念**：用户标注 → AI诊断差异 → agent修改检测器 → 重跑验证 → 循环

## 问题陈述

当前状态机检测器有两个根本问题：
1. **只看单根K线** — 但威科夫事件是多K线组合（SC是几根放量下跌+反转）
2. **阈值是手拍的** — 22个检测器有50+硬编码阈值，没有任何数据驱动的校准

结果：2000根真实ETH H4数据上，244次状态变化，31个"完整结构"，每10天一个循环。
真实市场一年可能就2-3个完整结构。

## 解决方案

**闭环：你标注 → 系统量化差异 → AI分析为什么不对 → 我改代码 → 重跑验证**

不是让AI直接改代码，是三层：
- 参数不对 → GA自动调（你的标注当fitness）
- 逻辑不对 → AI诊断 → 我改
- 缺检测器 → 你设计概念 → 我实现

## 关于上帝视角

你标注的是**事件的特征**，不是**未来的走向**：
- "这3根K线构成SC" → 系统学到SC的量价模板（实时可识别）
- "区间在280-340之间" → 系统学到区间形成的条件（SC_LOW~AR_HIGH）
- "这里是BU回踩" → 系统学到BU的特征：JOC后+缩量+缓跌+到AR_HIGH附近

这些特征在实盘中都是左侧可观测的，不需要知道未来。

---

## Wave 1：基础设施（不改行为，纯加字段）

> 让检测器参数可进化 + 让事件有范围 + 标注数据模型

### T1.1 — Hypothesis 加 bar_range 字段
- `state_machine_v4.py`: Hypothesis 加 `bar_range: Tuple[int, int]`
- `_confirm_and_advance()`: 设 `bar_range = (proposed_at_bar, bars_processed)`
- `WyckoffStateResult` 加 `event_window: Optional[Tuple[int, int]]`
- 测试：确认事件后 event_window 非空

### T1.2 — 22个检测器暴露 get_evolvable_params()
- 每个 NodeDetector 子类实现 `get_evolvable_params() -> Dict[str, ParamSpec]`
- ParamSpec = `{min, max, default, current}` 
- 例：SCDetector: `{"volume_threshold": {min:1.2, max:5.0, default:2.0}}`
- evaluate() 中硬编码值改为读 self._params[key]
- 测试：所有22个检测器 get_evolvable_params() 返回非空 dict

### T1.3 — 标注数据模型 + 存储
- 新建 `src/plugins/annotation/` 插件
- WyckoffAnnotation 数据类：
  ```
  type: 'event' | 'level' | 'structure'
  event_type: str          # "SC" | "AR" | "SPRING" ...
  start_time/end_time: int # 时间戳
  price: float             # 水平线价格
  level_label: str         # "SC_LOW" | "AR_HIGH" | "CREEK"
  structure_type: str      # "ACCUMULATION" | "DISTRIBUTION"
  confidence: float        # 0.5~1.0
  ```
- 存储：`data/annotations/{symbol}_{timeframe}.jsonl`
- 测试：CRUD 操作

### T1.4 — 标注 CRUD API
- `POST /api/annotations` — 创建标注
- `GET /api/annotations?symbol=&timeframe=` — 获取标注列表
- `DELETE /api/annotations/{id}` — 删除标注
- 测试：API 契约测试

---

## Wave 2：前端标注工具

> 在 AnalysisPage 上加4个标注工具，基于现有 ISeriesPrimitive 模式

### T2.1 — AnnotationLayer.ts（渲染层）
- 新建 chart plugin，跟 TRBoundaryBox.ts 同模式
- 渲染三种标注：事件范围（半透明矩形）、水平线（虚线+标签）、结构标签
- 从 store 读取标注数据渲染
- 测试：mock 数据渲染无报错

### T2.2 — 标注模式交互
- AnalysisPage 加标注模式开关
- 范围选择：点第一根→拖到最后一根→弹出下拉选事件类型
- 水平线：点击某价格位→输入标签（SC_LOW/AR_HIGH等）
- 测试：playwright 标注流程

### T2.3 — 前后端联通
- 标注完成 → POST → store更新 → 图表刷新
- 页面加载 → GET → 渲染已有标注
- 删除标注 → DELETE → 刷新
- 测试：完整 CRUD 往返

---

## Wave 3：对比引擎

### T3.1 — AnnotationMatcher
- 新建 `src/plugins/annotation/matcher.py`
- 输入：标注列表 + 状态机转换历史
- 匹配：系统确认事件落在标注[start,end]内 = match
- 输出：match列表（匹配/遗漏/误判/类型错误）
- 测试：已知标注集精确match score

### T3.2 — 差异可视化
- 你的标注（实线）vs 机器标注（虚线）并排显示
- 绿=匹配、红=遗漏、黄=误判 + 差异摘要面板

### T3.3 — 标注匹配度接入fitness
- COMPOSITE_SCORE 加标注匹配权重（0.3），有标注时生效

---

## Wave 4：内建AI诊断系统 + Python原生记忆

> 不接VCP，完全内建。仿VCP TagMemo概念，用Python原生向量检索。
> AI诊断顾问完全内建，无跨系统通信。

### T4.1 — 诊断prompt系统
- 系统prompt: 威科夫状态机诊断顾问角色
- 诊断prompt: AnnotationMatch + BarFeatures + 检测器源码片段
  → 差异原因 + 证据 + 参数修改建议 + 追问
- 追问机制: AI遇到不确定标注边界时主动提问
- 跟 evolution_advisor/prompts.py 同模式
- 测试: mock对话流，验证追问触发条件

### T4.2 — 对话式诊断类（双后端OpenAI/Ollama）
- 跟 advisor.py 同模式，支持多轮对话（conversation history）
- 每轮自动注入: 当前标注数据 + 机器状态 + BarFeatures
- `diagnose_chat(message, context) -> AIResponse`
- AIResponse含: text + suggested_params + highlighted_bars
- 测试: 多轮对话保持上下文

### T4.3 — AnalysisPage 侧边对话面板
- 右侧可折叠对话面板
- 图表↔对话联动: 点K线→对话引用, AI提到bar→图上高亮
- WebSocket /api/annotations/chat
- 对话历史按标注session保存
- 测试: playwright 对话+高亮联动

### T4.4 — AI输出→结构化修改建议
- JSON格式: diagnosis + evidence + param_changes + logic_changes
- 用户确认后 → coding agent执行 → 重跑验证
- 测试: JSON解析+字段验证

### T4.5 — 检测器知识库（Python原生向量记忆）
- **不接VCP，完全内建**
- 仿VCP TagMemo概念，但用Python原生实现:
  - 存储层: sqlite-vec (SQLite向量扩展) 或 chromadb
  - 向量化: sentence-transformers 本地模型 (all-MiniLM-L6-v2)
  - 无需Rust引擎，无需Node.js
- 检测器知识存储:
  ```
  data/detector_knowledge.db  (SQLite + 向量索引)
  表: rules (id, detector_name, rule_text, embedding BLOB, source, confidence, created_at)
  ```
- 每次诊断后AI总结规则，向量化存储
- 下次诊断时按检测器名精确查 + 语义相似度查
- 规则积累 = AI的"记忆"，跨session持久化
- 核心API:
  - `add_rule(detector, rule_text, source, confidence)`
  - `search_rules(detector, query, k=5) -> List[Rule]`
  - `get_detector_rules(detector) -> List[Rule]`
- 测试: 规则CRUD + 向量检索 + 跨session持久化

---

## Wave 5：闭环

### T5.1 — GA用标注匹配度优化22个检测器参数
### T5.2 — 标注WFA回归守护（Pareto改进）
### T5.3 — 增量标注：新标注→自动对比→提示调整

---

## 防过拟合

| 机制 | 说明 |
|------|------|
| 最小标注量 | ≥5完整结构+≥50事件才启动优化 |
| 标注WFA | 70%训练/30%验证按时段分 |
| 参数硬边界 | 每参数有min/max不能无限调 |
| 5层守护 | MBL+OOS-DR+DSR+MonteCarlo+CPCV继续生效 |
| Pareto改进 | 只接受全局改善 |

## 工作量

| Wave | 内容 | 天数 |
|------|------|------|
| 1 | 基础设施（参数暴露+数据模型+API） | 2-3 |
| 2 | 前端标注工具 | 3-4 |
| 3 | 对比引擎+差异可视化 | 2 |
| **小计** | **能标注+看差异** | **7-9** |
| 4 | 内建AI诊断+Python原生向量记忆 | 3-4 |
| 5 | 闭环进化 | 2 |
| **总计** | **完整闭环** | **12-15** |

## 执行建议

**Wave 1-3先做，Wave 3完成后停下验证。**
到时你能标注、看差异、进化能用标注当评判。
如果差异分析够你直接告诉我怎么改，Wave 4-5可延后。

## 护栏

- 不改 process_bar()→BarSignal 接口
- 不改 TransitionGuard 白名单（理论约束不是数据驱动）
- AI只输出建议，不直接改代码
- MVP只做H4、只标历史、单用户

