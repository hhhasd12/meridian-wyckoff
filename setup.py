#!/usr/bin/env python3
"""
威科夫全自动逻辑引擎 - 一键安装脚本

功能：
1. 检查Python环境
2. 安装依赖包
3. 创建虚拟环境（可选）
4. 验证安装
5. 创建配置文件模板
"""

import os
import sys
import subprocess
import platform
from pathlib import Path
import shutil


class WyckoffInstaller:
    """威科夫引擎安装器"""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.requirements_file = self.project_root / "requirements.txt"
        self.config_template = self.project_root / "config.example.yaml"
        self.config_file = self.project_root / "config.yaml"

        # 颜色输出（支持Windows和Unix）
        self.colors = {
            "reset": "\033[0m",
            "bold": "\033[1m",
            "green": "\033[32m",
            "yellow": "\033[33m",
            "red": "\033[31m",
            "blue": "\033[34m",
            "cyan": "\033[36m",
        }

        # Windows不支持ANSI颜色
        if platform.system() == "Windows":
            for key in self.colors:
                self.colors[key] = ""

    def print_colored(self, text, color="reset", bold=False):
        """彩色输出"""
        style = self.colors[color]
        if bold:
            style += self.colors["bold"]
        print(f"{style}{text}{self.colors['reset']}")

    def print_header(self, text):
        """打印标题"""
        self.print_colored(f"\n{'=' * 60}", "cyan", True)
        self.print_colored(f" {text}", "cyan", True)
        self.print_colored(f"{'=' * 60}", "cyan", True)

    def print_success(self, text):
        """打印成功消息"""
        self.print_colored(f"✅ {text}", "green")

    def print_warning(self, text):
        """打印警告消息"""
        self.print_colored(f"⚠️  {text}", "yellow")

    def print_error(self, text):
        """打印错误消息"""
        self.print_colored(f"❌ {text}", "red")

    def print_info(self, text):
        """打印信息消息"""
        self.print_colored(f"ℹ️  {text}", "blue")

    def check_python_version(self):
        """检查Python版本"""
        self.print_header("检查Python环境")

        python_version = sys.version_info
        self.print_info(f"当前Python版本: {sys.version}")

        if python_version.major < 3 or (
            python_version.major == 3 and python_version.minor < 9
        ):
            self.print_error("需要Python 3.9或更高版本")
            self.print_info("请从 https://python.org 下载最新版本")
            return False

        self.print_success(f"Python版本符合要求 (>=3.9)")
        return True

    def check_requirements_file(self):
        """检查requirements文件"""
        self.print_header("检查依赖文件")

        if not self.requirements_file.exists():
            self.print_error(f"未找到依赖文件: {self.requirements_file}")
            return False

        self.print_success(f"找到依赖文件: {self.requirements_file}")

        # 读取依赖
        with open(self.requirements_file, "r", encoding="utf-8") as f:
            requirements = [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]

        self.print_info(f"发现 {len(requirements)} 个依赖包")
        return True

    def install_dependencies(self, use_venv=False, venv_name="venv"):
        """安装依赖包"""
        self.print_header("安装依赖包")

        # 确定pip命令
        pip_cmd = [sys.executable, "-m", "pip"]

        if use_venv:
            venv_path = self.project_root / venv_name
            if platform.system() == "Windows":
                pip_cmd = [str(venv_path / "Scripts" / "python.exe"), "-m", "pip"]
            else:
                pip_cmd = [str(venv_path / "bin" / "python"), "-m", "pip"]

        # 升级pip
        self.print_info("升级pip...")
        try:
            subprocess.run(
                [*pip_cmd, "install", "--upgrade", "pip"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.print_success("pip升级成功")
        except subprocess.CalledProcessError as e:
            self.print_warning(f"pip升级失败: {e}")

        # 安装依赖
        self.print_info("安装项目依赖...")
        try:
            result = subprocess.run(
                [*pip_cmd, "install", "-r", str(self.requirements_file)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.print_success("依赖安装成功")

            # 显示安装的包
            lines = result.stdout.split("\n")
            installed = [line for line in lines if "Successfully installed" in line]
            if installed:
                self.print_info(installed[0])

        except subprocess.CalledProcessError as e:
            self.print_error(f"依赖安装失败: {e}")
            self.print_error(f"错误输出: {e.stderr}")
            return False

        return True

    def create_virtual_environment(self, venv_name="venv"):
        """创建虚拟环境"""
        self.print_header("创建虚拟环境")

        venv_path = self.project_root / venv_name

        if venv_path.exists():
            self.print_warning(f"虚拟环境已存在: {venv_path}")
            response = input("是否重新创建？(y/N): ").strip().lower()
            if response != "y":
                self.print_info("使用现有虚拟环境")
                return True
            shutil.rmtree(venv_path)

        self.print_info(f"创建虚拟环境到: {venv_path}")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.print_success("虚拟环境创建成功")

            # 显示激活命令
            self.print_header("虚拟环境激活命令")
            if platform.system() == "Windows":
                self.print_info(f"激活: {venv_name}\\Scripts\\activate")
            else:
                self.print_info(f"激活: source {venv_name}/bin/activate")

            return True
        except subprocess.CalledProcessError as e:
            self.print_error(f"虚拟环境创建失败: {e}")
            return False

    def create_config_template(self):
        """创建配置文件模板"""
        self.print_header("创建配置文件")

        if self.config_file.exists():
            self.print_warning(f"配置文件已存在: {self.config_file}")
            return True

        # 如果没有模板，创建基本配置
        config_content = """# 威科夫引擎配置文件
# 最后更新: 2026年1月20日

# 数据源配置
data_sources:
  crypto:
    enabled: true
    exchanges: ["binance", "bybit"]
    symbols: ["BTC/USDT", "ETH/USDT"]
    timeframes: ["4h", "1h", "15m", "5m"]
  
  stocks:
    enabled: false
    symbols: ["AAPL", "GOOGL", "TSLA"]
    timeframes: ["1d", "4h", "1h"]

# 威科夫参数
wyckoff:
  # 成交量分析
  min_volume_ratio: 1.5      # 最小成交量比率
  volume_spike_threshold: 2.0 # 成交量突增阈值
  
  # 遗产系统
  heritage_decay_rate: 0.85   # 遗产衰减率
  min_heritage_score: 0.3     # 最小遗产分数
  
  # 确认条件
  confirmation_bars: 3        # 确认K线数
  breakout_confirmation_pct: 0.02  # 突破确认百分比
  
  # 状态机
  state_timeout_bars: 20      # 状态超时K线数
  min_evidence_score: 0.6     # 最小证据分数

# 多周期配置
multi_timeframe:
  # 周期权重 (总和应为1.0)
  weights:
    weekly: 0.25
    daily: 0.20
    four_hour: 0.18
    one_hour: 0.15
    fifteen_min: 0.12
    five_min: 0.10
  
  # 冲突解决
  conflict_resolution:
    enable_priority_override: true
    trend_overrides_range: true
    higher_tf_weight_multiplier: 1.5

# 风险管理
risk_management:
  position_sizing:
    max_position_size: 0.1     # 最大仓位比例 (10%)
    min_position_size: 0.01    # 最小仓位比例 (1%)
    
  stop_loss:
    fixed_percentage: 0.02     # 固定止损比例 (2%)
    atr_multiplier: 1.5        # ATR倍数止损
    trailing_enabled: true
    trailing_activation_pct: 0.015  # 跟踪止损激活百分比
    
  take_profit:
    risk_reward_ratio: 2.0     # 风险回报比
    partial_profit_levels: [0.5, 0.8, 1.0]  # 分批止盈水平

# 性能与监控
performance:
  # 缓存设置
  cache_enabled: true
  cache_size_mb: 512
  cache_ttl_seconds: 3600
  
  # 监控设置
  health_check_interval: 300   # 健康检查间隔 (秒)
  performance_log_interval: 60 # 性能日志间隔 (秒)
  
  # 资源限制
  max_memory_usage: 0.8        # 最大内存使用率
  max_cpu_usage: 0.7           # 最大CPU使用率
  
  # 日志设置
  log_level: "INFO"            # DEBUG, INFO, WARNING, ERROR
  log_file: "logs/wyckoff.log"
  log_rotation: "daily"        # daily, weekly, monthly
  log_retention_days: 30

# 系统协调器
orchestrator:
  default_mode: "simulation"   # realtime, backtest, simulation
  simulation_speed: "1x"       # 1x, 5x, 10x, max
  
  # 回测设置
  backtest:
    initial_capital: 10000.0
    commission_rate: 0.001     # 手续费率 (0.1%)
    slippage_pct: 0.0005       # 滑点百分比
    
  # 实时交易设置
  realtime:
    data_refresh_interval: 60  # 数据刷新间隔 (秒)
    signal_check_interval: 30  # 信号检查间隔 (秒)
    max_concurrent_symbols: 5  # 最大并发交易品种

# 自动化进化
automated_evolution:
  mistake_book:
    enabled: true
    max_entries: 1000
    auto_analysis_interval: 86400  # 自动分析间隔 (秒)
    
  weight_variation:
    enabled: true
    max_variation_pct: 0.05    # 最大变异百分比 (5%)
    adaptation_rate: 0.1       # 适应率
    
  wfa_backtest:
    enabled: true
    walk_forward_windows: 5    # 前向窗口数
    train_test_ratio: 0.7      # 训练测试比例

# 通知设置 (可选)
notifications:
  email:
    enabled: false
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    sender_email: ""
    sender_password: ""
    recipient_emails: []
    
  telegram:
    enabled: false
    bot_token: ""
    chat_id: ""
    
  webhook:
    enabled: false
    webhook_url: ""
    secret_key: ""

# 高级设置 (仅限高级用户)
advanced:
  # 算法参数
  algorithm:
    fvg_sensitivity: 0.7       # FVG敏感度 (0.0-1.0)
    curve_fitting_precision: 0.8  # 曲线拟合精度
    regime_confidence_threshold: 0.65  # 体制置信度阈值
    
  # 实验功能
  experimental:
    enable_ml_enhancements: false
    enable_correlation_analysis: false
    enable_sentiment_integration: false
    
  # 调试模式
  debug:
    enable_debug_logging: false
    export_decision_logs: false
    visualize_state_transitions: false
"""

        try:
            # 创建配置目录
            config_dir = self.project_root / "config"
            config_dir.mkdir(exist_ok=True)

            # 写入配置文件
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(config_content)

            self.print_success(f"配置文件已创建: {self.config_file}")
            self.print_info("请根据实际情况修改配置参数")
            return True

        except Exception as e:
            self.print_error(f"创建配置文件失败: {e}")
            return False

    def verify_installation(self):
        """验证安装"""
        self.print_header("验证安装")

        test_imports = [
            ("numpy", "numpy"),
            ("pandas", "pandas"),
            ("scipy", "scipy"),
            ("plotly", "plotly"),
        ]

        all_passed = True

        for name, module_name in test_imports:
            try:
                __import__(module_name)
                self.print_success(f"{name}: 导入成功")
            except ImportError as e:
                self.print_error(f"{name}: 导入失败 - {e}")
                all_passed = False

        # 测试项目模块导入
        self.print_info("测试项目模块导入...")

        # 添加项目根目录到Python路径
        sys.path.insert(0, str(self.project_root))

        project_modules = [
            ("市场体制模块", "src.plugins.market_regime.detector"),
            (
                "威科夫状态机",
                "src.plugins.wyckoff_state_machine.wyckoff_state_machine_legacy",
            ),
            ("系统协调器", "src.plugins.orchestrator.system_orchestrator_legacy"),
        ]

        for name, module_path in project_modules:
            try:
                __import__(module_path)
                self.print_success(f"{name}: 导入成功")
            except ImportError as e:
                self.print_warning(f"{name}: 导入失败 - {e}")
                # 不标记为失败，因为可能缺少依赖

        if all_passed:
            self.print_success("基本依赖验证通过")
        else:
            self.print_warning("部分依赖验证失败，可能需要手动安装")

        return all_passed

    def create_startup_scripts(self):
        """创建启动脚本"""
        self.print_header("创建启动脚本")

        scripts_dir = self.project_root / "scripts"
        scripts_dir.mkdir(exist_ok=True)

        # Windows批处理脚本
        windows_script = scripts_dir / "start_wyckoff.bat"
        windows_content = """@echo off
chcp 65001 >nul
echo ========================================
echo  威科夫全自动逻辑引擎 - Windows启动脚本
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到Python，请确保已安装Python 3.9+
    pause
    exit /b 1
)

REM 检查虚拟环境
if exist "venv\\Scripts\\activate.bat" (
    echo ✅ 检测到虚拟环境，正在激活...
    call venv\\Scripts\\activate.bat
) else (
    echo ℹ️  未找到虚拟环境，使用系统Python
)

REM 添加项目路径
set PYTHONPATH=%PYTHONPATH%;%CD%

REM 检查配置文件
if not exist "config.yaml" (
    echo ⚠️  未找到config.yaml，使用默认配置
    copy config.example.yaml config.yaml >nul 2>&1
    if errorlevel 1 (
        echo ℹ️  创建默认配置...
        python -c "open('config.yaml', 'w').write('# 默认配置\\n')"
    )
)

REM 启动演示
echo.
echo 请选择启动模式：
echo 1. 最终演示（数字生命体全流程）
echo 2. 实时流水线演示
echo 3. 性能分析工具
echo 4. 退出
echo.
set /p choice="请输入选择 (1-4): "

if "%choice%"=="1" (
    echo 启动最终演示...
    python examples/final_digital_life_demo.py
) else if "%choice%"=="2" (
    echo 启动实时流水线演示...
    python examples/real_time_pipeline_demo.py
) else if "%choice%"=="3" (
    echo 启动性能分析工具...
    python examples/performance_analysis.py
) else (
    echo 退出
    exit /b 0
)

pause
"""

        # Linux/macOS shell脚本
        linux_script = scripts_dir / "start_wyckoff.sh"
        linux_content = """#!/bin/bash

# 威科夫全自动逻辑引擎 - Linux/macOS启动脚本

set -e

echo "========================================"
echo "  威科夫全自动逻辑引擎 - 启动脚本"
echo "========================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到Python3，请确保已安装Python 3.9+"
    exit 1
fi

# 检查虚拟环境
if [ -f "venv/bin/activate" ]; then
    echo "✅ 检测到虚拟环境，正在激活..."
    source venv/bin/activate
else
    echo "ℹ️  未找到虚拟环境，使用系统Python"
fi

# 添加项目路径
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 检查配置文件
if [ ! -f "config.yaml" ]; then
    echo "⚠️  未找到config.yaml，使用默认配置"
    if [ -f "config.example.yaml" ]; then
        cp config.example.yaml config.yaml
    else
        echo "ℹ️  创建默认配置..."
        echo "# 默认配置" > config.yaml
    fi
fi

# 启动菜单
echo ""
echo "请选择启动模式："
echo "1. 最终演示（数字生命体全流程）"
echo "2. 实时流水线演示"
echo "3. 性能分析工具"
echo "4. 退出"
echo ""
read -p "请输入选择 (1-4): " choice

case $choice in
    1)
        echo "启动最终演示..."
        python3 examples/final_digital_life_demo.py
        ;;
    2)
        echo "启动实时流水线演示..."
        python3 examples/real_time_pipeline_demo.py
        ;;
    3)
        echo "启动性能分析工具..."
        python3 examples/performance_analysis.py
        ;;
    4)
        echo "退出"
        exit 0
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac
"""

        try:
            # 写入Windows脚本
            with open(windows_script, "w", encoding="utf-8") as f:
                f.write(windows_content)
            self.print_success(f"Windows启动脚本: {windows_script}")

            # 写入Linux脚本
            with open(linux_script, "w", encoding="utf-8") as f:
                f.write(linux_content)

            # 设置执行权限 (Linux/macOS)
            if platform.system() != "Windows":
                os.chmod(linux_script, 0o755)

            self.print_success(f"Linux/macOS启动脚本: {linux_script}")
            self.print_info("启动脚本已创建到 scripts/ 目录")

            # 创建快捷方式说明
            readme = scripts_dir / "README.md"
            with open(readme, "w", encoding="utf-8") as f:
                f.write("# 启动脚本说明\n\n")
                f.write("## Windows 用户\n")
                f.write("双击 `start_wyckoff.bat` 或命令行运行:\n")
                f.write("```cmd\nscripts\\start_wyckoff.bat\n```\n\n")
                f.write("## Linux/macOS 用户\n")
                f.write(
                    "```bash\nchmod +x scripts/start_wyckoff.sh\n./scripts/start_wyckoff.sh\n```\n"
                )

            return True

        except Exception as e:
            self.print_error(f"创建启动脚本失败: {e}")
            return False

    def create_directory_structure(self):
        """创建目录结构"""
        self.print_header("创建目录结构")

        directories = [
            "logs",
            "data",
            "data/historical",
            "data/realtime",
            "cache",
            "exports",
            "exports/decisions",
            "exports/reports",
            "backtests",
            "backtests/results",
            "backtests/scenarios",
        ]

        for directory in directories:
            dir_path = self.project_root / directory
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                self.print_success(f"创建目录: {directory}")
            except Exception as e:
                self.print_error(f"创建目录 {directory} 失败: {e}")

        return True

    def run_quick_test(self):
        """运行快速测试"""
        self.print_header("运行快速测试")

        # 检查是否安装了pytest
        try:
            import pytest
        except ImportError:
            self.print_warning("未安装pytest，跳过测试")
            return True

        # 运行测试
        test_dir = self.project_root / "tests"
        if not test_dir.exists():
            self.print_warning("测试目录不存在，跳过测试")
            return True

        self.print_info("运行单元测试...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                self.print_success("测试通过")
                # 提取测试结果
                lines = result.stdout.split("\n")
                passed = sum(1 for line in lines if "PASSED" in line)
                failed = sum(1 for line in lines if "FAILED" in line)
                self.print_info(f"通过: {passed}, 失败: {failed}")
            else:
                self.print_warning("测试失败")
                self.print_info(result.stdout[-500:])  # 显示最后500字符

        except Exception as e:
            self.print_error(f"运行测试时出错: {e}")

        return True

    def print_final_instructions(self):
        """打印最终说明"""
        self.print_header("安装完成")

        self.print_colored("🎉 威科夫全自动逻辑引擎安装完成！", "green", True)

        self.print_colored("\n📋 下一步：", "cyan", True)
        self.print_info("1. 编辑配置文件: config.yaml")
        self.print_info("2. 运行演示脚本了解系统功能")
        self.print_info("3. 查看文档了解详细使用方法")

        self.print_colored("\n🚀 启动系统：", "cyan", True)
        if platform.system() == "Windows":
            self.print_info("双击 scripts/start_wyckoff.bat")
        else:
            self.print_info("运行: ./scripts/start_wyckoff.sh")

        self.print_colored("\n📚 文档位置：", "cyan", True)
        self.print_info("部署指南: docs/deployment_guide.md")
        self.print_info("项目进度: 项目进程说明书.md")
        self.print_info("开发计划: 项目开发计划书.md")

        self.print_colored("\n🔧 测试系统：", "cyan", True)
        self.print_info("最终演示: python examples/final_digital_life_demo.py")
        self.print_info("实时流水线: python examples/real_time_pipeline_demo.py")
        self.print_info("性能分析: python examples/performance_analysis.py")

        self.print_colored("\n⚠️  重要提醒：", "yellow", True)
        self.print_info("本系统为技术演示和研究用途")
        self.print_info("实盘交易前请充分测试和验证")

        self.print_colored("\n📞 支持：", "cyan", True)
        self.print_info("查看项目进程说明书了解最新状态")
        self.print_info("运行测试确保系统完整: pytest tests/")

        self.print_colored(f"\n{'=' * 60}", "cyan", True)
        self.print_colored("  祝您使用愉快！交易顺利！", "green", True)
        self.print_colored(f"{'=' * 60}", "cyan", True)


def main():
    """主安装程序"""
    installer = WyckoffInstaller()

    # 显示欢迎信息
    installer.print_header("威科夫全自动逻辑引擎 - 安装程序")
    installer.print_colored("版本: 1.0.0 | 状态: 第五阶段75%完成", "blue")
    installer.print_colored("最后更新: 2026年1月20日", "blue")
    installer.print_colored(f"{'=' * 60}", "cyan")

    # 安装选项
    print("\n安装选项:")
    print("1. 快速安装（仅安装依赖）")
    print("2. 完整安装（依赖 + 虚拟环境 + 配置）")
    print("3. 开发安装（完整 + 测试）")
    print("4. 自定义安装")
    print("5. 退出")

    try:
        choice = input("\n请选择安装模式 (1-5): ").strip()
    except KeyboardInterrupt:
        print("\n安装已取消")
        return

    if choice == "5":
        installer.print_info("安装已取消")
        return

    # 根据选择设置选项
    use_venv = choice in ["2", "3", "4"]
    run_tests = choice in ["3", "4"]
    create_config = choice in ["2", "3", "4"]
    create_scripts = choice in ["2", "3", "4"]
    create_dirs = choice in ["2", "3", "4"]

    if choice == "4":
        # 自定义选项
        print("\n自定义选项:")
        use_venv = input("创建虚拟环境？ (y/N): ").strip().lower() == "y"
        create_config = input("创建配置文件？ (y/N): ").strip().lower() == "y"
        create_scripts = input("创建启动脚本？ (y/N): ").strip().lower() == "y"
        create_dirs = input("创建目录结构？ (y/N): ").strip().lower() == "y"
        run_tests = input("运行测试？ (y/N): ").strip().lower() == "y"

    # 执行安装步骤
    try:
        # 1. 检查Python
        if not installer.check_python_version():
            return

        # 2. 检查requirements
        if not installer.check_requirements_file():
            return

        # 3. 创建虚拟环境（如果需要）
        if use_venv:
            if not installer.create_virtual_environment():
                installer.print_warning("继续使用系统Python")

        # 4. 安装依赖
        if not installer.install_dependencies(use_venv=use_venv):
            installer.print_warning("依赖安装遇到问题，继续安装...")

        # 5. 创建目录结构
        if create_dirs:
            installer.create_directory_structure()

        # 6. 创建配置文件
        if create_config:
            installer.create_config_template()

        # 7. 创建启动脚本
        if create_scripts:
            installer.create_startup_scripts()

        # 8. 验证安装
        installer.verify_installation()

        # 9. 运行测试（如果需要）
        if run_tests:
            installer.run_quick_test()

        # 10. 最终说明
        installer.print_final_instructions()

    except KeyboardInterrupt:
        installer.print_warning("\n安装被用户中断")
    except Exception as e:
        installer.print_error(f"安装过程中出现未知错误: {e}")
        installer.print_error("请查看错误信息并手动安装")


if __name__ == "__main__":
    main()
