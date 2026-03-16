# 回测系统诊断报告

**诊断时间**: 2026-03-03
**状态**: 静态代码扫描完成，待运行诊断确认

---

## 一、数据加载函数读取了多少行数据？

### 涉及文件
- `src/data/loader.py` — `DataLoader` / `MarketDataLoader`
- `src/backtest/engine.py` — `BacktestEngine.run()`
- `src/core/wfa_backtester.py` — `WFABacktester`

### 关键发现：数据加载被 `@error_handler` 静默吞错

`DataLoader` 的所有加载方法均使用了：
```python
@error_handler(logger=logger, reraise=False, default_return=pd.DataFrame())
```

`reraise=False` 意味着：一旦文件不存在（FileNotFoundError）或格式解析失败，
装饰器会：
1. 记录日志（但日志级别可能被过滤掉）
2. **直接返回空 DataFrame，完全不抛出异常**

调用方拿到空 DataFrame 后无法感知错误，继续往下执行。

### data_cache 目录实际不存在

环境声明的第二工作目录 `D:\AAAAA\opencode\wyckoff\data_cache` **物理上不存在**（Glob 扫描确认）。
若数据加载从该路径读取，100% 返回 **0 行空 DataFrame**。

---

## 二、回测时间循环（Loop）起点和终点

### BacktestEngine（`src/backtest/engine.py:148`）

```python
for i, (idx, row) in enumerate(data.iterrows()):
    current_price = row["close"]
    ...
```

- **起点**：`data` 的第 0 行（DataFrame 索引第一条）
- **终点**：`data` 的最后一行
- **若 data 为空 DataFrame（0行）**：循环体**一次都不执行**，直接跳到 `_calculate_statistics()`
- `_calculate_statistics()` 检测到 `self.trades` 为空，立即返回 `BacktestResult()`（默认值全0）

→ **整个 `run()` 在空数据下约 < 1ms 完成，脚本表现为"1秒就结束"**

### WFABacktester（`src/core/wfa_backtester.py:454`）

```python
while (
    start_idx + self.train_days + self.test_days <= total_days
    and len(windows) < max_windows
):
```

- 默认 `train_days=60, test_days=20`，要求至少 **80行数据**
- 若 `total_days < 80`（空或不足），`while` 不执行，直接返回 `_create_insufficient_data_result()`
- 测试脚本中用的是**内部生成的 mock 数据**（100~365天），不依赖外部文件

---

## 三、try...except 吞掉报错的情况（全部清单）

| 位置 | 代码 | 是否静默吞错 | 影响 |
|------|------|-------------|------|
| `src/data/loader.py:57` | `@error_handler(reraise=False, default_return=pd.DataFrame())` | **是** | 文件不存在时返回空DF |
| `src/data/loader.py:91` | 同上（load_excel） | **是** | 同上 |
| `src/data/loader.py:128` | 同上（load_parquet） | **是** | 同上 |
| `src/data/loader.py:153` | 同上（load_json） | **是** | 同上 |
| `src/data/loader.py:180` | 同上（load_auto） | **是** | 同上 |
| `src/data/loader.py:264` | 同上（load_market_data） | **是** | 同上 |
| `src/backtest/engine.py:105` | `@error_handler(reraise=False, default_return=BacktestResult())` | **是** | 回测任意异常直接返回空结果 |
| `src/core/wfa_backtester.py:801-824` | `try: mistake_book.record_mistake... except Exception as e: warnings.warn(...)` | **是** | 验证失败记录被吞 |
| `tests/test_automated_backtest_framework.py:641-646` | `except Exception as e: print(...); traceback.print_exc()` | 否（有打印）| 会输出但继续 |
| `tests/test_simple_backtest.py:17-28` | `except ImportError as e: sys.exit(1)` | 否 | 导入失败会退出 |
| `src/data/loader.py:312-319` | `except Exception as e: logger.error(...)` | 部分 | 多文件批量加载时单个失败会跳过 |

**最危险的组合**：`DataLoader.load_csv(reraise=False)` + `BacktestEngine.run(reraise=False)`
= **两层静默**，外部完全看不到任何错误，只看到"程序正常运行并立刻结束"。

---

## 四、初步结论（待运行诊断验证）

**假设最大嫌疑（按概率排序）：**

### 嫌疑 A（概率最高）：数据文件路径不对，加载到 0 行数据
- `data_cache/` 目录不存在
- `DataLoader` 的 `@error_handler(reraise=False)` 静默返回空 DataFrame
- `BacktestEngine.run()` 对空 DF 进行 0 次循环迭代
- 约 < 1 秒完成并退出

### 嫌疑 B：数据加载成功但格式不对（列名不匹配）
- `MarketDataLoader._validate_ohlcv()` 在缺列时只 `logger.warning`，不中断
- `row["close"]` 在 engine.py:149 会抛 `KeyError`
- 被 `@error_handler(reraise=False)` 捕获后返回空 `BacktestResult()`

### 嫌疑 C：信号列表（signals）为空
- `engine.py:146` 对空列表排序后
- `signal_index` 永远不推进，所有 bar 都无信号
- 循环正常跑完但 0 成交，< 1 秒结束

---

---

# ══ 实际运行诊断结果（trace_evolution.py）══

**运行时间**: 2026-03-03
**数据文件**: `data/ETHUSDT_4h.csv`，原始 18700 行，截取末尾 2000 行

---

## 五、实际变量状态（关键节点打印）

| 检查点 | 实际值 |
|--------|--------|
| 数据文件是否存在 | ✅ 存在，csv |
| `len(data)` 实际行数 | **2000 行**（正常） |
| 索引类型 | Timestamp（正常） |
| `close` 均值 | 3088.3（ETH 价格，合理） |
| 导入耗时 | 0.02s，全部成功 |
| 整个脚本是否跑完 | ✅ **7 个 STEP 全部执行完毕，正常退出** |

---

## 六、真正的问题：3 个核心 Bug

### Bug-1（最严重）：WyckoffStateMachine 状态机永远卡在 IDLE

```
3b. 200根K线测试 → 状态分布: {'IDLE': 200}
```

**200 根 bar 全部返回 IDLE**，状态机从未发生任何 Wyckoff 阶段转换。
但 `state_confidences` 里仍有非零置信度（bull≈0.633，bear≈0.683），
说明状态机内部计算了信心值，但从未触发状态切换，`process_candle` 始终返回 `IDLE`。

信号不是从 IDLE 生成的，而是从 PeriodWeightFilter 的 `primary_bias` 产生：
- 2000根 → 9个信号（BUY=4, SELL=5）
- 信号是存在的，但与状态机完全脱节

---

### Bug-2（进化失效）：Config 对评分结果无任何影响

```
baseline config  (threshold=0.40): COMPOSITE_SCORE=0.7096, 信号数=9, 交易数=4
mutated config   (threshold=0.60): COMPOSITE_SCORE=0.7096, 信号数=9, 交易数=4
📌 分数差 = 0.0000
```

`confidence_threshold` 从 0.40 改到 0.60，结果**分毫不差**。
原因：所有信号的 PeriodWeightFilter 置信度恰好都在 0.63~0.68 之间，
同时高于 0.40 和 0.60，两个 threshold 切到的信号集完全一样。
→ **进化引擎无法产生选择压力，变异永远没有意义。**

---

### Bug-3（WFA 全量拒绝）：所有变异体被 WFABacktester 拒绝

```
validate_mutations → accepted=0  rejected=2
cycle 耗时 = 0.83s（不是"程序崩溃"，是正常完成后退出）
```

拒绝链路：
- 每次 WFA 窗口（train=300天/test=100天/step=200天）只能产生 **3 个窗口**
- `_check_for_overfitting` 低相关性检查 + 稳定性阈值（0.7）未能通过
- 所有变异被打为 REJECTED，`run_correction_cycle` 正常返回 `success=True`
- 脚本执行完 7 个 STEP 后正常退出

---

## 七、"1 秒就结束"的真相

**程序没有崩溃，也没有数据加载失败。**

真相是：
1. `run_correction_cycle` 完整运行了一次，耗时 **0.83 秒**
2. 脚本 `trace_evolution.py` 在完成所有 7 个 STEP 后正常退出
3. **没有外层循环让进化持续运行**

你看到"1秒就结束"，是因为整个单次 cycle 确实只需不到 1 秒。
若期望进化持续迭代，需要在外层套一个 `while True` 或多轮循环。

---

## 八、修复方向（待你确认后执行）

| # | 问题 | 修复方向 |
|---|------|---------|
| 1 | 状态机永远 IDLE | 检查 `process_candle` 的状态切换条件与 `STATE_SWITCH_HYSTERESIS=0.75` 的关系，当前阈值可能过高导致永不切换 |
| 2 | Config 对评分无影响 | performance_evaluator 中 threshold 的过滤区间与实际 confidence 分布不重叠，需调整 threshold 搜索空间或信号生成逻辑 |
| 3 | WFA 拒绝全部变异 | 放宽 `stability_threshold`（当前0.7）或减小 `correlation_threshold`（当前0.7），或增加 WFA 窗口数让统计更稳 |
| 4 | 无持续循环 | 在外层添加多轮迭代逻辑 |

**等你确认后，我才动代码。**
