"""
Pytest 配置文件

提供测试 fixtures 和配置
"""

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
