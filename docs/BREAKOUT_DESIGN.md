# Breakout检测器设计文档

> 来源：2026-04-09 WyckoffInspector与莱恩的设计讨论，基于三张实盘图驱动。

## 1. 定位

Breakout检测器 = **事件引擎的检测器**（8种检测模板之一：区间突破型）。

**只做一件事：检测"价格是否离开了区间"。**

- 不判断阶段（规则引擎管）
- 不判断方向（规则引擎管）
- 不做交易决策（决策层管）
- 不硬编码量价要求（进化系统管）

产出：BREAKOUT事件（CANDIDATE → CONFIRMED/FAILED）

## 2. 核心设计理念（来自莱恩的交易直觉）

### 2.1 突破的本质是"无阻力"

突破不是"价格穿越了一条线"。
突破是"价格到了之前有阻力的地方，这次无阻力通过"。

之前每次碰到Creek都被打回来（有阻力）→ 这次没被打回 → 这就是JOC。

### 2.2 突破不一定需要放量

存在两种合法的突破模式：

**模式A - 缩量突破：**
- 长时间区间（如195天）→浮动筹码被反复换手→ 弱手出局
- 区间末期成交量急剧缩减（浮筹清空的证据）
- 突破时小量就能推动（没有对手盘了）
- 量价序列：区间早期量大→ 逐步缩减 → 末期极度萎缩 → 突破时小量回升

**模式B - 放量突破：**
- 大资金主动推动 → 大量冲过边界 → 力度压倒阻力

两种都是合法JOC。**禁止硬编码"放量才算突破"**——交给进化系统从标注中学习。

### 2.3 Creek/Ice不一定是长期趋势线

-吸筹区间的Creek通常比较清晰（B阶段反弹高点连线）
- 派发区间的Ice可能非常短暂——可能只是最后一个LPSY位置形成的几天支撑
- 吸筹和派发存在不对称性

### 2.4 Breakout是事件链条的最后一环

莱恩的核心哲学："用确定性的事件，预测后续可能的事件，然后应对。"

BC → ST → UT → LPSY → SOW → **breakout**

前面每一步都在增加"接下来会breakout"的确定性。Breakout检测器不需要自己判断链条——它只管最后一步。

### 2.5 Breakout与边界测试是同一硬币的两面

- 边界测试：价格接近边界 → 被打回 → 有阻力 → 区间还在
- Breakout：价格接近边界 → 没被打回 → 无阻力 → 区间结束

同一个触发点，不同的结果。

## 3. 边界定义：三级退回

检测器需要知道"边界在哪"。按优先级：

1. **优先：莱恩画的Creek/Ice**（标注数据中的线段，最准确）
2. **其次：引擎拟合的Creek/Ice**（区间引擎在B阶段自动拟合的趋势线）
3. **兜底：区间通道边界**（三点定区间的上下轨，永远存在）

实现时：从区间的Range数据结构中获取。Creek/Ice是TrendLine对象（有slope和intercept），支持斜线。每根K线需要用`price_at(bar_index)` 计算当前边界价格。

## 4. 状态机

```
IDLE│
  │价格进入边界附近区域（距离 < approach_zone）
  ▼
APPROACHING
  │
  │ 收盘价越过边界
  ▼
CANDIDATE  ──→产出BREAKOUT_CANDIDATE事件
  │
  ├─ 价格回到区间内 ──→ FAILED（假突破）
  │                产出 BREAKOUT_FAILED 事件
  │
  ├─ 回踩边界不破 ──→ CONFIRMED（事件确认）
  │                     产出 BREAKOUT_CONFIRMED 事件
  │
  └─ 远离超过阈值 ──→ CONFIRMED（距离确认）
                产出 BREAKOUT_CONFIRMED 事件
```

**确认方式支持两种**（哪种更好交给进化）：
- 事件确认：回踩边界不破
- 距离确认：价格远离边界超过 confirm_distance

## 5. 特征提取（给进化系统）

每个BREAKOUT事件产出时，提取以下特征存入EventCase：

### 5.1 突破时刻
- `penetration_depth`: 收盘价超过边界的深度（百分比）
- `breakout_bar_volume_ratio`: 突破K线成交量 / 近期均量
- `bar_body_ratio`: K线实体占比（实体/振幅）
- `bar_direction`: K线方向（阳/阴）

### 5.2 突破前背景
- `range_duration`: 区间持续时间（K线数量）
- `volume_trend`: 末期成交量趋势（缩量/放量/平稳）
- `boundary_test_count`: 之前测试该边界的次数
- `last_test_distance`: 距离上次测试的K线数

### 5.3 突破后行为
- `has_pullback`: 是否发生回踩
- `pullback_depth`: 回踩深度
- `pullback_volume_ratio`: 回踩时的量价比
- `departure_speed`: 远离速度（N根K线内的价格变化率）

### 5.4 事件链上下文（EVD-10）
- `prior_events`: 区间内已发生的事件列表（如["BC","ST","UT","LPSY","SOW"]）
- `current_phase`: 当前阶段
- `range_shape`: 区间形状（水平/上斜/下斜）

## 6. 进化参数

| 参数 | 含义 | 初版默认值 | 备注 |
|------|------|-----------|------|
| `approach_zone` | 多近算"接近边界"（占区间宽度的比例） | 0.15 (15%) | 宽松|
| `breakout_depth` | 穿越多深算候选（占区间宽度的比例） | 0.02 (2%) | 极宽松，几乎收盘过线就算 |
| `confirm_distance` | 远离多远自动确认（占区间宽度的比例） | 0.10 (10%) | |
| `confirm_bars` | 持续多久不回来算确认 | 5 |备用，优先用事件确认 |
| `volume_context_window` | 计算量价背景的窗口长度 | 20 | |
| `return_threshold` | 回来多深算假突破（占穿越深度的比例） | 0.8 (80%) | 回来80%以上算失败 |

**所有参数都暴露给进化系统。** 初版默认值设极宽松（RD-55原则）。

## 7. 与其他模块的接口

### 7.1 输入依赖
- **区间引擎**：当前ACTIVE区间的Range对象（包含Creek/Ice TrendLine、通道边界）
- **K线数据**：实时K线流
- **标注数据**（可选）：莱恩画的Creek/Ice线段

### 7.2 输出
- BREAKOUT_CANDIDATE / BREAKOUT_CONFIRMED / BREAKOUT_FAILED 事件
- 事件携带：方向（UP/DOWN）、边界类型（CREEK/ICE/CHANNEL）、特征数据

### 7.3 下游消费者
- **规则引擎**：根据breakout事件推进阶段（D→E）或退回（E→B假突破）
- **区间引擎**：根据规则引擎判决更新区间状态（ACTIVE→BROKEN）
- **进化系统**：case_builder从breakout事件构建EventCase

## 8. 代码结构建议

文件位置：`src/plugins/engine/detectors/breakout.py`

```python
class BreakoutDetector:
    """区间突破检测器 - 检测价格是否离开区间"""
    
    def __init__(self, params: dict):
        self.state = "IDLE"  # IDLE/APPROACHING/CANDIDATE
        self.params = params  # 进化参数
        self.candidate_bar = None  # CANDIDATE状态开始的K线
        self.boundary_value = None  # 当前边界价格
        self.boundary_type = None  # CREEK/ICE/CHANNEL
        self.direction = None  # UP/DOWN
    def update(self, bar, range_obj) -> Optional[Event]:
        """每根K线调用一次，返回事件或None"""
        # 1. 获取边界（三级退回）
        # 2. 状态机转换
        # 3. 特征提取
        # 4. 产出事件
    
    def _get_boundary(self, range_obj, bar_index) -> Tuple[float, str]:
        """三级退回获取边界价格"""
        # 优先Creek/Ice →兜底通道边界
    
    def _extract_features(self, bar, range_obj, bars_history) -> dict:
        """提取特征给进化系统"""
    
    def reset(self):
        """重置状态机"""
```

## 9. EVD-10：事件链依赖

**新设计决策**：EventCase增加 `prior_events` 字段。

### 实现要求
1. `case_builder.py` 的 `build_case()` 增加 prior_events 采集逻辑
2. `case_store.py` 的 event_cases 表增加 prior_events 列（JSON格式存储）
3. `optimizer.py` 初版不改——等数据积累后再加分组优化逻辑

### 未来演进路径
- 第一步（现在）：数据结构预留，先记录不用于优化
- 第二步（积累后）：optimizer按事件链上下文分组统计
- 第三步（成熟期）：链条完整度影响检测器敏感度

## 10. 注意事项

1. **不要硬编码量价要求** —缩量突破和放量突破都是合法的
2. **斜线边界** — Creek/Ice可以是斜的，每根K线要重新计算边界价格
3. **阶段不设硬性前提** — 不要求"必须在D阶段"，任何阶段都可以检测穿越
4. **初版宽松** — 所有参数设极宽松默认值，让进化来收紧
5. **检测器只举证不推进** — 产出事件，不直接修改阶段或区间状态