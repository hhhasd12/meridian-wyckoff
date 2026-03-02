# AGENTS.md - 威科夫全自动逻辑引擎开发指南

本文档为AI代理（如opencode）提供在本代码库中工作的指导，包含构建、测试命令和代码风格规范。

## 项目概述

威科夫全自动逻辑引擎是一个基于威科夫理论的自动化交易系统，用于加密货币市场。项目采用模块化设计，包含市场体制检测、状态机、风险管理、自动化进化等核心模块。

## 构建和测试命令

### 环境设置
```bash
# 安装依赖（使用Python 3.9+）
pip install -r requirements.txt

# 创建必要的目录结构
mkdir -p logs reports status data_cache exports/decisions exports/reports backtests/results backtests/scenarios
```

### 代码质量检查
```bash
# 代码格式化（使用Black）
black src/ tests/

# 代码检查（使用Pylint）
pylint src/

# 类型检查（使用mypy，如果配置了）
mypy src/
```

### 测试命令
```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/core/test_market_regime.py -v

# 运行单个测试函数
pytest tests/core/test_market_regime.py::TestMarketRegime::test_enum_values -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=src --cov-report=html --cov-report=term

# 运行特定模块的测试
pytest tests/core/ -v

# 快速测试模式（不显示详细输出）
pytest tests/ -q

# 运行测试并输出详细断言信息
pytest tests/ -v --tb=short
```

### 开发工具
```bash
# 启动系统（生产模式）
python run_live.py

# 启动系统（自定义配置）
python run_live.py config_production.yaml

# 运行安装脚本
python setup.py

# 清理缓存文件
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete
```

## 代码风格指南

### 导入顺序
遵循PEP 8导入顺序，每组之间空一行：
1. 标准库导入
2. 第三方库导入
3. 本地模块导入

示例：
```python
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass

from src.core.market_regime import MarketRegime
from src.utils.data_helpers import normalize_data
```

### 格式化规范
- 使用**Black**进行自动格式化（行宽88字符）
- 使用**4个空格**缩进（不要使用Tab）
- 最大行宽：88字符（Black默认）
- 字符串使用双引号（与现有代码一致）

### 类型注解
- 所有函数和方法必须包含类型注解
- 使用Python的`typing`模块（`Dict`, `List`, `Tuple`, `Optional`, `Any`, `Callable`等）
- 复杂类型使用`TypeAlias`或自定义类型
- 返回值类型必须明确，无返回值使用`-> None`

示例：
```python
def process_data(
    df: pd.DataFrame,
    config: Optional[Dict[str, Any]] = None
) -> Tuple[pd.DataFrame, float]:
    """处理数据并返回结果和置信度"""
    ...
```

### 命名约定
- **类名**：`CamelCase`（如`RegimeDetector`, `WyckoffStateMachine`）
- **函数/方法名**：`snake_case`（如`detect_regime`, `calculate_atr`）
- **变量名**：`snake_case`（如`current_regime`, `confidence_score`）
- **常量**：`UPPER_SNAKE_CASE`（如`MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT`）
- **模块名**：`snake_case`（如`market_regime.py`, `data_helpers.py`）
- **私有成员**：前缀单下划线`_private_method`
- **类型变量**：使用`TypeVar`时用`T`, `U`, `V`等

### 文档字符串
- 使用**Google风格**的文档字符串
- 每个模块、类、公共方法必须有文档字符串
- 包含Args、Returns、Raises部分
- 示例代码（如果适用）

示例：
```python
class RegimeDetector:
    """市场体制检测器 - 独立模块，打破循环依赖
    
    设计原则：
    1. 无状态启动：初始化时不需要历史K线形态信息
    2. 仅基于技术指标：ATR、ADX、历史波动率
    3. 不与K线形态识别相互依赖
    4. 输出稳定的市场体制判断
    """
    
    def detect_regime(self, df: pd.DataFrame) -> Dict:
        """检测市场体制
        
        Args:
            df: 包含OHLCV数据的DataFrame，必须包含以下列：
                - 'open', 'high', 'low', 'close', 'volume'
        
        Returns:
            Dict包含：
                - regime: MarketRegime枚举
                - confidence: 置信度 [0, 1]
                - metrics: 各项指标值
                - reasons: 判断理由
        
        Raises:
            ValueError: 当DataFrame缺少必需列时
        """
        ...
```

### 错误处理
- 使用具体的异常类型（`ValueError`, `TypeError`, `KeyError`等）
- 避免捕获过于宽泛的异常（如`except Exception`）
- 使用`logging`记录错误信息，不要仅使用`print`
- 返回错误信息时使用结构化的字典或数据类

示例：
```python
import logging

logger = logging.getLogger(__name__)

def safe_division(a: float, b: float) -> Optional[float]:
    """安全的除法运算"""
    if b == 0:
        logger.warning("除零错误: a=%s, b=%s", a, b)
        return None
    return a / b
```

### 日志记录
- 使用模块级别的logger：`logger = logging.getLogger(__name__)`
- 日志级别：DEBUG（调试）、INFO（信息）、WARNING（警告）、ERROR（错误）
- 生产代码避免使用`print`，使用`logger.info()`代替
- 日志消息应包含足够上下文信息

### 数据结构
- 使用`dataclass`定义数据容器
- 使用`Enum`定义有限的选项集合
- 复杂配置使用`TypedDict`或Pydantic模型（如果引入）

示例：
```python
from enum import Enum
from dataclasses import dataclass
from typing import List

class MarketRegime(Enum):
    """市场体制枚举"""
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"

@dataclass
class DetectionResult:
    """检测结果数据类"""
    regime: MarketRegime
    confidence: float
    metrics: Dict[str, float]
    reasons: List[str]
```

## 测试指南

### 测试结构
- 测试文件位于`tests/`目录，镜像`src/`目录结构
- 测试类名：`TestClassName`（如`TestRegimeDetector`）
- 测试方法名：`test_functionality_description`（如`test_detect_regime_with_trending_data`）
- 使用`pytest`框架，不要使用`unittest`

### 测试夹具
- 使用`setup_method`进行测试初始化
- 复杂的测试数据可以使用`@pytest.fixture`
- 测试数据应尽可能真实，但可重复

### 断言
- 使用`assert`语句，不要使用`unittest`的断言方法
- 断言消息应清晰说明期望和实际值
- 测试边缘情况和错误路径

示例：
```python
def test_detect_regime_with_insufficient_data(self):
    """测试数据不足的情况"""
    empty_df = pd.DataFrame()
    result = self.detector.detect_regime(empty_df)
    assert result["regime"] == MarketRegime.UNKNOWN
    assert result["confidence"] < 0.5
```

### 测试覆盖率
- 目标覆盖率：核心模块>80%，工具模块>70%
- 使用`pytest-cov`生成覆盖率报告
- 关注边界条件和错误处理

## 提交前检查

在提交代码前，确保通过以下检查：

```bash
# 1. 代码格式化
black src/ tests/

# 2. 代码检查（无严重错误）
pylint src/ --fail-under=7.0

# 3. 运行相关测试
pytest tests/ -xvs

# 4. 类型检查（如果配置）
mypy src/
```

## 性能注意事项

- 避免在循环中重复计算，使用缓存或预计算
- 使用向量化操作（NumPy/Pandas）代替Python循环
- 大数据处理使用Polars（已包含在依赖中）
- 监控内存使用，及时释放大对象

## 安全最佳实践

- 永不提交API密钥或敏感信息到版本控制
- 使用环境变量存储敏感配置
- 实盘交易代码需要双重确认
- 所有外部API调用需要错误处理和重试机制

## 模块依赖规范

- 核心模块（`src/core/`）不应依赖可视化模块
- 打破循环依赖，使用接口或回调
- 新功能优先考虑添加到现有模块，而不是创建新模块
- 保持模块职责单一，避免上帝对象

## 配置管理

- 使用YAML配置文件（`config.yaml`）
- 配置参数应有默认值和类型验证
- 生产环境配置使用环境变量覆盖
- 配置更改需要文档说明

## 扩展开发

添加新功能时：
1. 先在`src/`下创建模块或扩展现有模块
2. 编写单元测试
3. 更新配置文件模板（如果需要）
4. 更新相关文档
5. 运行完整测试套件

---

*本文档最后更新：2026-02-20*  
*对应项目版本：威科夫全自动逻辑引擎 v1.0*  
*参考文件：requirements.txt, setup.py, config.yaml, src/core/market_regime.py*