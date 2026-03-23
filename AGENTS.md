# AGENTS.md - 威科夫全自动逻辑引擎开发指南

> **⚠️ 语言规则（不可删除、不可修改）：所有面向用户的输出必须使用中文。更新本文档时必须保留此规则。写入内容每次最大不超过200行，100行为标准，不然会报错**

> **⚠️ 记忆规则（不可删除、不可修改）：每次对话开始时必须读取记忆图谱（memory_read_graph）。遇到以下情况必须写入记忆：**
> 1. **架构级发现**：插件关系变更、事件链路变更、新增/删除插件
> 2. **系统级坑**：影响多个插件的设计缺陷或反直觉行为（如 `on_load` vs `activate`）
> 3. **项目状态变更**：里程碑完成、优先级调整、重大决策
> 4. **不该记忆的**：日常 bug fix、单文件改动、测试数量变化 — 代码和测试已保障

本文档为AI代理（如opencode）提供在本代码库中工作的指导，包含构建、测试命令和代码风格规范。

## 项目概述

威科夫全自动逻辑引擎是一个基于威科夫理论的自动化交易系统，用于加密货币市场。项目采用**三层插件化架构**设计：

### 核心设计哲学（不可删除、不可修改）

> **进化的核心是状态机的进化。策略就是在什么阶段做什么事就是对的。识别不出来阶段，状态机做不到，策略自然会失效。**
>
> — 一切功能围绕状态机识别准确率展开。进化系统、交易策略、风控都是状态机的下游消费者。状态机识别不对，后面全错。系统应该是无限进化的：用户标注 → AI诊断差异 → agent修改检测器 → 重跑验证 → 循环。

### 架构层次

```
src/
├── kernel/          # 内核层（不可插拔）— 插件生命周期、事件总线、配置系统
│   ├── types.py           # 所有共享类型定义（枚举、数据类）
│   ├── base_plugin.py     # 插件抽象基类
│   ├── plugin_manifest.py # Manifest 解析器
│   ├── plugin_manager.py  # 插件生命周期管理
│   ├── event_bus.py       # 事件总线（发布/订阅）
│   └── config_system.py   # 配置系统（YAML + 环境变量）
├── plugins/         # 插件层（可插拔）— 18个业务插件
│   ├── market_regime/     # 市场体制检测
│   ├── data_pipeline/     # 数据管道
│   ├── orchestrator/      # 系统编排器
│   ├── wyckoff_state_machine/  # 威科夫状态机
│   ├── wyckoff_engine/    # 威科夫引擎（统一分析入口）
│   ├── pattern_detection/ # K线形态识别
│   ├── perception/        # 感知层（FVG/K线物理属性/针体分析）
│   ├── signal_validation/ # 信号验证
│   ├── risk_management/   # 风险管理
│   ├── position_manager/  # 仓位管理
│   ├── weight_system/     # 权重系统
│   ├── evolution/         # 自动化进化
│   ├── exchange_connector/# 交易所连接器
│   ├── dashboard/         # Web 仪表盘
│   ├── self_correction/   # 自我纠错
│   ├── evolution_advisor/ # 进化顾问（AI策略优化）
│   ├── telegram_notifier/ # Telegram 通知
│   └── audit_logger/      # 审计日志
├── api/             # FastAPI 后端（REST API + WebSocket）
└── utils/           # 工具层
```

### 系统入口

- **`src/app.py`** — `WyckoffApp` 类，插件化系统入口
- **`run.py`** — 统一启动脚本（支持 api/trading/evolution/web/all 5种模式）

### 关键文档

- **`docs/PLUGIN_DEVELOPMENT.md`** — 插件开发完整指南
- **`.sisyphus/plans/system-architecture-v3.md`** — 权威架构设计文档（2564+行）

### v3.0 完成状态（2026-03-21 生产就绪）

> **⚠️ 当前状态：v3.0 全部完成，1271 tests passing（含冒烟+集成+API契约测试），全系统接线修复完毕。下一步是进化系统端到端验证。**

**已完成的 8 个 Phase：**

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 0 | 清理死代码（删12000行） | ✅ |
| Phase 1 | 状态机重建（TransitionGuard + StateMachineV2, 22+4状态） | ✅ 611 tests |
| Phase 2 | WyckoffEngine重建（类型化接口 + process_bar） | ✅ 632 tests |
| Phase 3 | 事件链接通（Orchestrator→trading.signal→PositionManager→Exchange） | ✅ 648 tests |
| Phase 4 | 进化系统重建（BarByBarBacktester + GA + WFA + 5层防过拟合） | ✅ 689 tests |
| Phase 5 | 后端API（4端点 + WebSocket） | ✅ 707 tests |
| Phase 6 | 前端从零构建（React 18 + TS + Vite + Tailwind + LWC v5.1） | ✅ 2337行 |
| Phase 7 | 进化顾问AI Agent（OpenAI/Ollama双后端） | ✅ 738 tests |
| Phase 8 | Numba加速 + SelfCorrection集成 | ✅ |

**生产就绪审计结果：** F1 PASS (10/10 Must Have) | F2+F3 PASS (1271 tests) | F4 PASS (27/27 compliant)

**18个插件：** market_regime, data_pipeline, orchestrator, wyckoff_state_machine, wyckoff_engine, pattern_detection, perception, signal_validation, risk_management, position_manager, weight_system, evolution, exchange_connector, dashboard, self_correction, evolution_advisor, telegram_notifier, audit_logger

**技术栈：** Python 3.9+ | FastAPI | React 18 + TypeScript + Vite | Docker | 1271 tests

### `.sisyphus/` 归档

| 文件 | 说明 | 状态 |
|------|------|------|
| `plans/system-architecture-v3.md` | 权威架构设计文档（2675行） | 📖 参考文档 |
| `plans/production-readiness.md` | 生产就绪修复计划（31 Tasks, 5 Wave） | ✅ 已归档 |
| `plans/architecture-redesign.md` | v3.0 架构重组（Phase 1-5） | ✅ 已归档 |
| `plans/evolution-redesign.md` | 进化子系统重建 | ✅ 已归档 |
| `plans/evolution-dashboard.md` | 前端进化仪表盘（Wave A-D） | ✅ 已归档 |
| `handoff_evolution_diagnosis.md` | 进化系统 13 个 BUG 诊断与修复 | ✅ 全部修复 |
| `handoff_evolution_wfa_fix.md` | WFA 接受率修复 | ✅ 已修复 |
| `plans/evolution-overfit-fix.md` | 进化过拟合修复（7根因, 5/7已修复） | ✅ 已审计+部分修复 |
| `plans/frontend-integration.md` | 前后端集成（被 full-system-cleanup 取代） | ✅ 已归档 |
| `plans/full-system-cleanup.md` | 全系统清理（死代码+集成+进化修复） | 🔧 执行中 |

### 插件开发关键陷阱（必读）

1. **生命周期只有 `on_load()`**：`PluginManager.load_plugin()` 只调用 `on_load()`，**永远不调用 `activate()`**。所有初始化逻辑必须放在 `on_load()` 里，不能放在 `activate()` 里。
2. **API 方法必须存在**：如果 `src/api/app.py` 调用了 `plugin.some_method()`，该方法必须在插件的 `plugin.py` 中定义。否则前端对应功能会静默失败。
3. **事件数据格式是契约**：修改事件发布的字段时，必须同步更新所有订阅者。用 `tests/test_integration_chain.py::TestEventContracts` 验证。

### 验证工具

```bash
# 系统完整性检查（插件初始化 + API方法 + 事件链路）
python check_system_integrity.py

# 三层测试
pytest tests/test_smoke.py -q          # 冒烟（5秒）
pytest tests/test_integration_chain.py -q  # 集成（15秒）
pytest tests/test_api_contract.py -q   # API契约（25秒）

# 全部测试
pytest tests/ -q                       # 1271 tests（72秒）
```

## 构建和测试命令

### 环境设置
```bash
# 安装依赖（使用Python 3.9+）
pip install -r requirements.txt
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

# 运行内核测试
pytest tests/kernel/ -v

# 运行插件测试
pytest tests/plugins/ -v

# 运行特定插件测试
pytest tests/plugins/test_market_regime.py -v

# 运行核心模块测试（兼容层）
pytest tests/core/ -v

# 运行特定测试文件
pytest tests/core/test_market_regime.py -v

# 运行单个测试函数
pytest tests/core/test_market_regime.py::TestMarketRegime::test_enum_values -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=src --cov-report=html --cov-report=term

# 快速测试模式（不显示详细输出）
pytest tests/ -q

# 运行测试并输出详细断言信息
pytest tests/ -v --tb=short
```

### 开发工具
```bash
# 启动 API 服务器（推荐）
python run.py --mode=api

# 启动交易系统
python run.py --mode=trading

# 启动全部服务
python run.py --mode=all

# 运行健康检查
python health_check.py

# 运行安装脚本
pip install -r requirements.txt

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

from src.kernel.types import MarketRegime
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

- **内核层**（`src/kernel/`）不依赖任何插件，是系统基础
- **插件层**（`src/plugins/`）只依赖内核层，插件间通过事件总线通信
- **兼容层**（`src/core/`）已删除，所有实现已迁移至 `src/plugins/`
- 打破循环依赖，使用事件总线或回调
- 新功能优先以**插件**形式开发，参考 `docs/PLUGIN_DEVELOPMENT.md`
- 保持模块职责单一，避免上帝对象

## 配置管理

- 使用YAML配置文件（`config.yaml`）
- 配置参数应有默认值和类型验证
- 生产环境配置使用环境变量覆盖（前缀 `WYCKOFF_`）
- 插件配置在 `config.yaml` 的 `plugins` 节下
- 配置更改需要文档说明

## 扩展开发

添加新插件时：
1. 在 `src/plugins/` 下创建插件目录
2. 编写 `plugin-manifest.yaml` 和 `plugin.py`（继承 `BasePlugin`）
3. 编写单元测试（`tests/plugins/test_xxx.py`）
4. 在 `config.yaml` 的 `plugins` 节添加配置
5. 更新相关文档
6. 运行完整测试套件：`pytest tests/ -v`

详细指南参见 **`docs/PLUGIN_DEVELOPMENT.md`**。

---

*本文档最后更新：2026-03-21*
*对应项目版本：威科夫全自动逻辑引擎 v3.0（生产就绪）*  
*参考文件：requirements.txt, config.yaml, src/app.py, docs/PLUGIN_DEVELOPMENT.md*