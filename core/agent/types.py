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
    
    🆕 V4.3: 新增 needs_persistence 字段，用于判断是否需要跨 Session 持久化
    🆕 V4.6: 新增 skip_memory_retrieval 字段，用于智能决定是否需要 Mem0 记忆检索
    🆕 V6.0: 新增 needs_multi_agent 字段，用于智能决定是否需要 Multi-Agent 协作（Prompt-First）
    🆕 V6.1: 新增 is_follow_up 字段，用于识别追问/上下文延续（避免误判为新话题）
    🆕 V7.0: 新增 complexity_score 字段，LLM 直接输出 0-10 评分（废弃 ComplexityScorer）
    🆕 V7.8: 新增 LLM 语义建议字段，供 AgentFactory 参数映射时使用
    """
    task_type: TaskType                          # 任务类型
    complexity: Complexity                       # 复杂度等级
    needs_plan: bool                             # 是否需要规划
    complexity_score: float = 5.0                # 🆕 V7.0: 复杂度评分 0-10，由 LLM 直接输出
    needs_persistence: bool = False              # 🆕 V4.3: 是否需要跨 Session 持久化
    skip_memory_retrieval: bool = False          # 🆕 V4.6: 是否跳过 Mem0 记忆检索（默认不跳过）
    needs_multi_agent: bool = False              # 🆕 V6.0: 是否需要 Multi-Agent 协作（默认不需要）
    is_follow_up: bool = False                   # 🆕 V6.1: 是否为追问/上下文延续（默认否，视为新话题）
    keywords: List[str] = field(default_factory=list)  # 提取的关键词
    confidence: float = 1.0                      # 置信度
    raw_response: Optional[str] = None           # LLM 原始响应（用于调试）
    
    # ==================== V7.8 LLM 语义建议 ====================
    # 这些字段由 IntentAnalyzer 输出，供 AgentFactory 参数映射时优先使用
    # 相比硬规则，LLM 能更好地理解"虽然问题简短但需要深度分析"等边界情况
    
    suggested_planning_depth: Optional[str] = None  # 🆕 V7.8: none / minimal / full
    requires_deep_reasoning: bool = False        # 🆕 V7.8: 是否需要深度推理（即使问题简短）
    tool_usage_hint: Optional[str] = None        # 🆕 V7.8: single / sequential / parallel
    
    # ==================== V8.0 执行策略 ====================
    # 由 LLM 语义判断，决定使用 SimpleAgent 还是 RVRBAgent
    execution_strategy: str = "rvr"  # 🆕 V8.0: "rvr" | "rvr-b"
    # - rvr: 标准 RVR 循环（简单确定性任务）
    # - rvr-b: RVR + Backtrack（探索性任务、可能失败需重试、多步骤任务）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_type": self.task_type.value,
            "complexity": self.complexity.value,
            "complexity_score": self.complexity_score,
            "needs_plan": self.needs_plan,
            "needs_persistence": self.needs_persistence,
            "skip_memory_retrieval": self.skip_memory_retrieval,
            "needs_multi_agent": self.needs_multi_agent,
            "is_follow_up": self.is_follow_up,
            "keywords": self.keywords,
            "confidence": self.confidence,
            # V7.8 LLM 语义建议
            "suggested_planning_depth": self.suggested_planning_depth,
            "requires_deep_reasoning": self.requires_deep_reasoning,
            "tool_usage_hint": self.tool_usage_hint,
            # V8.0 执行策略
            "execution_strategy": self.execution_strategy,
        }

