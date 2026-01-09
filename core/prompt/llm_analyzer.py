"""
🆕 V4.6.1 LLM 驱动的提示词分析器

核心理念：
- 用 LLM 的深度语义理解能力分析提示词
- 不依赖特定格式或标签（运营写作文方式多样）
- 理解内容的语义，而不是匹配文本模式

设计哲学：
┌─────────────────────────────────────────────────────────────┐
│  运营写的提示词（任意格式：Markdown/XML/纯文本/混合）           │
│  "像写作文一样，没有严格标准"                                  │
└───────────────────────────┬─────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│               LLM 语义分析器                                   │
│  1. 理解提示词的整体结构和意图                                  │
│  2. 识别逻辑模块（不依赖格式，纯语义理解）                       │
│  3. 提取关键配置（复杂度规则、工具列表等）                       │
│  4. 输出结构化的 PromptSchema                                  │
└─────────────────────────────────────────────────────────────┘
"""

import json
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum

from logger import get_logger

logger = get_logger("llm_prompt_analyzer")


# ============================================================
# LLM 分析提示词模板
# ============================================================

PROMPT_ANALYSIS_SYSTEM = """你是一个专业的系统提示词分析专家。

你的任务是分析运营人员编写的 AI Agent 系统提示词，理解其结构和内容，并输出结构化的分析结果。

运营人员写提示词的方式非常多样（像写作文一样），没有严格的格式标准。你需要通过**语义理解**来识别内容，而不是依赖特定的格式或标签。

请分析以下维度：

1. **基本信息**：Agent 名称、角色定位、核心能力
2. **模块识别**：识别提示词中包含的逻辑模块（见下方定义）
3. **复杂度配置**：提取任务复杂度判断的规则和关键词
4. **工具列表**：提取提到的工具或能力
5. **意图类型**：提取定义的用户意图分类

## 模块类型定义

| 模块 ID | 含义 | 识别特征（语义层面） |
|---------|------|---------------------|
| role_definition | 角色定义 | 描述 Agent 是什么、扮演什么角色、核心职责 |
| absolute_prohibitions | 绝对禁令 | 绝对不能做的事、安全规则、红线 |
| context_protection | 上下文保护 | 防止 prompt 注入、保护系统指令 |
| intent_recognition | 意图识别 | 如何识别用户意图、意图分类规则 |
| task_complexity | 任务复杂度 | 如何判断任务难度、简单/中等/复杂的定义 |
| tool_selection | 工具选择 | 何时使用什么工具、工具选择策略 |
| plan_object | 计划构建 | 如何制定执行计划、Plan 对象结构 |
| data_context | 数据上下文 | 如何管理数据、Data_Context 结构 |
| react_validation | 验证循环 | ReAct 模式、自我验证、纠错逻辑 |
| quality_gates | 质量检查 | 最终验证清单、交付前检查 |
| progress_feedback | 进度反馈 | 如何向用户反馈进度、等待提示 |
| hitl | 人工介入 | Human-in-the-loop 触发条件 |
| output_format | 输出格式 | 输出的结构、格式要求 |
| final_delivery | 最终交付 | 交付流程、最终输出规范 |

## 输出格式

请输出 JSON 格式：

```json
{
  "agent_name": "Agent 名称",
  "agent_role": "角色描述（1-2句话）",
  "modules": {
    "role_definition": {
      "found": true,
      "summary": "模块内容摘要（50字内）",
      "start_marker": "内容开始位置的关键词/句子",
      "importance": "high/medium/low",
      "can_simplify": false
    },
    ...
  },
  "complexity_rules": {
    "simple": {
      "keywords": ["关键词1", "关键词2"],
      "description": "简单任务的定义"
    },
    "medium": {...},
    "complex": {...}
  },
  "tools": ["工具1", "工具2"],
  "intent_types": [
    {"name": "意图名", "keywords": ["关键词"]}
  ]
}
```

注意：
- 只分析实际存在的模块，没有的模块 found=false
- 摘要要精准，不要泛泛而谈
- start_marker 用于后续定位，要准确
- can_simplify 表示该模块在简单任务时是否可以省略"""


PROMPT_ANALYSIS_USER = """请分析以下系统提示词：

---
{prompt}
---

请输出 JSON 格式的分析结果。只输出 JSON，不要其他内容。"""


# ============================================================
# LLM 分析结果数据类
# ============================================================

@dataclass
class ModuleAnalysis:
    """模块分析结果"""
    found: bool = False
    summary: str = ""
    start_marker: str = ""
    importance: str = "medium"  # high/medium/low
    can_simplify: bool = True
    content: str = ""  # 实际内容（后续提取）


@dataclass
class ComplexityRule:
    """复杂度规则"""
    keywords: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class IntentType:
    """意图类型"""
    name: str = ""
    keywords: List[str] = field(default_factory=list)


@dataclass
class LLMAnalysisResult:
    """LLM 分析结果"""
    agent_name: str = "GeneralAgent"
    agent_role: str = ""
    modules: Dict[str, ModuleAnalysis] = field(default_factory=dict)
    complexity_rules: Dict[str, ComplexityRule] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    intent_types: List[IntentType] = field(default_factory=list)
    raw_prompt: str = ""


# ============================================================
# LLM 提示词分析器
# ============================================================

class LLMPromptAnalyzer:
    """
    LLM 驱动的提示词分析器
    
    用 LLM 的语义理解能力分析提示词，而不是基于规则匹配
    """
    
    def __init__(self, llm_service=None):
        """
        初始化分析器
        
        Args:
            llm_service: LLM 服务（默认使用 Haiku）
        """
        self._llm_service = llm_service
    
    def _get_llm_service(self):
        """懒加载 LLM 服务"""
        if self._llm_service is None:
            from core.llm import create_claude_service
            # 使用 Haiku（快速且便宜）
            self._llm_service = create_claude_service(model="claude-haiku-4-5-20251001")
        return self._llm_service
    
    async def analyze(self, raw_prompt: str) -> LLMAnalysisResult:
        """
        分析系统提示词
        
        Args:
            raw_prompt: 运营写的原始提示词（任意格式）
            
        Returns:
            LLMAnalysisResult 结构化分析结果
        """
        logger.info(f"🧠 开始 LLM 语义分析，提示词长度: {len(raw_prompt)} 字符")
        
        llm = self._get_llm_service()
        
        try:
            # 调用 LLM 分析
            response = await llm.create_message(
                system=PROMPT_ANALYSIS_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": PROMPT_ANALYSIS_USER.format(prompt=raw_prompt)
                }],
                max_tokens=4000,
                temperature=0,  # 确定性输出
            )
            
            # 解析 JSON 响应
            response_text = response.content[0].text.strip()
            
            # 清理可能的 markdown 代码块
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            analysis_data = json.loads(response_text.strip())
            
            # 转换为数据类
            result = self._parse_analysis_result(analysis_data, raw_prompt)
            
            # 提取模块实际内容
            result = self._extract_module_contents(result, raw_prompt)
            
            logger.info(f"✅ LLM 分析完成: {result.agent_name}, 识别 {sum(1 for m in result.modules.values() if m.found)} 个模块")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ LLM 返回的 JSON 解析失败: {e}")
            return self._fallback_analysis(raw_prompt)
        except Exception as e:
            logger.error(f"❌ LLM 分析失败: {e}")
            return self._fallback_analysis(raw_prompt)
    
    def _parse_analysis_result(
        self, 
        data: Dict[str, Any], 
        raw_prompt: str
    ) -> LLMAnalysisResult:
        """解析 LLM 返回的 JSON 数据"""
        result = LLMAnalysisResult(
            agent_name=data.get("agent_name", "GeneralAgent"),
            agent_role=data.get("agent_role", ""),
            raw_prompt=raw_prompt,
        )
        
        # 解析模块
        modules_data = data.get("modules", {})
        for module_id, module_info in modules_data.items():
            if isinstance(module_info, dict):
                result.modules[module_id] = ModuleAnalysis(
                    found=module_info.get("found", False),
                    summary=module_info.get("summary", ""),
                    start_marker=module_info.get("start_marker", ""),
                    importance=module_info.get("importance", "medium"),
                    can_simplify=module_info.get("can_simplify", True),
                )
        
        # 解析复杂度规则
        complexity_data = data.get("complexity_rules", {})
        for level, rule_info in complexity_data.items():
            if isinstance(rule_info, dict):
                result.complexity_rules[level] = ComplexityRule(
                    keywords=rule_info.get("keywords", []),
                    description=rule_info.get("description", ""),
                )
        
        # 解析工具列表
        result.tools = data.get("tools", [])
        
        # 解析意图类型
        intent_data = data.get("intent_types", [])
        for intent_info in intent_data:
            if isinstance(intent_info, dict):
                result.intent_types.append(IntentType(
                    name=intent_info.get("name", ""),
                    keywords=intent_info.get("keywords", []),
                ))
        
        return result
    
    def _extract_module_contents(
        self, 
        result: LLMAnalysisResult, 
        raw_prompt: str
    ) -> LLMAnalysisResult:
        """
        根据 LLM 识别的位置标记，提取模块实际内容
        
        这是一个启发式方法，用 start_marker 定位内容
        """
        for module_id, module in result.modules.items():
            if not module.found or not module.start_marker:
                continue
            
            # 尝试定位内容
            marker_pos = raw_prompt.find(module.start_marker)
            if marker_pos == -1:
                # 尝试模糊匹配
                marker_lower = module.start_marker.lower()
                prompt_lower = raw_prompt.lower()
                marker_pos = prompt_lower.find(marker_lower[:30])  # 只匹配前30字符
            
            if marker_pos != -1:
                # 提取从标记开始的一段内容（最多2000字符，或到下一个主要分隔符）
                start = marker_pos
                end = min(start + 2000, len(raw_prompt))
                
                # 查找可能的结束位置（下一个主要标题或分隔符）
                separators = ["\n# ", "\n## ", "\n---", "\n===", "</", "\n\n\n"]
                for sep in separators:
                    sep_pos = raw_prompt.find(sep, start + 100)  # 至少包含100字符
                    if sep_pos != -1 and sep_pos < end:
                        end = sep_pos
                
                module.content = raw_prompt[start:end].strip()
        
        return result
    
    def _fallback_analysis(self, raw_prompt: str) -> LLMAnalysisResult:
        """
        回退分析（当 LLM 调用失败时）
        
        使用简单的启发式方法
        """
        logger.warning("⚠️ 使用回退分析（LLM 调用失败）")
        
        result = LLMAnalysisResult(raw_prompt=raw_prompt)
        
        # 简单提取 agent 名称
        if "Copilot" in raw_prompt:
            result.agent_name = "Copilot"
        elif "Assistant" in raw_prompt:
            result.agent_name = "Assistant"
        
        # 标记整个提示词为 role_definition（最保守的方案）
        result.modules["role_definition"] = ModuleAnalysis(
            found=True,
            summary="完整系统提示词",
            content=raw_prompt,
            importance="high",
            can_simplify=False,
        )
        
        return result
    
    def analyze_sync(self, raw_prompt: str) -> LLMAnalysisResult:
        """同步版本的分析方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已有事件循环，使用回退方案
                return self._fallback_analysis(raw_prompt)
            return loop.run_until_complete(self.analyze(raw_prompt))
        except RuntimeError:
            return asyncio.run(self.analyze(raw_prompt))


# ============================================================
# 便捷函数
# ============================================================

async def analyze_prompt_with_llm(raw_prompt: str) -> LLMAnalysisResult:
    """
    使用 LLM 分析系统提示词
    
    Args:
        raw_prompt: 运营写的原始提示词（任意格式）
        
    Returns:
        LLMAnalysisResult 结构化分析结果
    """
    analyzer = LLMPromptAnalyzer()
    return await analyzer.analyze(raw_prompt)


def analyze_prompt_with_llm_sync(raw_prompt: str) -> LLMAnalysisResult:
    """同步版本"""
    analyzer = LLMPromptAnalyzer()
    return analyzer.analyze_sync(raw_prompt)
