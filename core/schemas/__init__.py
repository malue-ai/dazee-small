"""
Schema 模块 - 定义框架与 Prompt 之间的契约

核心组件：
- AgentSchema: Agent 配置的完整定义
- 各组件配置类: IntentAnalyzerConfig, PlanManagerConfig 等
- 验证器: 确保 LLM 生成的配置符合规范
"""

from core.schemas.validator import (
    # 基础配置
    ComponentConfig,
    
    # 组件配置
    IntentAnalyzerConfig,
    PlanManagerConfig,
    ToolSelectorConfig,
    MemoryManagerConfig,
    OutputFormatterConfig,
    
    # 其他配置
    SkillConfig,
    ContextLimitsConfig,
    
    # 核心 Schema
    AgentSchema,
    
    # 默认值
    DEFAULT_AGENT_SCHEMA,
)

__all__ = [
    # 基础
    "ComponentConfig",
    
    # 组件配置
    "IntentAnalyzerConfig",
    "PlanManagerConfig", 
    "ToolSelectorConfig",
    "MemoryManagerConfig",
    "OutputFormatterConfig",
    
    # 其他
    "SkillConfig",
    "ContextLimitsConfig",
    
    # 核心
    "AgentSchema",
    "DEFAULT_AGENT_SCHEMA",
]

