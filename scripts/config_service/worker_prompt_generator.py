"""
Worker Prompt 生成器

使用 LLM 为不同类型的 Worker 生成高质量系统提示词

设计原则：
- LLM 智能生成，非模板拼接
- 生成后需经 HITL 确认
- 支持迭代优化
"""

import json
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from logger import get_logger

logger = get_logger("worker_prompt_generator")


# ==================== Worker 类型定义 ====================

WORKER_SPECIALIZATIONS = {
    "research": {
        "name": "研究分析",
        "description": "信息收集、竞品分析、市场调研",
        "typical_tasks": [
            "研究竞品的产品战略",
            "分析行业趋势",
            "收集市场数据"
        ],
        "key_capabilities": [
            "系统性信息收集",
            "批判性分析",
            "洞察提炼"
        ]
    },
    "document": {
        "name": "文档生成",
        "description": "PPT、报告、文档撰写",
        "typical_tasks": [
            "生成产品介绍 PPT",
            "撰写分析报告",
            "编写技术文档"
        ],
        "key_capabilities": [
            "结构化表达",
            "可视化呈现",
            "专业写作"
        ]
    },
    "data_analysis": {
        "name": "数据分析",
        "description": "数据处理、统计分析、可视化",
        "typical_tasks": [
            "销售数据分析",
            "用户行为分析",
            "趋势预测"
        ],
        "key_capabilities": [
            "数据清洗",
            "统计分析",
            "图表生成"
        ]
    },
    "code": {
        "name": "代码开发",
        "description": "代码编写、重构、测试",
        "typical_tasks": [
            "功能开发",
            "代码重构",
            "单元测试"
        ],
        "key_capabilities": [
            "代码质量",
            "设计模式",
            "测试驱动"
        ]
    },
    "general": {
        "name": "通用助手",
        "description": "通用任务处理",
        "typical_tasks": [
            "问答",
            "翻译",
            "总结"
        ],
        "key_capabilities": [
            "理解能力",
            "通用知识",
            "灵活应对"
        ]
    }
}


# ==================== 生成 Prompt ====================

GENERATION_PROMPT = """
## 你的任务

为指定类型的 AI Worker 生成高质量的系统提示词。

## Worker 信息

- 类型: {specialization}
- 名称: {spec_name}
- 描述: {spec_description}
- 典型任务: {typical_tasks}
- 核心能力: {key_capabilities}

## 具体任务上下文

{task_context}

## 输出要求

生成的系统提示词应该：
1. **专业化**：突出该 Worker 的专业领域和角色定位
2. **具体化**：针对具体任务类型给出指导
3. **可操作**：包含明确的执行方法论或步骤
4. **约束清晰**：明确输出格式和质量要求

## 输出格式

输出 JSON 格式：
```json
{{
  "reasoning": "生成推理过程...",
  "system_prompt": "生成的系统提示词...",
  "suggested_tools": ["建议使用的工具列表"],
  "quality_checklist": ["质量检查项"]
}}
```

请生成系统提示词：
"""


# ==================== 优化 Prompt ====================

OPTIMIZATION_PROMPT = """
## 你的任务

根据运营人员的反馈，优化 Worker 的系统提示词。

## 当前提示词

{current_prompt}

## 运营反馈

{feedback}

## 优化要求

1. 保留原有优点
2. 针对反馈进行改进
3. 不要过度修改，保持简洁

## 输出格式

输出 JSON 格式：
```json
{{
  "reasoning": "优化推理过程...",
  "optimized_prompt": "优化后的系统提示词...",
  "changes_summary": "修改摘要"
}}
```

请优化提示词：
"""


@dataclass
class GenerationResult:
    """生成结果"""
    success: bool
    specialization: str
    system_prompt: str
    reasoning: str = ""
    suggested_tools: List[str] = None
    quality_checklist: List[str] = None
    error: Optional[str] = None
    generated_at: datetime = None
    
    def __post_init__(self):
        if self.generated_at is None:
            self.generated_at = datetime.now()
        if self.suggested_tools is None:
            self.suggested_tools = []
        if self.quality_checklist is None:
            self.quality_checklist = []
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "specialization": self.specialization,
            "system_prompt": self.system_prompt,
            "reasoning": self.reasoning,
            "suggested_tools": self.suggested_tools,
            "quality_checklist": self.quality_checklist,
            "error": self.error,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None
        }


class WorkerPromptGenerator:
    """
    Worker Prompt 生成器
    
    使用 LLM 为不同类型的 Worker 生成系统提示词
    
    使用示例：
        generator = WorkerPromptGenerator(llm_service=claude_service)
        
        # 生成 research Worker 提示词
        result = await generator.generate(
            specialization="research",
            task_context="研究竞品的 AI 战略"
        )
        
        # 根据反馈优化
        optimized = await generator.optimize(
            current_prompt=result.system_prompt,
            feedback="请加入对财报数据的关注"
        )
    """
    
    def __init__(
        self,
        llm_service=None,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        """
        初始化生成器
        
        Args:
            llm_service: LLM 服务实例
            model: 使用的模型
        """
        self.llm_service = llm_service
        self.model = model
        
        logger.info("WorkerPromptGenerator 初始化完成")
    
    async def generate(
        self,
        specialization: str,
        task_context: str = ""
    ) -> GenerationResult:
        """
        生成 Worker 系统提示词
        
        Args:
            specialization: Worker 类型
            task_context: 任务上下文（可选）
            
        Returns:
            GenerationResult
        """
        logger.info(f"生成 Worker 提示词: specialization={specialization}")
        
        # 获取类型信息
        spec_info = WORKER_SPECIALIZATIONS.get(specialization, WORKER_SPECIALIZATIONS["general"])
        
        # 构建 Prompt
        prompt = GENERATION_PROMPT.format(
            specialization=specialization,
            spec_name=spec_info["name"],
            spec_description=spec_info["description"],
            typical_tasks=", ".join(spec_info["typical_tasks"]),
            key_capabilities=", ".join(spec_info["key_capabilities"]),
            task_context=task_context or "（无具体任务上下文）"
        )
        
        try:
            if self.llm_service:
                response = await self._call_llm(prompt)
                result = self._parse_generation_response(response, specialization)
            else:
                # Fallback: 使用默认模板
                result = self._generate_default(specialization, spec_info)
            
            logger.info(f"Worker 提示词生成完成: {specialization}")
            return result
            
        except Exception as e:
            logger.error(f"Worker 提示词生成失败: {e}")
            return GenerationResult(
                success=False,
                specialization=specialization,
                system_prompt="",
                error=str(e)
            )
    
    async def optimize(
        self,
        current_prompt: str,
        feedback: str
    ) -> GenerationResult:
        """
        根据反馈优化提示词
        
        Args:
            current_prompt: 当前提示词
            feedback: 运营反馈
            
        Returns:
            GenerationResult
        """
        logger.info("优化 Worker 提示词")
        
        prompt = OPTIMIZATION_PROMPT.format(
            current_prompt=current_prompt,
            feedback=feedback
        )
        
        try:
            if self.llm_service:
                response = await self._call_llm(prompt)
                result = self._parse_optimization_response(response)
            else:
                # Fallback: 简单追加
                result = GenerationResult(
                    success=True,
                    specialization="optimized",
                    system_prompt=f"{current_prompt}\n\n## 补充要求\n{feedback}",
                    reasoning="简单追加（无 LLM）"
                )
            
            logger.info("Worker 提示词优化完成")
            return result
            
        except Exception as e:
            logger.error(f"Worker 提示词优化失败: {e}")
            return GenerationResult(
                success=False,
                specialization="optimized",
                system_prompt=current_prompt,
                error=str(e)
            )
    
    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        response = await self.llm_service.create_message(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        if hasattr(response, 'content'):
            for block in response.content:
                if hasattr(block, 'text'):
                    return block.text
        
        return str(response)
    
    def _parse_generation_response(self, response: str, specialization: str) -> GenerationResult:
        """解析生成响应"""
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            
            return GenerationResult(
                success=True,
                specialization=specialization,
                system_prompt=data.get("system_prompt", ""),
                reasoning=data.get("reasoning", ""),
                suggested_tools=data.get("suggested_tools", []),
                quality_checklist=data.get("quality_checklist", [])
            )
        except Exception as e:
            logger.warning(f"解析生成响应失败: {e}")
            raise
    
    def _parse_optimization_response(self, response: str) -> GenerationResult:
        """解析优化响应"""
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            
            return GenerationResult(
                success=True,
                specialization="optimized",
                system_prompt=data.get("optimized_prompt", ""),
                reasoning=data.get("reasoning", "")
            )
        except Exception as e:
            logger.warning(f"解析优化响应失败: {e}")
            raise
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON"""
        import re
        
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            return json_match.group(1).strip()
        
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return text[start:end + 1]
        
        raise ValueError("未找到 JSON 内容")
    
    def _generate_default(self, specialization: str, spec_info: Dict) -> GenerationResult:
        """生成默认提示词"""
        prompt = f"""你是一位专业的{spec_info['name']}专家。

## 专业领域
{spec_info['description']}

## 核心能力
{chr(10).join(f'- {cap}' for cap in spec_info['key_capabilities'])}

## 工作方法
1. 理解任务需求
2. 系统性执行
3. 输出高质量结果

请认真完成分配给你的任务。"""
        
        return GenerationResult(
            success=True,
            specialization=specialization,
            system_prompt=prompt,
            reasoning="使用默认模板生成"
        )
    
    def get_available_specializations(self) -> Dict:
        """获取可用的 Worker 类型"""
        return WORKER_SPECIALIZATIONS


def create_worker_prompt_generator(
    llm_service=None,
    **kwargs
) -> WorkerPromptGenerator:
    """创建生成器"""
    return WorkerPromptGenerator(
        llm_service=llm_service,
        **kwargs
    )
