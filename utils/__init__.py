"""
工具模块

提供各种工具类和辅助函数
"""

from utils.background_tasks import BackgroundTaskService, get_background_task_service
from utils.file_processor import (
    FileCategory,
    FileProcessor,
    ProcessedFile,
    get_file_processor,
)
from utils.json_utils import (
    JSONExtractor,
    extract_json,
    extract_json_list,
)
from utils.message_utils import (
    extract_text_from_message,
    normalize_message_format,
)
# S3 上传模块已删除，不再导出
# TODO: 迁移到 local_store

__all__ = [
    # 后台任务
    "BackgroundTaskService",
    "get_background_task_service",
    # 消息工具
    "normalize_message_format",
    "extract_text_from_message",
    # JSON 工具
    "JSONExtractor",
    "extract_json",
    "extract_json_list",
    # 文件处理
    "FileProcessor",
    "FileCategory",
    "ProcessedFile",
    "get_file_processor",
]
