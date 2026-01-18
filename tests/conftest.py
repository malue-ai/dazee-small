"""
pytest 配置文件

设置测试环境，包括：
- 添加项目根目录到 Python 路径
- 配置 asyncio 模式
- 共享的 fixtures
"""

import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# pytest-asyncio 配置
import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """使用默认的事件循环策略"""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
