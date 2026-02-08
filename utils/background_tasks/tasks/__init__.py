"""
后台任务模块 - 自动导入所有任务

设计原则：
- 自动扫描并导入当前目录下所有 .py 文件（排除 __init__.py）
- 任务文件中使用 @background_task 装饰器自动注册
- 新增任务只需创建新文件，无需修改此文件
"""

import importlib
import pkgutil

from logger import get_logger

logger = get_logger("background_tasks.tasks")


def _auto_import_tasks():
    """自动导入当前包下所有任务模块（兼容 PyInstaller 打包环境）"""
    for finder, module_name, is_pkg in pkgutil.iter_modules(__path__):
        if module_name.startswith("_"):
            continue
        try:
            importlib.import_module(f".{module_name}", package=__name__)
            logger.debug(f"✅ 已导入任务模块: {module_name}")
        except Exception as e:
            logger.warning(f"⚠️ 导入任务模块失败: {module_name}, error={e}")


# 模块加载时自动导入所有任务
_auto_import_tasks()
