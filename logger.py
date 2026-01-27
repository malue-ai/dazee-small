"""
日志管理模块
提供日志初始化和管理功能，支持多种输出格式和上下文追踪

使用指南:
=========

1. 基本使用 (推荐方式):
   ```python
   from logger import get_logger
   
   logger = get_logger()  # 自动获取当前模块名
   logger.info("处理开始")
   logger.error("发生错误", exc_info=True)
   ```

2. 带上下文追踪 (推荐):
   ```python
   from logger import get_logger, set_request_context
   
   logger = get_logger()
   
   # 设置请求上下文（在请求开始时）
   set_request_context(request_id="req-123", session_id="sess-456", user_id="user-789")
   
   logger.info("处理用户请求")
   # 输出: 2024-01-01 12:00:00 [INFO] [req-123] [sess-456] [user-789] module: 处理用户请求
   ```

3. 结构化日志 (添加额外字段):
   ```python
   logger.info("用户登录", extra={
       "action": "login",
       "ip_address": "192.168.1.1",
       "duration_ms": 123
   })
   ```

4. 性能监控:
   ```python
   from logger import log_execution_time
   
   with log_execution_time("数据库查询"):
       results = await db.query(...)
   ```

日志输出说明:
===========
- 控制台：易读的彩色格式，便于开发调试
- app.log：JSON 格式，便于日志分析和监控
- error.log：仅包含 ERROR/CRITICAL 级别，便于快速定位问题

日志级别使用建议:
===============
- DEBUG: 详细的调试信息，仅在开发环境使用
- INFO: 一般信息，记录程序的正常运行过程
- WARNING: 警告信息，程序仍能正常运行但需要注意
- ERROR: 错误信息，程序遇到错误但仍能继续运行
- CRITICAL: 严重错误，程序可能无法继续运行
"""
import logging
import logging.config
from pathlib import Path
from typing import Optional, Dict, Any
import sys
import os
import functools
import inspect
import json
import traceback
from datetime import datetime, timezone
from contextvars import ContextVar
from contextlib import contextmanager
import time


# ============================================================
# 上下文变量（用于追踪请求）
# ============================================================
request_id_var: ContextVar[str] = ContextVar('request_id', default='')
session_id_var: ContextVar[str] = ContextVar('session_id', default='')
user_id_var: ContextVar[str] = ContextVar('user_id', default='')


def set_request_context(
    request_id: str = '',
    session_id: str = '',
    user_id: str = ''
) -> None:
    """
    设置请求上下文信息
    
    Args:
        request_id: 请求ID
        session_id: 会话ID
        user_id: 用户ID
    """
    if request_id:
        request_id_var.set(request_id)
    if session_id:
        session_id_var.set(session_id)
    if user_id:
        user_id_var.set(user_id)


def clear_request_context() -> None:
    """清除请求上下文"""
    request_id_var.set('')
    session_id_var.set('')
    user_id_var.set('')


@contextmanager
def log_execution_time(operation_name: str, logger: Optional[logging.Logger] = None):
    """
    记录操作执行时间的上下文管理器
    
    Args:
        operation_name: 操作名称
        logger: 日志记录器（可选，不提供则自动获取）
    
    Usage:
        with log_execution_time("数据库查询"):
            results = await db.query(...)
    """
    if logger is None:
        logger = logging.getLogger("zenflux")
    
    start_time = time.time()
    logger.info(f"开始 {operation_name}")
    
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        logger.info(
            f"{operation_name} 完成",
            extra={"duration_ms": elapsed * 1000, "operation": operation_name}
        )


# ============================================================
# 日志配置（直接在代码中定义）
# ============================================================
LOG_CONFIG = {
    "level": "INFO",  # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
    "console_enabled": True,  # 是否输出到控制台
    "console_format": "human",  # 控制台格式: human（易读）或 json
    "file_enabled": True,  # 是否输出到文件
    "file": "logs/app.log",  # 主日志文件路径
    "error_file": "logs/error.log",  # 错误日志文件路径
    "max_size": 50 * 1024 * 1024,  # 单个日志文件最大大小 (50MB)
    "backup_count": 10,  # 保留的日志文件数量
}


class ContextFilter(logging.Filter):
    """添加上下文信息到日志记录"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """为日志记录添加上下文字段"""
        record.request_id = request_id_var.get() or '-'
        record.session_id = session_id_var.get() or '-'
        record.user_id = user_id_var.get() or '-'
        return True


class HumanReadableFormatter(logging.Formatter):
    """
    人类易读的日志格式化器（带颜色）
    
    输出格式:
    2024-01-01 12:00:00 [INFO] [req-123] [sess-456] [user-789] module.py:42 function_name: 消息内容
    """
    
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',     # 青色
        'INFO': '\033[32m',      # 绿色
        'WARNING': '\033[33m',   # 黄色
        'ERROR': '\033[31m',     # 红色
        'CRITICAL': '\033[35m',  # 紫色
        'RESET': '\033[0m'       # 重置
    }
    
    def __init__(self, use_colors: bool = True):
        """
        Args:
            use_colors: 是否使用颜色（在终端中显示）
        """
        super().__init__(
            fmt=(
                '%(asctime)s [%(levelname)s] '
                '[%(request_id)s] [%(session_id)s] [%(user_id)s] '
                '%(filename)s:%(lineno)d %(funcName)s: %(message)s'
            ),
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 添加颜色
        if self.use_colors:
            levelname = record.levelname
            color = self.COLORS.get(levelname, '')
            reset = self.COLORS['RESET']
            record.levelname = f"{color}{levelname}{reset}"
        
        # 格式化消息
        formatted = super().format(record)
        
        # 如果有异常信息，添加到末尾
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        
        return formatted


class JsonFormatter(logging.Formatter):
    """
    自定义 JSON 日志格式化器
    
    输出格式示例:
    {
        "timestamp": "2024-01-01T12:00:00.123456+00:00",
        "level": "INFO",
        "logger": "zenflux.module",
        "message": "处理完成",
        "filename": "module.py",
        "lineno": 42,
        "funcName": "process_data",
        "pathname": "/app/module.py",
        "extra_field": "value"  # 来自 extra 参数
    }
    """
    
    # 需要排除的内置 LogRecord 属性（不输出到 JSON）
    RESERVED_ATTRS = {
        'name', 'msg', 'args', 'created', 'levelname', 'levelno',
        'pathname', 'filename', 'module', 'exc_info', 'exc_text',
        'stack_info', 'lineno', 'funcName', 'msecs', 'relativeCreated',
        'thread', 'threadName', 'processName', 'process', 'message',
        'taskName'
    }
    
    def __init__(
        self,
        include_pathname: bool = False,
        include_thread: bool = False,
        include_process: bool = False,
    ):
        """
        初始化 JSON 格式化器
        
        Args:
            include_pathname: 是否包含完整文件路径（默认只显示文件名）
            include_thread: 是否包含线程信息
            include_process: 是否包含进程信息
        """
        super().__init__()
        self.include_pathname = include_pathname
        self.include_thread = include_thread
        self.include_process = include_process
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为 JSON 字符串"""
        # 构建基础日志结构
        log_data = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec='milliseconds'),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "filename": record.filename,
            "lineno": record.lineno,
            "funcName": record.funcName or "<module>",
            # 添加上下文信息
            "request_id": getattr(record, 'request_id', '-'),
            "session_id": getattr(record, 'session_id', '-'),
            "user_id": getattr(record, 'user_id', '-'),
        }
        
        # 可选：添加完整路径
        if self.include_pathname:
            log_data["pathname"] = record.pathname
        
        # 可选：添加线程信息
        if self.include_thread:
            log_data["thread"] = record.thread
            log_data["threadName"] = record.threadName
        
        # 可选：添加进程信息
        if self.include_process:
            log_data["process"] = record.process
            log_data["processName"] = record.processName
        
        # 处理异常信息
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self._format_traceback(record.exc_info),
            }
        
        # 添加 stack_info（如果有）
        if record.stack_info:
            log_data["stack_info"] = record.stack_info
        
        # 添加 extra 字段（用户自定义字段）
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS:
                # 尝试序列化，如果失败则转为字符串
                try:
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)
        
        # 序列化为 JSON（确保中文正常显示）
        return json.dumps(log_data, ensure_ascii=False, default=str)
    
    def _format_traceback(self, exc_info) -> str | None:
        """格式化异常堆栈"""
        if exc_info and exc_info[0] is not None:
            return ''.join(traceback.format_exception(*exc_info)).strip()
        return None


class Logger:
    """日志管理类"""
    
    _initialized = False
    _loggers: Dict[str, logging.Logger] = {}
    
    @classmethod
    def setup(cls) -> None:
        """初始化日志系统"""
        if cls._initialized:
            return

        # 获取并应用日志配置字典
        config_dict = cls.get_logger_config()
        logging.config.dictConfig(config_dict)
        
        # 应用 JSON 格式化器（如果启用）
        cls._apply_json_formatter()

        cls._initialized = True
        logging.info("日志系统已初始化")
    
    # JSON 格式化器实例（复用以提高性能）
    _json_formatter: JsonFormatter | None = None
    _standard_formatter: logging.Formatter | None = None
    
    @classmethod
    def _get_formatter(cls, use_json: bool) -> logging.Formatter:
        """获取格式化器（带缓存）"""
        if use_json:
            if cls._json_formatter is None:
                cls._json_formatter = JsonFormatter(
                    include_pathname=False,  # 默认不包含完整路径
                    include_thread=False,
                    include_process=False,
                )
            return cls._json_formatter
        else:
            if cls._standard_formatter is None:
                cls._standard_formatter = logging.Formatter(
                    fmt="%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d] %(funcName)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
            return cls._standard_formatter
    
    @classmethod
    def get_logger_config(cls) -> Dict[str, Any]:
        """获取日志配置"""
        log_config = LOG_CONFIG
        
        # 构建日志配置字典
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "context_filter": {
                    "()": ContextFilter
                }
            },
            "formatters": {
                "standard": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S"
                }
            },
            "handlers": {},
            "loggers": {
                "zenflux": {
                    "level": log_config["level"],
                    "handlers": [],
                    "propagate": False
                }
            },
            "root": {
                "level": "INFO",
                "handlers": []
            }
        }
        
        # 添加控制台处理器
        if log_config["console_enabled"]:
            config["handlers"]["console"] = {
                "class": "logging.StreamHandler",
                "level": log_config["level"],
                "formatter": "standard",
                "filters": ["context_filter"],
                "stream": "ext://sys.stdout"
            }
            config["loggers"]["zenflux"]["handlers"].append("console")
            config["root"]["handlers"].append("console")
        
        # 添加主日志文件处理器
        if log_config["file_enabled"]:
            # 确保日志目录存在
            log_file_path = Path(log_config["file"])
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            config["handlers"]["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_config["level"],
                "formatter": "standard",
                "filters": ["context_filter"],
                "filename": log_config["file"],
                "maxBytes": log_config["max_size"],
                "backupCount": log_config["backup_count"],
                "encoding": "utf8"
            }
            config["loggers"]["zenflux"]["handlers"].append("file")
            config["root"]["handlers"].append("file")
            
            # 添加错误日志文件处理器（仅记录 ERROR 和 CRITICAL）
            error_file_path = Path(log_config["error_file"])
            error_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            config["handlers"]["error_file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",  # 只记录错误级别
                "formatter": "standard",
                "filters": ["context_filter"],
                "filename": log_config["error_file"],
                "maxBytes": log_config["max_size"],
                "backupCount": log_config["backup_count"],
                "encoding": "utf8"
            }
            config["loggers"]["zenflux"]["handlers"].append("error_file")
            config["root"]["handlers"].append("error_file")
        
        return config
    
    @classmethod
    def _apply_json_formatter(cls) -> None:
        """根据配置应用合适的格式化器"""
        # 为控制台和文件应用不同的格式化器
        console_format = LOG_CONFIG.get("console_format", "human")
        
        # 获取 zenflux logger 的所有 handlers
        zenflux_logger = logging.getLogger("zenflux")
        for handler in zenflux_logger.handlers:
            handler_name = handler.__class__.__name__
            
            if handler_name == "StreamHandler":
                # 控制台使用易读格式或JSON
                use_json = (console_format == "json")
                if use_json:
                    handler.setFormatter(cls._get_formatter(use_json=True))
                else:
                    handler.setFormatter(HumanReadableFormatter(use_colors=True))
            else:
                # 文件使用 JSON 格式
                handler.setFormatter(cls._get_formatter(use_json=True))
        
        # 获取 root logger 的所有 handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler_name = handler.__class__.__name__
            
            if handler_name == "StreamHandler":
                use_json = (console_format == "json")
                if use_json:
                    handler.setFormatter(cls._get_formatter(use_json=True))
                else:
                    handler.setFormatter(HumanReadableFormatter(use_colors=True))
            else:
                handler.setFormatter(cls._get_formatter(use_json=True))
    
    @classmethod
    def get_logger(cls, name: Optional[str] = None) -> logging.Logger:
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称，如果不提供则自动获取调用模块名称
            
        Returns:
            日志记录器实例
        """
        if not cls._initialized:
            cls.setup()
        
        # 如果没有提供name，自动获取调用者的模块名
        if name is None:
            frame = inspect.currentframe()
            try:
                # 获取调用者的frame
                caller_frame = frame.f_back
                if caller_frame:
                    caller_module = caller_frame.f_globals.get('__name__', 'unknown')
                    # 移除模块前缀以简化名称
                    if '.' in caller_module:
                        name = caller_module.split('.')[-1]
                    else:
                        name = caller_module
                else:
                    name = 'root'
            finally:
                del frame
        
        # 缓存日志记录器以提高性能
        full_name = f"zenflux.{name}" if name != 'root' else "zenflux"
        if full_name not in cls._loggers:
            cls._loggers[full_name] = logging.getLogger(full_name)
            
        return cls._loggers[full_name]
    
    @classmethod
    def set_level(cls, level: str, logger_name: Optional[str] = None) -> None:
        """
        设置日志级别
        
        Args:
            level: 日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
            logger_name: 要设置的日志记录器名称，如果为None则设置所有记录器
        """
        if not cls._initialized:
            cls.setup()
        
        level_upper = level.upper()
        
        # 更新全局配置
        LOG_CONFIG["level"] = level_upper
        
        # 设置指定日志记录器的级别
        if logger_name:
            full_name = f"zenflux.{logger_name}" if logger_name != "root" else None
            logging.getLogger(full_name).setLevel(level_upper)
        else:
            # 设置所有日志记录器的级别
            logging.getLogger("zenflux").setLevel(level_upper)
            for logger in cls._loggers.values():
                logger.setLevel(level_upper)
    
    @classmethod
    def reload_config(cls) -> None:
        """重新加载日志配置"""
        config_dict = cls.get_logger_config()
        logging.config.dictConfig(config_dict)
        cls._apply_json_formatter()
    
    @classmethod
    def set_console_format(cls, format_type: str = "human") -> None:
        """
        设置控制台日志格式
        
        Args:
            format_type: 格式类型，"human"（易读）或 "json"
        """
        if format_type not in ("human", "json"):
            raise ValueError("format_type 必须是 'human' 或 'json'")
        
        LOG_CONFIG["console_format"] = format_type
        
        # 重新应用格式化器
        cls._apply_json_formatter()
    
    @classmethod
    def enable_console_logging(cls, enable: bool = True) -> None:
        """
        启用或禁用控制台日志
        
        Args:
            enable: 是否启用控制台日志
        """
        LOG_CONFIG["console_enabled"] = enable
        # 优化：只重新加载配置，不重置初始化状态
        cls.reload_config()
    
    @classmethod
    def enable_file_logging(cls, enable: bool = True, file_path: Optional[str] = None) -> None:
        """
        启用或禁用文件日志
        
        Args:
            enable: 是否启用文件日志
            file_path: 日志文件路径（可选）
        """
        LOG_CONFIG["file_enabled"] = enable
        if file_path:
            LOG_CONFIG["file"] = file_path
        # 优化：只重新加载配置，不重置初始化状态
        cls.reload_config()


# 装饰器：自动注入logger
def with_logger(func):
    """
    装饰器：为函数自动注入logger参数
    
    Usage:
        @with_logger
        def my_function(arg1, arg2, logger=None):
            logger.info("Function called")
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if 'logger' not in kwargs or kwargs['logger'] is None:
            # 获取被装饰函数所在模块的logger
            module_name = func.__module__
            if '.' in module_name:
                logger_name = module_name.split('.')[-1]
            else:
                logger_name = module_name
            kwargs['logger'] = Logger.get_logger(logger_name)
        return func(*args, **kwargs)
    return wrapper


# 获取日志记录器的快捷函数
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称，如果不提供则自动获取调用模块名称
        
    Returns:
        日志记录器实例
    """
    return Logger.get_logger(name) 