"""
失败经验总结模块（MVP）

在 Agent 触发失败/中断时生成结构化总结，用于上下文压缩和续聊恢复。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import yaml
from pydantic import BaseModel, Field, ValidationError

from core.llm import Message
from logger import get_logger
from utils.json_utils import extract_json

logger = get_logger(__name__)

_CONFIG_CACHE: Optional["FailureSummaryConfig"] = None


class FailureSummaryConfig(BaseModel):
    """失败经验总结配置（框架级）"""

    enabled: bool = True
    trigger_on_stop_reasons: List[str] = Field(default_factory=lambda: ["max_turns_reached"])
    keep_recent_messages: Optional[int] = Field(
        default=None, description="保留最近消息条数（None 则由 ContextStrategy 决定）"
    )
    max_input_chars: int = 12000
    max_summary_chars: int = 1200
    max_block_chars: int = 1000


class FailureSummary(BaseModel):
    """结构化失败总结"""

    goal: str = ""
    progress: List[str] = Field(default_factory=list)
    failures: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    key_files: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    final_status: str = ""


@dataclass
class FailureSummaryResult:
    """失败总结结果"""

    summary_text: str
    summary: Optional[FailureSummary] = None
    raw_text: str = ""
    created_at: str = ""


async def get_failure_summary_config(config_path: Optional[Path] = None) -> FailureSummaryConfig:
    """
    加载失败经验总结配置（带缓存）

    Args:
        config_path: 配置文件路径，默认 config/context_compaction.yaml

    Returns:
        FailureSummaryConfig
    """
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    if config_path is None:
        from utils.app_paths import get_bundle_dir
        config_path = get_bundle_dir() / "config" / "context_compaction.yaml"

    config_data: Dict[str, Any] = {}
    if config_path.exists():
        try:
            async with aiofiles.open(config_path, "r", encoding="utf-8") as f:
                content = await f.read()
                config_data = yaml.safe_load(content) or {}
            logger.info(f"✅ 失败总结配置已加载: {config_path}")
        except Exception as e:
            logger.warning(f"⚠️ 加载失败总结配置失败: {e}，使用默认值")
    else:
        logger.warning(f"⚠️ 未找到配置文件: {config_path}，使用默认值")

    raw_cfg = config_data.get("failure_summary", {}) if isinstance(config_data, dict) else {}
    try:
        _CONFIG_CACHE = FailureSummaryConfig.model_validate(raw_cfg or {})
    except ValidationError as e:
        logger.warning(f"⚠️ 失败总结配置校验失败: {e}，使用默认值")
        _CONFIG_CACHE = FailureSummaryConfig()

    return _CONFIG_CACHE


def build_failure_summary_prompt() -> str:
    """构建失败总结 System Prompt"""
    return (
        "你是失败经验总结器。请基于对话记录生成结构化失败总结，用于续聊恢复。\n"
        "要求：\n"
        "1) 输出必须是严格 JSON，不要包含多余文本、Markdown 或代码块。\n"
        "2) 内容要短、可执行，避免复述细节。\n"
        "3) 总结目标、已完成、失败原因、约束、关键文件、下一步、避免事项、未解决问题。\n"
        "4) 若信息不足，请留空字段或给出空列表。\n"
        "\n"
        "JSON 字段：\n"
        "{\n"
        '  "goal": "...",\n'
        '  "progress": ["..."],\n'
        '  "failures": ["..."],\n'
        '  "constraints": ["..."],\n'
        '  "next_steps": ["..."],\n'
        '  "avoid": ["..."],\n'
        '  "key_files": ["..."],\n'
        '  "open_questions": ["..."],\n'
        '  "final_status": "..."\n'
        "}"
    )


def format_failure_summary(summary: FailureSummary, max_chars: int) -> str:
    """
    将结构化失败总结格式化为文本

    Args:
        summary: 结构化总结
        max_chars: 最大字符数

    Returns:
        文本总结
    """
    lines: List[str] = []
    if summary.goal:
        lines.append(f"目标: {summary.goal}")
    if summary.progress:
        lines.append(f"已完成: {'；'.join(summary.progress)}")
    if summary.failures:
        lines.append(f"失败原因: {'；'.join(summary.failures)}")
    if summary.constraints:
        lines.append(f"约束/限制: {'；'.join(summary.constraints)}")
    if summary.next_steps:
        lines.append(f"下一步: {'；'.join(summary.next_steps)}")
    if summary.avoid:
        lines.append(f"避免/不要: {'；'.join(summary.avoid)}")
    if summary.key_files:
        lines.append(f"关键文件: {'；'.join(summary.key_files)}")
    if summary.open_questions:
        lines.append(f"待确认: {'；'.join(summary.open_questions)}")
    if summary.final_status:
        lines.append(f"终止原因: {summary.final_status}")

    text = "\n".join(lines).strip()
    if not text:
        text = "未生成有效失败总结"
    return _truncate_text(text, max_chars)


def serialize_messages_for_summary(
    messages: List[Dict[str, Any]], max_chars: int, max_block_chars: int
) -> str:
    """
    将消息列表序列化为总结输入文本

    Args:
        messages: 消息列表（dict 格式）
        max_chars: 最大字符数
        max_block_chars: 单个 block 最大字符数

    Returns:
        总结输入文本
    """
    lines: List[str] = []
    total_chars = 0

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        content_text = _extract_content_text(content, max_block_chars)
        if not content_text:
            continue

        line = f"{role}: {content_text}"
        if total_chars + len(line) > max_chars:
            lines.append("...(对话已截断)")
            break

        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines)


class FailureSummaryGenerator:
    """失败总结生成器"""

    def __init__(self, llm_service, config: FailureSummaryConfig):
        self.llm_service = llm_service
        self.config = config

    async def generate(
        self, messages: List[Dict[str, Any]], stop_reason: str
    ) -> FailureSummaryResult:
        """
        生成失败总结

        Args:
            messages: 需要总结的消息列表
            stop_reason: 停止原因

        Returns:
            FailureSummaryResult
        """
        created_at = datetime.now().isoformat()
        if not messages:
            return FailureSummaryResult(
                summary_text="未生成有效失败总结", summary=None, raw_text="", created_at=created_at
            )

        conversation_text = serialize_messages_for_summary(
            messages,
            max_chars=self.config.max_input_chars,
            max_block_chars=self.config.max_block_chars,
        )
        user_prompt = (
            f"停止原因: {stop_reason}\n" "以下为对话记录（将被压缩）：\n" f"{conversation_text}"
        )

        try:
            response = await self.llm_service.create_message_async(
                messages=[Message(role="user", content=user_prompt)],
                system=build_failure_summary_prompt(),
                tools=[],
                max_tokens=1024,
            )
        except Exception as e:
            logger.warning(f"⚠️ 失败总结生成失败: {e}")
            return FailureSummaryResult(
                summary_text=_fallback_summary(
                    stop_reason, messages, self.config.max_summary_chars
                ),
                summary=None,
                raw_text="",
                created_at=created_at,
            )

        raw_text = _extract_text_from_llm_response(response)
        parsed = extract_json(raw_text)

        summary: Optional[FailureSummary] = None
        if isinstance(parsed, dict):
            try:
                summary = FailureSummary.model_validate(parsed)
            except ValidationError as e:
                logger.debug(f"JSON 解析失败，回退为文本总结: {e}")

        if summary:
            summary_text = format_failure_summary(summary, self.config.max_summary_chars)
        else:
            summary_text = _truncate_text(
                raw_text.strip(), self.config.max_summary_chars
            ) or _fallback_summary(stop_reason, messages, self.config.max_summary_chars)

        return FailureSummaryResult(
            summary_text=summary_text, summary=summary, raw_text=raw_text, created_at=created_at
        )


def _extract_content_text(content: Any, max_block_chars: int) -> str:
    """提取消息内容为文本（含 tool_use/tool_result）"""
    if isinstance(content, str):
        return _truncate_text(content, max_block_chars)

    if not isinstance(content, list):
        return _truncate_text(str(content), max_block_chars)

    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text", "")
            if text:
                parts.append(text)
        elif block_type == "tool_use":
            name = block.get("name", "unknown")
            input_data = block.get("input", {})
            input_text = _safe_json_dump(input_data)
            parts.append(f"[工具调用:{name}] {input_text}")
        elif block_type == "tool_result":
            result = block.get("content", "")
            parts.append(f"[工具结果] {_normalize_tool_result(result)}")
        else:
            text = block.get("text", "")
            if text:
                parts.append(text)

    merged = "\n".join(parts).strip()
    return _truncate_text(merged, max_block_chars)


def _normalize_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        return _safe_json_dump(result)
    return str(result)


def _safe_json_dump(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return str(data)


def _extract_text_from_llm_response(response: Any) -> str:
    """从 LLMResponse 中提取文本"""
    if not response or not getattr(response, "content", None):
        return ""

    parts: List[str] = []
    for block in response.content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif "text" in block:
                parts.append(str(block.get("text", "")))
        elif hasattr(block, "text"):
            parts.append(block.text)

    return "\n".join([p for p in parts if p]).strip()


def _truncate_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _fallback_summary(stop_reason: str, messages: List[Dict[str, Any]], max_chars: int) -> str:
    """生成简易失败总结（无需 LLM）"""
    first_user = ""
    last_assistant = ""

    for msg in messages:
        if msg.get("role") == "user" and not first_user:
            first_user = _extract_content_text(msg.get("content", ""), max_chars)
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            last_assistant = _extract_content_text(msg.get("content", ""), max_chars)
            break

    lines = []
    if first_user:
        lines.append(f"目标: {first_user}")
    if last_assistant:
        lines.append(f"最新进展: {last_assistant}")
    lines.append(f"终止原因: {stop_reason}")

    return _truncate_text("\n".join(lines), max_chars)


class FailureSummaryManager:
    """
    🆕 V10.0: 失败总结管理器

    从 Agent._maybe_generate_failure_summary 提取，
    使 Agent 保持纯 RVR 编排层。

    职责：
    1. 根据配置和条件判断是否需要生成总结
    2. 获取对话消息
    3. 调用 FailureSummaryGenerator 生成总结
    4. 写入 conversation metadata
    """

    def __init__(
        self,
        conversation_service,
        llm_service,
        config: Optional[FailureSummaryConfig] = None,
        context_strategy=None,
    ):
        """
        Args:
            conversation_service: 对话服务（用于获取和更新对话）
            llm_service: LLM 服务（用于生成总结）
            config: 失败总结配置（可选）
            context_strategy: 上下文策略（可选，用于确定保留消息数）
        """
        self.conversation_service = conversation_service
        self.llm_service = llm_service
        # get_failure_summary_config() is async; callers must pass config explicitly.
        # Use sync default if config is not provided.
        self.config = config or FailureSummaryConfig()
        self.context_strategy = context_strategy
        self._generator: Optional[FailureSummaryGenerator] = None

    @property
    def generator(self) -> FailureSummaryGenerator:
        """懒加载生成器"""
        if self._generator is None:
            self._generator = FailureSummaryGenerator(self.llm_service, self.config)
        return self._generator

    async def maybe_generate(
        self,
        conversation_id: str,
        stop_reason: Optional[str],
        session_id: str,
        user_id: Optional[str],
        message_id: Optional[str] = None,
    ) -> Optional[FailureSummaryResult]:
        """
        在失败/中断时生成失败经验总结，并写入对话 metadata

        Args:
            conversation_id: 对话 ID
            stop_reason: 停止原因
            session_id: 会话 ID
            user_id: 用户 ID
            message_id: 消息 ID（可选）

        Returns:
            FailureSummaryResult 或 None
        """
        if not self.config.enabled:
            return None
        if not stop_reason or stop_reason not in self.config.trigger_on_stop_reasons:
            return None
        if not self.conversation_service:
            logger.warning("⚠️ 未提供 conversation_service，跳过失败总结")
            return None
        if not conversation_id:
            logger.warning("⚠️ 未提供 conversation_id，跳过失败总结")
            return None

        # 获取对话消息
        try:
            result = await self.conversation_service.get_conversation_messages(
                conversation_id=conversation_id, limit=1000, order="asc"
            )
            db_messages = result.get("messages", [])
        except Exception as e:
            logger.warning(f"⚠️ 获取对话消息失败，跳过失败总结: {e}")
            return None

        if not db_messages:
            return None

        # 确定保留消息数
        preserve_last_n = 2
        if self.context_strategy and hasattr(self.context_strategy, "preserve_last_n"):
            preserve_last_n = self.context_strategy.preserve_last_n
        keep_recent = self.config.keep_recent_messages or max(preserve_last_n * 2, 2)

        if len(db_messages) <= keep_recent:
            logger.info("📦 消息数量不足，跳过失败总结")
            return None

        early_messages = db_messages[:-keep_recent]
        compress_from_message = db_messages[-(keep_recent + 1)]
        from_message_id = (
            compress_from_message.get("id") if isinstance(compress_from_message, dict) else None
        )
        if not from_message_id:
            logger.warning("⚠️ 未找到压缩起点 message_id，跳过失败总结")
            return None

        # 生成总结
        summary_result = await self.generator.generate(
            messages=early_messages, stop_reason=stop_reason
        )
        if not summary_result.summary_text:
            logger.info("📦 失败总结为空，跳过写入")
            return None

        # 写入 metadata
        try:
            conversation = await self.conversation_service.get_conversation(conversation_id)
            existing_metadata = (
                conversation.metadata if isinstance(conversation.metadata, dict) else {}
            )

            compression_info = {
                "compressed_at": summary_result.created_at or datetime.now().isoformat(),
                "from_message_id": from_message_id,
                "summary": summary_result.summary_text,
                "type": "failure_summary",
                "stop_reason": stop_reason,
                "session_id": session_id,
                "message_id": message_id,
                "user_id": user_id,
            }

            existing_metadata["compression"] = compression_info
            existing_metadata["failure_summary"] = {
                "created_at": summary_result.created_at or datetime.now().isoformat(),
                "stop_reason": stop_reason,
                "summary": summary_result.summary_text,
                "raw": summary_result.raw_text,
                "session_id": session_id,
                "message_id": message_id,
                "user_id": user_id,
            }

            await self.conversation_service.update_conversation(
                conversation_id=conversation_id, metadata=existing_metadata
            )
            logger.info(
                f"✅ 失败总结已写入 metadata: conversation_id={conversation_id}, "
                f"stop_reason={stop_reason}"
            )
        except Exception as e:
            logger.warning(f"⚠️ 写入失败总结失败: {e}")

        return summary_result


    # V11.0: 移除 generate_failure_summary_for_multiagent（小搭子不使用多智能体）
