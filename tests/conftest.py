"""
Pytest 配置文件

提供测试 fixtures 和配置
"""

# ⚠️ 必须在最开头加载 .env，在导入任何模块之前（包括 pathlib）
# 因为项目根目录的 __init__.py 会触发模块导入链
import os as _os

def _load_env_file():
    """手动解析 .env 文件并设置环境变量（不依赖任何第三方库）"""
    # 计算 .env 文件路径
    conftest_dir = _os.path.dirname(_os.path.abspath(__file__))
    env_path = _os.path.join(_os.path.dirname(conftest_dir), ".env")
    
    if not _os.path.exists(env_path):
        return
    
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue
            # 解析 KEY=VALUE
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # 移除引号
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                # 只设置未定义的环境变量
                if key and not _os.environ.get(key):
                    _os.environ[key] = value

# 立即加载
_load_env_file()

# 如果 .env 中没有这些配置，使用默认值
if not _os.getenv("DATABASE_URL"):
    _os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/zenflux_test"

if not _os.getenv("REDIS_URL"):
    _os.environ["REDIS_URL"] = "redis://localhost:6379/1"

if not _os.getenv("ANTHROPIC_API_KEY"):
    _os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key-for-testing"

# 现在可以安全导入其他模块了
import os
from pathlib import Path

# 配置 pytest-asyncio：使用 session scope 的 event loop
# 避免每个测试函数使用不同的 loop 导致数据库连接问题
pytest_plugins = ('pytest_asyncio',)

import pytest
import asyncio
from typing import Generator


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    创建事件循环用于异步测试
    
    使用 session scope 以便在所有测试中复用
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_logger(mocker):
    """
    Mock logger 用于测试日志输出
    """
    return mocker.patch("logger.get_logger")
