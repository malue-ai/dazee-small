"""
工具模块

提供各种工具类和辅助函数
"""

from utils.background_tasks import BackgroundTaskService, get_background_task_service
from utils.message_utils import (
    normalize_message_format,
    extract_text_from_message,
)
from utils.s3_uploader import S3Uploader, get_s3_uploader
from utils.json_utils import (
    JSONExtractor,
    extract_json,
    extract_json_list,
)
from utils.file_processor import (
    FileProcessor,
    FileCategory,
    ProcessedFile,
    get_file_processor,
)
from utils.context_manager import (
    ContextManager,
    TruncationStrategy,
    TokenStats,
    get_context_manager,
    truncate_messages,
    count_tokens,
    count_messages_tokens,
)

__all__ = [
    # 后台任务
    "BackgroundTaskService",
    "get_background_task_service",
    
    # 消息工具
    "normalize_message_format",
    "extract_text_from_message",
    
    # S3 上传
    "S3Uploader",
    "get_s3_uploader",
    
    # JSON 工具
    "JSONExtractor",
    "extract_json",
    "extract_json_list",
    
    # 文件处理
    "FileProcessor",
    "FileCategory",
    "ProcessedFile",
    "get_file_processor",
    
    # 上下文管理
    "ContextManager",
    "TruncationStrategy",
    "TokenStats",
    "get_context_manager",
    "truncate_messages",
    "count_tokens",
    "count_messages_tokens",
]

