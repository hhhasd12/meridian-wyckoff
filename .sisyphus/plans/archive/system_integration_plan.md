# 威科夫交易系统整合计划

## 一、现状分析

### 1.1 系统架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              威科夫交易系统                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────┐      ┌─────────────────────────────┐     │
│  │        后端 (Python)        │      │        前端 (React)         │     │
│  │    localhost:9527 (FastAPI) │      │    localhost:5173 (Vite)    │     │
│  └─────────────────────────────┘      └─────────────────────────────┘     │
│                │                                   │                         │
│                │                                   │                         │
│                ▼                                   ▼                         │
│  ┌─────────────────────────────┐      ┌─────────────────────────────┐     │
│  │   插件系统 (13个插件)       │      │   页面系统 (6个插件)        │     │
│  │   src/plugins/             │      │   frontend/src/plugins/    │     │
│  └─────────────────────────────┘      └─────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 后端插件列表

| 序号 | 插件名称 | 功能描述 | 状态 | 对应前端 |
|------|---------|---------|------|---------|
| 1 | market_regime | 市场体制检测 | ✅ 完整 | 无直接对应 |
| 2 | data_pipeline | 数据管道 | ✅ 完整 | 无直接对应 |
| 3 | orchestrator | 系统编排器 | ✅ 完整 | 无直接对应 |
| 4 | wyckoff_state_machine | 威科夫状态机 | ✅ 完整 | 无直接对应 |
| 5 | pattern_detection | K线形态识别 | ✅ 完整 | 无直接对应 |
| 6 | perception | 感知层 | ✅ 完整 | 无直接对应 |
| 7 | signal_validation | 信号验证 | ✅ 完整 | 无直接对应 |
| 8 | risk_management | 风险管理 | ✅ 完整 | `/risk` 页面 |
| 9 | weight_system | 权重系统 | ✅ 完整 | 无直接对应 |
| 10 | position_manager | 持仓管理 | ✅ 完整 | `/positions`, `/trades` |
| 11 | exchange_connector | 交易所连接器 | ✅ 完整 | 无直接对应 |
| 12 | dashboard | Web仪表盘 | ✅ 完整 | `/` 仪表盘页面 |
| 13 | evolution | 进化系统 | ❌ **断裂** | `/evolution` 页面 |

### 1.3 前端页面列表

| 序号 | 页面路径 | 页面名称 | 对应后端插件 | 状态 |
|------|---------|---------|-------------|------|
| 1 | `/` | 仪表盘 | dashboard | ✅ 正常 |
| 2 | `/positions` | 持仓管理 | position_manager | ✅ 正常 |
| 3 | `/trades` | 交易历史 | position_manager | ✅ 正常 |
| 4 | `/plugins` | 插件管理 | plugin_manager | ✅ 正常 |
| 5 | `/risk` | 风险监控 | risk_management | ⚠️ 部分占位符 |
| 6 | `/evolution` | 进化系统 | evolution | ❌ **断裂** |

### 1.4 启动方式

| 系统 | 启动命令 | 端口 | 数据来源 | 用途 |
|------|---------|------|---------|------|
| API服务器 | `python -m uvicorn src.api.app:app --port 9527` | 9527 | - | 前端查询接口 |
| 前端开发 | `cd frontend && npm run dev` | 5173 | - | Web界面 |
| 进化盘 | `python run_evolution.py` | 无API | 本地data/ | 策略优化 |
| 实盘 | `python run_live.py` | 无API | 交易所API | 真实交易 |

---

## 二、核心问题清单

### 问题1：进化系统架构断裂（严重）

**问题描述：**
- `run_evolution.py` 独立运行，不通过插件系统
- `evolution` 插件只封装了 EvolutionArchivist，没有真正的进化逻辑
- API 端点 `/api/evolution/*` 是占位符，返回假数据

**影响：**
- 前端 `/evolution` 页面的"启动进化"按钮无效
- 进化状态无法通过 API 查询
- 进化盘和实盘数据混淆

**代码证据：**
```python
# src/api/app.py 第598-604行
@app.post("/api/evolution/start")
async def start_evolution():
    return {"status": "started"}  # 假的！

@app.post("/api/evolution/stop")
async def stop_evolution():
    return {"status": "stopped"}  # 假的！
```

---

### 问题2：进化盘与实盘未分离（严重）

**问题描述：**
- 前端没有区分"进化盘"和"实盘"的模式
- 持仓数据共用 `position_manager` 插件
- 没有独立的进化盘持仓存储

**影响：**
- 用户无法区分当前是进化盘还是实盘
- 进化页面的"模拟持仓"显示错误数据

**代码证据：**
```typescript
// frontend/src/plugins/evolution/index.tsx 第85行
const { positions, trades } = useAppStore()  // 使用全局数据！
```

---

### 问题3：API 端点不完整（中等）

**问题描述：**
多个 API 端点是占位符或返回硬编码空数据：

| 端点 | 问题 |
|------|------|
| `/api/evolution/start` | 返回 `{"status": "started"}`，无实际逻辑 |
| `/api/evolution/stop` | 返回 `{"status": "stopped"}`，无实际逻辑 |
| `/api/evolution/status` | 返回硬编码默认值，未连接真实状态 |
| `/api/evolution/state-machine-logs` | 依赖不存在的方法 |
| `/api/evolution/decision-traces` | 依赖不存在的方法 |
| `/api/risk/anomalies` | 硬编码返回 `[]` |

---

### 问题4：前端页面数据源混乱（中等）

**问题描述：**
- `/evolution` 页面的数据来自全局 store，不是进化系统特有
- 没有进化盘专属的持仓和交易历史

**影响：**
- 用户看到的进化数据不准确

---

### 问题5：系统入口混乱（中等）

**问题描述：**
- 有 `run_evolution.py`（独立运行）
- 有 `run_live.py`（独立运行）
- 有 `src/api/app.py`（API服务器）
- 三个入口互不关联

**影响：**
- 用户不知道该用哪个入口
- API 无法控制进化系统的启动/停止

---

## 三、整合目标

### 3.1 总体目标

将系统整合为一个统一架构，进化盘和实盘通过 API 服务器统一管理：

```
                    ┌─────────────────────────────────────────────┐
                    │              前端 (React)                    │
                    │         localhost:5173                       │
                    │                                              │
                    │   ┌─────────┐  ┌─────────┐  ┌─────────┐  │
                    │   │ 仪表盘  │  │ 进化盘  │  │  实盘   │  │
                    │   └────┬────┘  └────┬────┘  └────┬────┘  │
                    └────────┼────────────┼────────────┼────────┘
                             │            │            │
                             │            │            │
                             ▼            ▼            ▼
                    ┌─────────────────────────────────────────────┐
                    │           API 服务器 (FastAPI)             │
                    │            localhost:9527                  │
                    │                                              │
                    │   ┌─────────────────────────────────────┐  │
                    │   │  /api/system/*     - 系统状态       │  │
                    │   │  /api/evolution/* - 进化盘控制     │  │
                    │   │  /api/live/*       - 实盘控制       │  │
                    │   │  /api/positions/*  - 持仓查询       │  │
                    │   └─────────────────────────────────────┘  │
                    └────────────────────┬───────────────────────┘
                                         │
                    ┌────────────────────┼───────────────────────┐
                    │                    │                       │
                    ▼                    ▼                       ▼
         ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
         │   进化盘引擎      │  │    实盘引擎      │  │   插件系统        │
         │  (EvolutionApp)  │  │  (LiveTradingApp)│  │ (WyckoffApp)     │
         │                  │  │                  │  │                  │
         │ - WFA回测       │  │ - 交易所连接    │  │ - 13个业务插件   │
         │ - 权重优化      │  │ - 实时数据      │  │ - 事件驱动       │
         │ - 错题本        │  │ - 真实交易      │  │ - 生命周期管理   │
         └──────────────────┘  └──────────────────┘  └──────────────────┘
                    │                    │                       │
                    │                    │                       │
                    ▼                    ▼                       ▼
              data/目录           交易所API              src/plugins/
```

### 3.2 具体目标

**目标1：修复 evolution 插件**
- 将 `SelfCorrectionWorkflow`、`MistakeBook`、`WFABacktester` 封装到 evolution 插件
- 实现 `start_evolution()`、`stop_evolution()`、`get_status()` 方法

**目标2：修复 API 端点**
- `/api/evolution/start` 调用 `evolution_plugin.start_evolution()`
- `/api/evolution/stop` 调用 `evolution_plugin.stop_evolution()`
- `/api/evolution/status` 返回真实进化状态

**目标3：分离进化盘和实盘**
- 进化盘使用独立的数据存储 (`evolution_positions.json`)
- 前端区分"进化盘"和"实盘"模式
- API 端点分离：`/api/evolution/*` vs `/api/live/*`

**目标4：统一系统入口**
- 只通过 API 服务器控制进化盘和实盘
- `run_evolution.py` 和 `run_live.py` 作为备用

---

## 四、详细实施计划

### 阶段一：后端进化插件重构

#### 任务1.1：重写 evolution 插件

**文件：** `src/plugins/evolution/plugin.py`

**目标：** 将 `SelfCorrectionWorkflow` 封装到插件中

**实现步骤：**
1. 读取现有 `src/plugins/evolution/plugin.py` 代码
2. 读取 `run_evolution.py` 中的 `SelfCorrectionWorkflow` 调用逻辑
3. 在插件中添加：
   - `_init_workflow()` 方法：初始化 SelfCorrectionWorkflow
   - `_load_historical_data()` 方法：加载 `data/` 目录的本地数据
   - `start_evolution()` 方法：启动进化循环
   - `stop_evolution()` 方法：停止进化循环
   - `get_evolution_status()` 方法：获取进化状态
   - `get_decision_history()` 方法：获取决策历史

**关键代码结构：**
```python
class EvolutionPlugin(BasePlugin):
    def __init__(self, name: str = "evolution") -> None:
        super().__init__(name)
        self._workflow = None
        self._is_evolving = False
        self._cycle_count = 0
        self._historical_data = {}
    
    def on_load(self) -> None:
        self._init_workflow()
        self._load_historical_data()
    
    async def start_evolution(self) -> Dict[str, Any]:
        # 启动进化循环
        pass
    
    async def stop_evolution(self) -> Dict[str, Any]:
        # 停止进化循环
        pass
    
    def get_evolution_status(self) -> Dict[str, Any]:
        # 返回进化状态
        pass
```

**验收标准：**
- [ ] 插件加载时自动加载 `data/` 目录的历史数据
- [ ] `start_evolution()` 启动后台进化循环
- [ ] `stop_evolution()` 停止后台进化循环
- [ ] `get_evolution_status()` 返回真实的进化状态

---

#### 任务1.2：修复 API 端点

**文件：** `src/api/app.py`

**目标：** 连接真正的进化插件方法

**实现步骤：**
1. 修改 `get_evolution_status()` 端点：
   ```python
   @app.get("/api/evolution/status")
   async def get_evolution_status():
       evolution_plugin = get_evolution_plugin()
       return evolution_plugin.get_evolution_status()
   ```

2. 修改 `start_evolution()` 端点：
   ```python
   @app.post("/api/evolution/start")
   async def start_evolution():
       evolution_plugin = get_evolution_plugin()
       return await evolution_plugin.start_evolution()
   ```

3. 修改 `stop_evolution()` 端点：
   ```python
   @app.post("/api/evolution/stop")
   async def stop_evolution():
       evolution_plugin = get_evolution_plugin()
       return await evolution_plugin.stop_evolution()
   ```

4. 修改 `get_decision_traces()` 端点：
   ```python
   @app.get("/api/evolution/decision-traces")
   async def get_decision_traces(limit: int = 50):
       evolution_plugin = get_evolution_plugin()
       return evolution_plugin.get_decision_history(limit)
   ```

**验收标准：**
- [ ] `/api/evolution/status` 返回真实的进化状态
- [ ] `/api/evolution/start` 真正启动进化系统
- [ ] `/api/evolution/stop` 真正停止进化系统
- [ ] `/api/evolution/decision-traces` 返回决策历史

---

### 阶段二：进化盘与实盘分离

#### 任务2.1：创建进化盘数据存储

**文件：** `src/storage/evolution_storage.py`（新建）

**目标：** 独立的进化盘持仓和交易历史存储

**实现步骤：**
1. 创建 `src/storage/` 目录（如果不存在）
2. 创建 `EvolutionStorage` 类：
   ```python
   class EvolutionStorage:
       def __init__(self, storage_path: str = "evolution_positions.json"):
           self.storage_path = storage_path
           self._positions = []
           self._trades = []
       
       def add_position(self, position: Dict[str, Any]) -> None:
           self._positions.append(position)
           self._save()
       
       def close_position(self, position_id: str, trade: Dict[str, Any]) -> None:
           # 找到持仓并平仓
           self._trades.append(trade)
           self._save()
       
       def get_positions(self) -> List[Dict[str, Any]]:
           return self._positions
       
       def get_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
           return self._trades[-limit:]
   ```

3. 在 evolution 插件中集成存储：
   ```python
   class EvolutionPlugin(BasePlugin):
       def __init__(self, ...):
           ...
           self._storage = EvolutionStorage()
   ```

**验收标准：**
- [ ] 进化系统的持仓独立存储，不与实盘混淆
- [ ] 进化系统的交易历史独立存储
- [ ] 数据持久化到 JSON 文件

---

#### 任务2.2：添加进化盘 API 端点

**文件：** `src/api/app.py`

**目标：** 独立的进化盘持仓和交易查询

**实现步骤：**
添加以下端点：
```python
@app.get("/api/evolution/positions")
async def get_evolution_positions():
    """获取进化盘持仓"""
    evolution_plugin = get_evolution_plugin()
    return evolution_plugin.get_positions()

@app.get("/api/evolution/trades")
async def get_evolution_trades(limit: int = 100):
    """获取进化盘交易历史"""
    evolution_plugin = get_evolution_plugin()
    return evolution_plugin.get_trades(limit)
```

**验收标准：**
- [ ] `/api/evolution/positions` 返回进化盘持仓
- [ ] `/api/evolution/trades` 返回进化盘交易历史

---

### 阶段三：前端页面改造

#### 任务3.1：添加模式切换功能

**文件：** `frontend/src/core/AppStore.ts` 或新建 `frontend/src/core/ModeManager.ts`

**目标：** 区分"进化盘"和"实盘"模式

**实现步骤：**
1. 在状态管理中添加当前模式：
   ```typescript
   type SystemMode = 'evolution' | 'live' | 'idle'
   
   interface AppState {
     mode: SystemMode
     setMode: (mode: SystemMode) => void
   }
   ```

2. 在 Header 组件中添加模式切换器：
   ```typescript
   const ModeSwitcher: FC = () => {
     const { mode } = useAppStore()
     
     return (
       <div className="mode-switcher">
         <button 
           className={mode === 'evolution' ? 'active' : ''}
           onClick={() => setMode('evolution')}
         >
           🧬 进化盘
         </button>
         <button 
           className={mode === 'live' ? 'active' : ''}
           onClick={() => setMode('live')}
         >
           💰 实盘
         </button>
       </div>
     )
   }
   ```

**验收标准：**
- [ ] 用户可以切换"进化盘"和"实盘"模式
- [ ] 模式状态持久化（刷新页面后保持）

---

#### 任务3.2：修复进化页面数据源

**文件：** `frontend/src/plugins/evolution/index.tsx`

**目标：** 使用进化盘专属的 API 端点

**实现步骤：**
1. 修改 API 调用：
   ```typescript
   // 原来
   const { positions, trades } = useAppStore()
   
   // 改为
   const [positions, setPositions] = useState([])
   const [trades, setTrades] = useState([])
   
   useEffect(() => {
     // 获取进化盘专属数据
     evolutionApi.getPositions().then(setPositions)
     evolutionApi.getTrades().then(setTrades)
   }, [])
   ```

2. 修改进化控制按钮：
   ```typescript
   const handleStart = async () => {
     await evolutionApi.start()
     // 刷新状态
     const status = await evolutionApi.getStatus()
     setEvolutionStatus(status)
   }
   ```

**验收标准：**
- [ ] `/evolution` 页面的持仓数据来自 `/api/evolution/positions`
- [ ] `/evolution` 页面的交易历史来自 `/api/evolution/trades`
- [ ] 启动/停止按钮真正调用后端 API

---

#### 任务3.3：修复风险监控页面

**文件：** `frontend/src/plugins/risk/index.tsx`

**目标：** 显示真实的风险数据

**实现步骤：**
1. 检查 `risk_management` 插件的 API 方法
2. 修复前端调用：
   ```typescript
   // 修复异常事件获取
   const anomalies = await riskApi.getAnomalies()
   
   // 修复熔断器状态
   const circuitBreakers = await riskApi.getCircuitBreakers()
   ```

**验收标准：**
- [ ] `/risk` 页面的异常事件来自 `/api/risk/anomalies`
- [ ] `/risk` 页面的熔断器状态来自 `/api/risk/circuit-breakers`

---

### 阶段四：统一系统入口

#### 任务4.1：重构 run_evolution.py

**文件：** `run_evolution.py`

**目标：** 作为 API 服务器的替代启动方式

**实现步骤：**
1. 保留原有逻辑作为备用
2. 添加说明注释：
   ```python
   """
   警告：此脚本是独立运行方式，不通过 API 服务器。
   建议使用 API 服务器方式：
   
   1. 启动 API 服务器：
      python -m uvicorn src.api.app:app --port 9527
   
   2. 通过 API 控制进化盘：
      curl -X POST http://localhost:9527/api/evolution/start
   
   此脚本保留作为备用启动方式。
   """
   ```

**验收标准：**
- [ ] `run_evolution.py` 仍然可以独立运行
- [ ] 添加了清晰的说明文档

---

#### 任务4.2：重构 run_live.py

**文件：** `run_live.py`

**目标：** 作为 API 服务器的替代启动方式

**实现步骤：**
同任务4.1

**验收标准：**
- [ ] `run_live.py` 仍然可以独立运行
- [ ] 添加了清晰的说明文档

---

### 阶段五：测试验证

#### 任务5.1：单元测试

**测试文件：** `tests/plugins/test_evolution.py`（新建）

**测试内容：**
```python
def test_evolution_plugin_load():
    # 测试插件加载
    pass

def test_evolution_plugin_start():
    # 测试启动进化
    pass

def test_evolution_plugin_stop():
    # 测试停止进化
    pass

def test_evolution_status():
    # 测试状态查询
    pass
```

---

#### 任务5.2：集成测试

**测试内容：**
1. 启动 API 服务器
2. 调用 `/api/evolution/start`
3. 等待几个周期
4. 调用 `/api/evolution/status` 验证状态
5. 调用 `/api/evolution/trades` 验证交易历史
6. 调用 `/api/evolution/stop` 停止

---

#### 任务5.3：前端测试

**测试内容：**
1. 打开 http://localhost:5173
2. 切换到进化盘模式
3. 点击"启动进化"按钮
4. 验证状态显示"运行中"
5. 验证持仓和交易历史显示
6. 点击"停止进化"按钮
7. 验证状态显示"已停止"

---

## 五、文件清单

### 5.1 需要修改的文件

| 序号 | 文件路径 | 修改类型 | 说明 |
|------|---------|---------|------|
| 1 | `src/plugins/evolution/plugin.py` | 重写 | 封装进化逻辑 |
| 2 | `src/api/app.py` | 修改 | 修复 API 端点 |
| 3 | `src/storage/evolution_storage.py` | 新建 | 进化盘数据存储 |
| 4 | `frontend/src/core/ModeManager.ts` | 新建 | 模式管理 |
| 5 | `frontend/src/plugins/evolution/index.tsx` | 修改 | 修复数据源 |
| 6 | `frontend/src/plugins/risk/index.tsx` | 修改 | 修复数据源 |
| 7 | `run_evolution.py` | 修改 | 添加说明 |
| 8 | `run_live.py` | 修改 | 添加说明 |

### 5.2 需要新建的文件

| 序号 | 文件路径 | 说明 |
|------|---------|------|
| 1 | `src/storage/__init__.py` | 存储模块初始化 |
| 2 | `src/storage/evolution_storage.py` | 进化盘数据存储 |
| 3 | `tests/plugins/test_evolution.py` | 进化插件测试 |
| 4 | `docs/ARCHITECTURE.md` | 架构文档 |

---

## 六、实施顺序

```
阶段一：后端进化插件重构
├── 任务1.1：重写 evolution 插件
└── 任务1.2：修复 API 端点

阶段二：进化盘与实盘分离
├── 任务2.1：创建进化盘数据存储
└── 任务2.2：添加进化盘 API 端点

阶段三：前端页面改造
├── 任务3.1：添加模式切换功能
├── 任务3.2：修复进化页面数据源
└── 任务3.3：修复风险监控页面

阶段四：统一系统入口
├── 任务4.1：重构 run_evolution.py
└── 任务4.2：重构 run_live.py

阶段五：测试验证
├── 任务5.1：单元测试
├── 任务5.2：集成测试
└── 任务5.3：前端测试
```

---

## 七、验收标准总结

### 7.1 功能验收

- [ ] API 服务器启动成功 (`python -m uvicorn src.api.app:app --port 9527`)
- [ ] 前端启动成功 (`cd frontend && npm run dev`)
- [ ] 进化系统可以通过 API 启动/停止
- [ ] 进化盘持仓独立于实盘
- [ ] 前端可以切换进化盘/实盘模式

### 7.2 架构验收

- [ ] 前后端插件一一对应
- [ ] 进化盘和实盘数据分离
- [ ] API 端点全部连接真实逻辑（无占位符）

### 7.3 文档验收

- [ ] 更新 AGENTS.md
- [ ] 创建 ARCHITECTURE.md
- [ ] 每个启动方式有清晰说明

---

## 八、风险与注意事项

### 8.1 风险

1. **数据兼容风险**：修改 evolution 插件可能影响现有进化结果
   - 缓解：先备份 `evolution_results/` 目录

2. **前端重构风险**：修改页面可能导致现有功能损坏
   - 缓解：分阶段测试，每改一步验证一次

3. **并发风险**：同时运行进化盘和实盘可能冲突
   - 缓解：在 API 层做互斥检查

### 8.2 注意事项

1. 不要删除任何现有代码，只做添加和修改
2. 每个任务完成后都要测试验证
3. 保持代码风格与现有代码一致
4. 添加必要的日志记录

---

## 九、链路验证机制

### 9.1 验证目标

确保前后端、插件链路整个是正常的，包括：
1. **前端 → API** 通信正常
 服务器2. **API 服务器 → 后端插件** 调用正常
3. **插件 → 插件** 事件总线正常
4. **数据流完整性** 端到端正常

### 9.2 验证架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         链路验证架构                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐          │
│  │   前端      │      │  API服务器   │      │   插件系统   │          │
│  │ (浏览器)    │ ──▶  │  (FastAPI)  │ ──▶  │ (WyckoffApp)│          │
│  │             │      │             │      │             │          │
│  │ healthCheck│      │ /health     │      │ plugins[]   │          │
│  │ component  │      │ endpoints   │      │ health_check│          │
│  └──────┬──────┘      └──────┬──────┘      └──────┬──────┘          │
│         │                    │                    │                   │
│         ▼                    ▼                    ▼                   │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    链路状态监控                              │    │
│  │                                                              │    │
│  │  {                                                            │    │
│  │    "frontend_status": "healthy",    // 前端健康状态         │    │
│  │    "api_status": "healthy",         // API服务器健康状态    │    │
│  │    "plugin_chain": {                 // 插件链路状态         │    │
│  │      "evolution": "healthy",         // 进化插件             │    │
│  │      "position_manager": "healthy", // 持仓插件             │    │
│  │      "risk_management": "healthy",  // 风险插件             │    │
│  │      ...                                                     │    │
│  │    },                                                         │    │
│  │    "data_flow": "healthy"           // 数据流健康状态       │    │
│  │  }                                                            │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.3 验证端点

#### 9.3.1 全局健康检查端点

**文件：** `src/api/app.py`

**新增端点：**
```python
@app.get("/api/health")
async def health_check():
    """全局健康检查 - 返回完整链路状态"""
    result = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "frontend": "unknown",      # 前端状态（需要前端主动上报）
            "api": "healthy",            # API 服务器始终健康
            "plugins": {},               # 各插件状态
            "event_bus": "healthy",      # 事件总线状态
            "data_flow": "healthy",      # 数据流状态
        },
        "links": {
            "frontend_to_api": "unknown",
            "api_to_plugins": "unknown",
            "plugin_to_plugin": "unknown",
        }
    }
    
    # 检查插件状态
    if app_state.wyckoff_app:
        manager = app_state.wyckoff_app.plugin_manager
        for name, plugin in manager._plugins.items():
            try:
                health = plugin.health_check()
                result["components"]["plugins"][name] = {
                    "status": health.status.value,
                    "message": health.message,
                }
            except Exception as e:
                result["components"]["plugins"][name] = {
                    "status": "error",
                    "message": str(e),
                }
    
    # 检查整体状态
    all_healthy = all(
        p.get("status") == "healthy" 
        for p in result["components"]["plugins"].values()
    )
    result["status"] = "healthy" if all_healthy else "degraded"
    
    return result
```

#### 9.3.2 插件链路测试端点

**新增端点：**
```python
@app.get("/api/health/plugin-chain")
async def test_plugin_chain():
    """测试插件链路 - 模拟完整数据流"""
    
    # 测试步骤：
    # 1. 模拟数据进入 data_pipeline
    # 2. 验证 market_regime 处理
    # 3. 验证 orchestrator 决策
    # 4. 验证 position_manager 持仓变化
    # 5. 验证 risk_management 风险检查
    
    test_result = {
        "test_name": "plugin_chain_test",
        "steps": [],
        "passed": True,
    }
    
    # Step 1: 数据管道
    try:
        data_plugin = get_plugin("data_pipeline")
        test_result["steps"].append({
            "step": "data_pipeline",
            "status": "passed" if data_plugin else "failed"
        })
    except Exception as e:
        test_result["steps"].append({"step": "data_pipeline", "status": "error", "error": str(e)})
        test_result["passed"] = False
    
    # Step 2: 市场体制检测
    try:
        regime_plugin = get_plugin("market_regime")
        test_result["steps"].append({
            "step": "market_regime",
            "status": "passed" if regime_plugin else "failed"
        })
    except Exception as e:
        test_result["steps"].append({"step": "market_regime", "status": "error", "error": str(e)})
        test_result["passed"] = False
    
    # ... 其他步骤
    
    return test_result
```

### 9.4 前端健康检查组件

**文件：** `frontend/src/components/HealthChecker.tsx`（新建）

**功能：**
```typescript
import { useState, useEffect } from 'react'
import { api } from '../core/ApiClient'

interface HealthStatus {
  status: 'healthy' | 'degraded' | 'error'
  timestamp: string
  components: {
    frontend: string
    api: string
    plugins: Record<string, { status: string; message: string }>
    event_bus: string
    data_flow: string
  }
  links: {
    frontend_to_api: string
    api_to_plugins: string
    plugin_to_plugin: string
  }
}

export const HealthChecker: FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await api.get('/api/health')
        setHealth(res.data)
      } catch (error) {
        console.error('健康检查失败', error)
      }
    }
    
    checkHealth()
    const interval = setInterval(checkHealth, 30000) // 每30秒检查一次
    
    return () => clearInterval(interval)
  }, [])
  
  if (!health) return <div>加载中...</div>
  
  return (
    <div className="health-check">
      <div className={`status-badge ${health.status}`}>
        {health.status === 'healthy' ? '✅' : '⚠️'} 系统状态: {health.status}
      </div>
      
      <div className="components">
        {Object.entries(health.components.plugins).map(([name, info]) => (
          <div key={name} className={`plugin-status ${info.status}`}>
            {info.status === 'healthy' ? '✅' : '❌'} {name}: {info.message}
          </div>
        ))}
      </div>
    </div>
  )
}
```

### 9.5 验证检查清单

每次启动系统后，按以下顺序验证：

| 步骤 | 验证项 | 验证方法 | 预期结果 |
|------|-------|---------|---------|
| 1 | API服务器启动 | `curl http://localhost:9527/` | 返回 JSON 响应 |
| 2 | 健康检查端点 | `curl http://localhost:9527/api/health` | 返回完整健康状态 |
| 3 | 插件加载 | 检查 `/api/health` 的 plugins 字段 | 所有插件状态为 healthy |
| 4 | 进化插件 | `curl http://localhost:9527/api/plugins \| grep evolution` | 插件状态为 ACTIVE |
| 5 | 前端启动 | 浏览器打开 http://localhost:5173 | 页面正常显示 |
| 6 | 前端API连接 | 检查浏览器控制台 | 无 502/504 错误 |
| 7 | 进化页面 | 打开 /evolution 页面 | 页面正常加载 |
| 8 | 启动进化 | POST /api/evolution/start | 返回 {status: "started"} |
| 9 | 进化状态 | GET /api/evolution/status | 返回真实状态（不是默认值） |
| 10 | 停止进化 | POST /api/evolution/stop | 返回 {status: "stopped"} |

### 9.6 自动验证脚本

**文件：** `scripts/verify_system.sh`（新建）

```bash
#!/bin/bash

echo "========================================="
echo "威科夫系统链路验证脚本"
echo "========================================="

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 验证函数
verify() {
    local name=$1
    local cmd=$2
    local expected=$3
    
    echo -n "验证 $name... "
    result=$(eval $cmd 2>/dev/null)
    
    if [[ "$result" == *"$expected"* ]]; then
        echo -e "${GREEN}通过${NC}"
        return 0
    else
        echo -e "${RED}失败${NC}"
        echo "  预期: $expected"
        echo "  实际: $result"
        return 1
    fi
}

# 1. API服务器启动
verify "API服务器" "curl -s http://localhost:9527/" "WyckoffApp"

# 2. 健康检查
verify "健康检查端点" "curl -s http://localhost:9527/api/health" "healthy"

# 3. 插件加载
verify "插件系统" "curl -s http://localhost:9527/api/plugins" "market_regime"

# 4. 进化插件状态
verify "进化插件" "curl -s http://localhost:9527/api/plugins \| grep evolution" "ACTIVE"

# 5. 启动进化
verify "启动进化" "curl -s -X POST http://localhost:9527/api/evolution/start" "started"

# 6. 进化状态
verify "进化状态" "curl -s http://localhost:9527/api/evolution/status" "running"

# 7. 停止进化
verify "停止进化" "curl -s -X POST http://localhost:9527/api/evolution/stop" "stopped"

echo "========================================="
echo "验证完成"
echo "========================================="
```

---

## 十、进化路径验证机制

### 10.1 进化系统完整链路

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          进化系统完整链路                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐│
│  │ 1. 数据加载  │───▶│ 2. WFA回测   │───▶│ 3. 权重变异  │───▶│ 4. 验证  ││
│  │              │    │              │    │              │    │          ││
│  │ data/目录    │    │ 训练/测试    │    │ 变异算子     │    │ 性能提升 ││
│  │ ETHUSDT.csv  │    │ Walk-Forward │    │ 突变/交叉    │    │ 显著性   ││
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────────┘│
│         │                   │                   │                   │     │
│         ▼                   ▼                   ▼                   ▼     │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                        5. 错题本 & 记忆系统                          │ │
│  │                                                                      │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │ │
│  │  │ 错误记录   │  │ 决策追踪   │  │ 向量化记忆 │  │ 进化档案   │   │ │
│  │  │ MistakeBook│  │ TraceLog   │  │ Archivist  │  │ JSONL存储  │   │ │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘   │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│         │                                                                  │
│         ▼                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                        6. 进化结果输出                               │ │
│  │                                                                      │ │
│  │  evolution_results/cycle_N_timestamp.json                           │ │
│  │  - 变异前权重                                                        │ │
│  │  - 变异后权重                                                        │ │
│  │  - 性能提升                                                          │ │
│  │  - WFA验证结果                                                       │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 进化路径验证点

| 验证点 | 验证内容 | 验证方法 | 预期结果 |
|-------|---------|---------|---------|
| **VP1** | 数据加载 | 检查 `data/` 目录文件 | 至少有 ETHUSDT_*.csv 文件 |
| **VP2** | 数据解析 | 调用 `_load_historical_data()` | DataFrame 不为空，列名正确 |
| **VP3** | WFA基准 | 调用 `initialize_wfa_baseline()` | 基准性能值有效 |
| **VP4** | 权重变异 | 调用 `WeightVariator.mutate()` | 权重在合理范围内变化 |
| **VP5** | WFA验证 | 调用 `WFABacktester.run_wfa()` | 返回有效窗口数 ≥ 2 |
| **VP6** | 错题本 | 调用 `MistakeBook.add_mistake()` | 错误被正确记录 |
| **VP7** | 进化周期 | 调用 `run_correction_cycle()` | 返回成功结果 |
| **VP8** | 结果保存 | 检查 `evolution_results/` | 生成 JSON 文件 |

### 10.3 进化逻辑验证 API 端点

**文件：** `src/api/app.py`

**新增端点：**

```python
@app.get("/api/evolution/verify/data")
async def verify_evolution_data():
    """验证进化数据加载"""
    if not app_state.wyckoff_app:
        raise HTTPException(status_code=500, detail="WyckoffApp not initialized")
    
    evolution_plugin = get_evolution_plugin()
    if not evolution_plugin:
        raise HTTPException(status_code=404, detail="Evolution plugin not found")
    
    # 检查数据加载
    data_status = {
        "data_dir_exists": os.path.exists("data"),
        "files": [],
        "loaded_timeframes": list(evolution_plugin._historical_data.keys()),
        "data_counts": {
            tf: len(df) for tf, df in evolution_plugin._historical_data.items()
        }
    }
    
    # 列出数据文件
    if os.path.exists("data"):
        for f in os.listdir("data"):
            if f.endswith((".csv", ".pkl")):
                filepath = os.path.join("data", f)
                data_status["files"].append({
                    "name": f,
                    "size_kb": os.path.getsize(filepath) / 1024,
                    "modified": datetime.fromtimestamp(
                        os.path.getmtime(filepath)
                    ).isoformat()
                })
    
    return {
        "status": "ok" if data_status["loaded_timeframes"] else "error",
        "verification_point": "VP1_VP2",
        "data": data_status
    }


@app.get("/api/evolution/verify/wfa")
async def verify_evolution_wfa():
    """验证WFA回测引擎"""
    evolution_plugin = get_evolution_plugin()
    if not evolution_plugin or not evolution_plugin._workflow:
        raise HTTPException(status_code=404, detail="Evolution workflow not initialized")
    
    workflow = evolution_plugin._workflow
    
    wfa_status = {
        "backtester_initialized": workflow.wfa_backtester is not None,
        "baseline_initialized": hasattr(workflow.wfa_backtester, '_baseline_metrics'),
        "train_days": workflow.config.get("wfa_backtester_config", {}).get("train_days", 0),
        "test_days": workflow.config.get("wfa_backtester_config", {}).get("test_days", 0),
        "min_windows": workflow.config.get("wfa_backtester_config", {}).get("min_window_count", 0),
    }
    
    # 尝试获取基准性能
    try:
        if hasattr(workflow.wfa_backtester, '_baseline_metrics'):
            baseline = workflow.wfa_backtester._baseline_metrics
            wfa_status["baseline_metrics"] = baseline
    except Exception as e:
        wfa_status["baseline_error"] = str(e)
    
    return {
        "status": "ok" if wfa_status["backtester_initialized"] else "error",
        "verification_point": "VP3_VP5",
        "wfa": wfa_status
    }


@app.get("/api/evolution/verify/weights")
async def verify_evolution_weights():
    """验证权重变异系统"""
    evolution_plugin = get_evolution_plugin()
    if not evolution_plugin or not evolution_plugin._workflow:
        raise HTTPException(status_code=404, detail="Evolution workflow not initialized")
    
    workflow = evolution_plugin._workflow
    
    weights_status = {
        "variator_initialized": workflow.weight_variator is not None,
        "current_weights": workflow.current_config.get("period_weight_filter", {}).get("weights", {}),
        "mutation_rate": workflow.config.get("weight_variator_config", {}).get("mutation_rate", 0),
        "max_mutation_percent": workflow.config.get("weight_variator_config", {}).get("max_mutation_percent", 0),
    }
    
    # 验证权重和为1
    weights = weights_status["current_weights"]
    if weights:
        total = sum(weights.values())
        weights_status["weights_sum"] = total
        weights_status["weights_valid"] = abs(total - 1.0) < 0.01
    
    return {
        "status": "ok" if weights_status["variator_initialized"] else "error",
        "verification_point": "VP4",
        "weights": weights_status
    }


@app.get("/api/evolution/verify/mistake-book")
async def verify_evolution_mistake_book():
    """验证错题本系统"""
    evolution_plugin = get_evolution_plugin()
    if not evolution_plugin or not evolution_plugin._workflow:
        raise HTTPException(status_code=404, detail="Evolution workflow not initialized")
    
    workflow = evolution_plugin._workflow
    mistake_book = workflow.mistake_book
    
    mistake_status = {
        "initialized": mistake_book is not None,
        "total_mistakes": 0,
        "recent_mistakes": [],
    }
    
    if mistake_book:
        try:
            # 获取错误统计
            if hasattr(mistake_book, 'get_all_mistakes'):
                all_mistakes = mistake_book.get_all_mistakes()
                mistake_status["total_mistakes"] = len(all_mistakes)
                mistake_status["recent_mistakes"] = all_mistakes[-5:] if all_mistakes else []
        except Exception as e:
            mistake_status["error"] = str(e)
    
    return {
        "status": "ok" if mistake_status["initialized"] else "error",
        "verification_point": "VP6",
        "mistake_book": mistake_status
    }


@app.get("/api/evolution/verify/results")
async def verify_evolution_results():
    """验证进化结果输出"""
    results_dir = "evolution_results"
    
    results_status = {
        "dir_exists": os.path.exists(results_dir),
        "total_cycles": 0,
        "latest_result": None,
        "files": [],
    }
    
    if os.path.exists(results_dir):
        files = [f for f in os.listdir(results_dir) if f.endswith(".json")]
        results_status["total_cycles"] = len(files)
        
        # 获取最新结果
        if files:
            files.sort(reverse=True)
            latest_file = os.path.join(results_dir, files[0])
            try:
                with open(latest_file, "r", encoding="utf-8") as f:
                    results_status["latest_result"] = json.load(f)
            except Exception as e:
                results_status["latest_result_error"] = str(e)
            
            # 列出最近10个文件
            for f in files[:10]:
                filepath = os.path.join(results_dir, f)
                results_status["files"].append({
                    "name": f,
                    "size_kb": os.path.getsize(filepath) / 1024,
                    "modified": datetime.fromtimestamp(
                        os.path.getmtime(filepath)
                    ).isoformat()
                })
    
    return {
        "status": "ok" if results_status["total_cycles"] > 0 else "warning",
        "verification_point": "VP8",
        "results": results_status
    }


@app.get("/api/evolution/verify/full-chain")
async def verify_evolution_full_chain():
    """验证完整进化链路 - 一键验证所有环节"""
    
    verification_results = {
        "timestamp": datetime.now().isoformat(),
        "overall_status": "ok",
        "checks": []
    }
    
    # VP1_VP2: 数据加载
    try:
        data_res = await verify_evolution_data()
        verification_results["checks"].append({
            "point": "VP1_VP2",
            "name": "数据加载",
            "status": data_res["status"],
            "details": data_res["data"]
        })
    except Exception as e:
        verification_results["checks"].append({
            "point": "VP1_VP2",
            "name": "数据加载",
            "status": "error",
            "error": str(e)
        })
        verification_results["overall_status"] = "error"
    
    # VP3_VP5: WFA回测
    try:
        wfa_res = await verify_evolution_wfa()
        verification_results["checks"].append({
            "point": "VP3_VP5",
            "name": "WFA回测引擎",
            "status": wfa_res["status"],
            "details": wfa_res["wfa"]
        })
    except Exception as e:
        verification_results["checks"].append({
            "point": "VP3_VP5",
            "name": "WFA回测引擎",
            "status": "error",
            "error": str(e)
        })
        verification_results["overall_status"] = "error"
    
    # VP4: 权重变异
    try:
        weights_res = await verify_evolution_weights()
        verification_results["checks"].append({
            "point": "VP4",
            "name": "权重变异",
            "status": weights_res["status"],
            "details": weights_res["weights"]
        })
    except Exception as e:
        verification_results["checks"].append({
            "point": "VP4",
            "name": "权重变异",
            "status": "error",
            "error": str(e)
        })
        verification_results["overall_status"] = "error"
    
    # VP6: 错题本
    try:
        mistake_res = await verify_evolution_mistake_book()
        verification_results["checks"].append({
            "point": "VP6",
            "name": "错题本",
            "status": mistake_res["status"],
            "details": mistake_res["mistake_book"]
        })
    except Exception as e:
        verification_results["checks"].append({
            "point": "VP6",
            "name": "错题本",
            "status": "error",
            "error": str(e)
        })
        verification_results["overall_status"] = "error"
    
    # VP8: 进化结果
    try:
        results_res = await verify_evolution_results()
        verification_results["checks"].append({
            "point": "VP8",
            "name": "进化结果",
            "status": results_res["status"],
            "details": {
                "total_cycles": results_res["results"]["total_cycles"],
                "latest_file": results_res["results"]["files"][0] if results_res["results"]["files"] else None
            }
        })
    except Exception as e:
        verification_results["checks"].append({
            "point": "VP8",
            "name": "进化结果",
            "status": "error",
            "error": str(e)
        })
    
    return verification_results
```

### 10.4 进化验证检查清单

| 步骤 | 验证项 | API 端点 | 预期结果 |
|------|-------|---------|---------|
| 1 | 数据文件存在 | `GET /api/evolution/verify/data` | `files` 列表不为空 |
| 2 | 数据已加载 | `GET /api/evolution/verify/data` | `loaded_timeframes` 包含 H4/H1/M15 |
| 3 | WFA初始化 | `GET /api/evolution/verify/wfa` | `backtester_initialized: true` |
| 4 | 基准性能有效 | `GET /api/evolution/verify/wfa` | `baseline_metrics` 存在 |
| 5 | 权重变异器 | `GET /api/evolution/verify/weights` | `variator_initialized: true` |
| 6 | 权重和为1 | `GET /api/evolution/verify/weights` | `weights_valid: true` |
| 7 | 错题本初始化 | `GET /api/evolution/verify/mistake-book` | `initialized: true` |
| 8 | 完整链路 | `GET /api/evolution/verify/full-chain` | `overall_status: ok` |

### 10.5 进化验证脚本

**文件：** `scripts/verify_evolution.sh`（新建）

```bash
#!/bin/bash

echo "========================================="
echo "进化系统路径验证脚本"
echo "========================================="

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 验证数据加载
echo -e "\n${YELLOW}[VP1_VP2] 数据加载验证${NC}"
data_result=$(curl -s http://localhost:9527/api/evolution/verify/data)
echo "$data_result" | python -m json.tool 2>/dev/null || echo "$data_result"

# 验证WFA回测
echo -e "\n${YELLOW}[VP3_VP5] WFA回测验证${NC}"
wfa_result=$(curl -s http://localhost:9527/api/evolution/verify/wfa)
echo "$wfa_result" | python -m json.tool 2>/dev/null || echo "$wfa_result"

# 验证权重变异
echo -e "\n${YELLOW}[VP4] 权重变异验证${NC}"
weights_result=$(curl -s http://localhost:9527/api/evolution/verify/weights)
echo "$weights_result" | python -m json.tool 2>/dev/null || echo "$weights_result"

# 验证错题本
echo -e "\n${YELLOW}[VP6] 错题本验证${NC}"
mistake_result=$(curl -s http://localhost:9527/api/evolution/verify/mistake-book)
echo "$mistake_result" | python -m json.tool 2>/dev/null || echo "$mistake_result"

# 验证进化结果
echo -e "\n${YELLOW}[VP8] 进化结果验证${NC}"
results_result=$(curl -s http://localhost:9527/api/evolution/verify/results)
echo "$results_result" | python -m json.tool 2>/dev/null || echo "$results_result"

# 完整链路验证
echo -e "\n${YELLOW}[FULL] 完整链路验证${NC}"
full_result=$(curl -s http://localhost:9527/api/evolution/verify/full-chain)
overall_status=$(echo "$full_result" | python -c "import sys,json; print(json.load(sys.stdin).get('overall_status','error'))" 2>/dev/null)

if [ "$overall_status" = "ok" ]; then
    echo -e "${GREEN}✅ 进化系统链路验证通过${NC}"
else
    echo -e "${RED}❌ 进化系统链路验证失败${NC}"
fi

echo "$full_result" | python -m json.tool 2>/dev/null || echo "$full_result"

echo "========================================="
echo "验证完成"
echo "========================================="
```

### 10.6 前端进化验证组件

**文件：** `frontend/src/components/EvolutionVerifier.tsx`（新建）

```typescript
import { useState, useEffect } from 'react'
import { api } from '../core/ApiClient'

interface VerificationCheck {
  point: string
  name: string
  status: 'ok' | 'error' | 'warning'
  details?: Record<string, any>
  error?: string
}

interface VerificationResult {
  timestamp: string
  overall_status: 'ok' | 'error' | 'warning'
  checks: VerificationCheck[]
}

export const EvolutionVerifier: FC = () => {
  const [result, setResult] = useState<VerificationResult | null>(null)
  const [loading, setLoading] = useState(false)

  const runVerification = async () => {
    setLoading(true)
    try {
      const res = await api.get('/api/evolution/verify/full-chain')
      setResult(res.data)
    } catch (error) {
      console.error('验证失败', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    runVerification()
  }, [])

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'ok': return '✅'
      case 'warning': return '⚠️'
      case 'error': return '❌'
      default: return '❓'
    }
  }

  if (loading) return <div>验证中...</div>
  if (!result) return <div>无验证结果</div>

  return (
    <div className="evolution-verifier">
      <div className="verifier-header">
        <h3>进化路径验证</h3>
        <button onClick={runVerification}>重新验证</button>
      </div>
      
      <div className={`overall-status ${result.overall_status}`}>
        {getStatusIcon(result.overall_status)} 整体状态: {result.overall_status}
      </div>
      
      <div className="checks-list">
        {result.checks.map((check, index) => (
          <div key={index} className={`check-item ${check.status}`}>
            <div className="check-header">
              {getStatusIcon(check.status)} [{check.point}] {check.name}
            </div>
            {check.details && (
              <pre className="check-details">
                {JSON.stringify(check.details, null, 2)}
              </pre>
            )}
            {check.error && (
              <div className="check-error">{check.error}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
```

---

## 十一、相关文档

- `docs/PLUGIN_DEVELOPMENT.md` - 插件开发指南
- `AGENTS.md` - 项目开发指南
- `config.yaml` - 配置文件

---

**计划制定时间：** 2026-03-11
**计划版本：** v1.0
**状态：** 待实施
