# 威科夫系统重构设计文档 v3.0

## 基于莱恩区间理论 | 2026-04-01

> **本文档是系统重构的施工蓝图。**
> 由WyckoffInspector（系统第二大脑）基于与莱恩先生的多轮理论讨论整理。
> v3.0整合了v2.0审阅后的全部修正：区间形状、SOS重定义、Creek/Ice、供需三级递进、规则引擎等。
> 所有理论内容来自莱恩先生，系统分析来自Inspector对190个代码文件的审查。

***

## 目录

1. [核心理念](#1-核心理念)
2. [理论框架](#2-理论框架)
3. [系统架构](#3-系统架构)
4. [数据结构定义](#4-数据结构定义)
5. [模块详细设计](#5-模块详细设计)
6. [事件类型全表](#6-事件类型全表)
7. [回测流水线](#7-回测流水线)
8. [记忆层设计](#8-记忆层设计)
9. [进化方案](#9-进化方案)

***

## 1. 核心理念

### 1.1 因果关系反转

**当前代码**：先运行状态机 → 状态机运行过程中尝试识别区间 → 区间是状态机的副产品
**新系统**：先识别区间 → 在区间之上检测事件 → 事件推进阶段 → 阶段决定交易方向

**区间是一切的基础设施，不是状态机的副产品。**

### 1.2 K线的核心是价格运动

-区间的形成是价格运动的结果

- 趋势到区间的转变也是价格运动的结果
- 通过极端价格（影线）和实体收盘定义候选边界
- 通过后续反弹（AR）确认区间
- 通过二次测试（ST）判定区间是否成立
- 通过阶段C测试（Spring/UTAD）确认供需方向

### 1.3 系统永远有立场

- 不存在"空仓等待"状态
- 下跌趋势 = 持有空仓，通过历史区间预测SC位置分批止盈
- 上升趋势 = 持有多仓，通过历史区间预测BC位置分批止盈
- 区间内= 根据阶段执行对应策略

### 1.3.1 冷启动协议（仅回测）

- 第一根K线的高低点作为初始候选SC/BC
- direction = NEUTRAL（"永远有立场"的唯一合法例外）
- 不产生交易信号
- 等区间确立或趋势形成后，系统正常运作
- 实盘启动时系统已有历史数据，不存在冷启动问题

### 1.4 先建记忆，再建智慧

- 每个事件完整记录（不论是否触发交易）
- 事件失败、阶段跳过、非标准路径同样完整记录——这是进化系统的燃料
- 先积累数据，再决定进化方式
- 历史区间库+ 事件案例库 + 交易记录库 = 系统记忆层

### 1.5 识别层与决策层分离

- **识别层**（状态机系统）：区间识别 + 事件检测 + 阶段管理 → 输出"市场现在在什么状态"
- **决策层**（交易系统）：基于识别层的输出做交易决策 → 可以有多种策略针对不同状态
- 两个系统独立开发和验证
- 先把识别层做对，再开发决策层

***

## 2. 理论框架

### 2.1 区间的生命周期

```
第1根K线 → 高低价= 第一个区间的起点↓
价格运动 → 形成趋势或盘整（大部分时间是盘整）
     ↓
极端价格事件(SC/BC) → 标记候选边界（结合历史区间位置锚点+成交量异常）
  ├── 极限价格（影线高低点）= 候选边界A
  └── 实体收盘价= 候选边界B↓
反弹(AR) → 标记另一侧边界└── 斐波那契预判AR力度（起点=前结构阶段C高点，终点=SC，加密市场常见0.318）↓
    **AR确认逻辑**：AR需要几根日线持续反弹，有相对大的涨幅，在关键阻力位停下来。AR是反弹结束后（出现回落）才回头确认的。死猫跳不是AR。需要量价参与。
二次测试(ST) → 区间判定门+ 方向预判
  ├── 撑住（缩量回测，不破边界）→ 区间确立
  ├── 失败（放量回测，供应未枯竭）→ 区间否定，重新寻找
  └── ST位置预判区间方向：高ST→可能上斜，低ST→可能下斜
     ↓
阶段B（ST-B多次测试）→ 确定区间形状 + 形成Creek/Ice
     ↓
阶段C（Spring/UTAD）→ 方向确认（可能跳过/失败/温和测试）
     ↓
阶段D（SOS/SOW供需确认 → JOC/跌破冰线区间突破）
     ↓
阶段E（趋势运行 → MSOS/MSOW回踩确认 → 寻找新SC/BC）
```

### 2.2 五大阶段（非线性路径）

| 阶段 | 核心功能    | 关键事件                               | 可能的非标准路径                                |
| -- | ------- | ---------------------------------- | --------------------------------------- |
| A  | 确定起点    | \[PS]→SC→AR→ST                     | ST失败→区间否定→重新寻找SC                        |
| B  | 建设区间    | ST-B/UT/UTA多次测试，Creek/Ice形成        | B→D跳过C暂不实现；B阶段边界跌破→区间BROKEN→趋势接管（RD-39） |
| C  | 确定方向    | Spring/SO（吸筹）或UTAD（派发）             | 可能跳过/失败/温和测试不penetrate                  |
| D  | 供需确认+突破 | SOS/SOW（供需确认）→ JOC/跌破冰线（突破）        | D失败（突破被打回）→回到区间                         |
| E  | 趋势运行    | MSOS/MSOW（回踩确认）→ UPTREND/DOWNTREND | 新SC/BC出现→新区间开始                          |

**C阶段定义**：C是确认性事件（Spring/UTAD），几根K线就结束，不是持续阶段。Phase.C用于标记事实。不需要B→C转换规则。

**阶段A确定起点，阶段C确定方向，阶段D确定突破。**

**五大阶段是理论框架，不是必经流程。** 每个阶段都可能成功、失败、或被跳过。实际区间的路径是一棵树：

```
A成功 → B
A失败（ST否定）→ 重新寻找SC

B → C（标准）
B → 持续震荡

C成功 → D
C失败（penetrate不收回）→ 区间打破
C跳过 → D（通过mSOS/mSOW渐进确认方向）
C温和测试（不penetrate）→ D

D成功（JOC/跌破冰线）→ E
D失败（突破被打回）→ 回到区间

E →新SC/BC → 新区间A
```

### 2.3阶段C是方向开关

| 当前结构 | C之前的交易方向 | C之后的交易方向 | 原因                 |
| ---- | -------- | -------- | ------------------ |
| 吸筹   | 只做空      | 只做多      | C前仍在下跌情绪中，C后方向确认反转 |
| 派发   | 只做多      | 只做空      | C前仍在上涨情绪中，C后方向确认反转 |
| 再吸筹  | 只做多      | 继续做多     | 上升趋势中的中继，C确认趋势延续   |
| 再派发  | 只做空      | 继续做空     | 下跌趋势中的中继，C确认趋势延续   |

**阶段C不只是技术信号，它是市场情绪的转折点。**

C之前，再吸筹和派发的方向一致（都做多），structure\_type = UNKNOWN不影响交易方向。C确认后才确定structure\_type。

### 2.4 区间形状

区间不一定是水平的。区间形状在阶段B判定，但在阶段A的ST位置就可以预判：

| 形状 | 特征       | ST位置特征                | 倾向       |
| -- | -------- | --------------------- | -------- |
| 水平 | 高低点在同一水平 | ST在SC附近               | 需要C确认方向  |
| 上斜 | 高低点都在上升  | ST很高（强势）              | 倾向吸筹/再吸筹 |
| 下斜 | 高低点都在下降  | ST位置较低（略penetrate后收回） | 倾向派发/再派发 |

区间形状判定流程：

1. 阶段A：ST位置预判（高ST → "水平 vs 上斜？"，低ST → "水平 vs 下斜？"）
2. 阶段B：ST-B多个高低点拟合趋势线→ 确定斜率 → 确定形状
3. 形状确定后，边界从固定价格更新为趋势线

**区间形状暗示方向**：上斜 = 买方渐强，下斜 = 卖方渐强。

**初版必须支持斜线区间**——区间斜率是动态的，不支持斜线就不可能正确识别。

### 2.4.1 SC→AR→ST序列的特殊情况

新低出现时不是简单替换SC。如果新低有阻力+量比SC低→可能是下斜区间的ST。下斜区间的成因就是ST比SC低。

### 2.5 Creek和Ice

Creek和Ice是区间的内部结构线，在阶段B自然形成：

- **Creek（小溪）**：吸筹区间中，连接阶段B多个反弹高点的线（区间内的阻力线）。锚点来自UTA高点和ST-B后的反弹高点
- **Ice（冰线）**：派发区间中，连接阶段B多个回调低点的线（区间内的支撑线）。锚点来自UT回落后的低点和ST-B后的回调低点

Creek/Ice不一定是水平的——如果区间是斜的，Creek/Ice也是斜的。

**Creek/Ice与区间边界的关系**：

- Creek可能低于区间上边界（AR高点），Ice可能高于区间下边界（SC低点）
- C阶段测试的是极端价格（SC/BC区域），与区间边界有关但没有强关联
- D阶段的JOC/跌破冰线突破的对象可能是外边界也可能是Creek/Ice，需要打分，不能定死

### 2.6 供需三级递进

| 级别   | 吸筹侧  | 派发侧  | 阶段       | 含义            |
| ---- | ---- | ---- | -------- | ------------- |
| 渐进信号 | mSOS | mSOW | B/C      | 区间内供需力量的渐进变化  |
| 明确确认 | SOS  | SOW  | D（C之后）   | 区间内供需力量的明确确认  |
| 回踩确认 | MSOS | MSOW | E（JOC之后） | 回踩不破，供需力量最终确认 |

**SOS/SOW不是突破！** SOS/SOW是"供需的确定"，在区间内部发生，C之后的D阶段事件。
\*\*JOC/跌破冰线才是区间突破。\*\*回调不再回到区间 =趋势开启。

### 2.7 再吸筹与再派发

- 与吸筹/派发结构一致（A→B→C→D→E同构）
- 可递归应用同一套区间逻辑
- 可能出现在区间上边界不破的位置
- 事件时间跨度可能更短（单根K线的Spring在再吸筹中是可能的）
- 可能跳过PS/PSY直接SC/BC
- 可能没有PS/PSY

### 2.7.1 structure\_type推导

不需要特别的判定逻辑。structure\_type通过entry\_trend + C阶段事件类型自然推导：

| entry\_trend | C阶段事件     | 方向变化     | structure\_type  |
| ------------ | --------- | -------- | ---------------- |
| SHORT (SC进入) | Spring/SO | 翻转→LONG  | ACCUMULATION     |
| LONG (BC进入)  | UTAD      | 翻转→SHORT | DISTRIBUTION     |
| LONG (BC进入)  | Spring/SO | 延续LONG   | RE\_ACCUMULATION |
| SHORT (SC进入) | UTAD      | 延续SHORT  | RE\_DISTRIBUTION |

C确认前structure\_type = UNKNOWN，不影响交易方向。
parent\_range\_id事后标注（前一个区间Phase=E且方向一致时自动设置），不影响交易逻辑。

### 2.8 供需原则（量价关系）

- **SC/BC**：出现在历史区间关键位置 + 成交量显著大于趋势内平均量
- **ST**：缩量回测边界 = 供应/需求枯竭确认。放量回测 = 供应/需求未枯竭 = 否定。不能固定标记，需综合价格位置+成交量+K线形态
- **Spring**：低量跌破 + 收回 = 假跌破，供应已被吸收
- **UTAD**：低量突破 + 回落 = 假突破，需求已被满足
- **SOS/SOW**：区间内供需力量确认（不是突破），表现为方向移动后弱反向运动+窄幅横盘
- **JOC/跌破冰线**：区间突破，回调不再回到区间
- **成交量基准**：区间内事件（ST/Spring等）用阶段B/C的均量作基准；区间形成前事件（SC/BC）用趋势中均量作基准

**区间告诉系统"在哪看"，成交量告诉系统"看到了什么"。**

### 2.9 SC/BC候选管理

- 趋势运行中（阶段E之后），系统持续寻找新SC/BC
- 每根K线的极端价格都可能是候选SC/BC
- 候选SC/BC的置信度由以下因素综合决定：
  1. **历史区间位置锚点**（权重最高）：是否在历史区间的支撑/阻力位附近
  2. **成交量异常度**：相对于趋势中均量的倍数
  3. **K线形态**：长下影线（买盘介入）vs 光脚阴线（未止跌）
  4. **下跌/上涨幅度**：累计幅度是否足够
  5. **PS/PSY特征**（增强因子）：SC候选之前是否有"放量阻止趋势"的K线
- 新低/新高出现时，旧候选被替换（同一时间只保留一个候选）
- 旧候选记录保留在记忆层（标记为REPLACED），供进化分析

### 2.10 PS/PSY的处理

- PS/PSY不作为独立事件实时检测
- 作为SC/BC置信度的增强因子：SC候选出现时，回头扫描之前的K线，看有没有PS特征（放量阻止趋势），如果有则增加SC置信度
- 再吸筹/再派发可能没有PS/PSY——没有PS/PSY时SC仍可通过其他因素获得足够置信度
- 正式派发一般有PSY（情绪原因），PSY作为BC置信度增强因子时权重应高于PS对SC的增强
- 事后标注到记忆层，供进化分析

### 2.11 历史区间的强度

- 时间衰减因子：距今越远的区间支撑/阻力越弱
- 测试消耗因子：被测试次数越多越弱
- 处女测试例外：从未被重新测试的区间可能保持原始强度
- 区间持续时间：越长的区间因果法则决定后续影响越大

### 2.12 斐波那契的角色

**吸筹侧**：

- 起点 = 前一个结构的阶段C高点（不是区间上下线），终点 = SC低点
- 如果没有前一个结构，用SC之前最近的显著高点（swing high）作为替代
- 预判AR反弹力度（加密市场观察到0.318为主，上限0.5）
- AR的上限是上一个区间的边界
- 预测上斜区间中UTAD的高点

**派发侧**：

- 起点 = 前一个结构的阶段C低点（不是区间上下线），终点 = BC高点
- 如果没有前一个结构，用BC之前最近的显著低点（swing low）作为替代
- 预判AR回落力度（对称于吸筹侧，0.318为主）
- AR的下限是上一个区间的边界
- 预测下斜区间中Spring的低点

**通用**：

- 反向使用：观察AR实际到达的Fib位置来诊断供需强度
- 斐波那契权重需要进化优化，不能固定
- 辅助判断再吸筹/再派发可能出现的位置

### 2.13 因果定律与B阶段时间

威科夫因果定律：区间（因）的持续时间和规模决定后续趋势（果）的幅度和持续时间。**吸筹过程是因，趋势是果。**

B阶段的时间影响三件事：

1. **区间成熟度**：B阶段太短 → 区间不成熟 → 事件可靠性低→ 置信度降低
2. **因果能量**：B阶段越长 → 积累的供需力量越大 → 后续趋势预期幅度越大（影响决策层的止盈目标）
3. **超时关注**：B阶段持续过长且无方向信号 → 可能供需平衡 → 规则引擎超时规则触发关注

B阶段的具体时间阈值（最小成熟时间/因果能量系数/超时阈值）需要通过回测确定，标记为进化参数。

### 2.14 非标准路径的记录（进化燃料）

所有非标准路径都完整记录到EventCase中：

| 路径类型              | 记录内容                              | 进化价值               |
| ----------------- | --------------------------------- | ------------------ |
| C失败（penetrate不收回） | penetrate深度/时长/量价、前N根K线量价趋势、区间上下文 | 学习"什么条件下Spring会失败" |
| C跳过（B直接到D）        | 区间形状、mSOS/mSOW信号、SOS/SOW特征        | 学习"什么条件下C会被跳过"     |
| ST失败（区间否定）        | 候选区间完整特征（标记REJECTED）              | 学习"什么条件下候选区间会被否定"  |
| D失败（突破被打回）        | 突破深度、突破后量价、打回速度                   | 学习"什么条件下突破会失败"     |

***

## 3. 系统架构

### 3.1 三层核心架构

```
┌─────────────────────────────────────────────────┐
│                  决策层（交易系统）                 │
│  多种交易策略，针对不同状态组合                      │
│  输入: 识别层输出  输出: 交易指令                    │
│（识别层完成后再开发）│
├─────────────────────────────────────────────────┤
│                  识别层（状态机系统）                 │
│  ┌─────────────────────────────────────────┐    │
│  │ 事件引擎 + 规则引擎（阶段管理）            │    │
│  │ 输入: K线+区间状态  输出: 事件+阶段+方向    │    │
│  ├─────────────────────────────────────────┤    │
│  │ 区间引擎                │    │
│  │输入: K线数据  输出: 活跃区间+边界+位置     │    │
│  └─────────────────────────────────────────┘    │
├─────────────────────────────────────────────────┤
│                  记忆层（持久化）                   │
│  历史区间库+ 事件案例库 + 交易记录库               │
└─────────────────────────────────────────────────┘
```

### 3.2 三大引擎职责声明与数据流

**区间引擎**负责：

- 趋势中寻找SC/BC候选（结合历史区间位置+成交量异常）
- 检测AR（斐波那契预判力度）、ST（区间判定门）
- 三点定区间（创建通道，SC→ST定斜率，平移到AR）
- 区间被突破后标记BROKEN，归档到历史区间库
- 阶段E中持续监控价格是否回到旧区间（假突破回归检测）
- 归档后回到"寻找新SC/BC"状态

**事件引擎**负责：

- 区间确立后的所有事件检测（ST-B/UT/UTA/Spring/SOS/JOC等）
- 按阶段过滤检测范围（B阶段检测ST-B/UT/UTA + Spring/SO/UTAD，C阶段检测Spring/UTAD，D阶段检测SOS/SOW/JOC）
- B阶段同时检测C阶段事件，Spring/UTAD成功=C完成=直接进入D
- 检测到JOC/跌破冰线→ 通知区间引擎"区间被突破了"

**规则引擎**负责：

- 所有阶段转换（A→B→C→D→E，以及E→B的假突破退回）
- 方向管理（SC→SHORT，BC→LONG，C确认→翻转/延续）
- 规则日志记录

**三大引擎调用关系**：
概念上三大引擎职责独立，实现上规则引擎由事件引擎调用。

- 区间引擎检测到SC/BC/AR/ST → 创建Event对象 → 传递给事件引擎
- 事件引擎统一创建EventCase（包括SC/BC的EventCase）
- 事件引擎每检测到一个事件 → 传递给规则引擎评估阶段转换

**趋势→区间转换**（E→A）：区间引擎发现SC/BC候选 → 规则引擎设置阶段A + 设置初始方向
**区间→趋势转换**（D→E）：事件引擎检测到JOC → 规则引擎推进到阶段E → 区间引擎将区间标记BROKEN并归档
**假突破回归**（E→B）：区间引擎检测到价格回到旧区间内 → 旧区间恢复ACTIVE → 规则引擎阶段退回B → JOC标记FAILED → 方向不变

- 假突破回归优先于新SC/BC寻找

三个进化参数：reentry\_threshold / confirmation\_bars / max\_breakout\_age（初版给默认值，回测进化）

```
K线数据 → [区间引擎] → 区间状态↓
         [事件引擎] → 事件 + 阶段 + 方向
                ↓
         [决策层] → 交易指令（多种策略可选）
                ↓
         [记忆层] ← 全程记录（含失败/跳过/非标准路径）
```

### 3.3 多时间框架架构

核心原则：不否决任何TF信号，用仓位表达确定性。

架构：

识别层：每个TF独立运行一套完整引擎（RangeEngine + EventEngine + RuleEngine），互不干扰

决策层：MTF协调器综合所有TF的输出，评估共振/冲突 → 确定性评分 → 仓位系数

记忆层：HistoricalRangeStore + EventCaseStore 跨TF共享

仓位方案：

TF级别决定基础仓位（日线=3x，4H=1x，1H=0.5x，具体倍数为进化参数）

共振增加确定性 → 仓位系数增加

冲突降低确定性 → 仓位系数减少（但不否决信号）

三种共振类型（全部需要）：

阶段共振：多TF同时处于相同阶段方向

位置共振：低TF事件发生在高TF关键位置（通过共享HistoricalRangeStore自然实现）

方向共振：多TF方向一致

共振示例：日线B阶段快到C时，4H出现完整派发周期（UTAD后回落）→ 日线C阶段概率大增 → 确定性增加 → 仓位增加。

嵌套问题：通过仓位自然解决。日线级别信号→大仓位，4H级别→小仓位。不需要在识别层处理嵌套逻辑。
方向冲突：通过仓位自然解决。冲突时仓位减少，不否决。日线派发时4H的向上运动是真实交易机会（UTAD前的可观涨幅），应通知交易系统进场。
权重问题：通过仓位自然解决。高TF信号→大仓位 = 自然的高权重。

***

## 4. 数据结构定义

### 4.1 区间（Range）

```python
@dataclass
class Range:
    range_id: str    # 唯一标识
    timeframe: str                   # 时间框架 (1H/4H/1D/1W)
    # 通道定义（三点定区间：SC/BC→AR→ST，上下边界平行）
    channel_slope: float             # 通道斜率（SC→ST连线确定，水平=0）
    channel_width: float             # 通道宽度（主边界到AR的垂直距离）
    primary_anchor_1: AnchorPoint    # 第一个极端事件锚点（吸筹=SC，派发=BC）
    primary_anchor_2: AnchorPoint    # 确认点锚点（ST）
    opposite_anchor: AnchorPoint     # 对侧锚点（AR）
    entry_trend: Direction           # 进入区间时的趋势方向（SC→SHORT，BC→LONG）
    # 区间形状（ST确认时由SC→ST斜率确定）
    range_shape: RangeShape          # HORIZONTAL / ASCENDING / DESCENDING
    
    # 内部结构线
    creek: Optional[TrendLine]       # Creek（吸筹侧，B阶段高点连线）
    ice: Optional[TrendLine]         # Ice（派发侧，B阶段低点连线）
    
    # 生命周期
    status: RangeStatus              # CANDIDATE / CONFIRMED / ACTIVE / BROKEN / ARCHIVED / REJECTED
    created_at_bar: int              # 创建时的K线索引
    confirmed_at_bar: Optional[int]  # ST确认时的K线索引
    broken_at_bar: Optional[int]     # 突破时的K线索引
    
    # 阶段
    current_phase: Phase# A / B / C / D / E
    structure_type: StructureType    # ACCUMULATION / DISTRIBUTION / RE_ACCUMULATION / RE_DISTRIBUTION / UNKNOWN
    direction_confirmed: bool        # 阶段C是否已确认方向
    phase_c_skipped: bool            # C阶段是否被跳过
    
    # 评分
    strength_score: float            # 支撑/阻力强度（含时间衰减）
    duration_bars: int               # 持续K线数
    test_count: int                  # 被测试次数
    last_test_bar: Optional[int]     # 最近一次测试的K线索引
    
    # 关联
    parent_range_id: Optional[str]   # 父级区间ID（再吸筹/再派发时）
    child_range_ids: List[str]       # 子级区间ID列表
    
    # 斐波那契
    fib_levels: Dict[float, float]   # {0.236: price, 0.318: price,0.5: price, ...}
    fib_reference_price: float       # Fib起点（吸筹=前C高点/swing high，派发=前C低点/swing low）
    fib_extreme_price: float         # Fib终点（吸筹=SC低点，派发=BC高点）
```

### 4.2 趋势线（TrendLine）

```python
@dataclass
class TrendLine:
    """趋势线定义——水平线是斜率为0的特殊情况"""
    slope: float                     # 斜率（水平=0，上斜>0，下斜<0）
    intercept: float                 # 截距
    anchor_points: List[AnchorPoint] # 锚点列表（用于拟合的价格点）
    r_squared: float                 # 拟合质量
    
    def price_at(self, bar_index: int) -> float:
        """返回该bar处的趋势线价格"""
        return self.slope * bar_index + self.intercept

@dataclass
class AnchorPoint:
    bar_index: int
    extreme_price: float             # 极限价格（影线）
    body_price: float                # 实体价格（收盘）
    volume: float                    # 成交量
```

### 4.3 枚举定义

```python
class RangeStatus(Enum):
    CANDIDATE = "candidate"      # SC/AR标记了候选边界，等待ST确认
    CONFIRMED = "confirmed"      # ST确认区间成立，进入阶段B
    ACTIVE = "active"            # 区间正在运行中（B/C/D阶段）
    BROKEN = "broken"            # 区间被突破（JOC/跌破冰线）
    ARCHIVED = "archived"        # 归档到历史区间库
    REJECTED = "rejected"        # ST否定，候选区间被拒绝（保留在记忆层供进化分析）

class Phase(Enum):
    A = "A"  # 起点确定
    B = "B"  # 区间建设
    C = "C"  # 方向确认
    D = "D"  # 供需确认+突破
    E = "E"  # 趋势运行

class StructureType(Enum):
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    RE_ACCUMULATION = "re_accumulation"
    RE_DISTRIBUTION = "re_distribution"
    UNKNOWN = "unknown"              # C确认前为UNKNOWN

class RangeShape(Enum):
    HORIZONTAL = "horizontal"        # 水平区间
    ASCENDING = "ascending"          # 上斜区间（买方渐强）
    DESCENDING = "descending"        # 下斜区间（卖方渐强）

class Direction(Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"

class EventType(Enum):
    # 极端事件型（模板3）
    SC = "sc"
    BC = "bc"
    # 反弹回落型（模板4）
    AR = "ar"
    # 边界测试型（模板1）
    ST = "st"
    ST_B = "st_b"
    UT = "ut"
    UTA = "uta"
    SPRING = "spring"
    SO = "so"
    UTAD = "utad"
    LPS = "lps"
    LPSY = "lpsy"
    BU = "bu"
    # 供需确认型（模板6）
    SOS = "sos"
    SOW = "sow"
    # 区间突破型（模板2）
    JOC = "joc"
    BREAK_ICE = "break_ice"
    # 渐进供需信号型（模板5）
    MSOS = "msos"
    MSOW = "msow"
    # 回踩确认型（模板7）
    MSOS_TREND = "msos_trend"
    MSOW_TREND = "msow_trend"
    # 事后标注型（模板8）
    PS = "ps"
    PSY = "psy"
    # 假突破回归
    FALSE_BREAKOUT_RETURN = "false_breakout_return"
```

### 4.4 事件（Event）

```python
@dataclass
class Event:
    event_id: str
    event_type: EventType            # 见第6节全表
    event_result: EventResult        # SUCCESS / FAILED / SKIPPED
    
    # 序列信息
    sequence_start_bar: int
    sequence_end_bar: int
    sequence_length: int
    
    # 供需特征
    volume_ratio: float              # 相对于基准均量的比率（区间内事件用B/C阶段均量，区间前事件用趋势均量）
    volume_pattern: str              # "climax" / "drying_up" / "normal" / "weak_reaction"
    effort_vs_result: float# 努力与结果评分 (-1 ~ +1)
    
    # 价格特征
    price_extreme: float
    price_body: float
    penetration_depth: float         # 跌破/突破深度（相对于边界趋势线当前值）
    recovery_speed: float
    
    # 上下文
    range_id: str
    phase: Phase
    position_in_range: float# 0=下沿, 1=上沿（基于趋势线当前值计算）
    
    # 置信度
    confidence: float                # 0-1
    
    # 变体标记
    variant_tag: Optional[str]
    variant_features: Dict

class EventResult(Enum):
    SUCCESS = "success"              # 事件成功确认
    FAILED = "failed"                # 事件尝试但失败（如Spring penetrate但不收回）
    SKIPPED = "skipped"              # 事件被跳过（如C阶段跳过）
```

### 4.5 事件案例（EventCase）

```python
@dataclass
class EventCase:
    """完整的事件案例记录——供记忆层持久化"""
    case_id: str
    timestamp: datetime
    
    # 事件本身
    event: Event
    
    # 区间上下文
    range_snapshot: Dict             # 事件发生时的区间快照（含形状、Creek/Ice）
    range_age_bars: int
    range_width_pct: float
    range_shape: RangeShape
    
    # K线序列
    pre_sequence: List[dict]         # 事件前N根K线 (默认10根)
    sequence: List[dict]             # 事件本身的K线序列
    post_sequence: List[dict]        # 事件后N根K线 (默认20根，回测填充，实盘异步回填)
    
    # penetrate前的量价（C失败分析关键数据）
    pre_volume_trend: str# 接近边界时的量趋势
    pre_price_pattern: str           # 接近边界时的价格模式
    
    # 市场环境
    market_regime: str
    volatility_index: float
    trend_strength: float
    multi_tf_context: Dict
    
    # 后续结果
    result_5bar: float
    result_10bar: float
    result_20bar: float
    max_adverse: float
    max_favorable: float
    
    # 交易表现
    trade_executed: bool
    entry_price: Optional[float]
    exit_price: Optional[float]
    pnl: Optional[float]
    strategy_used: Optional[str]
```

### 4.6 补充数据结构

```python
@dataclass
class CandidateExtreme:
    """SC/BC候选——同一时间只保留一个"""
    candidate_type: str              # "SC" or "BC"
    bar_index: int
    extreme_price: float
    body_price: float
    volume: float
    volume_ratio: float              # 相对趋势均量的倍数
    confidence: float                # 综合置信度 (0~1)
    historical_range_anchor: Optional[str]
    ps_psy_boost: float              # PS/PSY增强因子
    replaced_by: Optional[str]       # 被替换时记录替换者ID


@dataclass
class RuleContext:
    """规则评估时的完整上下文"""
    phase: Phase
    event: Event
    range_ctx: RangeContext
    direction: Direction
    direction_confirmed: bool
    structure_type: StructureType
    entry_trend: Direction
    range_age_bars: int
    phase_age_bars: int


@dataclass
class PhaseTransition:
    """阶段转换记录"""
    from_phase: Phase
    to_phase: Phase
    trigger_event: Event
    trigger_rule: str
    bar_index: int
    timestamp: datetime
    direction_before: Direction
    direction_after: Direction
    notes: str


@dataclass
class EventContext:
    """事件引擎每根K线的输出"""
    new_events: List[Event]
    active_sequences: List[str]
    phase_transition: Optional[PhaseTransition]
    current_phase: Phase
    current_direction: Direction
    structure_type: StructureType


@dataclass
class RuleLogEntry:
    """规则触发日志"""
    bar_index: int
    rule_name: str
    rule_layer: str
    condition_snapshot: Dict
    result: str
    phase_before: Phase
    phase_after: Phase


@dataclass
class BacktestResult:
    """回测输出"""
    event_cases: List[EventCase]
    ranges: List[Range]
    phase_transitions: List[PhaseTransition]
    rule_log: List[RuleLogEntry]
    summary: Dict
```

### 4.7 计算公式

penetration\_depth: 相对于通道宽度的百分比，正值=越过边界

```
penetration_depth = abs(price - boundary_price_at_bar) / channel_width
```

effort\_vs\_result: 威科夫努力与结果法则，-1(大努力小结果) \~ +1(小努力大结果)

```
efficiency = price_change_pct / (volume_ratio * avg_price_change_pct)
effort_vs_result = clamp(efficiency - 1.0, -1.0, +1.0)
```

recovery\_speed: penetrate后收回速度，价格变动百分比/K线数

```
recovery_speed = abs(recovery_price - penetrate_price) / penetrate_price / num_bars
```

position\_in\_range: 价格在区间中的相对位置，0=下边界，1=上边界

```
position_in_range = (price - lower_boundary_at_bar) / (upper_boundary_at_bar - lower_boundary_at_bar)
```

***

## 5. 模块详细设计

### 5.1 历史区间库（HistoricalRangeStore）

**职责**：持久化存储所有历史区间（含REJECTED），提供查询接口

```python
class HistoricalRangeStore:
    def load(self, symbol: str, timeframe: str) -> List[Range]:
        """加载指定品种和时间框架的所有历史区间"""
    
    def save(self, range: Range):
        """保存/更新一个区间"""
    
    def find_nearby_support(self, price: float, symbol: str, tf: str) -> List[Range]:
        """查找当前价格下方的历史支撑区间，按强度排序"""
    
    def find_nearby_resistance(self, price: float, symbol: str, tf: str) -> List[Range]:
        """查找当前价格上方的历史阻力区间，按强度排序"""
    
    def calculate_strength(self, range: Range, current_bar: int) -> float:
        """计算区间的当前强度（含时间衰减+测试消耗）"""
    
    def archive(self, range: Range):
        """将区间归档"""
    
    def reject(self, range: Range):
        """将候选区间标记为REJECTED（保留供进化分析）"""
```

**强度计算公式**（初版，后续进化）：

强度针对每个关键价格点（SC/ST/AR/Creek/Ice边界位置）独立计算：

```
strength = base_strength × time_decay × test_consumption × duration

base_strength = sc_bc_volume_ratio × sc_bc_confidence
# sc_bc_volume_ratio: 形成该关键点的事件成交量 / 趋势中均量（越大=供需转折越剧烈）
# sc_bc_confidence: 形成该关键点的事件置信度(0~1)

time_decay = exp(-bars_since_creation / decay_halflife)  # 指数衰减，非线性
test_consumption =1.15if test_count == 0 else max(0.2, 1.0 - test_count × consumption_rate)
#处女测试（test_count=0）给予15%额外加分，比例为进化参数
# consumption_rate为进化参数
duration = min(2.0, 1.0 + log(duration_bars / 20))
```

### 5.2 区间引擎（RangeEngine）

**职责**：实时区间识别和管理，支持水平/斜线区间

```python
class RangeEngine:
    def __init__(self, store: HistoricalRangeStore):
        self.store = store
        self.active_range: Optional[Range] = None
        self.candidate_extreme: Optional[CandidateExtreme] = None  # 当前候选SC/BC（只保留一个，含type/价格/成交量/置信度）
    
    def process_bar(self, candle: dict, bar_index: int) -> RangeContext:
        """
        每根K线调用一次。
        内部逻辑：
        1. 如果没有活跃区间（趋势运行中）：
           - 持续寻找新SC/BC候选（结合历史区间位置+成交量异常）
           - 新低/新高出现时替换旧候选
           - 检测AR（反弹到Fib位置）
           - 检测ST（判定区间是否成立/否定）
        2. 如果有活跃区间：
           - 计算价格在区间中的位置（基于趋势线当前值）
           - 阶段B：更新区间形状（拟合ST-B高低点趋势线）
           - 阶段B：更新Creek/Ice
           - 检测边界测试/突破
        """
    
    def _update_range_shape(self, bar_index: int):
        """阶段B时调用：基于ST-B高低点拟合趋势线，更新区间形状"""
    
    def _update_creek_ice(self, bar_index: int):
        """阶段B时调用：更新Creek（高点连线）和Ice（低点连线）"""

@dataclass
class RangeContext:
    has_active_range: bool
    active_range: Optional[Range]
    position_in_range: float          # 基于趋势线当前值计算
    distance_to_lower: float          # 距离下边界趋势线当前值的百分比
    distance_to_upper: float          # 距离上边界趋势线当前值的百分比
    nearby_historical_support: List[Range]
    nearby_historical_resistance: List[Range]
    fib_levels: Dict[float, float]
    range_shape: Optional[RangeShape]
    creek_price: Optional[float]      # Creek在当前bar的价格
    ice_price: Optional[float]        # Ice在当前bar的价格
    pending_events: List[Event]       # 待处理事件队列（区间引擎传递给事件引擎）
```

### 5.3 事件引擎（EventEngine）

**职责**：基于区间上下文和K线数据，检测威科夫事件

```python
class EventEngine:
    def __init__(self):
        self.active_detectors: Dict[str, SequenceDetector] = {}  # 按模板类型组织
        self.rule_engine = RuleEngine()  # 规则引擎管理阶段推进
        self.confirmed_events: List[Event] = []
    def process_bar(self, candle: dict, range_ctx: RangeContext, bar_index: int) -> EventContext:
        """
        每根K线调用一次。
        
        关键设计决策：事件检测范围按阶段过滤。
        SOS/SOW只在D阶段检测。B→D跳过C的机制暂不实现。
        """
```

### 5.4 规则引擎（RuleEngine）— 替代线性PhaseManager

```python
class PhaseRule:
    """单条规则"""
    name: str
    condition: Callable[[RuleContext], bool]  # 判断条件
    action: Callable[[RuleContext], PhaseTransition]  # 满足条件时的动作
    priority: int  # 优先级（结构规则>条件规则>超时规则）
    layer: str  # "structural" / "conditional" / "timeout"

class RuleEngine:
    """
    规则引擎——替代线性PhaseManager。
    
    优势：
    - 条件可以包含量价、时间等复杂信息
    - 容易添加新规则
    - 进化系统可以调整规则参数甚至发现新规则
    - 不会死锁（没有匹配规则=保持现状）
    
    规则分层（防冲突）：
    - structural（结构规则）：阶段转换，优先级最高
    - conditional（条件规则）：量价判定，次之
    - timeout（超时规则）：长期无事件，最低
    同层规则不允许冲突。
    """
    
    def __init__(self):
        self.rules: List[PhaseRule] = []
        # 注意：Phase唯一真相源是Range.current_phase，规则引擎不保存current_phase
        self.direction: Direction = Direction.NEUTRAL
        self.direction_confirmed: bool = False
        self.structure_type: StructureType = StructureType.UNKNOWN
        self.rule_log: List[RuleLogEntry] = []  # 每次触发记录，方便调试
    
    def evaluate(self, event: Event, range_ctx: RangeContext) -> Optional[PhaseTransition]:
        """评估所有规则，返回最高优先级匹配的转换建议（不执行转换）"""
    
    def get_direction(self) -> Direction:
        """基于阶段C开关返回当前交易方向"""
```

**核心规则示例**：

```python
# 结构规则：ST确认 → A到B
Rule("ST_confirms_range", 
     condition=lambda ctx: ctx.phase == A and ctx.event.type == ST and ctx.event.result == SUCCESS,
     action=lambda ctx: transition(Phase.B),
     priority=100, layer="structural")

# 结构规则：Spring成功 → B/C到D（C确认）
Rule("Spring_confirms_direction",
     condition=lambda ctx: ctx.phase in [B, C] and ctx.event.type == SPRING and ctx.event.result == SUCCESS,
     action=lambda ctx: transition(Phase.D, direction_confirmed=True),
     priority=100, layer="structural")

# 结构规则：SC/BC设置初始方向
Rule("SC_sets_initial_direction",
     condition=lambda ctx: ctx.event.type == SC,
     action=lambda ctx: set_direction(Direction.SHORT),
     priority=110, layer="structural")

Rule("BC_sets_initial_direction",
     condition=lambda ctx: ctx.event.type == BC,
     action=lambda ctx: set_direction(Direction.LONG),
     priority=110, layer="structural")

# 条件规则：Spring penetrate但不收回 → C失败 → 区间打破
Rule("Spring_failure_breaks_range",
     condition=lambda ctx: ctx.phase in [B, C] and ctx.event.type == SPRING and ctx.event.result == FAILED,
     action=lambda ctx: break_range(),
     priority=80, layer="conditional")

# 结构规则：JOC突破 → D到E
Rule("JOC_starts_trend",
     condition=lambda ctx: ctx.phase == D and ctx.event.type == JOC,
     action=lambda ctx: transition(Phase.E),
     priority=100, layer="structural")

# 结构规则：假突破回归 → E退回B
Rule("false_breakout_recovery",
     condition=lambda ctx: ctx.phase == E and ctx.event.type == FALSE_BREAKOUT_RETURN,
     action=lambda ctx: transition(Phase.B, restore_range=True, mark_joc_failed=True),
     priority=100, layer="structural")

# 结构规则：B阶段边界跌破→ 区间打破 → 趋势接管
Rule("B_phase_boundary_break",
     condition=lambda ctx: ctx.phase == B and ctx.event.type in [ST_B] and ctx.event.result == FAILED,
     action=lambda ctx: break_range(),
     priority=90, layer="structural")
# 不需要超时兜底——价格跌破区间就是兜底机制
```

**Creek/Ice构建规则**：

- C确认前（structure\_type = UNKNOWN）：同时构建Creek和Ice
- C确认后：吸筹保留Creek（JOC突破对象），派发保留Ice（跌破冰线突破对象）

### 5.5 决策层（StrategyEngine）— 识别层完成后开发

```python
class StrategyEngine:
    """
    基于识别层输出做交易决策。
    包含MTF协调器：综合所有TF的识别层输出，评估共振/冲突，
    计算确定性评分和仓位系数。
    区间震荡策略（A/B阶段高位空低位多）也在决策层实现，
    与识别层的方向开关表无关。
    """
    
    def process(self, candle: dict, range_ctx: RangeContext,
                event_ctx: EventContext, bar_index: int) -> Optional[TradeSignal]:
        """根据当前状态选择并执行对应策略"""
```

***

## 6. 事件类型全表

### 6.1 事件检测模板（8种）

**模板1：边界测试型**

```
IDLE → APPROACHING → [PENETRATING] → [HOLDING] → RECOVERING → CONFIRMED→ FAILED
适用事件：Spring, SO, UTAD, ST, ST-B,UT, UTA, LPS, LPSY, BU（10种）
PENETRATING和HOLDING可选（温和测试不penetrate也可能确认）
成功=收回，失败=不收回
```

**模板2：区间突破型**

```
IDLE → APPROACHING → PENETRATING → HOLDING → CONFIRMED（不收回=成功）
                                             → FAILED（收回=失败）
适用事件：JOC, 跌破冰线（2种）
回调不再回到区间 =趋势开启
JOC突破的具体对象（外边界/Creek）影响置信度打分，不能定死，留给进化
```

**模板3：极端事件型**

```
IDLE → DETECTING → CANDIDATE → WAITING_AR → CONFIRMED（AR出现）
                                           → REPLACED（新极值出现）
适用事件：SC, BC（2种）
结合历史区间位置锚点+成交量异常判定置信度
新低/新高出现时旧候选被替换
```

**模板4：反弹回落型**

```
IDLE → BOUNCING → MEASURING → CONFIRMED
适用事件：AR（1种）
用斐波那契衡量反弹力度（起点=前结构阶段C高点，终点=SC）
反弹力度本身是信息（0.318vs 0.5= 不同的供需强度）
```

**模板5：渐进供需信号型**

```
不用序列状态机，用滑动窗口统计
适用事件：mSOS, mSOW（2种）
统计：上涨K线均量 vs 下跌K线均量、价格重心移动、回调深度趋势
综合评分超过阈值 → 标记mSOS或mSOW
是连续信号而非离散事件
```

**模板6：供需确认型**

```
IDLE → DIRECTIONAL_MOVE → WEAK_REACTION → NARROW_CONSOLIDATION → CONFIRMED
                                                                → FAILED
适用事件：SOS, SOW（2种）
SOS/SOW不是突破！是区间内的供需力量确认
SOW表现：UTAD后下跌到关键位置 → 弱反弹（几根K线）→ 超级小幅度横盘
SOS表现：Spring后上涨到关键位置 → 浅回调 → 窄幅横盘
```

**模板7：回踩确认型**

```
IDLE → PULLBACK → HOLDING_ABOVE → CONFIRMED（不破=成功）
                                 → FAILED（破了=失败）
适用事件：MSOS, MSOW（2种）
阶段E，JOC/跌破冰线之后回踩不破 = 供需力量最终确认
```

**模板8：事后标注型**

```
不进入实时序列检测器
SC确认后回扫标注
适用事件：PS, PSY（2种）
作为SC/BC置信度增强因子
```

### 6.2 吸筹侧事件全表

| 事件     | 阶段  | 模板   | 描述                  | 供需特征                |
| ------ | --- | ---- | ------------------- | ------------------- |
| PS     | A   | 事后标注 | SC前的放量阻止下跌          | 买盘首次出现，SC置信度增强因子    |
| SC     | A   | 极端事件 | 恐慌抛售+急跌             | 极端放量+历史区间位置锚点       |
| AR     | A   | 反弹回落 | SC后反弹到Fib位置         | 量能递减                |
| ST     | A→B | 边界测试 | 缩量回测SC区域            | 供应枯竭确认（缩量=成功，放量=失败） |
| ST-B   | B   | 边界测试 | B阶段再次测试下边界（ST附近）    | 验证下边界有效性，构建区间形状     |
| UTA    | B   | 边界测试 | B阶段测试上边界（AR区域）后回落   | 验证上边界有效性，构建Creek锚点  |
| mSOS   | B/C | 渐进供需 | 区间内买方力量渐进变化         | 上涨放量+回调缩量+回调变浅      |
| Spring | C   | 边界测试 | penetrate下沿后收回      | 低量跌破，收回时量增          |
| SO     | C   | 边界测试 | 类Spring但更温和         | 量更小，跌破更浅            |
| SOS    | D   | 供需确认 | Spring后区间内供需确认      | 上涨到关键位置→浅回调→窄幅横盘    |
| LPS    | D   | 边界测试 | Spring后更高低点         | 缩量回测                |
| JOC    | D→E | 区间突破 | 突破区间（外边界/Creek，需打分） | 放量突破+回调不回区间         |
| MSOS   | E   | 回踩确认 | JOC后回踩不破            | 供需力量最终确认            |
| BU     | E   | 边界测试 | 刚突破区间后的回踩（还在区间附近）   | 缩量回踩                |

**D阶段事件时间线（吸筹侧）**：
Spring成功→mSOS（不再跌回下沿）→LPS（弱回调=支撑点）→极度横盘→SOS（强势上涨=供需确认）→JOC（突破）→E阶段→MSOS（回踩不回区间=最终确认）。
**明确LPS≠SOS**：LPS是弱回调的支撑点，SOS是强势上涨的供需确认。

### 6.3 派发侧事件全表

| 事件   | 阶段  | 模板   | 描述                | 供需特征             |
| ---- | --- | ---- | ----------------- | ---------------- |
| PSY  | A   | 事后标注 | BC前的放量阻止上涨        | 卖盘首次出现，BC置信度增强因子 |
| BC   | A   | 极端事件 | 狂热买入+急涨           | 极端放量+历史区间位置锚点    |
| AR   | A   | 反弹回落 | BC后回落到Fib位置       | 量能递减             |
| ST   | A→B | 边界测试 | 缩量回测BC区域          | 需求枯竭确认           |
| ST-B | B   | 边界测试 | B阶段再次测试下边界（AR区域）  | 验证下边界有效性，构建区间形状  |
| UT   | B   | 边界测试 | B阶段测试上边界（BC区域）后回落 | 供应暗示，构建Ice锚点     |

**ST-B位置说明**：ST-B主要在B阶段前期。UT/UTA之后的下边界测试更接近Spring/SO，一般不再标识为ST-B。事件引擎根据区间成熟度（是否已有UT/UTA）判断下边界测试类型。
\| mSOW | B/C | 渐进供需 | 区间内卖方力量渐进变化 | 下跌放量+反弹缩量+反弹变弱 |
\| UTAD | C | 边界测试 | penetrate上沿后收回 | 低量突破，回落时量增 |
\| SOW | D | 供需确认 | UTAD后区间内供需确认 | 下跌到关键位置→弱反弹→窄幅横盘 |
\| LPSY | D | 边界测试 | UTAD后更低高点 | 缩量反弹 |
\| 跌破冰线 | D→E | 区间突破 | 突破区间（外边界/Ice，需打分） | 放量跌破+回调不回区间 |
\| MSOW | E | 回踩确认 | 跌破冰线后回踩不破 | 供需力量最终确认 |
\| BU | E | 边界测试 | 刚突破区间后的回踩（还在区间附近） | 缩量回踩 |

**MSOS/MSOW因果原则说明**：
MSOS/MSOW（回踩确认型）是趋势运行中的回踩（已远离区间）。注意：MSOS/MSOW位置的回踩可能触发区间引擎的SC/BC候选检测——回踩深度够+放量→新区间开始；浅+缩量→MSOS/MSOW确认→趋势继续。这是因果原则的交互点：前一个区间B阶段越长（因）→趋势越强（果）→回踩越浅。

### 6.4 趋势状态（非事件）

趋势不需要独立的检测算法。趋势 = "不在区间中"的状态。

UPTREND：区间突破后（JOC），direction = LONG

DOWNTREND：区间突破后（跌破冰线），direction = SHORT
趋势中系统持续寻找新SC/BC候选，直到新区间形成。

***

## 7. 回测流水线

### 7.1 整体流程

```python
def run_backtest(ohlcv_data: List[dict], 
                 symbol: str, 
                 timeframe: str,
                 historical_ranges: Optional[List[Range]] = None) -> BacktestResult:
    # 初始化
    range_store = HistoricalRangeStore()
    if historical_ranges:
        for r in historical_ranges:
            range_store.save(r)
    
    range_engine = RangeEngine(range_store)
    event_engine = EventEngine()
    memory = MemoryLayer()
    
    # 逐根处理（识别层）
    for i, candle in enumerate(ohlcv_data):
        range_ctx = range_engine.process_bar(candle, i)
        event_ctx = event_engine.process_bar(candle, range_ctx, i)
        memory.record_bar(candle, range_ctx, event_ctx, i)
    
    # 输出（识别层结果）
    return BacktestResult(
        event_cases=memory.get_event_cases(),
        updated_ranges=range_store.get_all(),
        phase_transitions=event_engine.get_phase_log(),
        rule_log=event_engine.rule_engine.rule_log
    )
```

### 7.2 每根K线的处理流水线

```
K线 #N到达
│
├── [区间引擎]
│   ├── 更新价格位置（基于趋势线当前值）
│   ├── 如果阶段B：更新区间形状（拟合趋势线）
│   ├── 如果阶段B：更新Creek/Ice
│   ├── 检测边界接近/突破
│   ├── 查询历史区间库
│   └── 输出: RangeContext
│
├── [事件引擎]
│   ├── 确定检测范围（当前阶段事件 + 可能导致跳过的事件）
│   ├── 推进各模板检测器
│   ├── 供需验证（成交量检查，基准按阶段区分）
│   ├── 事件确认/失败 → 规则引擎评估 → 阶段推进
│   ├── 方向判定（阶段C开关）
│   └── 输出: EventContext
│
└── [记忆层]
    ├── 记录本根K线的完整状态
    ├── 如果有事件确认/失败：创建EventCase
    └── 如果有阶段转换：记录PhaseTransition
```

***

## 8. 记忆层设计

### 8.1 四个持久化存储

```
记忆层
├── 历史区间库(HistoricalRangeStore)
│   ├── 按品种+TF组织
│   ├── 每个区间的完整生命周期记录（含形状、Creek/Ice）
│   ├── 含REJECTED状态的否定候选区间
│   └── 强度打分（含时间衰减）
│
├── 事件案例库 (EventCaseStore)
│   ├── 每个事件的完整案例（成功+失败+跳过）
│   ├── 包含前后K线序列、供需特征、市场环境
│   ├── 包含penetrate前的量价趋势（C失败分析关键）
│   ├── 包含后续结果（5/10/20根K线涨跌）
│   └── 变体标记（初期为空，后续进化时标注）
│
├── 规则日志库 (RuleLogStore)
│   ├── 每次规则触发的完整记录
│   ├── 哪条规则、什么条件、什么结果
│   └── 供调试和进化分析
│
└── 交易记录库 (TradeRecordStore)（决策层完成后使用）
    ├── 每笔交易的完整记录
    ├── 关联到触发交易的事件案例
    └── 策略名称+参数快照
```

### 8.2 存储格式

初版使用JSON文件，每个品种一个目录：

```
wyckoff/data/memory/
├── ETHUSDT/
│   ├── ranges_1D.json
│   ├── ranges_4H.json
│   ├── events.json
│   ├── rule_log.json
│   └── trades.json
├── BTCUSDT/
│   ├── ...
```

***

## 9. 进化方案

### 9.1 渐进式进化路径

**阶段1：先记录** — 每个事件（含失败/跳过）完整记录，不做分类，积累数据
**阶段2：手动变体模板** — 基于数据人工定义3-5种变体，参数通过回测优化
**阶段3：数据驱动发现** — 聚类分析，发现实际分类
**阶段4：相似度检索** — 新事件检索最相似历史案例，动态调整策略

**进化分层设计**：

- **不变层**：基本逻辑（区间识别、方向开关、阶段转换规则）
- **参数层**：阈值权重（penetrate深度、holding时间、volume\_ratio阈值等）
- **变体层**：聚类发现（通过数据驱动发现新的变体分类）
- **策略层**：交易策略（止盈止损、仓位分配、风险管理）

**进化机制**：宽松初始规则 → 莱恩标注 → 参数优化 → 变体聚类

### 9.2 什么需要进化，什么不需要

| 类别          | 是否需要进化 | 说明                             |
| ----------- | ------ | ------------------------------ |
| 区间识别逻辑      | 否      | 基于价格运动的第一性原理                   |
| 方向开关逻辑      | 否      | 阶段C的方向规则是固定的                   |
| 规则引擎的规则参数   | 是      | 条件中的阈值（penetrate深度、holding时间等） |
| 事件变体识别      | 是      | 不同变体需要不同的检测参数                  |
| JOC突破对象打分权重 | 是      | 外边界/Creek的权重，加密偏向区间            |
| 斐波那契权重      | 是      | 不同市场环境可能不同                     |
| 区间强度衰减系数    | 是      | 需要历史数据验证                       |
| 序列长度阈值      | 是      | 不同级别的区间可能不同                    |
| 止盈比例        | 是      | 通过回测数据优化                       |
| 仓位分配        | 是      | 通过回测数据优化                       |

### 9.3 变体案例

**温和UTAD**：不penetrate但确认方向（高量突破后快速回落，但未越过边界）
**极速SC-AR**：几天完成（常见于小级别区间或高波动市场）
**延迟ST**：AR后很久才出现（长时间震荡后才回测边界）
**ST-B未到下边界**：中轨就拉回（区间上斜，下边界抬升）

***

## 附录：关键设计决策记录

| 编号    | 决策                                      | 原因                                       | 日期         |
| ----- | --------------------------------------- | ---------------------------------------- | ---------- |
| RD-1  | 区间是基础设施，先于状态机                           | 因果关系反转                                   | 2026-04-01 |
| RD-2  | 第一根K线即起点                                | 消除递归依赖                                   | 2026-04-01 |
| RD-3  | 阶段C是方向开关                                | 市场情绪转折点                                  | 2026-04-01 |
| RD-4  | 系统永远有立场                                 | 不存在空仓等待                                  | 2026-04-01 |
| RD-5  | 极限价格+实体价格双候选边界                          | 影线和收盘提供不同信息                              | 2026-04-01 |
| RD-6  | ST是区间判定门                                | 撑住=确立，失败=重新寻找                            | 2026-04-01 |
| RD-7  | 事件是多根K线序列                               | 需要序列状态机                                  | 2026-04-01 |
| RD-8  | 再吸筹/再派发递归同构                             | 同一套逻辑                                    | 2026-04-01 |
| RD-9  | 变体进化先记录再分类                              | 先积累数据                                    | 2026-04-01 |
| RD-10 | 删除TRDetector百分位逻辑                       | 与区间理论冲突                                  | 2026-04-01 |
| RD-11 | 供需=区间位置+成交量异常                           | SC/BC=关键位置+异常放量                          | 2026-04-01 |
| RD-12 | 斐波那契用于预判+诊断+UTAD预测                      | 预判AR力度，诊断供需，预测UTAD高点                     | 2026-04-01 |
| RD-13 | SOS/SOW是供需确认不是突破                        | SOS在区间内，JOC才是突破                          | 2026-04-01 |
| RD-14 | 五大阶段可跳过/可失败                             | PhaseManager用规则引擎替代线性推进                  | 2026-04-01 |
| RD-15 | 初版必须支持斜线区间                              | 区间斜率动态变化，不支持斜线无法正确识别                     | 2026-04-01 |
| RD-16 | Creek/Ice在阶段B自然形成                       | B阶段高低点连线                                 | 2026-04-01 |
| RD-17 | 识别层与决策层分离                               | 先做识别层做对，再开发交易策略                          | 2026-04-01 |
| RD-18 | PS/PSY作为SC置信度增强因子                       | 不独立检测，SC出现时回扫标注                          | 2026-04-01 |
| RD-19 | JOC突破对象不定死                              | 外边界/Creek打分权重留给进化                        | 2026-04-01 |
| RD-20 | 非标准路径完整记录                               | 进化系统的燃料                                  | 2026-04-01 |
| RD-21 | ST判定综合量价不固定标记                           | 固定标记会误杀和漏判                               | 2026-04-01 |
| RD-22 | 成交量基准按阶段区分                              | 区间内用B/C均量，区间前用趋势均量                       | 2026-04-01 |
| RD-23 | 候选SC新低替换                                | 同一时间只保留一个候选                              | 2026-04-01 |
| RD-24 | 否定候选区间保留记忆层                             | REJECTED状态，供进化分析                         | 2026-04-01 |
| RD-25 | C成功后D几乎必然（加密市场）                         | C是最关键决策点                                 | 2026-04-01 |
| RD-26 | 三点定区间=通道模型                              | SC→ST定斜率，平移到AR=上边界，上下平行                  | 2026-04-01 |
| RD-27 | UT/UTA恢复为独立事件                           | UT(派发)/UTA(吸筹)测试上边界，ST-B测试下边界            | 2026-04-01 |
| RD-28 | SOS/SOW锁定D阶段                            | 即将突破才出现，B→D跳过C暂不实现                       | 2026-04-01 |
| RD-29 | SC/BC设置初始方向                             | SC→SHORT，BC→LONG，C确认后翻转                  | 2026-04-01 |
| RD-30 | 区间边界是区域不是精确线                            | extreme/body都是打分因素，penetrate深度影响置信度      | 2026-04-01 |
| RD-31 | 因果定律：B阶段时间决定趋势幅度                        | 时间阈值为进化参数                                | 2026-04-01 |
| RD-32 | 通道斜率不修正                                 | 三点定了就固定，ST-B偏离影响事件置信度不影响通道               | 2026-04-01 |
| RD-33 | PSY权重高于PS                               | 正式派发一般有PSY（情绪原因）                         | 2026-04-01 |
| RD-34 | 假突破回归：E→B退回                             | JOC确认后价格回到旧区间→区间恢复ACTIVE→阶段退回B→方向不变      | 2026-04-01 |
| RD-35 | 双候选边界打分暂缓                               | 通道锚点用body还是extreme作为进化参数，回测时两种都试         | 2026-04-01 |
| RD-36 | 三大引擎职责边界                                | 区间引擎=区间形成事件+生命周期，事件引擎=区间内事件，规则引擎=阶段转换+方向 | 2026-04-01 |
| RD-37 | 冷启动：第一根K线作为候选SC/BC，NEUTRAL方向，不交易        | 仅回测存在                                    | 2026-04-02 |
| RD-38 | structure\_type通过entry\_trend+C事件类型自然推导 | 不需要特别判定逻辑                                | 2026-04-02 |
| RD-39 | B阶段边界跌破→区间BROKEN→趋势接管                   | 价格运动本身是兜底，不需要超时规则                        | 2026-04-02 |
| RD-40 | 通道锚点默认使用extreme（影线）                     | 进化参数，初版用extreme                          | 2026-04-02 |
| RD-41 | SO与Spring区别留给进化参数                       | SO可能是"没有C阶段"的体现                          | 2026-04-02 |
| RD-42 | BU=刚突破回踩，MSOS/MSOW=趋势中回踩                | MSOS/MSOW可能触发SC/BC候选（因果交互）               | 2026-04-02 |
| RD-43 | 多TF不否决任何信号，用仓位表达确定性                     | 日线3x/4H=1x/1H=0.5x（进化参数）                 | 2026-04-02 |
| RD-44 | 三种共振全部需要（阶段/位置/方向）                      | 共振→确定性↑→仓位↑                              | 2026-04-02 |
| RD-45 | 识别层每TF独立，决策层MTF协调器统一                    | 记忆层跨TF共享                                 | 2026-04-02 |
| RD-46 | 进化参数只声明存在和含义，不定义具体值                     | 初版给默认值，回测进化                              | 2026-04-02 |
| RD-47 | 区间震荡策略是决策层的事                            | 不影响识别层方向开关表                              | 2026-04-02 |
| RD-48 | C是确认性事件，几根K线就结束                         | Phase.C用于标记事实，不需要B→C转换规则                 | 2026-04-02 |
| RD-49 | AR确认需要几根日线+相对大涨幅+关键阻力                   | 死猫跳不是AR，需要量价参与                           | 2026-04-02 |
| RD-50 | SC→AR→ST序列新低可能是下斜区间的ST                  | 新低有阻力+量比SC低→ST比SC低=下斜                    | 2026-04-02 |
| RD-51 | B阶段同时检测C阶段事件                            | Spring/UTAD成功=C完成=直接进入D                  | 2026-04-02 |
| RD-52 | Phase唯一真相源是Range.current\_phase         | 规则引擎只读取+返回转换建议                           | 2026-04-02 |
| RD-53 | Event传递机制：区间引擎→事件引擎→规则引擎                | pending\_events字段传递                      | 2026-04-02 |
| RD-54 | 进化分层：不变层/参数层/变体层/策略层                    | 初版宽松规则→莱恩标注→参数优化→变体聚类                    | 2026-04-02 |
| RD-55 | 初版采用宽松规则+莱恩标注驱动进化                       | 不追求初版完美，追求可进化                            | 2026-04-02 |

***

> **文档版本**: v3.1
> **作者**: WyckoffInspector (系统第二大脑)
> **理论来源**: 莱恩先生
> **日期**: 2026-04-02（v3.0修订）
> **状态**: 基于v2.0审阅后的全部修正，待莱恩先生审阅确认
> **变更摘要**:
>
> - 新增：区间形状（水平/上斜/下斜）+趋势线边界+初版必须支持
> - 新增：Creek/Ice定义+阶段B自然形成
> - 新增：供需三级递进（mSOS→SOS→MSOS）
> - 修正：SOS/SOW从"突破"改为"区间内供需确认"
> - 修正：JOC/跌破冰线才是区间突破
> - 修正：PhaseManager从线性推进改为规则引擎
> - 修正：五大阶段可跳过/可失败（非线性路径）
> - 新增：PS/PSY作为SC置信度增强因子
> - 新增：8种事件检测模板（替代通用序列状态机）
> - 新增：非标准路径记录机制
> - 修正：识别层与决策层分离
> - 新增：REJECTED状态+否定候选区间保留
> - 新增：斐波那契预测UTAD高点
> - 新增：25条关键设计决策记录
>   **新增变更（2026-04-02）**:
> - 新增：冷启动协议（§1.3.1）
> - 新增：structure\_type自然推导逻辑（§2.7.1）
> - 新增：三大引擎调用关系+假突破回归流程（§3.2）
> - 新增：多时间框架架构+仓位方案+三种共振（§3.3）
> - 新增：EventType枚举+6个补充数据结构+4个计算公式（§4）
> - 新增：B阶段边界跌破规则+Creek/Ice构建规则（§5.4）
> - 修正：趋势从"事件"改为"状态"（§6.4）
> - 修正：BU定义明确化+MSOS/MSOW因果原则交互（§6.2/6.3）
> - 新增：RD-37\~RD-47共11条设计决策

---

## v3.1 更新记录（2026-04-09）

>基于4/6~4/8与莱恩先生的多轮讨论，以下内容更新/补充了v3.0的对应章节。
> 理论框架（55条RD）全部有效，无一推翻。以下是细节修正和认知补充。

### 更新1: §1.3.1 冷启动协议修正

**原文**：第一根K线的高低点作为初始候选SC/BC，direction=NEUTRAL

**修正**：
- **实盘**：莱恩不做无历史区间的标的——"没有底或顶，我不敢"。系统启动前提是已有足够历史数据建立第一个区间。第一个区间通过莱恩标注建立（标注工作台主路径）。
- **回测（fallback）**：保留原协议。第一个区间通过SC→AR→ST三点识别，位置维度权重归零（RD-58）。

### 更新2: §2.1 AR确认逻辑补充

在原文"死猫跳不是AR。需要量价参与"之后补充：

- **AR量价特征**：成交量逐步递减的上升，到最高点缩量+遇阻力。AR量一般比SC小
- **AR看双方**：上方有卖压+ 下方支撑区间转阻力（散户情绪/换手程度）
- **弱AR = 可能是下跌中继**，还在趋势内，不是区间。AR的强弱是第一道过滤器
- AR的真假要等ST来判，AR和ST是一个整体
- 前提条件：SC和ST看支撑区间，AR看阻力区间。没有历史区间 = 没有锚点

### 更新3: §2.8 成交量基准细化

补充以下内容：

- **阶段绑定均量（RD-56）**：均量计算使用阶段绑定累加器，每次阶段转换重置，不用滑动窗口。"为什么用最近N根均量，而不是UTAD之后的趋势量？"——滑动窗口太粗糙，应和阶段/趋势绑定
- **SOW/LPSY两层基准（RD-59）**：①局部基准（当前阶段均量）②区间基准（BC/AR/ST量级）。D阶段下跌中的"放量"不需要和BC/AR/ST比，SOW/LPSY的量只需要在局部"显著偏大"
- **SC/BC前趋势量特征**：越来越大（集中释放），能启动盘整的K线一般是趋势里偏大甚至很大的

### 更新4: §2.11 历史区间强度修正

- **删除时间衰减因子（RD-57）**：不是时间让支撑变弱，而是后续事件让支撑变弱或失效
- **改为事件驱动强度变化**：测试成功=增强（×strengthen_factor），测试失败=削弱（×weaken_factor），跌破=归零翻转
- 莱恩原话："如果位置差不多，强度为什么变化？它本身就会在这里停下。"
- **核心认知**："与其说强度，不如说在什么位置做什么事"

### 更新5: §5.1 强度计算公式修正

原公式中`time_decay = exp(-bars_since_creation / decay_halflife)` 删除。

修正后：
```
strength = base_strength × event_modifier × test_consumption × duration

event_modifier = 1.0  # 初始值
# 测试成功 → event_modifier *= strengthen_factor (进化参数，初版1.15)
# 测试失败 → event_modifier *= weaken_factor (进化参数，初版0.7)
# 跌破 → event_modifier = 0（归零）
```

### 更新6: §9进化方案 — 方法论转变

**旧方法**：写算法→跑数据→看结果→调参数（盲人摸象）
**新方法**：人工标注→从标注中学习→提取规则→写算法（有靶子再射箭）

- **引擎是学习框架，不是自动检测器**（ED-1）。智慧来自莱恩标注，不来自预设规则
- **RD-55的真正含义**：初版几乎不过滤 → 莱恩标注=过滤器 → 进化收紧参数 → 噪音减少
- **系统学习的对象**：不是"SC长什么样"，而是"在什么场域条件下，状态A转换到状态B"
- **进化闭环**：标注 → EventCase → 案例库 → 统计优化(百分位数) → 参数 → 引擎热加载 → 更精准候选 → 莱恩修正 → 循环
- **修正案例权重=3.0**（EVD-5）：莱恩修正引擎错误 = 最高价值学习信号

### 新增: §2.15莱恩核心交易认知

以下认知来自4/6~4/8的多轮讨论，是系统算法的真相源：

1. **位置驱动，不是K线驱动**："上来直接看到的就是区间，而不是K线"。判断流程：历史区间 → 支撑阻力地图 → 当前价格位置 → K线形态 → 成交量 → 趋势整体 → 多TF交叉验证
2. **健康趋势 = 量价同步 + 回调缩量**：上涨时放量、回调时缩量=健康。反之=不健康=可能是趋势末端
3. **极端黑天鹅**：单根K线可看作SC，日线内反弹=AR，然后等ST
4. **置信度→仓位**：测试次数越多 → 支撑越可信 → 仓位越大
5. **SC/BC需要持续优化**："没有那种是市场通用的"——进化系统的核心目标之一
6. **方法论极限**：莱恩的交易判断是多维度同时运作的直觉，无法逐条拆解为规则。正确路径是标注驱动
7. **引擎定位（ED-1）**：引擎是学习框架，不是自动检测器

### 新增设计决策 RD-56 ~ RD-59

| 编号 | 决策 | 原因 | 日期 |
|------|------|------|------|
| RD-56 | 成交量基准改为阶段绑定均量 | 滑动窗口太粗糙，应和阶段/趋势绑定 | 2026-04-06 |
| RD-57 | 删除时间衰减，改为事件驱动强度变化 | 不是时间让支撑变弱，而是后续事件 | 2026-04-06 |
| RD-58 | 第一个区间SC→AR→ST三点识别，位置权重归零 | 第一个区间没有历史区间，位置锚点不可用 | 2026-04-06 |
| RD-59 | SOW/LPSY用两层成交量基准（局部+区间） | D阶段放量不需要和BC/AR/ST比 | 2026-04-06 |

> **v3.1变更摘要（2026-04-09）**:
> - 修正：冷启动协议区分实盘/回测（§1.3.1）
> - 补充：AR量价特征+弱AR判断（§2.1）
> - 补充：阶段绑定均量+两层基准（§2.8, RD-56/59）
> - 修正：时间衰减→事件驱动强度（§2.11, §5.1, RD-57）
> - 补充：方法论转变——标注驱动进化（§9, ED-1）
> - 新增：§2.15 莱恩核心交易认知（7条）
> - 新增：RD-56~59（4条设计决策）