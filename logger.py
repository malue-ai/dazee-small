"""
日志管理模块
提供日志初始化和管理功能

使用指南:
=========

1. 基本使用 (推荐方式):
   ```python
   from logger import get_logger
   
   logger = get_logger()  # 自动获取当前模块名
   logger.info("处理开始")
   logger.error("发生错误", exc_info=True)
   ```

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

4. 结构化日志 (JSON格式):
   ```python
   logger.info("用户登录", extra={
       "user_id": "12345",
       "action": "login",
       "ip_address": "192.168.1.1"
   })
   ```

5. 性能监控:
   ```python
   import time
   start_time = time.time()
   # ... 业务逻辑
   logger.info("操作完成", extra={
       "duration": time.time() - start_time,
       "operation": "data_processing"
   })
   ```

最佳实践:
=========
- 使用 get_logger() 而不是直接使用 logging.getLogger()
- 避免使用 print() 语句，统一使用日志系统
- 在异常处理中使用 exc_info=True 记录完整异常信息
- 使用结构化日志字段便于后续分析和监控
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
    "json_format": False,  # 是否使用JSON格式
}


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

        cls._initialized = True
        logging.info("日志系统已初始化")
    
    @classmethod
    def get_logger_config(cls) -> Dict[str, Any]:
        """获取日志配置"""
        log_config = LOG_CONFIG
        
        # 构建 formatters 字典
        formatters = {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            }
        }
        if log_config["json_format"]:
            formatters["json"] = {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d",
                "class": "pythonjsonlogger.jsonlogger.JsonFormatter"
            }
        
        # 构建日志配置字典
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters,
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
                "formatter": "json" if log_config["json_format"] else "standard",
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
                "formatter": "json" if log_config["json_format"] else "standard",
                "filename": log_config["file"],
                "maxBytes": log_config["max_size"],
                "backupCount": log_config["backup_count"],
                "encoding": "utf8"
            }
            config["loggers"]["zenflux"]["handlers"].append("file")
            config["root"]["handlers"].append("file")
        
        return config
    
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