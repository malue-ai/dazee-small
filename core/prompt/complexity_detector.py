"""
V5.0 任务复杂度检测器

核心理念：
- 所有复杂度判断都通过 LLM 语义理解完成
- 不使用关键词匹配或长度规则
- 保守的 fallback（MEDIUM），不做关键词猜测

设计原则：
- 运营无需配置任何关键词规则
- LLM 学习 Few-Shot 示例进行语义泛化推理
- 代码只做调用和解析，不做规则判断
"""

import asyncio
from typing import Any, Optional, Tuple

from logger import get_logger

from .prompt_layer import PromptSchema, TaskComplexity

logger = get_logger("complexity_detector")


class ComplexityDetector:
    """
    V5.0 任务复杂度检测器

    策略：LLM-First 语义推理
    - 直接使用 LLM 进行语义理解
    - 不使用关键词匹配
    - 不使用长度规则
    - 保守的 fallback（MEDIUM）
    """

    def __init__(
        self,
        schema: Optional[PromptSchema] = None,
        use_llm_fallback: bool = True,  # 保持兼容，但默认就是 LLM
        llm_threshold: float = 0.5,  # 保持兼容
    ):
        """
        初始化检测器

        Args:
            schema: PromptSchema（保持兼容，V5.0 不使用其中的 keywords）
            use_llm_fallback: 保持兼容
            llm_threshold: 保持兼容
        """
        self.schema = schema
        self._semantic_inference = None

    def _get_semantic_inference(self):
        """获取语义推理服务（懒加载）"""
        if self._semantic_inference is None:
            try:
                from core.inference import SemanticInference

                self._semantic_inference = SemanticInference()
            except Exception as e:
                logger.warning(f"⚠️ 语义推理服务初始化失败: {e}")
                return None
        return self._semantic_inference

    def detect(self, query: str) -> Tuple[TaskComplexity, float]:
        """
        同步检测任务复杂度

        V5.0 策略：使用保守默认值，推荐使用异步方法 detect_async

        Args:
            query: 用户输入

        Returns:
            (复杂度级别, 置信度 0-1)
        """
        _running = False
        try:
            asyncio.get_running_loop()
            _running = True
        except RuntimeError:
            _running = False

        if _running:
            # 事件循环已运行，使用保守默认值
            logger.info("⚠️ 事件循环已运行，使用保守默认值 MEDIUM")
            return TaskComplexity.MEDIUM, 0.5

        # 没有运行中的事件循环，安全使用 asyncio.run()
        return asyncio.run(self.detect_async(query))

    async def detect_async(self, query: str) -> Tuple[TaskComplexity, float]:
        """
        异步检测任务复杂度（推荐方法）

        V5.0 策略：LLM-First 语义推理

        Args:
            query: 用户输入

        Returns:
            (复杂度级别, 置信度 0-1)
        """
        inference = self._get_semantic_inference()

        if inference is None:
            # LLM 服务不可用，使用保守默认值
            logger.info(f"⚠️ 语义推理服务不可用，使用保守默认值 MEDIUM")
            return TaskComplexity.MEDIUM, 0.3

        try:
            # 使用语义推理
            result = await inference.infer_complexity(query)

            # 转换结果
            complexity_str = result.result.get("complexity", "medium")
            complexity_map = {
                "simple": TaskComplexity.SIMPLE,
                "medium": TaskComplexity.MEDIUM,
                "complex": TaskComplexity.COMPLEX,
            }

            complexity = complexity_map.get(complexity_str, TaskComplexity.MEDIUM)
            confidence = result.confidence

            logger.info(f"🧠 复杂度检测: {complexity.value} (confidence={confidence:.2f})")
            logger.debug(f"   推理: {result.reasoning}")

            return complexity, confidence

        except Exception as e:
            logger.warning(f"⚠️ LLM 推理失败: {e}，使用保守默认值 MEDIUM")
            return TaskComplexity.MEDIUM, 0.3

    def detect_with_llm_fallback(self, query: str) -> Tuple[TaskComplexity, float]:
        """
        检测任务复杂度（保持兼容）

        V5.0: 直接调用 detect()，因为 LLM 是默认方法
        """
        return self.detect(query)


# ============================================================
# 便捷函数
# ============================================================


def detect_complexity(
    query: str,
    schema: Optional[PromptSchema] = None,
    use_llm: bool = True,  # V5.0: 默认使用 LLM
) -> TaskComplexity:
    """
    检测任务复杂度（简化接口）

    V5.0: 始终使用 LLM 语义推理

    Args:
        query: 用户输入
        schema: 可选的 PromptSchema（V5.0 不使用其中的 keywords）
        use_llm: 保持兼容（V5.0 始终为 True）

    Returns:
        TaskComplexity 枚举值
    """
    detector = ComplexityDetector(schema)
    complexity, _ = detector.detect(query)
    return complexity


def detect_complexity_with_confidence(
    query: str,
    schema: Optional[PromptSchema] = None,
    use_llm: bool = True,  # V5.0: 默认使用 LLM
) -> Tuple[TaskComplexity, float]:
    """
    检测任务复杂度（带置信度）

    V5.0: 始终使用 LLM 语义推理

    Args:
        query: 用户输入
        schema: 可选的 PromptSchema（V5.0 不使用其中的 keywords）
        use_llm: 保持兼容（V5.0 始终为 True）

    Returns:
        (TaskComplexity, 置信度 0-1)
    """
    detector = ComplexityDetector(schema)
    return detector.detect(query)


async def detect_complexity_async(
    query: str,
    schema: Optional[PromptSchema] = None,
) -> Tuple[TaskComplexity, float]:
    """
    异步检测任务复杂度（推荐方法）

    V5.0: 使用 LLM 语义推理

    Args:
        query: 用户输入
        schema: 可选的 PromptSchema（V5.0 不使用其中的 keywords）

    Returns:
        (TaskComplexity, 置信度 0-1)
    """
    detector = ComplexityDetector(schema)
    return await detector.detect_async(query)
