# 插件开发指南

本文档指导开发者如何为威科夫全自动逻辑引擎创建新插件。

## 目录

1. [架构概览](#架构概览)
2. [插件目录结构](#插件目录结构)
3. [Manifest 规范](#manifest-规范)
4. [编写插件类](#编写插件类)
5. [事件通信](#事件通信)
6. [配置管理](#配置管理)
7. [健康检查](#健康检查)
8. [编写测试](#编写测试)
9. [现有插件列表](#现有插件列表)

---

## 架构概览

系统采用三层架构：

```
src/
├── kernel/          # 内核层（不可插拔）
│   ├── types.py           # 所有共享类型定义
│   ├── base_plugin.py     # 插件抽象基类
│   ├── plugin_manifest.py # Manifest 解析器
│   ├── plugin_manager.py  # 插件生命周期管理
│   ├── event_bus.py       # 事件总线
│   └── config_system.py   # 配置系统
├── plugins/         # 插件层（可插拔）
│   ├── market_regime/     # 市场体制检测
│   ├── data_pipeline/     # 数据管道
│   ├── orchestrator/      # 系统编排器
│   └── ...                # 更多插件
└── utils/           # 工具层
```

**插件生命周期状态：**

```
UNLOADED → LOADING → ACTIVE → UNLOADING → UNLOADED
                                    ↑
任意状态 → ERROR ──────────────────┘（恢复路径）
```

---

## 插件目录结构

每个插件是 `src/plugins/` 下的一个 Python 包：

```
src/plugins/my_plugin/
├── __init__.py              # 包入口，导出公共 API
├── plugin.py                # 插件类（继承 BasePlugin）
├── plugin-manifest.yaml     # 插件清单（必需）
├── core_logic.py            # 核心业务逻辑（可选）
└── helpers.py               # 辅助函数（可选）
```

**命名规范：**
- 目录名：`snake_case`（如 `market_regime`、`risk_management`）
- 插件类名：`CamelCase` + `Plugin` 后缀（如 `MarketRegimePlugin`）
- Manifest 中的 `name` 必须与目录名一致

---

## Manifest 规范

每个插件必须包含 `plugin-manifest.yaml` 文件：

```yaml
# 插件基本信息
name: my_plugin                    # 必需：与目录名一致
version: "1.0.0"                   # 必需：语义化版本
description: "插件功能描述"         # 必需：简短描述
author: "Wyckoff Engine Team"      # 必需：作者
plugin_type: synchronous           # 必需：synchronous 或 asynchronous

# 入口点：PluginManager 从此模块导入插件类
entry_point: plugin                # 必需：指向 plugin.py

# 插件依赖（其他插件名称列表）
dependencies: []                   # 可选：如 ["market_regime", "data_pipeline"]

# 事件声明
events:                            # 可选
  publishes:                       # 本插件发布的事件
    - "my_plugin.result_ready"
  subscribes:                      # 本插件订阅的事件
    - "data_pipeline.ohlcv_ready"

# 配置 schema
config_schema:                     # 可选
  param_name:
    type: int                      # int, float, str, bool
    default: 14
    description: "参数描述"
```

**`plugin_type` 说明：**
- `synchronous` — 同步插件，适用于计算密集型任务
- `asynchronous` — 异步插件，适用于 I/O 密集型任务（如网络请求）

---

## 编写插件类

### 最小示例

```python
"""我的自定义插件"""

import logging
from typing import Any, Dict, Optional

from src.kernel.base_plugin import BasePlugin
from src.kernel.types import HealthCheckResult, HealthStatus

logger = logging.getLogger(__name__)


class MyPlugin(BasePlugin):
    """自定义插件示例

    实现 on_load() 和 on_unload() 即可完成最小插件。
    """

    def __init__(
        self,
        name: str = "my_plugin",
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name=name, config=config)
        self._internal_state: Optional[Any] = None

    def on_load(self) -> None:
        """加载插件：初始化内部状态"""
        self._internal_state = self._create_state()
        logger.info("MyPlugin 已加载")

    def on_unload(self) -> None:
        """卸载插件：清理资源"""
        self._internal_state = None
        logger.info("MyPlugin 已卸载")

    def _create_state(self) -> Any:
        """创建内部状态（使用 self._config 获取配置）"""
        return {"initialized": True}
```

### BasePlugin 提供的属性和方法

| 属性/方法 | 说明 |
|-----------|------|
| `self._name` | 插件名称（只读） |
| `self._state` | 当前生命周期状态（PluginState 枚举） |
| `self._config` | 插件配置字典 |
| `self._event_bus` | 事件总线实例（由 PluginManager 注入） |
| `self._plugin_manager` | 插件管理器实例（由 PluginManager 注入） |
| `self.name` | 属性，返回 `self._name` |
| `self.state` | 属性，返回 `self._state` |
| `self.config` | 属性，返回 `self._config` |

### 必须实现的方法

| 方法 | 说明 |
|------|------|
| `on_load(self) -> None` | 插件加载时调用，初始化资源 |
| `on_unload(self) -> None` | 插件卸载时调用，清理资源 |

### 可选覆盖的方法

| 方法 | 说明 |
|------|------|
| `on_config_update(self, new_config) -> None` | 配置热更新回调 |
| `health_check(self) -> HealthCheckResult` | 健康检查 |

---

## 事件通信

插件通过 EventBus 进行松耦合通信。

### 发布事件

```python
def on_load(self) -> None:
    # 初始化后发布事件
    if self._event_bus:
        self._event_bus.emit(
            "my_plugin.initialized",
            data={"status": "ready"},
            publisher=self._name,
        )
```

### 订阅事件

```python
def on_load(self) -> None:
    # 订阅其他插件的事件
    if self._event_bus:
        self._event_bus.subscribe(
            event_pattern="data_pipeline.ohlcv_ready",
            handler=self._on_data_ready,
            priority=5,
            subscriber_name=self._name,
        )

def _on_data_ready(self, data: Dict[str, Any]) -> None:
    """处理数据就绪事件"""
    df = data.get("dataframe")
    if df is not None:
        result = self._process(df)
        # 处理完成后发布结果
        if self._event_bus:
            self._event_bus.emit(
                "my_plugin.result_ready",
                data={"result": result},
                publisher=self._name,
            )
```

### 事件命名规范

- 格式：`{plugin_name}.{event_name}`
- 示例：`market_regime.detected`、`data_pipeline.ohlcv_ready`

---

## 配置管理

### 从 config.yaml 读取配置

插件配置在 `config.yaml` 的 `plugins` 节下：

```yaml
plugins:
  my_plugin:
    param_a: 14
    param_b: 0.5
    enabled: true
```

在插件中通过 `self._config` 访问：

```python
def on_load(self) -> None:
    param_a = self._config.get("param_a", 14)
    param_b = self._config.get("param_b", 0.5)
```

### 配置热更新

```python
def on_config_update(self, new_config: Dict[str, Any]) -> None:
    """配置变更时自动调用"""
    self._config.update(new_config)
    # 重新初始化依赖配置的组件
    self._internal_state = self._create_state()
    logger.info("MyPlugin 配置已更新")
```

---

## 健康检查

```python
def health_check(self) -> HealthCheckResult:
    """返回插件健康状态"""
    if self._internal_state is None:
        return HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message="内部状态未初始化",
        )
    return HealthCheckResult(
        status=HealthStatus.HEALTHY,
        message="运行正常",
        details={"state_size": len(self._internal_state)},
    )
```

---

## 编写测试

测试文件放在 `tests/plugins/test_my_plugin.py`：

```python
"""MyPlugin 单元测试"""

from unittest.mock import MagicMock
from src.plugins.my_plugin.plugin import MyPlugin


class TestMyPlugin:
    """MyPlugin 测试类"""

    def setup_method(self) -> None:
        self.plugin = MyPlugin(config={"param_a": 10})

    def test_on_load(self) -> None:
        """测试插件加载"""
        self.plugin.on_load()
        assert self.plugin._internal_state is not None

    def test_on_unload(self) -> None:
        """测试插件卸载"""
        self.plugin.on_load()
        self.plugin.on_unload()
        assert self.plugin._internal_state is None

    def test_health_check_healthy(self) -> None:
        """测试健康检查 - 健康状态"""
        self.plugin.on_load()
        result = self.plugin.health_check()
        assert result.status.value == "healthy"

    def test_event_subscription(self) -> None:
        """测试事件订阅"""
        mock_bus = MagicMock()
        self.plugin._event_bus = mock_bus
        self.plugin.on_load()
        # 验证订阅了预期事件
        mock_bus.subscribe.assert_called()
```

运行测试：

```bash
pytest tests/plugins/test_my_plugin.py -v
```

---

## 现有插件列表

| 插件名 | 目录 | 说明 |
|--------|------|------|
| `market_regime` | `src/plugins/market_regime/` | 市场体制检测（趋势/震荡/高波动） |
| `data_pipeline` | `src/plugins/data_pipeline/` | 数据获取与清洗管道 |
| `orchestrator` | `src/plugins/orchestrator/` | 系统编排与决策引擎 |
| `wyckoff_state_machine` | `src/plugins/wyckoff_state_machine/` | 威科夫状态机 |
| `pattern_detection` | `src/plugins/pattern_detection/` | K线形态识别 |
| `perception` | `src/plugins/perception/` | 感知层（K线物理学） |
| `signal_validation` | `src/plugins/signal_validation/` | 信号验证与过滤 |
| `risk_management` | `src/plugins/risk_management/` | 风险管理与仓位控制 |
| `weight_system` | `src/plugins/weight_system/` | 权重系统与变异算子 |
| `evolution` | `src/plugins/evolution/` | 自动化进化引擎 |
| `exchange_connector` | `src/plugins/exchange_connector/` | 交易所连接器 |
| `dashboard` | `src/plugins/dashboard/` | Web 仪表盘 |
| `self_correction` | `src/plugins/self_correction/` | 自我纠错工作流 |

---

*文档版本：1.0 | 更新日期：2026-03-10*
