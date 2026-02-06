"""
提示词分层模块

🆕 V4.6.1: LLM 驱动的语义分析

核心功能：
1. 用 LLM 语义理解分析提示词（不依赖特定格式）
2. 根据任务复杂度智能裁剪
3. 生成 Simple/Medium/Complex 三个版本
4. 框架组件已处理的模块自动排除

使用示例：
```python
from core.prompt import (
    parse_prompt,
    generate_prompt,
    detect_complexity,
    TaskComplexity
)

# 1. 解析运营写的完整提示词（🆕 使用 LLM 语义分析）
#    支持任意格式：Markdown、XML、纯文本、混合...
schema = parse_prompt(raw_prompt, use_llm=True)

# 2. 检测用户查询的复杂度
complexity = detect_complexity(user_query, schema)

# 3. 生成对应版本的提示词（智能排除框架已处理模块）
prompt = generate_prompt(schema, complexity, agent_schema=agent_schema)
```
"""

from .complexity_detector import (
    ComplexityDetector,
    detect_complexity,
    detect_complexity_async,
    detect_complexity_with_confidence,
)

# 🆕 V4.6.2: 实例级提示词缓存
from .instance_cache import (
    CacheMetrics,
    InstancePromptCache,
    get_instance_cache,
    load_instance_cache,
)

# 🆕 V4.6.2: 动态意图识别提示词生成器
from .intent_prompt_generator import (
    IntentPromptGenerator,
    generate_intent_prompt,
    get_default_intent_prompt,
)

# 🆕 V4.6.1: LLM 驱动的提示词分析器
from .llm_analyzer import (
    LLMAnalysisResult,
    LLMPromptAnalyzer,
    analyze_prompt_with_llm,
)
from .prompt_layer import (
    PromptGenerator,
    PromptModule,
    PromptParser,
    PromptSchema,
    TaskComplexity,
    generate_prompt,
    get_prompt_for_complexity,
    parse_prompt,
)

# 🆕 V5.5: 提示词结果输出管理器（面向运营）
from .prompt_results_writer import (
    PromptResults,
    PromptResultsMetadata,
    PromptResultsWriter,
    create_prompt_results_writer,
)

# 🆕 V6.0: 运行时上下文构建器（自动检测环境，异步）
from .runtime_context_builder import (
    RuntimeContextBuilder,
    RuntimeEnvironment,
    detect_and_build_environment_context_async,
    get_environment_async,
)

# 🆕 V6.2: Skill Prompt 构建器（延迟加载机制）
from .skill_prompt_builder import (
    SkillPromptBuilder,
    SkillSummary,
    build_skills_instructions,
    build_skills_prompt,
)

__all__ = [
    # 核心类型
    "TaskComplexity",
    "PromptModule",
    "PromptSchema",
    # 解析器和生成器
    "PromptParser",
    "PromptGenerator",
    # 复杂度检测
    "ComplexityDetector",
    # 🆕 LLM 分析器
    "LLMPromptAnalyzer",
    "LLMAnalysisResult",
    "analyze_prompt_with_llm",
    # 🆕 V4.6.2: 实例级缓存
    "InstancePromptCache",
    "CacheMetrics",
    "get_instance_cache",
    "load_instance_cache",
    # 🆕 V4.6.2: 意图识别提示词生成器
    "IntentPromptGenerator",
    "generate_intent_prompt",
    "get_default_intent_prompt",
    # 🆕 V5.5: 提示词结果输出管理器
    "PromptResultsWriter",
    "PromptResultsMetadata",
    "PromptResults",
    "create_prompt_results_writer",
    # 🆕 V6.0: 运行时上下文构建器（异步）
    "RuntimeEnvironment",
    "RuntimeContextBuilder",
    "get_environment_async",
    "detect_and_build_environment_context_async",
    # 🆕 V6.2: Skill Prompt 构建器
    "SkillPromptBuilder",
    "SkillSummary",
    "build_skills_prompt",
    "build_skills_instructions",
    # 便捷函数
    "parse_prompt",
    "generate_prompt",
    "get_prompt_for_complexity",
    "detect_complexity",
    "detect_complexity_with_confidence",
    "detect_complexity_async",
]
