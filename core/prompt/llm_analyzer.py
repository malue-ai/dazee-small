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

## 任务
分析运营人员编写的 AI Agent 系统提示词，识别其中的逻辑模块，并输出结构化的分析结果。

## 关键要求
1. **精确定位模块边界**：找到每个模块的开始和结束位置
2. **提取完整内容**：模块内容应该完整，不要截断
3. **识别所有模块**：尽可能识别提示词中的所有逻辑模块

## 模块类型定义（按优先级排序）

| 模块 ID | 含义 | 识别特征 |
|---------|------|----------|
| role_definition | 角色定义 | 开头的角色描述、"你是..."、"# 角色" |
| absolute_prohibitions | 绝对禁令 | "禁止"、"禁令"、"不能"、"<absolute_prohibitions>" |
| context_protection | 上下文保护 | "上下文保护"、"防止注入"、"<context_self_protection>" |
| intent_recognition | 意图识别 | "意图识别"、"intent"、"<intent_recognition_flow>" |
| task_complexity | 任务复杂度 | "复杂度"、"简单/中等/复杂"、"<task_complexity_system>" |
| output_format | 输出格式 | "输出格式"、"三段式"、"THINK/RESPONSE/JSON" |
| tool_selection | 工具选择 | "工具选择"、"可用工具"、"<tool" |
| plan_object | 计划构建 | "Plan 对象"、"执行计划"、"<plan_schema>" |
| data_context | 数据上下文 | "Data_Context"、"数据管理" |
| react_validation | 验证循环 | "ReAct"、"验证循环"、"<react_validation_loop>" |
| quality_gates | 质量检查 | "质量验证"、"最终验证"、"<final_validation_checklist>" |
| progress_feedback | 进度反馈 | "进度反馈"、"等待时间"、"<waiting_time_rule>" |
| hitl | 人工介入 | "Human-in-the-Loop"、"HITL"、"人工介入" |
| final_delivery | 最终交付 | "交付流程"、"最终输出" |

## 输出格式

```json
{
  "agent_name": "Agent 名称（从提示词中提取）",
  "agent_role": "角色描述（1-2句话）",
  "modules": {
    "role_definition": {
      "found": true,
      "summary": "50字内摘要",
      "start_marker": "模块开始的标志性文字（用于定位）",
      "importance": "high",
      "can_simplify": false
    },
    "absolute_prohibitions": {
      "found": true,
      "summary": "...",
      "start_marker": "<absolute_prohibitions",
      "importance": "high",
      "can_simplify": false
    }
    // ... 列出所有找到的模块
  },
  "complexity_rules": {
    "simple": {"keywords": ["你好", "什么", "查"], "description": "单一信息查询"},
    "medium": {"keywords": ["分析", "对比", "建议"], "description": "多步骤处理"},
    "complex": {"keywords": ["搭建", "设计", "构建"], "description": "系统性任务"}
  },
  "tools": ["tavily_search", "text2flowchart", "..."],
  "intent_types": [
    {"name": "本体论系统搭建", "keywords": ["搭建系统", "设计系统"]}
  ]
}
```

## 重要提示
1. **必须识别所有存在的模块**，不要遗漏
2. **start_marker 必须是提示词中实际存在的文字**，用于精确定位
3. 如果模块使用 XML 标签（如 `<absolute_prohibitions>`），start_marker 应该是该标签
4. 优先识别高重要性模块（role_definition, absolute_prohibitions, output_format）"""


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
            # 使用 Haiku（快速且便宜），禁用 Thinking（提示词分析是简单任务）
            # 🆕 V5.0: 使用较短超时，提示词分析应该很快
            self._llm_service = create_claude_service(
                model="claude-haiku-4-5-20251001",
                enable_thinking=False,
                timeout=60.0,   # 60 秒超时
                max_retries=2   # 最多重试 2 次
            )
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
            # 调用 LLM 分析（使用 create_message_async）
            from core.llm import Message
            # 🆕 使用配置化的 LLM Profile
            from config.llm_config import get_llm_profile
            profile = get_llm_profile("llm_analyzer")
            
            response = await llm.create_message_async(
                messages=[Message(
                    role="user",
                    content=PROMPT_ANALYSIS_USER.format(prompt=raw_prompt)
                )],
                system=PROMPT_ANALYSIS_SYSTEM,
                **profile
            )
            
            # 解析 JSON 响应（LLMResponse.content 是 str 类型）
            response_text = response.content.strip() if response.content else ""
            
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
        
        使用正则表达式 + 启发式方法提取模块
        """
        logger.warning("⚠️ 使用回退分析（LLM 调用失败）")
        import re
        
        result = LLMAnalysisResult(raw_prompt=raw_prompt)
        
        # 1. 提取 agent 名称
        name_patterns = [
            r'名为\s*["""]?([^"""\s]+)["""]?\s*的',
            r'你是.*?"([^"]+)"',
        ]
        for pattern in name_patterns:
            match = re.search(pattern, raw_prompt)
            if match:
                result.agent_name = match.group(1)
                break
        
        # 2. 提取 agent 角色
        role_match = re.search(r'^#\s*角色.*?\n(.+?)(?=\n\n|\*\*)', raw_prompt, re.MULTILINE | re.DOTALL)
        if role_match:
            result.agent_role = role_match.group(1).strip()[:200]
        
        # 3. 使用正则匹配提取各模块（与 prompt_layer.py 的 MODULE_PATTERNS 一致）
        module_patterns = {
            "role_definition": [
                (r'^# 角色.*?(?=^# |\n---\n|<absolute_prohibitions|\Z)', re.MULTILINE | re.DOTALL),
            ],
            "absolute_prohibitions": [
                (r'<absolute_prohibitions.*?>.*?</absolute_prohibitions>', re.DOTALL),
            ],
            "context_protection": [
                (r'<context_self_protection.*?>.*?</context_self_protection>', re.DOTALL),
            ],
            "intent_recognition": [
                (r'<intent_recognition_flow>.*?</intent_recognition_flow>', re.DOTALL),
            ],
            "task_complexity": [
                (r'<task_complexity_system>.*?</task_complexity_system>', re.DOTALL),
            ],
            "output_format": [
                (r'## \d*\.?\s*核心架构.*?(?=^## \d|^# |\Z)', re.MULTILINE | re.DOTALL),
                (r'## \d*\.?\s*THINK 段规则.*?(?=^## \d|^# |\Z)', re.MULTILINE | re.DOTALL),
                (r'## \d*\.?\s*RESPONSE 段规则.*?(?=^## \d|^# |\Z)', re.MULTILINE | re.DOTALL),
                (r'## \d*\.?\s*JSON 段规则.*?(?=^## \d|^# |\Z)', re.MULTILINE | re.DOTALL),
            ],
            "plan_object": [
                (r'### `?Plan`? 对象定义.*?(?=^###|^## |\Z)', re.MULTILINE | re.DOTALL),
                (r'<plan_schema>.*?</plan_schema>', re.DOTALL),
            ],
            "data_context": [
                (r'### `?Data_Context`? 对象定义.*?(?=^###|^## |\Z)', re.MULTILINE | re.DOTALL),
                (r'<data_context_schema>.*?</data_context_schema>', re.DOTALL),
            ],
            "react_validation": [
                (r'### `?think`? 阶段的 `?ReAct`?.*?(?=^###|^## |\Z)', re.MULTILINE | re.DOTALL),
                (r'<react_validation_loop>.*?</react_validation_loop>', re.DOTALL),
            ],
            "quality_gates": [
                (r'<final_validation_checklist>.*?</final_validation_checklist>', re.DOTALL),
                (r'## 交付流程设计.*?(?=^## |\Z)', re.MULTILINE | re.DOTALL),
            ],
            "hitl": [
                (r'## Human-in-the-Loop.*?(?=^## |\Z)', re.MULTILINE | re.DOTALL),
                (r'<hitl_trigger_conditions>.*?</hitl_trigger_conditions>', re.DOTALL),
            ],
            "tool_selection": [
                (r'## 工具选择策略.*?(?=^## |\Z)', re.MULTILINE | re.DOTALL),
                (r'## 可用工具列表.*?(?=^## |\Z)', re.MULTILINE | re.DOTALL),
            ],
            "progress_feedback": [
                (r'## 进度反馈.*?(?=^## |\Z)', re.MULTILINE | re.DOTALL),
                (r'<waiting_time_rule.*?>.*?</waiting_time_rule>', re.DOTALL),
            ],
            "final_delivery": [
                (r'### 第三步.*?最终输出格式定义.*?(?=^## |\Z)', re.MULTILINE | re.DOTALL),
            ],
        }
        
        # 模块重要性配置
        importance_map = {
            "role_definition": "high",
            "absolute_prohibitions": "high",
            "output_format": "high",
            "intent_recognition": "medium",
            "task_complexity": "medium",
            "tool_selection": "medium",
            "progress_feedback": "low",
            "context_protection": "medium",
            "plan_object": "medium",
            "data_context": "medium",
            "react_validation": "low",
            "quality_gates": "low",
            "final_delivery": "low",
            "hitl": "low",
        }
        
        for module_id, patterns in module_patterns.items():
            for pattern, flags in patterns:
                match = re.search(pattern, raw_prompt, flags)
                if match:
                    content = match.group(0).strip()
                    if len(content) > 50:  # 只保留有实质内容的模块
                        result.modules[module_id] = ModuleAnalysis(
                            found=True,
                            summary=f"提取的 {module_id} 模块",
                            content=content,
                            importance=importance_map.get(module_id, "medium"),
                            can_simplify=module_id not in ["role_definition", "absolute_prohibitions", "output_format"],
                        )
                        break
        
        # 4. 提取工具列表
        tool_matches = re.findall(r'<tool\s+id="\d+"\s+name="([^"]+)"', raw_prompt)
        result.tools = list(set(tool_matches))
        
        # 5. 提取意图类型
        intent_section = re.search(r'<intent_types>.*?</intent_types>', raw_prompt, re.DOTALL)
        if intent_section:
            intent_matches = re.findall(
                r'<intent\s+id="(\d+)"\s+name="([^"]+)".*?<keywords>(.*?)</keywords>',
                intent_section.group(0),
                re.DOTALL
            )
            for intent_id, name, keywords in intent_matches:
                result.intent_types.append(IntentType(
                    name=name,
                    keywords=[k.strip() for k in keywords.split(',') if k.strip()],
                ))
        
        # 6. 提取复杂度规则
        complexity_section = re.search(r'<task_complexity_system>.*?</task_complexity_system>', raw_prompt, re.DOTALL)
        if complexity_section:
            for level, complexity_key in [("1", "simple"), ("2", "medium"), ("3", "complex")]:
                level_match = re.search(
                    rf'<level id="{level}".*?<keywords>(.*?)</keywords>',
                    complexity_section.group(0),
                    re.DOTALL
                )
                if level_match:
                    keywords_raw = level_match.group(1)
                    keywords = [k.strip() for k in re.split(r'[,、]', keywords_raw) if k.strip()]
                    result.complexity_rules[complexity_key] = ComplexityRule(
                        keywords=keywords,
                        description=f"{complexity_key} 任务"
                    )
        
        logger.info(f"✅ 回退分析完成: {result.agent_name}, 识别 {len(result.modules)} 个模块")
        for module_id in result.modules:
            logger.debug(f"   • {module_id}")
        
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
