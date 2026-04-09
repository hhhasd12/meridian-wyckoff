#供需力量对比检测器设计文档

> 来源：2026-04-09 WyckoffInspector与莱恩的设计讨论
> 统一检测器，覆盖：SOS/SOW/LPSY/LPS/MSOS/MSOW/mSOS/mSOW

## 1. 定位

**一个检测器，多种事件。**

检测器检测的是统一的模式：**"方向移动 → 反向运动质量 → 窄幅横盘"**。
产出一个通用的"供需力量对比事件"，由**规则引擎根据上下文（阶段+位置+方向）命名**为具体的事件类型。

### 检测器产出 vs 规则引擎命名

| 规则引擎命名 | 阶段 | 位置 | 系统角色 |
|---|---|---|---|
| mSOS/mSOW | B/C阶段 | 区间内 | 渐进暗示，积累方向确定性 |
| SOS/SOW | D阶段 | 区间内 | 供需确认，确认方向|
| LPSY/LPS | D阶段 |靠近边界 | 增加breakout确定性 |
| MSOS/MSOW | E阶段 |区间外（JOC后） | 趋势确认，回踩撑住 |

## 2. 核心设计理念

### 2.1 本质是"方向性力量对比"

**弱势方向（SOW/LPSY/MSOW）：**
- 价格跌到区间下部，抄底的人来了
- 但越往高位，抛压越大 — 主力迫不及待地卖
- 往上走一点就有抛压出现
- =涨不回去

**强势方向（SOS/LPS/MSOS）：**
- 价格回调，但跌不下去
- 没人卖，筹码锁定
- 同一位置反复撑住
- = 跌不下去

### 2.2 威科夫第一定律：努力与结果

-量大但价格没动 = effort_vs_result低= 弱势
- 量小但价格动了 = effort_vs_result高 = 强势

### 2.3 三段式模式

所有供需事件都遵循：
```
方向移动（一段明确的涨或跌）→ 弱反向运动（反弹/回调质量差）
    → 窄幅横盘（在一个区域盘整，走不动了）
```

## 3. SOS实盘解剖（莱恩的ETH上斜吸筹图）

**四层信息：**
1. **巨量阴线砸到区间中线** — 卖方集中释放，但砸不穿中线
2. **后续阴线递减→红绿转变** — 卖方衰竭，买方渗透
3. **同一位置反复跌不下去** — 多根K线低点在同一水平，支撑反复确认
4. **缩量环境中出现买方量脉冲** — 有人在这个位置主动买入

## 4. 量化特征提取

### 4.1 方向移动检测
- `move_direction`: 上/下
- `move_magnitude`: 移动幅度（价格变化百分比）
- `move_bars`: 移动持续K线数
- `move_volume_profile`: 移动过程中的成交量分布

### 4.2 反向运动质量
- `retracement_ratio`: 反弹幅度 / 下跌幅度（或回调幅度 / 上涨幅度）
- `effort_vs_result`: price_change / (volume_ratio × avg_change)
- `bar_type_shift`: 阴阳线比率的滑动窗口变化（阴线占比从高→低 = 转强）
- `volume_decay`: 反向运动中的成交量衰减趋势

### 4.3 窄幅横盘
- `consolidation_range`: 横盘区域的高低点范围（占区间宽度比例）
- `low_consistency`: 多根K线低点的标准差（越小=支撑越一致）
- `high_consistency`: 多根K线高点的标准差（越小=阻力越一致）
- `consolidation_bars`: 横盘持续K线数

### 4.4 量价转变
- `buy_sell_volume_ratio`: 买方量/卖方量比率
- `volume_pulse`:缩量环境中的量脉冲（突然出现的买方/卖方量）
- `volume_trend`: 整体成交量趋势（缩量/放量/平稳）

### 4.5 位置
- `position_in_range`: 当前价格在区间中的相对位置（0=底部, 1=顶部）
- `distance_to_boundary`: 距离最近边界的距离

## 5. 状态机

```
IDLE
  │
  │检测到方向移动（幅度 > move_threshold）
  ▼
MOVE_DETECTED
  │
  │ 方向移动结束，开始反向运动
  ▼
EVALUATING_RESPONSE
  │
  ├─ 反向运动强（retracement_ratio > strong_threshold）→ IDLE（不是供需信号）
  │
  ├─ 反向运动弱 + 进入窄幅横盘 → CANDIDATE
  │     │
  │     │ 产出 SUPPLY_DEMAND_SIGNAL事件
  │     │ 携带：方向 + 特征数据 + 位置
  │     │
  │     │ 规则引擎接收后根据上下文命名：
  │     │   D阶段+区间内→ SOS/SOW
  │     │   D阶段+靠近边界 → LPS/LPSY
  │     │   E阶段+JOC后 → MSOS/MSOW
  │     │   B/C阶段 → mSOS/mSOW
  │     ▼
  │   CONFIRMED
  │
  └─ 超时未进入横盘 → IDLE（重置）
```

## 6. 进化参数

| 参数 | 含义 | 初版默认值 | 备注 |
|------|------|-----------|------|
| `move_threshold` | 多大的移动才算"方向移动" | 0.02 (2%) | 极宽松 |
| `move_window` | 检测移动的K线窗口 | 10 | |
| `strong_retracement` | 反弹比率超过多少算"强反向"（=不是供需信号） | 0.7 (70%) | |
| `consolidation_threshold` | 横盘区域多窄算"窄幅" | 0.03 (3%) | 占区间宽度 |
| `min_consolidation_bars` | 最少横盘多少根K线 | 3 | |
| `effort_result_threshold` | effort_vs_result低于多少算"弱势" | 0.5 | |
| `volume_decay_threshold` | 成交量衰减多少算"缩量" | 0.6 | 相对于移动期均量 |
| `boundary_proximity` | 多近算"靠近边界"（用于LPSY/LPS判定） | 0.15 (15%) | 占区间宽度 |

**所有参数暴露给进化系统。** 初版极宽松（RD-55）。
不同事件类型可能需要不同参数阈值——这是进化系统的分组优化（按事件类型分组）。

## 7. 与其他模块的接口

### 7.1 输入依赖
- **K线数据**：实时K线流
- **区间引擎**：当前ACTIVE区间的Range对象（边界、宽度、Creek/Ice）
- **规则引擎**：当前阶段（用于事件命名）

### 7.2 输出
- `SUPPLY_DEMAND_SIGNAL` 事件
- 携带：方向(BULLISH/BEARISH) + 强度(effort_vs_result值) + 位置 + 全部特征数据

### 7.3 下游消费者
- **规则引擎**：根据阶段+位置命名事件 → 推进阶段/积累确定性
- **进化系统**：case_builder从事件构建EventCase

## 8. 代码结构建议

文件位置：`src/plugins/engine/detectors/supply_demand.py`

```python
class SupplyDemandDetector:
    """供需力量对比检测器 - 统一检测SOS/SOW/LPSY/LPS/MSOS/MSOW/mSOS/mSOW"""
    
    def __init__(self, params: dict):
        self.state = "IDLE"
        self.params = params
        self.move_start = None
        self.move_direction = None
        self.move_bars = []
        self.response_bars = []
    
    def update(self, bar, range_obj) -> Optional[Event]:
        """每根K线调用一次"""
        # 1. 状态机转换
        # 2. 方向移动检测
        # 3. 反向运动质量评估
        # 4. 窄幅横盘检测
        # 5. 特征提取
        # 6. 产出事件
    
    def _detect_move(self, bars) -> Optional[dict]:
        """检测方向移动"""
    
    def _evaluate_response(self, move, response_bars) -> dict:
        """评估反向运动质量"""
        # effort_vs_result
        # retracement_ratio
        # bar_type_shift
    
    def _detect_consolidation(self, bars) -> Optional[dict]:
        """检测窄幅横盘"""
        # low_consistency
        # high_consistency
        # consolidation_range
    def _extract_features(self, bar, range_obj) -> dict:
        """提取全部特征给进化系统"""
    
    def reset(self):
        """重置状态机"""
```

## 9. 规则引擎命名逻辑（需要在规则引擎中实现）

```python
def classify_supply_demand_signal(signal_event, current_phase, range_obj):
    """将通用供需信号命名为具体事件类型"""
    
    position = signal_event.position_in_range
    direction = signal_event.direction
    is_near_boundary = position > (1 - boundary_proximity) or position < boundary_proximity
    
    if current_phase == "E":
        return "MSOS" if direction == "BULLISH" else "MSOW"
    
    if current_phase == "D":
        if is_near_boundary:
            return "LPS" if direction == "BULLISH" else "LPSY"
        else:
            return "SOS" if direction == "BULLISH" else "SOW"
    
    # B/C阶段
    return "mSOS" if direction == "BULLISH" else "mSOW"
```

## 10. 注意事项

1. **不硬编码量价方向** — 弱势可以有量（努力但没结果），也可以缩量（没人买）
2. **检测器不命名事件** — 只产出通用信号，命名是规则引擎的事
3. **初版宽松** — 所有参数极宽松，让进化来收紧
4. **参数分化** — 未来进化系统可以按事件类型分组优化不同阈值
5. **位置很重要** — SOS通常在区间中部偏上，SOW在中部偏下，LPSY靠近边界
6. **事件链上下文** — 记录prior_events（EVD-10），供需信号的价值依赖前置事件