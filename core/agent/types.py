"""
Agent 类型定义

统一的数据结构定义，用于模块间通信
"""

# 1. 标准库
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional

# 2. 第三方库（无）

# 3. 本地模块（无）


class TaskType(Enum):
    """任务类型"""
    INFORMATION_QUERY = "information_query"      # 信息查询
    CONTENT_GENERATION = "content_generation"    # 内容生成
    CODE_DEVELOPMENT = "code_development"        # 代码开发
    DATA_ANALYSIS = "data_analysis"              # 数据分析
    CONVERSATION = "conversation"                # 日常对话
    TASK_EXECUTION = "task_execution"            # 任务执行
    OTHER = "other"                              # 其他


class Complexity(Enum):
    """任务复杂度"""
    SIMPLE = "simple"      # 简单：单步骤，无需规划
    MEDIUM = "medium"      # 中等：需要少量工具调用
    COMPLEX = "complex"    # 复杂：需要规划和多步骤执行


class PromptLevel(Enum):
    """提示词级别"""
    SIMPLE = "simple"      # 简洁版：日常对话
    STANDARD = "standard"  # 标准版：一般任务
    FULL = "full"          # 完整版：复杂任务


@dataclass
class IntentResult:
    """
    意图分析结果
    
    包含任务类型、复杂度、是否需要规划等信息
    """
    task_type: TaskType                          # 任务类型
    complexity: Complexity                       # 复杂度
    needs_plan: bool                             # 是否需要规划
    prompt_level: PromptLevel                    # 推荐的提示词级别
    keywords: List[str] = field(default_factory=list)  # 提取的关键词
    confidence: float = 1.0                      # 置信度
    raw_response: Optional[str] = None           # LLM 原始响应（用于调试）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_type": self.task_type.value,
            "complexity": self.complexity.value,
            "needs_plan": self.needs_plan,
            "prompt_level": self.prompt_level.value,
            "keywords": self.keywords,
            "confidence": self.confidence
        }


@dataclass
class ExecutionConfig:
    """
    执行配置
    
    根据意图分析结果生成的执行配置
    """
    system_prompt: str                           # 系统提示词
    prompt_name: str                             # 提示词名称
    enable_thinking: bool = True                 # 是否启用 Extended Thinking
    enable_streaming: bool = True                # 是否启用流式输出
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "prompt_name": self.prompt_name,
            "enable_thinking": self.enable_thinking,
            "enable_streaming": self.enable_streaming
        }

