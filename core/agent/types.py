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


@dataclass
class IntentResult:
    """
    意图分析结果
    
    包含任务类型、复杂度、是否需要规划等信息
    
    注意：Prompt 选择由 AgentFactory 在创建 Agent 时确定，
    不再通过 IntentAnalyzer 动态切换。
    """
    task_type: TaskType                          # 任务类型
    complexity: Complexity                       # 复杂度
    needs_plan: bool                             # 是否需要规划
    keywords: List[str] = field(default_factory=list)  # 提取的关键词
    confidence: float = 1.0                      # 置信度
    raw_response: Optional[str] = None           # LLM 原始响应（用于调试）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_type": self.task_type.value,
            "complexity": self.complexity.value,
            "needs_plan": self.needs_plan,
            "keywords": self.keywords,
            "confidence": self.confidence
        }

