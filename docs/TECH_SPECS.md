# 威科夫全自动逻辑引擎 - 技术规范

## 1. 内部数据格式规范 (事实标准)

### 1.1 DataFrame 结构

基于当前代码库 (`src/plugins/data_pipeline.py`, `src/data/binance_fetcher.py`) 的事实标准：

#### 列名规范
- **当前标准**: 全小写英文单词
- **必需列**: `timestamp`, `open`, `high`, `low`, `close`, `volume`
- **可选列**: `quote_asset_volume`, `number_of_trades`, `taker_buy_base_volume`, `taker_buy_quote_volume`
- **禁止**: 首字母大写、缩写（如 `o`, `h`, `l`, `c`, `v`）、中文列名

#### 索引规范
- **当前标准**: `DatetimeIndex` (pandas Timestamp)
- **设置方式**: `df.set_index('timestamp', inplace=True)`
- **排序要求**: 必须按时间升序排序 `df.sort_index(inplace=True)`

#### 数据类型
| 列名 | 类型 | 说明 |
|------|------|------|
| timestamp | datetime64[ns] | 必须转换为时区无关的UTC时间 |
| open | float64 | 开盘价 |
| high | float64 | 最高价 |
| low | float64 | 最低价 |
| close | float64 | 收盘价 |
| volume | float64 | 成交量 |

#### 时间戳格式
- **当前标准**: Python `datetime` / pandas `Timestamp` 对象
- **原始来源**: 外部API通常返回Unix毫秒整数
- **转换时机**: 在数据管道层立即转换为datetime对象
- **时区**: 所有时间必须转换为UTC，禁止传递带时区的对象

**需统一**: 考虑将内部时间戳统一为Unix毫秒整数 (int64)，以减少datetime对象转换开销。当前代码库混合使用datetime对象和毫秒整数。

### 1.2 数据质量要求

#### 完整性
- 禁止NaN值进入计算层
- 缺失数据必须在管道层处理（插值或丢弃）
- 零成交量需标记为异常事件

#### 合理性检查
- `high` ≥ `low`
- `close` 在 `high` 和 `low` 范围内
- 价格 > 0
- 成交量 ≥ 0

#### 时间连续性
- 时间戳必须单调递增
- 最大间隔不得超过3倍正常间隔（根据时间框架）

## 2. 外部数据接入规范 (边境管制)

### 2.1 设计原则
- **单一入口**: 所有外部数据必须通过 `DataPipeline` 类接入
- **立即清洗**: 在接入层立即进行数据清洗和标准化
- **异常隔离**: 异常数据不得直接流入策略引擎
- **可追溯性**: 保留原始数据用于审计

### 2.2 名词清洗映射表

外部数据字段必须按以下映射表重命名：

| 外部字段 | 内部标准字段 | 类型 | 转换规则 |
|----------|--------------|------|----------|
| timestamp, ts, kline_time | timestamp | int64 | Unix毫秒，立即转换为datetime |
| open, o, opening_price | open | float64 | 直接转换 |
| high, h | high | float64 | 直接转换 |
| low, l | low | float64 | 直接转换 |
| close, c, closing_price | close | float64 | 直接转换 |
| volume, vol, v, qty, sz, amount | volume | float64 | 直接转换 |
| quote_volume, quote_asset_volume | quote_asset_volume | float64 | 可选 |
| trades, number_of_trades | number_of_trades | int64 | 可选 |
| taker_buy_volume | taker_buy_base_volume | float64 | 可选 |
| taker_buy_quote_volume | taker_buy_quote_volume | float64 | 可选 |

### 2.3 时区清洗规则
1. **强制UTC转换**: 所有外部时间必须在接口层转换为UTC
2. **时区剥离**: 转换后移除时区信息 `df.index.tz_localize(None)`
3. **禁止时区传播**: 系统内部禁止传递带时区的时间对象

### 2.4 异常处理流程

#### 数据缺失处理
```python
# 数据管道层必须检查
required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
missing_cols = [col for col in required_columns if col not in raw_data]

if missing_cols:
    raise DataValidationError(f"缺失必要字段: {missing_cols}")
```

#### 异常值处理
- **价格跳空**: 标记为异常事件，传递到状态机分析
- **零成交量**: 加密/外汇市场触发熔断机制
- **时间戳重叠/断裂**: 记录异常，根据市场类型处理

#### 熔断机制
- **触发条件**: 连续2根K线数据异常（零成交量或极端跳空）
- **恢复条件**: 连续5根正常K线
- **市场差异**:
  - 股票市场: 允许有限插值
  - 加密/外汇市场: 禁止插值，触发熔断

## 3. 模块间数据传递规范

### 3.1 函数接口

#### 数据管道 → 清洗模块
```python
def sanitize_candle(raw_candle: RawCandle, historical_context: HistoricalContext) 
    -> Tuple[Union[RawCandle, AnomalyEvent], bool, Optional[AnomalyEvent]]:
    """
    参数:
        raw_candle: RawCandle对象，包含timestamp(datetime), open, high, low, close, volume
        historical_context: 历史上下文数据
        
    返回:
        (data_object, is_anomaly, anomaly_event)
        - 正常数据: 返回原始RawCandle
        - 异常数据: 返回AnomalyEvent对象
    """
```

#### 清洗模块 → 状态机
```python
def process_candle(candle: pd.Series, context: Dict[str, Any]) -> str:
    """
    参数:
        candle: pd.Series，索引为datetime，包含open, high, low, close, volume等字段
        context: 包含TR边界、市场体制等上下文信息
        
    返回:
        状态名称字符串 (如 "SC", "AR", "LPS"等)
    """
```

### 3.2 数据结构定义

#### RawCandle (src/plugins/data_sanitizer.py)
```python
@dataclass
class RawCandle:
    timestamp: datetime          # UTC时间，无时区
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: Optional[str] = None
    exchange: Optional[str] = None
```

#### HistoricalContext (src/plugins/data_sanitizer.py)
```python
@dataclass
class HistoricalContext:
    volume_ma20: float = 0.0           # 20周期成交量移动平均
    volume_ma50: float = 0.0           # 50周期成交量移动平均
    previous_close: Optional[float] = None  # 前收盘价
    atr14: float = 1.0                 # 14周期ATR
    avg_body_size: float = 1.0         # 平均实体大小
    price_ma50: Optional[float] = None # 50周期价格移动平均
    recent_candles: List[RawCandle] = field(default_factory=list)  # 最近K线
```

## 4. 依赖与计算库规范

### 4.1 核心依赖
- **pandas**: 主要数据结构库
- **numpy**: 数值计算
- **ccxt**: 加密货币交易所数据（可选）
- **yfinance**: 股票数据（可选）
- **aiohttp**: 异步HTTP请求

### 4.2 禁止依赖
- **polars**: 当前代码库未使用，禁止引入
- **pandas_ta**: 技术指标使用自定义实现
- **talib**: 技术指标使用自定义实现

### 4.3 技术指标计算
- **ATR**: 自定义实现 (src/plugins/data_sanitizer.py)
- **移动平均**: pandas内置 `rolling().mean()`
- **成交量分析**: 自定义VSA算法
- **价格模式**: 自定义威科夫模式检测

## 5. 代码实现示例

### 5.1 数据管道标准化示例
```python
# src/plugins/data_pipeline.py 中的标准实现
async def fetch_ccxt_data(self, request: DataRequest) -> pd.DataFrame:
    # 获取原始数据
    ohlcv = exchange.fetch_ohlcv(...)
    
    # 转换为DataFrame，使用标准列名
    df = pd.DataFrame(
        ohlcv, 
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    
    # 时间戳转换：毫秒整数 → datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    
    # 设置索引
    df.set_index("timestamp", inplace=True)
    
    # 排序
    df.sort_index(inplace=True)
    
    return df
```

### 5.2 数据清洗示例
```python
# src/plugins/data_sanitizer.py 中的标准实现
def sanitize_dataframe(self, df: pd.DataFrame, symbol: str, exchange: str):
    # 验证必要列
    required_columns = ["open", "high", "low", "close", "volume"]
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"DataFrame必须包含以下列: {required_columns}")
    
    # 按时间排序
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp")
    elif df.index.name == "timestamp" or df.index.dtype == "datetime64[ns]":
        df = df.sort_index()
    
    # 处理每一行
    for i, row in df.iterrows():
        raw_candle = RawCandle(
            timestamp=row.name if isinstance(row.name, pd.Timestamp) else pd.to_datetime(i),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            symbol=symbol,
            exchange=exchange,
        )
        
        # 异常检测（不清洗）
        sanitized_data, is_anomaly, anomaly_event = self.sanitize_candle(
            raw_candle, historical_context
        )
```

## 6. 迁移与统一计划

### 6.1 当前冲突点
1. **时间戳格式不一致**: 部分模块使用datetime对象，部分使用Unix毫秒整数
2. **列名大小写**: 整体使用小写，但需确保所有模块一致
3. **数据验证时机**: 部分验证在管道层，部分在清洗层

### 6.2 统一建议
1. **时间戳统一为Unix毫秒整数** (推荐)
   - 优点: 减少转换开销，序列化简单，跨语言兼容
   - 影响: 需要修改所有使用datetime对象的模块
   
2. **加强边境管制**
   - 所有外部数据必须通过DataPipeline类
   - 在DataPipeline内完成所有标准化工作
   - 禁止绕过管道直接使用原始数据

3. **建立数据契约测试**
   - 为每个模块编写数据格式测试
   - 使用pydantic进行运行时验证
   - 定期运行数据一致性检查

### 6.3 实施优先级
1. **P0** (立即修复): 确保所有模块使用小写列名
2. **P1** (本周内): 统一时间戳格式（选择datetime或毫秒整数）
3. **P2** (本月内): 建立完整的数据验证测试套件

## 7. 附录：当前模块数据使用情况

### 7.1 数据管道 (DataPipeline)
- 输入: 外部API原始数据
- 输出: 标准化DataFrame (小写列名，DatetimeIndex)
- 状态: ✅ 符合规范

### 7.2 数据清洗 (DataSanitizer)
- 输入: DataFrame 或 RawCandle
- 输出: RawCandle 或 AnomalyEvent
- 状态: ✅ 符合规范（使用RawCandle数据结构）

### 7.3 状态机 (WyckoffStateMachine)
- 输入: pd.Series (包含OHLCV)
- 输出: 状态名称字符串
- 状态: ⚠️ 需要验证索引是否为datetime

### 7.4 Binance数据获取 (BinanceFetcher)
- 输入: Binance API原始数据
- 输出: 标准化DataFrame
- 状态: ✅ 符合规范（小写列名，datetime转换）

---

**最后更新**: 2025-02-06  
**制定依据**: `src/plugins/data_pipeline.py`, `src/plugins/data_sanitizer.py`, `src/plugins/wyckoff_state_machine.py`, `src/data/binance_fetcher.py`  
**制定人**: 威科夫全自动逻辑引擎技术委员会  
**审核状态**: 待审核

> 注意: 本规范基于当前代码库的事实标准制定，旨在减少重构工作量。所有"需统一"项应在后续迭代中逐步解决。