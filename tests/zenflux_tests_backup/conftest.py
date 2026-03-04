"""
测试配置

确保项目根目录在 sys.path 中，使 import 正常工作。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
