"""
后台任务模块 - 自动导入所有任务

设计原则：
- 自动扫描并导入当前目录下所有 .py 文件（排除 __init__.py）
- 任务文件中使用 @background_task 装饰器自动注册
- 新增任务只需创建新文件，无需修改此文件
- PyInstaller 打包环境下使用显式列表（pkgutil.iter_modules 在 frozen 环境可能失效）
"""

import importlib
import pkgutil

from logger import get_logger
from utils.app_paths import is_frozen

logger = get_logger("background_tasks.tasks")

# PyInstaller frozen 环境下 pkgutil.iter_modules(__path__) 可能返回空列表，
# 因为模块被打包进 PYZ archive 而非真实文件系统。
# 维护显式列表作为 fallback。新增任务模块时需同步更新此列表。
_KNOWN_TASK_MODULES = [
    'memory_flush',
    'mem0_update',
    'recommended_questions',
    'title_generation',
    'playbook_extraction',
]


def _auto_import_tasks():
    """自动导入当前包下所有任务模块（兼容 PyInstaller 打包环境）"""
    if is_frozen():
        # PyInstaller 打包环境：使用显式列表
        for module_name in _KNOWN_TASK_MODULES:
            try:
                importlib.import_module(f".{module_name}", package=__name__)
                logger.debug(f"已导入任务模块: {module_name}")
            except Exception as e:
                logger.warning(f"导入任务模块失败: {module_name}, error={e}")
    else:
        # 开发环境：自动扫描发现
        for finder, module_name, is_pkg in pkgutil.iter_modules(__path__):
            if module_name.startswith("_"):
                continue
            try:
                importlib.import_module(f".{module_name}", package=__name__)
                logger.debug(f"已导入任务模块: {module_name}")
            except Exception as e:
                logger.warning(f"导入任务模块失败: {module_name}, error={e}")


# 模块加载时自动导入所有任务
_auto_import_tasks()
