# -*- coding: utf-8 -*-
"""
执行器基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseExecutor(ABC):
    """执行器基类"""

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行命令

        Returns:
            执行结果字典
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源"""
        pass
