"""
任务复杂度检测器

职责：
1. 分析用户 query，判断任务复杂度
2. 基于关键词 + LLM 推断（低置信度时）
3. 决定使用哪个版本的系统提示词
"""

import re
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from .prompt_layer import TaskComplexity, PromptSchema

from logger import get_logger

logger = get_logger("complexity_detector")

# LLM 推断复杂度的 Prompt
COMPLEXITY_INFERENCE_PROMPT = """你是一个任务复杂度分类器。根据用户的查询，判断其复杂度级别。

**复杂度定义**：
- **simple（简单）**: 单一问答、简单查询、打招呼、获取基本信息。无需多步骤处理。
- **medium（中等）**: 需要分析、对比、生成报告或文档、提供建议。需要 3-5 步处理。
- **complex（复杂）**: 系统设计、架构规划、业务流程构建、多实体关系建模。需要完整规划和多轮迭代。

**用户查询**：
{query}

**请直接输出一个词**（simple/medium/complex），不要其他内容："""


class ComplexityDetector:
    """
    任务复杂度检测器
    
    策略：
    1. 先用关键词匹配快速判断
    2. 如果不确定，使用 LLM 推断（可选）
    3. 返回复杂度级别和置信度
    """
    
    # 默认关键词（可被 PromptSchema 中的配置覆盖）
    DEFAULT_KEYWORDS = {
        TaskComplexity.SIMPLE: [
            # 问答类
            "什么", "是什么", "多少", "几", "哪里", "哪个", "怎么样",
            "查", "查一下", "查询", "告诉我",
            # 简单操作
            "天气", "时间", "日期", "价格",
            # 打招呼
            "你好", "hi", "hello", "早上好", "下午好",
            # 英文
            "what", "how much", "where", "when", "who",
        ],
        TaskComplexity.MEDIUM: [
            # 分析类
            "分析", "对比", "评估", "建议", "方案",
            "调研", "研究", "报告", "总结",
            # 生成类（中等复杂度）
            "写一个", "生成", "创建", "制作",
            "PPT", "文档", "报表",
            # 英文
            "analyze", "compare", "suggest", "report",
        ],
        TaskComplexity.COMPLEX: [
            # 系统设计
            "搭建", "设计", "构建", "开发", "实现",
            "系统", "架构", "平台", "框架",
            # 业务系统
            "ERP", "CRM", "BI", "OA", "HR系统",
            "管理系统", "业务流程",
            # 深度分析
            "本体论", "实体关系", "数据模型",
            # 英文
            "build", "design", "develop", "implement", "architecture",
        ],
    }
    
    # 复杂度指示词权重
    COMPLEXITY_INDICATORS = {
        TaskComplexity.SIMPLE: {
            "short_query": 1.5,      # 短查询（< 20 字符）
            "question_mark": 1.2,    # 包含问号
            "single_task": 1.3,      # 单一任务
        },
        TaskComplexity.MEDIUM: {
            "multiple_parts": 1.3,   # 多个部分/步骤
            "analysis_words": 1.4,   # 分析类词汇
            "output_required": 1.2,  # 需要输出物
        },
        TaskComplexity.COMPLEX: {
            "system_design": 2.0,    # 系统设计相关
            "long_query": 1.3,       # 长查询（> 100 字符）
            "multi_entity": 1.5,     # 多实体/关系
            "iterative": 1.4,        # 迭代/优化相关
        },
    }
    
    def __init__(
        self, 
        schema: Optional[PromptSchema] = None,
        use_llm_fallback: bool = True,
        llm_threshold: float = 0.5,
    ):
        """
        初始化检测器
        
        Args:
            schema: PromptSchema，提供自定义关键词配置
            use_llm_fallback: 低置信度时是否使用 LLM 辅助判断
            llm_threshold: 触发 LLM 辅助的置信度阈值
        """
        self.schema = schema
        self.use_llm_fallback = use_llm_fallback
        self.llm_threshold = llm_threshold
        self._llm_service = None
        
        # 使用 schema 中的关键词（如果有），否则使用默认
        if schema and schema.complexity_keywords:
            self.keywords = schema.complexity_keywords
        else:
            self.keywords = self.DEFAULT_KEYWORDS
    
    def detect(self, query: str) -> Tuple[TaskComplexity, float]:
        """
        检测任务复杂度
        
        Args:
            query: 用户输入
            
        Returns:
            (复杂度级别, 置信度 0-1)
        """
        query_lower = query.lower()
        
        # 1. 计算各复杂度的得分
        scores = {
            TaskComplexity.SIMPLE: 0.0,
            TaskComplexity.MEDIUM: 0.0,
            TaskComplexity.COMPLEX: 0.0,
        }
        
        # 2. 关键词匹配
        for complexity, keywords in self.keywords.items():
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    scores[complexity] += 1.0
                    logger.debug(f"   关键词匹配: '{keyword}' → {complexity.value}")
        
        # 3. 结构指示器
        scores = self._apply_structural_indicators(query, scores)
        
        # 4. 选择得分最高的复杂度
        max_complexity = max(scores, key=scores.get)
        max_score = scores[max_complexity]
        
        # 5. 计算置信度
        total_score = sum(scores.values())
        confidence = max_score / total_score if total_score > 0 else 0.5
        
        # 6. 如果置信度太低，默认为 MEDIUM
        if confidence < 0.4:
            logger.info(f"⚠️ 复杂度判断不确定 (confidence={confidence:.2f})，默认为 MEDIUM")
            return TaskComplexity.MEDIUM, 0.5
        
        logger.info(f"✅ 复杂度检测: {max_complexity.value} (confidence={confidence:.2f})")
        logger.debug(f"   得分: {scores}")
        
        return max_complexity, confidence
    
    def _apply_structural_indicators(
        self,
        query: str,
        scores: Dict[TaskComplexity, float]
    ) -> Dict[TaskComplexity, float]:
        """应用结构指示器"""
        
        # 短查询 → Simple
        if len(query) < 20:
            scores[TaskComplexity.SIMPLE] += self.COMPLEXITY_INDICATORS[TaskComplexity.SIMPLE]["short_query"]
        
        # 问号 → Simple
        if "?" in query or "？" in query:
            scores[TaskComplexity.SIMPLE] += self.COMPLEXITY_INDICATORS[TaskComplexity.SIMPLE]["question_mark"]
        
        # 长查询 → Complex
        if len(query) > 100:
            scores[TaskComplexity.COMPLEX] += self.COMPLEXITY_INDICATORS[TaskComplexity.COMPLEX]["long_query"]
        
        # 多个"和"/"、" → 可能是多步骤
        if query.count("和") > 2 or query.count("、") > 3:
            scores[TaskComplexity.MEDIUM] += self.COMPLEXITY_INDICATORS[TaskComplexity.MEDIUM]["multiple_parts"]
        
        # 包含"步骤"、"流程"、"阶段" → Complex
        if any(word in query for word in ["步骤", "流程", "阶段", "迭代"]):
            scores[TaskComplexity.COMPLEX] += self.COMPLEXITY_INDICATORS[TaskComplexity.COMPLEX]["iterative"]
        
        return scores
    
    def _get_llm_service(self) -> Any:
        """获取 LLM 服务（懒加载）"""
        if self._llm_service is None:
            try:
                from services.llm_service import ClaudeLLMService
                self._llm_service = ClaudeLLMService()
            except Exception as e:
                logger.warning(f"⚠️ LLM 服务初始化失败: {e}")
                return None
        return self._llm_service
    
    async def _infer_with_llm(self, query: str) -> Optional[TaskComplexity]:
        """
        使用 LLM 推断复杂度
        
        Args:
            query: 用户查询
            
        Returns:
            推断的复杂度，失败返回 None
        """
        llm = self._get_llm_service()
        if not llm:
            return None
        
        try:
            prompt = COMPLEXITY_INFERENCE_PROMPT.format(query=query)
            
            response = await llm.create_message_async(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            
            # 解析响应
            result = response.content[0].text.strip().lower()
            
            complexity_map = {
                "simple": TaskComplexity.SIMPLE,
                "medium": TaskComplexity.MEDIUM,
                "complex": TaskComplexity.COMPLEX,
            }
            
            if result in complexity_map:
                logger.info(f"🧠 LLM 推断复杂度: {result}")
                return complexity_map[result]
            else:
                logger.warning(f"⚠️ LLM 返回未知复杂度: {result}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ LLM 推断失败: {e}")
            return None
    
    def detect_with_llm_fallback(self, query: str) -> Tuple[TaskComplexity, float]:
        """
        检测任务复杂度（带 LLM 回退）
        
        在关键词匹配置信度较低时，使用 LLM 进行更精确的判断。
        
        Args:
            query: 用户输入
            
        Returns:
            (复杂度级别, 置信度 0-1)
        """
        # 1. 先进行关键词匹配
        complexity, confidence = self.detect(query)
        
        # 2. 如果置信度足够高，直接返回
        if confidence >= self.llm_threshold:
            return complexity, confidence
        
        # 3. 置信度较低，尝试使用 LLM
        if self.use_llm_fallback:
            try:
                # 运行异步方法
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已有事件循环，使用 nest_asyncio 或返回原结果
                    logger.debug("事件循环已运行，跳过 LLM 推断")
                else:
                    llm_result = loop.run_until_complete(self._infer_with_llm(query))
                    if llm_result:
                        return llm_result, 0.8  # LLM 判断给予较高置信度
            except RuntimeError:
                # 没有事件循环，创建新的
                llm_result = asyncio.run(self._infer_with_llm(query))
                if llm_result:
                    return llm_result, 0.8
            except Exception as e:
                logger.warning(f"⚠️ LLM 回退失败: {e}")
        
        return complexity, confidence


# ============================================================
# 便捷函数
# ============================================================

def detect_complexity(
    query: str, 
    schema: Optional[PromptSchema] = None,
    use_llm: bool = False,
) -> TaskComplexity:
    """
    检测任务复杂度（简化接口）
    
    Args:
        query: 用户输入
        schema: 可选的 PromptSchema
        use_llm: 是否在低置信度时使用 LLM
        
    Returns:
        TaskComplexity 枚举值
    """
    detector = ComplexityDetector(schema, use_llm_fallback=use_llm)
    if use_llm:
        complexity, _ = detector.detect_with_llm_fallback(query)
    else:
        complexity, _ = detector.detect(query)
    return complexity


def detect_complexity_with_confidence(
    query: str,
    schema: Optional[PromptSchema] = None,
    use_llm: bool = False,
) -> Tuple[TaskComplexity, float]:
    """
    检测任务复杂度（带置信度）
    
    Args:
        query: 用户输入
        schema: 可选的 PromptSchema
        use_llm: 是否在低置信度时使用 LLM
        
    Returns:
        (TaskComplexity, 置信度 0-1)
    """
    detector = ComplexityDetector(schema, use_llm_fallback=use_llm)
    if use_llm:
        return detector.detect_with_llm_fallback(query)
    return detector.detect(query)


async def detect_complexity_async(
    query: str,
    schema: Optional[PromptSchema] = None,
) -> Tuple[TaskComplexity, float]:
    """
    异步检测任务复杂度（带 LLM 回退）
    
    Args:
        query: 用户输入
        schema: 可选的 PromptSchema
        
    Returns:
        (TaskComplexity, 置信度 0-1)
    """
    detector = ComplexityDetector(schema, use_llm_fallback=True)
    
    # 1. 先进行关键词匹配
    complexity, confidence = detector.detect(query)
    
    # 2. 如果置信度足够高，直接返回
    if confidence >= detector.llm_threshold:
        return complexity, confidence
    
    # 3. 置信度较低，尝试使用 LLM
    llm_result = await detector._infer_with_llm(query)
    if llm_result:
        return llm_result, 0.8
    
    return complexity, confidence
