"""
质量扫描器（Quality Scanner）

定期扫描最近 N 条对话，使用 LLM Judge 批量评估质量问题。

工作流程：
1. 定时任务（每小时）扫描最近 N 条对话
2. 调用 ModelBasedGraders 批量评估
3. 自动标记低质量响应
4. 记录到 FailureDetector
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.monitoring.failure_detector import FailureDetector, FailureType
from evaluation.graders.model_based import ModelBasedGraders

logger = logging.getLogger(__name__)


class QualityScanner:
    """
    质量扫描器

    使用方式：
        scanner = QualityScanner(
            failure_detector=failure_detector,
            llm_judge=model_graders,
            conversation_service=conv_service
        )

        # 手动触发扫描
        await scanner.scan_recent_conversations(limit=100)

        # 启动定时任务
        await scanner.start_periodic_scan(interval_hours=1)
    """

    def __init__(
        self,
        failure_detector: FailureDetector,
        llm_judge: ModelBasedGraders,
        conversation_service: Any = None,
        quality_threshold: float = 0.6,
    ):
        """
        初始化质量扫描器

        Args:
            failure_detector: 失败检测器实例
            llm_judge: LLM 评分器实例
            conversation_service: 对话服务（用于获取对话历史）
            quality_threshold: 质量阈值（低于此值标记为失败）
        """
        self.failure_detector = failure_detector
        self.llm_judge = llm_judge
        self.conversation_service = conversation_service
        self.quality_threshold = quality_threshold
        self._scanning = False

    async def scan_recent_conversations(
        self, limit: int = 100, time_range_hours: int = 24, min_confidence: float = 0.7
    ) -> Dict[str, Any]:
        """
        扫描最近的对话，检测质量问题

        Args:
            limit: 扫描数量限制
            time_range_hours: 时间范围（小时）
            min_confidence: 最低置信度（低于此值需要人工复核）

        Returns:
            Dict: 扫描结果统计
        """
        if self.conversation_service is None:
            logger.warning("⚠️ ConversationService 未配置，无法扫描对话")
            return {
                "scanned": 0,
                "failures_detected": 0,
                "errors": 0,
            }

        cutoff_time = datetime.now() - timedelta(hours=time_range_hours)

        try:
            # 获取最近的对话（需要根据实际 ConversationService 接口调整）
            # 这里假设有 get_recent_conversations 方法
            conversations = await self._get_recent_conversations(limit=limit, since=cutoff_time)

            logger.info(f"📊 开始扫描 {len(conversations)} 条对话")

            failures_detected = 0
            errors = 0

            # 批量扫描（控制并发数）
            semaphore = asyncio.Semaphore(10)  # 最多10个并发

            async def scan_one(conv: Dict[str, Any]) -> Optional[Any]:
                async with semaphore:
                    try:
                        return await self._scan_conversation(conv, min_confidence)
                    except Exception as e:
                        logger.error(f"扫描对话失败 {conv.get('id', 'unknown')}: {e}")
                        return None

            results = await asyncio.gather(*[scan_one(conv) for conv in conversations])

            failures_detected = sum(1 for r in results if r is not None)
            errors = sum(1 for r in results if r is None)

            logger.info(
                f"✅ 扫描完成: 总计 {len(conversations)}, "
                f"检测到 {failures_detected} 个质量问题, "
                f"错误 {errors} 个"
            )

            return {
                "scanned": len(conversations),
                "failures_detected": failures_detected,
                "errors": errors,
                "scan_time": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"扫描过程出错: {e}", exc_info=True)
            return {
                "scanned": 0,
                "failures_detected": 0,
                "errors": 1,
                "error": str(e),
            }

    async def _get_recent_conversations(self, limit: int, since: datetime) -> List[Dict[str, Any]]:
        """
        获取最近的对话列表

        Args:
            limit: 数量限制
            since: 起始时间

        Returns:
            List[Dict]: 对话列表
        """
        # 这里需要根据实际的 ConversationService 接口实现
        # 假设有类似的方法
        if hasattr(self.conversation_service, "get_recent_conversations"):
            return await self.conversation_service.get_recent_conversations(
                limit=limit, since=since
            )

        # 如果没有实现，返回空列表
        logger.warning("⚠️ ConversationService 未实现 get_recent_conversations 方法")
        return []

    async def _scan_conversation(
        self, conversation: Dict[str, Any], min_confidence: float
    ) -> Optional[Any]:
        """
        扫描单个对话

        Args:
            conversation: 对话数据
            min_confidence: 最低置信度

        Returns:
            FailureCase: 如果检测到质量问题，返回失败案例
        """
        conversation_id = conversation.get("id")
        messages = conversation.get("messages", [])

        if not messages:
            return None

        # 获取最后一条用户消息和助手回复
        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]

        if not user_messages or not assistant_messages:
            return None

        user_query = user_messages[-1].get("content", "")
        agent_response = assistant_messages[-1].get("content", "")

        # 构建 transcript（简化版）
        transcript = {
            "messages": messages,
            "tool_calls": conversation.get("tool_calls", []),
            "token_usage": conversation.get("token_usage", {}),
            "duration_ms": conversation.get("duration_ms", 0),
            "metadata": conversation.get("metadata", {}),
        }

        # 调用 detect_response_quality
        failure_case = await self.failure_detector.detect_response_quality(
            conversation_id=conversation_id,
            user_query=user_query,
            agent_response=agent_response,
            transcript=transcript,
            llm_judge=self.llm_judge,
            user_id=conversation.get("user_id"),
        )

        return failure_case

    async def start_periodic_scan(self, interval_hours: float = 1.0, limit: int = 100) -> None:
        """
        启动定时扫描任务

        Args:
            interval_hours: 扫描间隔（小时）
            limit: 每次扫描的数量限制
        """
        if self._scanning:
            logger.warning("⚠️ 扫描任务已在运行中")
            return

        self._scanning = True
        logger.info(f"🚀 启动定时质量扫描，间隔 {interval_hours} 小时")

        try:
            while self._scanning:
                await self.scan_recent_conversations(limit=limit)
                await asyncio.sleep(interval_hours * 3600)  # 转换为秒
        except asyncio.CancelledError:
            logger.info("⏹️ 扫描任务已取消")
        except Exception as e:
            logger.error(f"❌ 扫描任务异常: {e}", exc_info=True)
        finally:
            self._scanning = False

    def stop_periodic_scan(self) -> None:
        """停止定时扫描任务"""
        self._scanning = False
        logger.info("⏹️ 停止定时质量扫描")
