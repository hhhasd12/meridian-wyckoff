# 错误处理与日志记录规范

## 一、概述

本文档定义威科夫全自动逻辑引擎项目的错误处理和日志记录标准。

## 二、错误处理规范

### 2.1 使用装饰器

项目已提供统一的错误处理装饰器，位于 `src/utils/error_handler.py`:

```python
from src.utils.error_handler import error_handler
import logging

logger = logging.getLogger(__name__)

@error_handler(logger=logger, reraise=False, default_return=None)
def my_function():
    ...
```

### 2.2 装饰器选项

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `logger` | Logger | 模块级logger | 日志记录器 |
| `reraise` | bool | True | 是否重新抛出异常 |
| `default_return` | Any | None | 异常时的默认返回值 |
| `log_level` | int | ERROR | 日志级别 |
| `capture_exceptions` | tuple | (Exception,) | 捕获的异常类型 |

### 2.3 异常分类

使用 `ErrorCategory` 枚举分类异常：

```python
from src.utils.error_handler import ErrorCategory

# VALIDATION - 数据验证错误
# NETWORK - 网络相关错误  
# DATA - 数据处理错误
# COMPUTATION - 计算错误
# TIMEOUT - 超时错误
# AUTH - 认证/授权错误
# CONFIG - 配置错误
# UNKNOWN - 未知错误
```

### 2.4 严重程度

使用 `ErrorSeverity` 枚举确定严重程度：

```python
from src.utils.error_handler import ErrorSeverity

# LOW - 不影响核心功能
# MEDIUM - 影响部分功能
# HIGH - 影响核心功能
# CRITICAL - 系统无法正常工作
```

### 2.5 重试机制

对于临时性错误，使用重试装饰器：

```python
from src.utils.error_handler import retry

@retry(max_attempts=3, delay_seconds=1.0, backoff_factor=2.0)
def fetch_data():
    ...
```

## 三、日志记录规范

### 3.1 Logger 初始化

每个模块必须创建模块级 logger：

```python
import logging

logger = logging.getLogger(__name__)
```

### 3.2 日志级别使用

| 级别 | 使用场景 |
|------|----------|
| DEBUG | 详细调试信息，变量值 |
| INFO | 正常业务流程 |
| WARNING | 可恢复的异常 |
| ERROR | 功能失败 |
| CRITICAL | 系统级严重错误 |

### 3.3 执行时间追踪

使用 `@log_execution_time` 装饰器监控性能：

```python
from src.utils.error_handler import log_execution_time

@log_execution_time(logger=logger, threshold_seconds=1.0)
def slow_function():
    ...
```

### 3.4 日志格式

推荐格式：

```
[时间] [级别] [模块名] 消息内容
```

示例：

```
[2026-02-20 18:00:00] [ERROR] [data_pipeline] 函数 fetch_data 执行失败: [HIGH] ConnectionError: 连接超时
```

## 四、错误处理模式

### 4.1 业务逻辑错误

```python
from src.utils.error_handler import error_handler

@error_handler(logger=logger, reraise=True)
def validate_price(price: float) -> None:
    if price <= 0:
        raise ValueError(f"价格必须为正数: {price}")
```

### 4.2 外部API调用

```python
from src.utils.error_handler import error_handler, retry

@retry(max_attempts=3, delay_seconds=2.0)
@error_handler(logger=logger, reraise=False, default_return={})
def fetch_market_data(symbol: str) -> dict:
    # API调用逻辑
    ...
```

### 4.3 数据处理

```python
@error_handler(logger=logger, reraise=False, default_return=[])
def process_ohlcv_data(data: pd.DataFrame) -> list:
    # 数据处理逻辑
    ...
```

## 五、最佳实践

1. **不要捕获所有异常**: 只捕获需要处理的特定异常
2. **记录上下文**: 在日志中包含足够的调试信息
3. **使用结构化日志**: 尽量使用字典格式记录复杂数据
4. **避免日志噪声**: DEBUG级别用于开发，生产使用INFO+
5. **错误消息要清晰**: 描述问题而非仅仅记录异常类型
6. **保持异常链**: 使用 `raise ... from e` 保持原始异常信息

## 六、配置管理

使用统一的配置加载器：

```python
from src.utils.config_loader import load_config

# 加载配置
config = load_config("config.yaml", env_override=True)

# 带默认值的配置
defaults = {"timeout": 30, "retries": 3}
config = load_config_with_defaults("config.yaml", defaults)
```

---

*最后更新: 2026-02-20*
