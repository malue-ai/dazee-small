"""
日志管理模块

提供统一的日志接口，支持上下文追踪和性能监控。

快速开始:
=========

```python
from logger import get_logger, set_request_context, log_execution_time

logger = get_logger()

# 设置请求上下文（在请求入口处调用一次）
set_request_context(user_id="u-123", conversation_id="conv-456")

# 记录日志（自动包含上下文信息）
logger.info("处理请求")
logger.error("发生错误", exc_info=True)

# 性能监控
with log_execution_time("数据库查询", logger):
    results = await db.query(...)
```

日志输出:
========
- 控制台：彩色易读格式（开发环境）
- 文件：JSON 格式，便于 AWS CloudWatch 分析和快速定位
"""
import asyncio
import functools
import inspect
import json
import logging
import logging.config
import sys
import time
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

# ============================================================
# 配置
# ============================================================


def _get_log_dir() -> Path:
    """获取日志目录，统一使用 app_paths 管理路径"""
    try:
        from utils.app_paths import get_logs_dir
        return get_logs_dir()
    except Exception:
        # Fallback：app_paths 尚未可用时（极早期导入）
        if getattr(sys, 'frozen', False):
            import platform
            import os
            if platform.system() == 'Darwin':
                home = os.environ.get('HOME', os.path.expanduser('~'))
                return Path(home) / 'Library' / 'Application Support' / 'com.zenflux.agent' / 'logs'
            return Path(sys.executable).parent / 'logs'
        import tempfile
        return Path(tempfile.gettempdir()) / 'zenflux-agent' / 'logs'


_log_dir = _get_log_dir()


LOG_CONFIG = {
    "level": "INFO",
    "console_enabled": True,
    "file_enabled": True,
    "file": str(_log_dir / "app.log"),
    "error_file": str(_log_dir / "error.log"),
    "max_size": 50 * 1024 * 1024,  # 50MB
    "backup_count": 10,
}

# ============================================================
# 上下文变量（用于追踪请求）
# ============================================================
_user_id: ContextVar[str] = ContextVar('user_id', default='')
_conversation_id: ContextVar[str] = ContextVar('conversation_id', default='')
_message_id: ContextVar[str] = ContextVar('message_id', default='')


def set_request_context(
    user_id: str = '',
    conversation_id: str = '',
    message_id: str = ''
) -> None:
    """
    设置请求上下文（在请求入口处调用）
    
    Args:
        user_id: 用户ID
        conversation_id: 对话ID
        message_id: 消息ID
    """
    if user_id:
        _user_id.set(user_id)
    if conversation_id:
        _conversation_id.set(conversation_id)
    if message_id:
        _message_id.set(message_id)


def clear_request_context() -> None:
    """清除请求上下文（在请求结束时调用）"""
    _user_id.set('')
    _conversation_id.set('')
    _message_id.set('')


@contextmanager
def log_execution_time(operation: str, logger: Optional[logging.Logger] = None):
    """
    记录操作执行时间
    
    Args:
        operation: 操作名称
        logger: 日志记录器（可选）
    
    Usage:
        with log_execution_time("数据库查询", logger):
            results = await db.query(...)
    """
    if logger is None:
        logger = logging.getLogger("zenflux")
    
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(f"{operation} 完成", extra={
            "operation": operation,
            "duration_ms": round(duration_ms, 2)
        })


# ============================================================
# 格式化器
# ============================================================

class _ContextFilter(logging.Filter):
    """添加上下文信息到日志记录"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.user_id = _user_id.get() or '-'
        record.conversation_id = _conversation_id.get() or '-'
        record.message_id = _message_id.get() or '-'
        return True


class _ConsoleFormatter(logging.Formatter):
    """控制台格式化器（彩色易读）"""
    
    COLORS = {
        'DEBUG': '\033[36m',     # 青色
        'INFO': '\033[32m',      # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 红色
        'CRITICAL': '\033[35m',  # 紫色
    }
    RESET = '\033[0m'
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s [%(levelname)s] [%(user_id)s:%(conversation_id)s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self.use_colors = sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors:
            record = logging.makeLogRecord(record.__dict__)
            color = self.COLORS.get(record.levelname, '')
            record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


class _JsonFormatter(logging.Formatter):
    """
    JSON 格式化器（用于文件输出和 AWS CloudWatch）
    
    输出示例:
    {"ts":"2024-01-01T12:00:00.123Z","level":"INFO","user":"u-123","conv":"c-456","logger":"chat_service","msg":"处理请求","duration_ms":45.2}
    """
    
    # 排除的内置属性
    _RESERVED = {
        'name', 'msg', 'args', 'created', 'levelname', 'levelno',
        'pathname', 'filename', 'module', 'exc_info', 'exc_text',
        'stack_info', 'lineno', 'funcName', 'msecs', 'relativeCreated',
        'thread', 'threadName', 'processName', 'process', 'message',
        'taskName', 'user_id', 'conversation_id', 'message_id'
    }
    
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec='milliseconds'),
            "level": record.levelname,
            "user": getattr(record, 'user_id', '-'),
            "conv": getattr(record, 'conversation_id', '-'),
            "msg_id": getattr(record, 'message_id', '-'),
            "logger": record.name.replace('zenflux.', ''),
            "file": f"{record.filename}:{record.lineno}",
            "func": record.funcName or "-",
            "msg": record.getMessage(),
        }
        
        # 添加异常信息
        if record.exc_info:
            log["error"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "msg": str(record.exc_info[1]) if record.exc_info[1] else None,
                "trace": ''.join(traceback.format_exception(*record.exc_info)).strip()
            }
        
        # 添加 extra 字段
        for key, value in record.__dict__.items():
            if key not in self._RESERVED:
                try:
                    json.dumps(value)
                    log[key] = value
                except (TypeError, ValueError):
                    log[key] = str(value)
        
        return json.dumps(log, ensure_ascii=False, default=str)


# ============================================================
# Logger 管理
# ============================================================

class _LoggerManager:
    """日志管理器（单例）"""
    
    _initialized = False
    _loggers: dict[str, logging.Logger] = {}
    
    @classmethod
    def setup(cls) -> None:
        """初始化日志系统"""
        if cls._initialized:
            return
        
        # 创建日志目录（加保护，避免只读文件系统崩溃）
        try:
            Path(LOG_CONFIG["file"]).parent.mkdir(parents=True, exist_ok=True)
            Path(LOG_CONFIG["error_file"]).parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Fallback：写到临时目录
            import tempfile
            fallback_dir = Path(tempfile.gettempdir()) / "zenflux_logs"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            LOG_CONFIG["file"] = str(fallback_dir / "app.log")
            LOG_CONFIG["error_file"] = str(fallback_dir / "error.log")
        
        # 配置 root logger
        root = logging.getLogger("zenflux")
        root.setLevel(LOG_CONFIG["level"])
        root.handlers.clear()
        
        context_filter = _ContextFilter()
        
        # 控制台处理器
        if LOG_CONFIG["console_enabled"]:
            console = logging.StreamHandler(sys.stdout)
            console.setLevel(LOG_CONFIG["level"])
            console.setFormatter(_ConsoleFormatter())
            console.addFilter(context_filter)
            root.addHandler(console)
        
        # 主日志文件（JSON 格式）
        if LOG_CONFIG["file_enabled"]:
            from logging.handlers import RotatingFileHandler
            
            file_handler = RotatingFileHandler(
                LOG_CONFIG["file"],
                maxBytes=LOG_CONFIG["max_size"],
                backupCount=LOG_CONFIG["backup_count"],
                encoding="utf-8"
            )
            file_handler.setLevel(LOG_CONFIG["level"])
            file_handler.setFormatter(_JsonFormatter())
            file_handler.addFilter(context_filter)
            root.addHandler(file_handler)
            
            # 错误日志文件
            error_handler = RotatingFileHandler(
                LOG_CONFIG["error_file"],
                maxBytes=LOG_CONFIG["max_size"],
                backupCount=LOG_CONFIG["backup_count"],
                encoding="utf-8"
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(_JsonFormatter())
            error_handler.addFilter(context_filter)
            root.addHandler(error_handler)
        
        cls._initialized = True
    
    @classmethod
    def get(cls, name: Optional[str] = None) -> logging.Logger:
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称（不提供则自动获取调用模块名）
        """
        if not cls._initialized:
            cls.setup()
        
        if name is None:
            frame = inspect.currentframe()
            try:
                caller = frame.f_back.f_back  # 跳过 get_logger -> get
                module = caller.f_globals.get('__name__', 'unknown')
                name = module.split('.')[-1] if '.' in module else module
            finally:
                del frame
        
        full_name = f"zenflux.{name}" if name != 'zenflux' else "zenflux"
        if full_name not in cls._loggers:
            cls._loggers[full_name] = logging.getLogger(full_name)
        
        return cls._loggers[full_name]


# ============================================================
# 公开接口
# ============================================================

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称（不提供则自动获取调用模块名）
    
    Returns:
        日志记录器实例
    
    Usage:
        logger = get_logger()
        logger.info("处理开始")
        logger.error("发生错误", exc_info=True)
    """
    return _LoggerManager.get(name)


def set_level(level: str) -> None:
    """
    设置日志级别
    
    Args:
        level: 日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    """
    LOG_CONFIG["level"] = level.upper()
    logging.getLogger("zenflux").setLevel(level.upper())
