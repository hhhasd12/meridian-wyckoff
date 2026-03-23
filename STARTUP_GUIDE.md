# 威科夫全自动逻辑引擎 - 生产环境启动指南

## 🚀 快速开始

### 1. 准备工作
```bash
# 安装依赖
pip install -r requirements.txt

# 创建必要的目录
mkdir -p logs reports status data_cache
```

### 2. 配置文件
```bash
# 使用默认配置文件（已包含）
cp config.yaml config_production.yaml

# 编辑配置文件
# 重要：修改 paper_trading 字段决定运行模式
# - true: 模拟交易（推荐）
# - false: 实盘交易（危险！）
```

### 3. 启动系统
```bash
# 使用默认配置启动
python run.py --mode=trading

# 使用自定义配置启动
python run.py --mode=trading config_production.yaml
```

## 📋 核心功能

### 1. 实盘/模拟切换
- **配置文件控制**: `paper_trading: true/false`
- **安全机制**: 实盘交易需要显式设置为 `false`
- **模式切换**: 修改配置后重启生效

### 2. 守护进程 (24/7运行)
- **不死鸟机制**: 崩溃后60秒自动重启
- **错误隔离**: 单个模块错误不影响整体运行
- **资源监控**: 自动检查内存/CPU使用率

### 3. 状态播报
- **每小时报告**: 系统健康状态
- **实时监控**: 处理次数、错误次数、最后信号
- **日志记录**: 详细运行日志保存在 `logs/` 目录

### 4. 安全检查
- **TECH_SPECS验证**: 启动时自动校验数据格式
- **配置验证**: 检查必需参数
- **环境检查**: 验证依赖和权限

## ⚙️ 配置说明

### 关键配置项
```yaml
# 运行模式
paper_trading: true  # 模拟交易（安全）
# paper_trading: false  # 实盘交易（危险！）

# 运行参数
processing_interval: 60      # 数据处理间隔（秒）
evolution_interval: 3600     # 进化间隔（秒）
health_report_interval: 3600 # 健康报告间隔（秒）

# 数据源
use_real_data: true          # 使用真实数据
symbols: ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
timeframes: ["H4", "H1", "M15"]
historical_days: 30          # 历史数据天数
```

### 环境变量
```bash
# 覆盖配置文件
export WYCKOFF_PAPER_TRADING=false
export WYCKOFF_API_KEY=your_api_key
export WYCKOFF_API_SECRET=your_api_secret
export WYCKOFF_LOG_LEVEL=DEBUG
```

## 📊 监控与维护

### 日志文件
```
logs/
├── wyckoff_production.log  # 主日志
├── errors.log              # 错误日志
└── system_run.log          # 系统运行日志
```

### 报告文件
```
reports/
├── health_report_*.txt     # 健康报告
└── evolution_report_*.json # 进化报告
```

### 状态文件
```
status/
├── final_status_*.json     # 最终状态
└── system_state_*.json     # 系统状态
```

## 🛡️ 安全警告

### 实盘交易前必须
1. **充分测试**: 至少运行模拟交易1个月
2. **小资金开始**: 初始资金不超过总资金的10%
3. **风险控制**: 设置合理的止损和仓位限制
4. **定期备份**: 备份配置和交易记录
5. **监控运行**: 实时监控系统状态

### 紧急停止
```bash
# 方法1: Ctrl+C (推荐)
# 方法2: kill -SIGINT <pid>
# 方法3: 删除 state_file 文件
```

## 🔧 故障排除

### 常见问题

#### 1. 启动失败
```bash
# 检查依赖
pip install -r requirements.txt

# 检查配置文件
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# 检查目录权限
mkdir -p logs reports status
```

#### 2. 数据获取失败
```bash
# 检查网络连接
ping api.binance.com

# 检查API密钥
echo $WYCKOFF_API_KEY

# 切换到模拟数据
# 修改 config.yaml: use_real_data: false
```

#### 3. 内存泄漏
```bash
# 查看内存使用
ps aux | grep python

# 调整缓存大小
# 修改 config.yaml: cache.size_mb: 256
```

#### 4. 性能问题
```bash
# 减少处理频率
# 修改 config.yaml: processing_interval: 120

# 减少交易品种
# 修改 config.yaml: symbols: ["BTC/USDT"]
```

## 📈 性能优化

### 生产环境建议
1. **服务器配置**: 至少4核CPU，8GB内存
2. **网络环境**: 稳定的互联网连接
3. **存储空间**: 至少10GB可用空间
4. **备份策略**: 每日自动备份

### 监控指标
- **处理延迟**: < 5秒
- **内存使用**: < 80%
- **错误率**: < 1%
- **运行时间**: > 99%

## 🔄 升级与维护

### 版本升级
```bash
# 备份当前配置
cp config.yaml config.yaml.backup

# 更新代码
git pull origin main

# 检查依赖
pip install -r requirements.txt

# 重启系统
python run.py --mode=trading
```

### 定期维护
1. **日志清理**: 每月清理旧日志
2. **数据备份**: 每周备份交易数据
3. **性能检查**: 每日检查系统状态
4. **安全更新**: 及时更新依赖包

## 📞 支持与帮助

### 文档资源
- `docs/TECH_SPECS.md` - 技术规范
- `docs/deployment_guide.md` - 部署指南
- `README.md` - 项目说明

### 问题反馈
1. 查看日志文件定位问题
2. 检查配置文件是否正确
3. 搜索现有问题解决方案
4. 提交issue到项目仓库

### 紧急联系
- **系统崩溃**: 检查 `logs/errors.log`
- **数据异常**: 检查 `data_cache/` 目录
- **配置错误**: 使用 `config.example.yaml` 对比

---

## 🎯 最佳实践

### 开发环境
```bash
# 使用模拟交易
paper_trading: true
use_real_data: false
processing_interval: 10  # 快速测试
```

### 测试环境
```bash
# 使用真实数据但模拟交易
paper_trading: true
use_real_data: true
processing_interval: 60
```

### 生产环境
```bash
# 实盘交易（谨慎！）
paper_trading: false
use_real_data: true
processing_interval: 60
health_report_interval: 3600
```

---

**最后更新**: 2026-02-06  
**版本**: v1.0  
**状态**: 生产就绪 ✅

> 注意: 实盘交易有风险，请谨慎操作。建议先充分测试再投入真实资金。