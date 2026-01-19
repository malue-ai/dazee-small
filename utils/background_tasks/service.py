"""
后台任务服务 - BackgroundTaskService

职责：
- 统一调度后台任务
- 提供共享资源（LLM、Mem0 Pool）

设计原则：
- 任务自动注册，无需手动维护 TASK_REGISTRY
- 任务实现在 tasks/ 目录下，使用 @background_task 装饰器
- Service 只负责调度和资源管理，不包含具体业务逻辑
"""

# 1. 标准库
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

# 2. 第三方库（无）

# 3. 本地模块
from logger import get_logger

from .context import TaskContext
from .registry import get_task_registry, get_registered_task_names

if TYPE_CHECKING:
    from core.llm import create_llm_service
    from core.llm.base import Message

logger = get_logger("background_tasks.service")


class BackgroundTaskService:
    """
    后台任务服务
    
    统一管理所有后台任务，提供可扩展的任务接口
    
    使用方式：
        # 统一调度
        await service.dispatch_tasks(
            task_names=["title_generation", "recommended_questions"],
            context=TaskContext(...)
        )
    
    新增任务只需：
    1. 在 tasks/ 目录下创建新文件
    2. 使用 @background_task("task_name") 装饰器
    """
    
    def __init__(self) -> None:
        """初始化后台任务服务"""
        # 使用 Haiku（快速、便宜，适合简单任务）
        self._llm = None  # 延迟初始化，避免启动时加载
        self._mem0_pool = None  # Mem0 Pool 延迟初始化
        
        # Prompt 模板（供 tasks 使用）
        self.title_generation_prompt = """请为以下对话内容生成一个简短的中文标题。

要求：
- 不超过15个字
- 不要加引号、书名号等标点符号
- 简洁明了，概括对话主题
- 只返回标题文本，不要任何其他内容

对话内容：
{message}

标题："""

        self.recommended_questions_prompt = """基于以下对话内容，生成3个用户可能想要继续问的相关问题。

要求：
- 生成3个问题
- 每个问题不超过25个字
- 问题要与对话主题相关且有价值
- 问题要能引导深入探讨
- 使用中文
- 返回 JSON 格式

对话内容：
用户：{user_message}
助手：{assistant_response}

请返回以下 JSON 格式：
```json
{{"questions": ["问题1", "问题2", "问题3"]}}
```"""
    
    # ==================== 共享资源管理 ====================
    
    def get_llm(self) -> Any:
        """
        获取 LLM 服务（懒加载）
        
        供 tasks 使用，避免重复创建 LLM 实例
        """
        if self._llm is None:
            from config.llm_config import get_llm_profile
            from core.llm import create_llm_service  # 延迟导入，避免循环依赖
            profile = get_llm_profile("background_task")
            self._llm = create_llm_service(**profile)
        return self._llm
    
    def get_mem0_pool(self) -> Optional[Any]:
        """
        获取 Mem0 Pool（懒加载）
        
        供 tasks 使用，避免重复创建 Pool 实例
        
        Returns:
            Mem0 Pool 实例，如果模块未安装则返回 None
        """
        if self._mem0_pool is None:
            try:
                from core.memory.mem0 import get_mem0_pool
                self._mem0_pool = get_mem0_pool()
            except ImportError:
                logger.warning("⚠️ mem0 模块未安装，Mem0 功能不可用")
                return None
        return self._mem0_pool
    
    # ==================== 统一调度入口 ====================
    
    async def dispatch_tasks(
        self,
        task_names: List[str],
        context: TaskContext
    ) -> Dict[str, bool]:
        """
        统一后台任务调度入口 ⭐
        
        任务自动注册，只需在 tasks/ 目录下创建文件并使用 @background_task 装饰器
        
        Args:
            task_names: 要执行的任务名列表，如 ["title_generation", "recommended_questions"]
            context: 任务上下文，包含所有任务可能需要的参数
            
        Returns:
            Dict[str, bool]: 各任务是否成功启动
        """
        results = {}
        registry = get_task_registry()
        
        for task_name in task_names:
            if task_name not in registry:
                logger.warning(f"⚠️ 未知的后台任务: {task_name}，已注册的任务: {get_registered_task_names()}")
                results[task_name] = False
                continue
            
            task_func = registry[task_name]
            
            try:
                # 启动后台任务（不等待完成）
                asyncio.create_task(task_func(context, self))
                results[task_name] = True
                logger.info(f"🚀 后台任务已启动: {task_name}")
            except Exception as e:
                logger.warning(f"⚠️ 启动后台任务失败: {task_name}, error={e}")
                results[task_name] = False
        
        return results
    
    # ==================== 工具方法 ====================
    
    @staticmethod
    def calc_duration_ms(start_time: datetime) -> int:
        """计算耗时（毫秒）"""
        return int((datetime.now() - start_time).total_seconds() * 1000)


# ==================== 便捷函数 ====================

_default_service: Optional[BackgroundTaskService] = None


def get_background_task_service() -> BackgroundTaskService:
    """获取默认后台任务服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = BackgroundTaskService()
    return _default_service
