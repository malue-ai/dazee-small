"""
后台任务模块 - 懒加载所有任务

设计原则：
- 任务文件中使用 @background_task 装饰器自动注册
- 新增任务只需创建新文件，无需修改此文件
- 任务模块在首次调用 ensure_tasks_imported() 时才导入，
  避免在 __init__.py 中使用 importlib.import_module 导致 import lock 死锁
- PyInstaller 打包环境下使用显式列表（pkgutil.iter_modules 在 frozen 环境可能失效）
"""

import importlib
import pkgutil

from logger import get_logger

logger = get_logger("background_tasks.tasks")

_KNOWN_TASK_MODULES = [
    'memory_flush',
    'mem0_update',
    'recommended_questions',
    'title_generation',
    'playbook_extraction',
    'persona_build',
]

_tasks_imported = False


def _auto_import_tasks():
    """自动导入当前包下所有任务模块（兼容 PyInstaller 打包环境）"""
    from utils.app_paths import is_frozen

    if is_frozen():
        for module_name in _KNOWN_TASK_MODULES:
            try:
                importlib.import_module(f".{module_name}", package=__name__)
                logger.debug(f"已导入任务模块: {module_name}")
            except Exception as e:
                logger.warning(f"导入任务模块失败: {module_name}, error={e}")
    else:
        for finder, module_name, is_pkg in pkgutil.iter_modules(__path__):
            if module_name.startswith("_"):
                continue
            try:
                importlib.import_module(f".{module_name}", package=__name__)
                logger.debug(f"已导入任务模块: {module_name}")
            except Exception as e:
                logger.warning(f"导入任务模块失败: {module_name}, error={e}")


def ensure_tasks_imported():
    """首次调用时导入所有任务模块（懒加载，避免 import 阶段死锁）"""
    global _tasks_imported
    if _tasks_imported:
        return
    _tasks_imported = True
    _auto_import_tasks()
