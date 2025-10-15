"""
CLI入口点
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_dev.cli.advanced_cli import main

if __name__ == "__main__":
    main()