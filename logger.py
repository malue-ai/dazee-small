"""
日志管理模块
提供日志初始化和管理功能，默认输出 JSON 格式日志

使用指南:
=========

1. 基本使用 (推荐方式):
   ```python
   from logger import get_logger
   
   logger = get_logger()  # 自动获取当前模块名
   logger.info("处理开始")
   logger.error("发生错误", exc_info=True)
   ```
   
   输出示例:
   {"timestamp": "2024-01-01T12:00:00.123", "level": "INFO", "logger": "zenflux.module", 
    "message": "处理开始", "filename": "module.py", "lineno": 42, "funcName": "process"}

2. 指定模块名:
   ```python
   from logger import get_logger
   
   logger = get_logger("audio")  # 明确指定模块名
   logger.debug("音频处理中...")
   ```

3. 使用装饰器 (函数级别):
   ```python
   from logger import with_logger
   
   @with_logger
   def process_data(data, logger=None):
       logger.info(f"处理数据: {len(data)} 条记录")
       # ... 处理逻辑
   ```

4. 结构化日志 (添加额外字段):
   ```python
   logger.info("用户登录", extra={
       "user_id": "12345",
       "action": "login",
       "ip_address": "192.168.1.1"
   })
   ```
   
   输出示例:
   {"timestamp": "...", "level": "INFO", "message": "用户登录", 
    "user_id": "12345", "action": "login", "ip_address": "192.168.1.1", ...}

5. 性能监控:
   ```python
   import time
   start_time = time.time()
   # ... 业务逻辑
   logger.info("操作完成", extra={
       "duration_ms": (time.time() - start_time) * 1000,
       "operation": "data_processing"
   })
   ```

最佳实践:
=========
- 使用 get_logger() 而不是直接使用 logging.getLogger()
- 避免使用 print() 语句，统一使用日志系统
- 在异常处理中使用 exc_info=True 记录完整异常信息
- 使用 extra={} 添加结构化字段，便于日志分析和监控
- 根据环境调整日志级别 (开发: DEBUG, 生产: INFO/WARNING)

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


# ============================================================
# 日志配置（直接在代码中定义）
# ============================================================
LOG_CONFIG = {
    "level": "INFO",  # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
    "console_enabled": True,  # 是否输出到控制台
    "file_enabled": True,  # 是否输出到文件
    "file": "logs/app.log",  # 日志文件路径
    "max_size": 10 * 1024 * 1024,  # 单个日志文件最大大小 (10MB)
    "backup_count": 5,  # 保留的日志文件数量
    "json_format": True,  # 默认使用 JSON 格式
}


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
        
        # 构建日志配置字典（不使用 dictConfig 的 formatters，手动设置）
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d] %(funcName)s: %(message)s",
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
                "formatter": "standard",  # 先用 standard，后面手动替换
                "stream": "ext://sys.stdout"
            }
            config["loggers"]["zenflux"]["handlers"].append("console")
            config["root"]["handlers"].append("console")
        
        # 添加文件处理器
        if log_config["file_enabled"]:
            # 确保日志目录存在
            log_file_path = Path(log_config["file"])
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            config["handlers"]["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_config["level"],
                "formatter": "standard",  # 先用 standard，后面手动替换
                "filename": log_config["file"],
                "maxBytes": log_config["max_size"],
                "backupCount": log_config["backup_count"],
                "encoding": "utf8"
            }
            config["loggers"]["zenflux"]["handlers"].append("file")
            config["root"]["handlers"].append("file")
        
        return config
    
    @classmethod
    def _apply_json_formatter(cls) -> None:
        """应用 JSON 格式化器到所有 handlers"""
        if not LOG_CONFIG["json_format"]:
            return
        
        formatter = cls._get_formatter(use_json=True)
        
        # 获取 zenflux logger 的所有 handlers
        zenflux_logger = logging.getLogger("zenflux")
        for handler in zenflux_logger.handlers:
            handler.setFormatter(formatter)
        
        # 获取 root logger 的所有 handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
    
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
    
    @staticmethod
    def get_all_loggers() -> Dict[str, logging.Logger]:
        """
        获取所有已创建的日志记录器
        
        Returns:
            日志记录器字典 {名称: 记录器实例}
        """
        return {name: logging.getLogger(name) for name in logging.root.manager.loggerDict}
    
    @classmethod
    def reload_config(cls) -> None:
        """
        重新加载日志配置（性能优化版本）
        """
        config_dict = cls.get_logger_config()
        logging.config.dictConfig(config_dict)
        # 重新应用 JSON 格式化器
        cls._apply_json_formatter()
    
    @classmethod
    def enable_json_format(cls, enable: bool = True) -> None:
        """
        启用或禁用 JSON 格式日志
        
        Args:
            enable: 是否启用 JSON 格式
        """
        LOG_CONFIG["json_format"] = enable
        
        # 获取适当的格式化器
        formatter = cls._get_formatter(use_json=enable)
        
        # 更新所有 handlers 的格式化器
        for logger_name in ["zenflux", ""]:  # zenflux 和 root logger
            logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
            for handler in logger.handlers:
                handler.setFormatter(formatter)
    
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