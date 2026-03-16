# 前后端分离架构设计

## 一、架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        前后端分离架构                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    前端层 (Frontend)                      │   │
│  │                                                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │  Dashboard  │  │   Config    │  │   Monitor   │      │   │
│  │  │   Plugin    │  │   Plugin    │  │   Plugin    │      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │              Frontend Plugin System               │   │   │
│  │  │  - 插件加载器                                       │   │   │
│  │  │  - 事件总线                                         │   │   │
│  │  │  - 状态管理                                         │   │   │
│  │  │  - API 客户端                                       │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              │ HTTP/WebSocket                   │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    后端层 (Backend)                       │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │              FastAPI Application                  │   │   │
│  │  │  - REST API                                        │   │   │
│  │  │  - WebSocket                                       │   │   │
│  │  │  - 认证授权                                         │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  │                              │                           │   │
│  │                              ▼                           │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │              Backend Plugin System                │   │   │
│  │  │  - 13个业务插件                                     │   │   │
│  │  │  - 事件总线                                         │   │   │
│  │  │  - 插件管理器                                       │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 二、统一启动入口

```bash
# 后端服务
python run.py --mode=api              # 启动 API 服务器
python run.py --mode=trading          # 启动交易系统
python run.py --mode=evolution        # 启动进化系统
python run.py --mode=all              # 启动全部服务

# 前端服务
python run.py --mode=web              # 启动前端开发服务器
python run.py --mode=web --build      # 构建前端生产版本
```

## 三、API 端点设计

### 3.1 核心 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/system/status` | GET | 系统状态 |
| `/api/system/start` | POST | 启动系统 |
| `/api/system/stop` | POST | 停止系统 |
| `/api/plugins` | GET | 插件列表 |
| `/api/plugins/{name}` | GET | 插件详情 |
| `/api/plugins/{name}/enable` | POST | 启用插件 |
| `/api/plugins/{name}/disable` | POST | 禁用插件 |
| `/api/positions` | GET | 持仓列表 |
| `/api/positions` | POST | 开仓 |
| `/api/positions/{symbol}` | DELETE | 平仓 |
| `/api/trades` | GET | 交易历史 |
| `/api/config` | GET/PUT | 配置管理 |
| `/api/evolution/status` | GET | 进化状态 |
| `/api/evolution/start` | POST | 启动进化 |

### 3.2 WebSocket 端点

| 端点 | 说明 |
|------|------|
| `/ws/positions` | 持仓实时更新 |
| `/ws/trades` | 交易实时推送 |
| `/ws/signals` | 信号实时推送 |
| `/ws/logs` | 日志实时流 |

## 四、前端插件系统

### 4.1 插件结构

```
frontend/
├── src/
│   ├── core/
│   │   ├── PluginLoader.ts      # 插件加载器
│   │   ├── EventBus.ts          # 事件总线
│   │   ├── StateManager.ts      # 状态管理
│   │   └── ApiClient.ts         # API 客户端
│   ├── plugins/
│   │   ├── dashboard/           # 仪表盘插件
│   │   ├── positions/           # 持仓管理插件
│   │   ├── trades/              # 交易历史插件
│   │   ├── config/              # 配置管理插件
│   │   ├── evolution/           # 进化监控插件
│   │   └── logs/                # 日志查看插件
│   ├── App.tsx
│   └── main.tsx
├── package.json
└── vite.config.ts
```

### 4.2 前端插件接口

```typescript
interface FrontendPlugin {
  name: string;
  version: string;
  routes: RouteConfig[];
  components: Record<string, Component>;
  menus: MenuConfig[];
  events: {
    subscribe: string[];
    publish: string[];
  };
  init(context: PluginContext): void;
  destroy(): void;
}
```

## 五、技术栈选择

### 后端
- **FastAPI** - 高性能异步 API 框架
- **WebSocket** - 实时通信
- **Pydantic** - 数据验证

### 前端
- **React 18** - UI 框架
- **TypeScript** - 类型安全
- **Vite** - 构建工具
- **TailwindCSS** - 样式
- **Zustand** - 状态管理
- **React Query** - 数据获取

## 六、实现计划

### Phase 1: 后端 API 层
1. 创建 FastAPI 应用
2. 实现 REST API 端点
3. 实现 WebSocket 端点
4. 添加认证中间件

### Phase 2: 前端基础
1. 创建 React + Vite 项目
2. 实现插件加载器
3. 实现事件总线
4. 实现 API 客户端

### Phase 3: 前端插件
1. Dashboard 插件
2. Positions 插件
3. Trades 插件
4. Config 插件
5. Evolution 插件

### Phase 4: 整合测试
1. 前后端联调
2. 性能优化
3. 生产构建
