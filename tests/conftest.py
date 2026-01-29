"""
Pytest 配置文件

提供测试 fixtures 和配置
"""

import os

# ⚠️ 必须在导入任何项目模块之前设置环境变量
# 因为某些模块（如 infra.database.engine）在导入时就会读取环境变量
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/zenflux_test"

if not os.getenv("REDIS_URL"):
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"

if not os.getenv("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key-for-testing"

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
