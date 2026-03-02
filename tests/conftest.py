"""
pytest 配置文件
确保 src 目录在测试路径中
"""

import sys
import os
from pathlib import Path

# 获取项目根目录（tests/ 的父目录）
project_root = Path(__file__).parent.parent

# 将项目根目录添加到 sys.path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 确保 src 目录在路径中
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
